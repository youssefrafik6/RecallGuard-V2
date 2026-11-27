"""Sample and evaluate independently reviewed pairs from a fixed linkage audit."""

import json
from pathlib import Path

import pandas as pd
from scipy.stats import hypergeom
from sklearn.metrics import cohen_kappa_score

from recallguard.raw import fingerprint

KEY = ["report_id", "recall_id"]
STRATA = ("high", "uncertain", "plausible_nonmatch", "random_remainder")
DECISIONS = ("match", "non_match", "uncertain")


def sample_pairs(snapshot: Path, out: Path, seed: int, per_stratum: int) -> dict:
    if per_stratum < 1:
        raise ValueError("Sample size per stratum must be positive")
    source = snapshot / "candidates.csv"
    audit = pd.read_csv(source, dtype={key: str for key in KEY})
    if audit.empty or audit[KEY].isna().any().any() or audit.duplicated(KEY).any():
        raise ValueError("Candidate frame must contain distinct pairs with source IDs")
    if not audit.confidence.isin(["high", "review", "rejected"]).all():
        raise ValueError("Unrecognized confidence tier in candidate frame")
    horizon = json.loads((snapshot / "summary.json").read_text())["config"][
        "horizon_days"
    ]
    plausible = audit.confidence.eq("rejected") & audit.days_to_recall.between(
        1, horizon
    )
    plausible &= audit.score.ge(0.35) | audit.model_exact | audit.gtin_exact
    audit["stratum"] = "random_remainder"
    audit.loc[plausible, "stratum"] = "plausible_nonmatch"
    audit.loc[audit.confidence.eq("review"), "stratum"] = "uncertain"
    audit.loc[audit.confidence.eq("high"), "stratum"] = "high"

    parts = []
    design = {}
    for index, stratum in enumerate(STRATA):
        population = audit.loc[audit.stratum.eq(stratum)].sort_values(KEY)
        size = min(per_stratum, len(population))
        design[stratum] = {"population": len(population), "sample": size}
        parts.append(population.sample(n=size, random_state=seed + index))
    sample = pd.concat(parts).sample(frac=1, random_state=seed).reset_index(drop=True)
    sample.insert(
        0, "pair_id", [f"P{number:05}" for number in range(1, len(sample) + 1)]
    )
    packet = sample.drop(
        columns=["stratum", "confidence", "score", "reason", "rank", "block_votes"]
    )
    for filename, key, prefix, date in (
        ("observations.csv", "report_id", "incident", "report_date"),
        ("recalls.csv", "recall_id", "recall", "recall_date"),
    ):
        fields = [key, "product", "manufacturer", date]
        catalog = pd.read_csv(snapshot / filename, usecols=fields, dtype=str)
        packet = packet.merge(
            catalog.rename(
                columns={
                    "product": f"{prefix}_product",
                    "manufacturer": f"{prefix}_manufacturer",
                }
            ),
            on=key,
            how="left",
            validate="many_to_one",
        )

    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    sample.to_csv(out / "design.csv", index=False)
    packet.to_csv(out / "review_packet.csv", index=False)
    manifest = {
        "candidate_sha256": fingerprint(source),
        "design_sha256": fingerprint(out / "design.csv"),
        "packet_sha256": fingerprint(out / "review_packet.csv"),
        "horizon_days": horizon,
        "seed": seed,
        "per_stratum": per_stratum,
        "strata": design,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    packet[["pair_id"]].assign(
        packet_sha256=manifest["packet_sha256"], decision=""
    ).to_csv(out / "decisions_template.csv", index=False)
    return manifest


def match_count_interval(population: int, sample: int, matches: int, tail: float):
    """Invert the two hypergeometric tails for an exact finite-population interval."""
    left, right = matches, population - sample + matches
    low, high = left, right
    while low < high:
        mid = (low + high) // 2
        if hypergeom.sf(matches - 1, population, mid, sample) >= tail:
            high = mid
        else:
            low = mid + 1
    minimum = low
    low, high = left, right
    while low < high:
        mid = (low + high + 1) // 2
        if hypergeom.cdf(matches, population, mid, sample) >= tail:
            low = mid
        else:
            high = mid - 1
    return minimum, low


def evaluate_pairs(sample_dir: Path, reviewer_files: list[Path]) -> dict:
    manifest = json.loads((sample_dir / "manifest.json").read_text())
    design_path = sample_dir / "design.csv"
    if fingerprint(design_path) != manifest["design_sha256"]:
        raise ValueError("Review design does not match manifest")
    if fingerprint(sample_dir / "review_packet.csv") != manifest["packet_sha256"]:
        raise ValueError("Review packet does not match manifest")
    design = pd.read_csv(design_path, dtype=str).set_index("pair_id")
    counts = design["stratum"].value_counts()
    strata = manifest["strata"]
    if (
        set(strata) != set(STRATA)
        or not design.index.is_unique
        or not set(counts.index) <= set(STRATA)
        or any(
            not 0 <= info["sample"] <= info["population"]
            or info["sample"] != counts.get(name, 0)
            or (info["population"] > 0 and info["sample"] == 0)
            for name, info in strata.items()
        )
    ):
        raise ValueError("Invalid stratified sampling manifest")
    if len(reviewer_files) not in (0, 2):
        raise ValueError("Supply two independently completed reviewer files")
    if len({path.resolve() for path in reviewer_files}) != len(reviewer_files):
        raise ValueError("Use separate files for each reviewer")

    result = {"status": "validation_pending", "sampled_pairs": len(design)}
    if not reviewer_files:
        return result
    for column, path in zip(("first", "second"), reviewer_files):
        decisions = pd.read_csv(path, dtype=str, keep_default_na=False)
        if (
            not decisions.packet_sha256.eq(manifest["packet_sha256"]).all()
            or not decisions.pair_id.isin(design.index).all()
            or decisions.pair_id.duplicated().any()
            or not decisions.decision.isin([*DECISIONS, ""]).all()
        ):
            raise ValueError("Invalid decisions or mismatched review packet")
        design[column] = decisions.set_index("pair_id").decision.replace("", pd.NA)
    paired = design.dropna(subset=["first", "second"])
    identical = paired["first"].eq(paired["second"])
    binary_agreement = identical & paired["first"].ne("uncertain")
    result.update(
        double_reviewed_pairs=len(paired),
        exact_agreements=int(identical.sum()),
        disagreements=int((~identical).sum()),
        unresolved_pairs=len(design) - int(binary_agreement.sum()),
        disagreement_pair_ids=paired.index[~identical].tolist(),
        agreement_by_stratum={
            stratum: {
                "paired": len(group),
                "agreements": int(group["first"].eq(group["second"]).sum()),
            }
            for stratum, group in paired.groupby("stratum")
        },
    )
    if len(paired):
        result["sample_percent_agreement"] = float(identical.mean())
        if pd.concat([paired["first"], paired["second"]]).nunique() > 1:
            result["sample_cohen_kappa"] = float(
                cohen_kappa_score(paired["first"], paired["second"])
            )
    if not len(design) or result["unresolved_pairs"]:
        return result

    # Simultaneous 95% intervals for stratum totals using Bonferroni allocation.
    tail = 0.05 / (2 * sum(info["population"] > 0 for info in strata.values()))
    estimated = {}
    intervals = {}
    for name, info in strata.items():
        population, size = info["population"], info["sample"]
        matches = int((design.stratum.eq(name) & design["first"].eq("match")).sum())
        estimated[name] = population * matches / size if size else 0.0
        intervals[name] = (
            match_count_interval(population, size, matches, tail) if size else (0, 0)
        )
    high = strata["high"]["population"]
    total = sum(estimated.values())
    low, upper = intervals["high"]
    rest_low = sum(intervals[name][0] for name in STRATA[1:])
    rest_upper = sum(intervals[name][1] for name in STRATA[1:])
    result.update(
        status="candidate_frame_evaluated",
        high_tier_precision=estimated["high"] / high if high else None,
        high_tier_precision_95ci=[low / high, upper / high] if high else None,
        candidate_frame_recall=estimated["high"] / total if total else None,
        candidate_frame_recall_95ci=[
            low / (low + rest_upper) if low + rest_upper else 0.0,
            upper / (upper + rest_low) if upper + rest_low else 1.0,
        ]
        if total
        else None,
    )
    return result
