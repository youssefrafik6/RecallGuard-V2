"""Boundary tests for the V2 analytics, batch and review paths."""

import sqlite3
from io import BytesIO

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from recallguard.analytics import aggregate
from recallguard.api import app
from recallguard.batch import read_batch
from recallguard.linkage import LinkageConfig, link, reference_coverage
from recallguard.review import ReviewDecision, record_review


def test_csv_batch_rejects_unknown_columns_and_oversize():
    with pytest.raises(ValueError, match="Unsupported"):
        read_batch(BytesIO(b"description,unknown\nsmoke,yes\n"))
    with pytest.raises(ValueError, match="100"):
        read_batch(BytesIO(b"product\n" + b"test kettle\n" * 101))
    assert (
        read_batch(BytesIO(b"product\nTest kettle\n")).incidents[0].product
        == "Test kettle"
    )


def test_analytics_endpoints_and_sql(tmp_path, monkeypatch):
    path = tmp_path / "incidents.csv"
    pd.DataFrame(
        {
            "Report No.": ["a", "b", "c"],
            "Report Date": ["2020-01-10", "2020-01-15", ""],
            "Product Description": ["Kettle", "Lamp", "Glove"],
            "Product Category": ["Kitchen", "Kitchen", "Other"],
            "label_recalled": [1, 0, 0],
        }
    ).to_csv(path, index=False)
    monkeypatch.setenv("RECALLGUARD_DATA", str(path))
    with TestClient(app) as client:
        result = client.get("/analytics/summary")
        assert result.status_code == 200
        assert result.json() == {
            "reports": 3,
            "linked_reports": 1,
            "unlabeled_reports": 0,
            "missing_report_dates": 1,
            "missing_manufacturers": 3,
        }
        assert client.get("/analytics/categories").json()[0] == {
            "category": "Kitchen",
            "reports": 2,
            "linked_reports": 1,
            "volume_rank": 1,
        }
        data = app.state.dataset
        assert aggregate(data, "trends").iloc[0].reports == 2
        assert aggregate(data, "manufacturers").iloc[0].manufacturer == "Unspecified"
    monkeypatch.delenv("RECALLGUARD_DATA")
    with TestClient(app) as client:
        assert client.get("/analytics/summary").status_code == 503
        assert client.get("/analytics/categories").status_code == 503
    candidates = pd.DataFrame(
        {"confidence": ["review", "review"], "report_id": ["1", "1"]}
    )
    row = aggregate(candidates, "confidence").iloc[0]
    assert (row.candidate_pairs, row.reports) == (2, 1)


def test_linkage_rank_and_review_history(tmp_path):
    incidents = pd.DataFrame(
        [
            {
                "product": "electric lantern",
                "brand": "",
                "manufacturer": "Example LLC",
                "report_date": pd.Timestamp("2020-01-01"),
                "report_id": "0001",
                "description": "electrical short in a rechargeable lantern",
            }
        ]
    )
    recalls = pd.DataFrame(
        [
            {
                "recall_id": "002",
                "product": "electric lantern",
                "heading": "lantern",
                "manufacturer": "Example",
                "recall_date": pd.Timestamp("2019-01-02"),
            },
            {
                "recall_id": "001",
                "product": "electric lantern",
                "heading": "lantern",
                "manufacturer": "Example",
                "recall_date": pd.Timestamp("2020-01-02"),
            },
        ]
    )
    audit = link(incidents, recalls, LinkageConfig())
    top = audit.iloc[0]
    assert top.recall_id == "001" and top["rank"] == 1 and top.confidence == "high"
    assert top.char_trigram_jaccard == top.edit_similarity == 1
    assert 0 < top.document_tfidf_cosine <= 1
    reference = pd.DataFrame(
        [
            {
                "report_id": "0001",
                "recall_id": "001",
                "Report Date": "2020-01-01",
                "Date": "2020-01-02",
            }
        ]
    )
    assert (
        reference_coverage(audit, reference, 365)["date_eligible"]["top_1_pairs"] == 1
    )

    path = tmp_path / "reviews.sqlite"
    for decision in ("uncertain", "match"):
        record_review(
            path,
            ReviewDecision(
                snapshot="a" * 64,
                report_id="0001",
                recall_id="001",
                decision=decision,
                reviewer="local review",
            ),
        )
    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT report_id, decision FROM decisions ORDER BY id"
        ).fetchall() == [("0001", "uncertain"), ("0001", "match")]
    assert top.confidence == "high"


def test_dashboard_saves_review(tmp_path, monkeypatch):
    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    candidates = tmp_path / "review.csv"
    candidates.write_text("report_id,recall_id,confidence\n0001,002,review\n")
    reviews = tmp_path / "reviews.sqlite"
    monkeypatch.setenv("RECALLGUARD_CANDIDATES", str(candidates))
    monkeypatch.setenv("RECALLGUARD_REVIEWS", str(reviews))
    monkeypatch.delenv("RECALLGUARD_DATA", raising=False)
    monkeypatch.delenv("RECALLGUARD_MODEL", raising=False)
    entry = Path(__file__).resolve().parents[1] / "dashboard" / "app.py"
    ui = AppTest.from_file(str(entry), default_timeout=30).run()
    ui.sidebar.radio[0].set_value("Record linkage").run()
    assert not ui.exception
    ui.text_input[0].set_value("Test reviewer")
    ui.selectbox[2].set_value("match")
    ui.button[0].click().run()
    assert not ui.exception
    with sqlite3.connect(reviews) as connection:
        assert connection.execute(
            "SELECT report_id, recall_id, decision FROM decisions"
        ).fetchone() == ("0001", "002", "match")
