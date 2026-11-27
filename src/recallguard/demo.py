"""Official CPSC inputs and strict upload handling for the public linkage demo."""

import csv
import re
from datetime import date
from functools import lru_cache
from io import StringIO
from pathlib import Path

import pandas as pd

from recallguard.data import load_recalls
from recallguard.linkage import LinkageConfig, gtin_codes, link

FIELDS = ("product", "report_date", "manufacturer", "brand", "model", "upc")
MAX_BYTES = 64 * 1024
MAX_ROWS = 50
MAX_FIELD = 120
# Selected product fields from published CPSC reports in the 2026-11-26
# snapshot. Report identifiers and narratives are intentionally omitted.
SCENARIOS = {
    "Black+Decker garment steamer": (
        "black decker easy garment steamer",
        "2024-01-18",
        "spectrum brands",
        "black decker",
        "hgs011",
        "00050875002722",
    ),
    "Insignia dual-basket air fryer": (
        "insignia 8 qt digital dual basket air fryer black",
        "2024-03-13",
        "best buy",
        "insignia",
        "ns-af8dbd2",
        "00600603279911",
    ),
    "Segway P100S electric scooter": (
        "segway p100s electric scooter",
        "2024-06-11",
        "segway",
        "segway",
        "p100s",
        "",
    ),
}
CATALOG_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "recalls_recall_listing (1).csv"
)


@lru_cache(maxsize=1)
def public_catalog() -> pd.DataFrame:
    path = CATALOG_PATH if CATALOG_PATH.is_file() else Path("data") / CATALOG_PATH.name
    return load_recalls(path).dropna(subset=["recall_date"])


OVERVIEW = [
    "report_id",
    "recall_id",
    "recall_product",
    "rank",
    "days_to_recall",
    "confidence",
    "score",
    "reason",
]


def demo_csv() -> str:
    return pd.DataFrame(SCENARIOS.values(), columns=FIELDS).to_csv(index=False)


def parse_upload(payload: bytes) -> list[dict[str, str]]:
    if len(payload) > MAX_BYTES:
        raise ValueError("The CSV exceeds 64 KiB.")
    try:
        reader = csv.reader(
            StringIO(payload.decode("utf-8-sig"), newline=""), strict=True
        )
        header = next(reader, [])
        if len(header) != len(set(header)) or not {"product", "report_date"} <= set(
            header
        ) <= set(FIELDS):
            raise ValueError(
                "Use unique columns from the template, including product and report_date."
            )
        rows = []
        for values in reader:
            if not values:
                continue
            if len(rows) >= MAX_ROWS:
                raise ValueError("The CSV exceeds 50 incident rows.")
            if len(values) != len(header):
                raise ValueError(
                    f"CSV line {reader.line_num} has the wrong number of fields."
                )
            rows.append(dict(zip(header, values)))
    except UnicodeDecodeError as exc:
        raise ValueError("Save the CSV as UTF-8.") from exc
    except csv.Error as exc:
        raise ValueError("Check the CSV quoting and delimiters.") from exc
    if not rows:
        raise ValueError("Add at least one incident row.")
    return rows


def match_demo(rows: list[dict[str, str]], horizon_days: int) -> pd.DataFrame:
    """Run the production linker in memory and return only safe, derived results."""
    if not 1 <= len(rows) <= MAX_ROWS:
        raise ValueError("Provide 1–50 incident rows.")
    clean = []
    for index, row in enumerate(rows, 1):
        values = {field: row.get(field, "") for field in FIELDS}
        if any(
            len(value) > MAX_FIELD or not value.isprintable() and value
            for value in values.values()
        ):
            raise ValueError(
                f"Incident {index}: use at most 120 printable characters per field."
            )
        values = {field: value.strip() for field, value in values.items()}
        if not values["product"]:
            raise ValueError(f"Incident {index}: product is required.")
        day = values["report_date"]
        if not re.fullmatch(r"(?:19\d\d|20\d\d|2100)-\d{2}-\d{2}", day):
            raise ValueError(f"Incident {index}: use YYYY-MM-DD between 1900 and 2100.")
        try:
            report_date = pd.Timestamp(date.fromisoformat(day))
        except ValueError as exc:
            raise ValueError(f"Incident {index}: report date is invalid.") from exc
        gtin = values["upc"]
        if gtin and (not re.fullmatch(r"[0-9]+", gtin) or not gtin_codes(gtin)):
            raise ValueError(
                f"Incident {index}: enter a checksum-valid GTIN or leave it blank."
            )
        clean.append(
            {**values, "report_id": f"INPUT-{index:02}", "report_date": report_date}
        )
    incidents = pd.DataFrame(clean)
    recalls = public_catalog()
    audit = link(incidents, recalls, LinkageConfig(horizon_days=horizon_days))
    if audit.empty:
        audit["recall_product"] = ""
    else:
        audit["recall_product"] = audit["recall_id"].map(
            recalls.set_index("recall_id")["product"]
        )
    return audit


def batch_results(rows: list[dict[str, str]], horizon_days: int) -> pd.DataFrame:
    audit = match_demo(rows, horizon_days)
    reports = pd.DataFrame(
        {"report_id": [f"INPUT-{index:02}" for index in range(1, len(rows) + 1)]}
    )
    results = reports.merge(audit[OVERVIEW], how="left", on="report_id")
    results["confidence"] = results["confidence"].fillna("no candidate")
    results["reason"] = results["reason"].fillna(
        "No candidate passed the blocking step"
    )
    return results
