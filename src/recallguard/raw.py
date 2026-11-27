"""Build a local, versioned linkage snapshot from the two official CPSC exports."""

import hashlib
import html
import json
from dataclasses import asdict
from pathlib import Path
from shutil import copyfileobj
from tempfile import TemporaryDirectory
from zipfile import ZipFile

import pandas as pd

from recallguard.data import (
    INCIDENT,
    RECALL,
    TARGET,
    manufacturer_key,
    normalize,
    read_export,
)
from recallguard.linkage import (
    LinkageConfig,
    construct_labels,
    gtin_codes,
    link,
    review_sample,
)

INCIDENT_URL = "https://www.saferproducts.gov/SPDB.zip"
RECALL_URL = "https://www.cpsc.gov/s3fs-public/recall-data/recalls_recall_listing.csv"
INCIDENT_MEMBER = "IncidentReports.csv"
SCHEMA_VERSION = 1


def fingerprint(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def incident_encoding(path: Path) -> str:
    try:
        with path.open(encoding="utf-8-sig") as source:
            while source.read(1024 * 1024):
                pass
    except UnicodeDecodeError:
        return "cp1252"
    return "utf-8-sig"


def validate_records(frame: pd.DataFrame, key: str, dates: tuple[str, ...]):
    """Account for every exclusion and quarantine conflicting primary keys."""
    source_rows = len(frame)
    missing = frame[key].eq("")
    present = frame.loc[~missing]
    distinct = present.drop_duplicates()
    conflicts = distinct[key].duplicated(keep=False)
    clean = distinct.loc[~conflicts].sort_values(key).reset_index(drop=True)
    if clean.empty:
        raise ValueError(f"No usable records for {key}")
    return clean, {
        "source_rows": source_rows,
        "missing_identifier_rows": int(missing.sum()),
        "duplicate_rows_collapsed": len(present) - len(distinct),
        "conflicting_rows_excluded": int(conflicts.sum()),
        "conflicting_identifiers": distinct.loc[conflicts, key].nunique(),
        "retained_rows": len(clean),
        "missing_product": int(clean["product"].map(normalize).eq("").sum()),
        "missing_manufacturer": int(
            clean["manufacturer"].map(manufacturer_key).eq("").sum()
        ),
        "dates": {
            field: {
                "missing_or_invalid": int(clean[field].isna().sum()),
                "earliest": clean[field].min().date().isoformat()
                if clean[field].notna().any()
                else None,
                "latest": clean[field].max().date().isoformat()
                if clean[field].notna().any()
                else None,
            }
            for field in dates
        },
    }


def prepare_raw(archive: Path, listing: Path, out: Path, config: LinkageConfig) -> dict:
    """Publish a complete run in a new directory after validation and linkage."""
    if out.exists():
        raise FileExistsError(f"Choose a new output directory: {out}")
    sources = {
        "incidents": {
            "url": INCIDENT_URL,
            "sha256": fingerprint(archive),
            "bytes": archive.stat().st_size,
        },
        "recalls": {
            "url": RECALL_URL,
            "sha256": fingerprint(listing),
            "bytes": listing.stat().st_size,
        },
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".cpsc-", dir=out.parent) as staging:
        stage = Path(staging)
        incident_csv = stage / INCIDENT_MEMBER
        with ZipFile(archive) as bundle:
            members = [
                item for item in bundle.infolist() if item.filename == INCIDENT_MEMBER
            ]
            if len(members) != 1 or members[0].file_size > 512 * 1024 * 1024:
                raise ValueError(
                    "Expected one IncidentReports.csv member of at most 512 MiB"
                )
            with (
                bundle.open(members[0]) as source,
                incident_csv.open("wb") as destination,
            ):
                copyfileobj(source, destination)
        sources["incidents"]["member_sha256"] = fingerprint(incident_csv)
        encoding = incident_encoding(incident_csv)
        sources["incidents"]["encoding"] = encoding
        sources["recalls"]["encoding"] = "utf-8-sig"
        incident_mapping = {
            header: field
            for header, field in INCIDENT.items()
            if field
            not in {
                "historical_confidence",
                "historical_match_rule",
                "recall_campaign",
                "description",
            }
        }
        incidents, incident_counts = validate_records(
            read_export(
                incident_csv,
                incident_mapping,
                set(incident_mapping),
                strict=True,
                encoding=encoding,
            ),
            "report_id",
            ("report_date", "publication_date"),
        )
        incident_csv.unlink()
        recalls, recall_counts = validate_records(
            read_export(listing, RECALL, set(RECALL), strict=True),
            "recall_id",
            ("recall_date",),
        )

        for frame in (incidents, recalls):
            frame["product"] = frame["product"].map(html.unescape).map(normalize)
            frame["manufacturer"] = (
                frame["manufacturer"].map(html.unescape).map(manufacturer_key)
            )
        for field in ("heading", "recall_description"):
            recalls[field] = recalls[field].map(html.unescape)
        incidents["brand"] = incidents["brand"].map(html.unescape).map(normalize)
        # Retain model separators for the existing identifier extractor.
        model = incidents["model"].str.normalize("NFKC").str.casefold()
        incidents["model"] = model.where(model.map(normalize).ne(""), "")
        incidents["upc"] = (
            incidents["upc"]
            .str.normalize("NFKC")
            .map(lambda value: " ".join(sorted(gtin_codes(value))))
        )

        # Narrative similarity from recall text alone cannot adjudicate a match.
        # The raw rebuild intentionally keeps incident narratives out of processing.
        audit = link(incidents, recalls, config)
        observations = construct_labels(incidents, audit).rename(
            columns={TARGET: "heuristic_label", "recall_id": "heuristic_recall_id"}
        )
        observations["verified_label"] = pd.Series(
            pd.NA, index=observations.index, dtype="Int64"
        )
        observations["label_status"] = (
            observations["heuristic_label"]
            .notna()
            .map({True: "heuristic", False: "unlabeled"})
        )
        pairs = audit["confidence"].value_counts()
        high = audit.loc[audit["confidence"].eq("high")]
        high_per_report = high.groupby("report_id").size()
        linked = observations.loc[observations["heuristic_label"].notna()]
        publication_lead = (
            linked["heuristic_recall_id"].map(
                recalls.set_index("recall_id")["recall_date"]
            )
            - linked["publication_date"]
        ).dt.days
        summary = {
            "schema_version": SCHEMA_VERSION,
            "sources": sources,
            "config": asdict(config),
            "incidents": incident_counts,
            "recalls": recall_counts,
            "linkage": {
                "candidate_pairs": len(audit),
                "confidence_counts": {
                    level: int(pairs.get(level, 0))
                    for level in ("high", "review", "rejected")
                },
                "reports_with_candidates": audit["report_id"].nunique(),
                "reports_without_candidates": len(incidents)
                - audit["report_id"].nunique(),
                "reports_with_multiple_high_candidates": int(
                    high_per_report.gt(1).sum()
                ),
                "high_pairs_with_gtin": int(high["gtin_exact"].sum()),
                "high_pairs_with_model": int(high["model_exact"].sum()),
                "heuristic_links_by_publication_timing": {
                    "recall_after_publication": int(publication_lead.gt(0).sum()),
                    "recall_on_or_before_publication": int(
                        publication_lead.le(0).sum()
                    ),
                    "publication_date_unavailable": int(publication_lead.isna().sum()),
                },
            },
            "reports_by_year": {
                str(year): int(count)
                for year, count in incidents["report_date"]
                .dt.year.dropna()
                .astype(int)
                .value_counts()
                .sort_index()
                .items()
                if count >= 10
            },
            "labels": {
                level: int(observations["label_status"].eq(level).sum())
                for level in ("verified", "heuristic", "unlabeled")
            },
            "evaluation": {
                "status": "insufficient_verified_labels",
                "verified_positives": 0,
                "verified_negatives": 0,
            },
        }
        # Keep public-dashboard inputs separate from local record-level artifacts.
        snapshot = stage / "snapshot"
        snapshot.mkdir(mode=0o700)
        audit.to_csv(snapshot / "candidates.csv", index=False)
        review_sample(audit, incidents, recalls).to_csv(
            snapshot / "review_sample.csv", index=False
        )
        observations.to_csv(snapshot / "observations.csv", index=False)
        recalls.drop(columns="recall_description").to_csv(
            snapshot / "recalls.csv", index=False
        )
        (snapshot / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        snapshot.rename(out)
    return summary
