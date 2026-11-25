"""Aggregate local data using packaged DuckDB SQL."""

import os
from importlib.resources import files
from pathlib import Path
from typing import Literal

import duckdb
import pandas as pd

from recallguard.data import load_incidents

Query = Literal["summary", "categories", "trends", "manufacturers", "confidence"]


def aggregate(frame: pd.DataFrame, query: Query) -> pd.DataFrame:
    if query not in {"summary", "categories", "trends", "manufacturers", "confidence"}:
        raise ValueError("Unknown analytics query")
    sql = files("recallguard").joinpath("sql", f"{query}.sql").read_text()
    with duckdb.connect(config={"threads": 2}) as connection:
        connection.register(
            "candidates" if query == "confidence" else "incidents", frame
        )
        return connection.execute(sql).df()


def configured_dataset(default: Path | None = None) -> pd.DataFrame | None:
    path = os.getenv("RECALLGUARD_DATA")
    if path:
        return load_incidents(Path(path), labeled=True)
    if default is not None and default.is_file():
        return load_incidents(default, labeled=True)
    return None
