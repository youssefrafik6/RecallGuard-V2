"""Append local human decisions with input snapshot provenance."""

from contextlib import closing
from pathlib import Path
from sqlite3 import connect
from typing import Literal

from pydantic import BaseModel, Field


class ReviewDecision(BaseModel):
    snapshot: str = Field(pattern=r"^[0-9a-f]{64}$")
    report_id: str = Field(min_length=1, max_length=240)
    recall_id: str = Field(min_length=1, max_length=240)
    decision: Literal["match", "non_match", "uncertain"]
    reviewer: str = Field(min_length=1, max_length=80)
    note: str = Field(default="", max_length=1000)


def record_review(path: Path, review: ReviewDecision) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(connect(path)) as connection, connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS decisions (
                id INTEGER PRIMARY KEY,
                snapshot TEXT NOT NULL, report_id TEXT NOT NULL, recall_id TEXT NOT NULL,
                decision TEXT NOT NULL, reviewer TEXT NOT NULL, note TEXT NOT NULL,
                recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        connection.execute(
            """INSERT INTO decisions (snapshot, report_id, recall_id, decision, reviewer, note)
               VALUES (:snapshot, :report_id, :recall_id, :decision, :reviewer, :note)""",
            review.model_dump(),
        )
