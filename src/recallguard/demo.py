"""Fictional inputs and strict upload handling for the public linkage demo."""

import csv
import re
from datetime import date
from io import StringIO

import pandas as pd

from recallguard.linkage import LinkageConfig, gtin_codes, link

FIELDS = ("product", "report_date", "manufacturer", "brand", "model", "upc")
MAX_BYTES = 64 * 1024
MAX_ROWS = 50
MAX_FIELD = 120
SCENARIOS = {
    "Lantern with model corroboration": (
        "Maple Trail lithium lantern",
        "2025-01-01",
        "Maple Trail LLC",
        "Maple Trail",
        "MTL-210",
        "",
    ),
    "Kettle with an exact GTIN": (
        "Glass kettle",
        "2025-01-10",
        "",
        "",
        "",
        "2001234567893",
    ),
    "Product with no candidate": ("Ceramic wall clock", "2025-01-10", "", "", "", ""),
}
CATALOG = (
    (
        "DEMO-101",
        "Maple Trail lithium lantern",
        "Maple Trail",
        "Maple Trail lantern recall",
        "Model MTL-210",
        "2025-02-01",
    ),
    (
        "DEMO-102",
        "Maple Trail solar lantern",
        "Maple Trail",
        "Maple Trail lantern recall",
        "Model MTS-330",
        "2024-11-01",
    ),
    (
        "DEMO-201",
        "Cedar Harbor glass kettle",
        "Cedar Harbor",
        "Cedar Harbor electric kettle recall",
        "Model CHK-440; GTIN 2001234567893",
        "2025-03-03",
    ),
)
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
            {**values, "report_id": f"DEMO-{index:02}", "report_date": report_date}
        )
    incidents = pd.DataFrame(clean)
    recalls = pd.DataFrame(
        CATALOG,
        columns=[
            "recall_id",
            "product",
            "manufacturer",
            "heading",
            "recall_description",
            "recall_date",
        ],
    )
    recalls["recall_date"] = pd.to_datetime(recalls["recall_date"])
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
        {"report_id": [f"DEMO-{index:02}" for index in range(1, len(rows) + 1)]}
    )
    results = reports.merge(audit[OVERVIEW], how="left", on="report_id")
    results["confidence"] = results["confidence"].fillna("no candidate")
    results["reason"] = results["reason"].fillna(
        "No candidate passed the blocking step"
    )
    return results
