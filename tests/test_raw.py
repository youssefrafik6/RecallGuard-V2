"""Verify the official-export workflow and its public dashboard boundary."""

import json
from pathlib import Path
from zipfile import ZipFile

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from recallguard.data import INCIDENT, RECALL
from recallguard.linkage import LinkageConfig
from recallguard.raw import prepare_raw


@pytest.fixture
def source_files(tmp_path):
    incident_fields = {
        header: ""
        for header, field in INCIDENT.items()
        if field
        not in ("historical_confidence", "historical_match_rule", "recall_campaign")
    }
    incident_fields.update(
        {
            "Report No.": "0001",
            "Report Date": "1/1/2025",
            "Publication Date": "1/28/2025",
            "Product Description": "EXAMPLE Café Kettle",
            "Manufacturer / Importer / Private Labeler Name": "Example Ltd.",
            "Brand": "Example",
            "Model Name or Number": "KT-123",
            "Category of Submitter": "PRIVATE-CONTEXT",
            "Incident Description": "PRIVATE-NARRATIVE",
            "label_recalled": "0",
        }
    )
    incidents = pd.DataFrame(
        [
            incident_fields,
            {
                **incident_fields,
                "Report No.": "0002",
                "Model Name or Number": "",
                "Product Description": "Bar stool",
                "Manufacturer / Importer / Private Labeler Name": "",
                "Brand": "",
            },
        ]
    )
    archive = tmp_path / "SPDB.zip"
    with ZipFile(archive, "w") as bundle:
        csv = '"Disclaimer: test export"\n' + incidents.to_csv(index=False)
        bundle.writestr("IncidentReports.csv", csv.encode("cp1252"))

    recall_fields = dict.fromkeys(RECALL, "")
    recall_fields.update(
        {
            "Recall Number": "0003",
            "Date": "January 10, 2025",
            "Name of product": "Example Café Kettle",
            "Manufacturers": "Example Inc.",
            "Description": "This recall involves model KT-123.",
        }
    )
    listing = tmp_path / "recalls.csv"
    pd.DataFrame(
        [
            recall_fields,
            recall_fields,
            {**recall_fields, "Recall Number": "0004"},
            {
                **recall_fields,
                "Recall Number": "0004",
                "Name of product": "Example Kettle 2",
            },
            {
                **recall_fields,
                "Recall Number": "",
                "Product Safety Warning Number": "Notice-5",
            },
        ]
    ).to_csv(listing, index=False, encoding="utf-8-sig")
    return archive, listing


def test_raw_normalization_and_label_provenance(tmp_path, source_files):
    snapshot = tmp_path / "processed"
    report = prepare_raw(*source_files, snapshot, LinkageConfig())
    assert report["sources"]["incidents"]["encoding"] == "cp1252"
    assert report["recalls"]["duplicate_rows_collapsed"] == 1
    assert report["recalls"]["missing_identifier_rows"] == 1
    assert report["recalls"]["conflicting_rows_excluded"] == 2
    assert (
        report["linkage"]["heuristic_links_by_publication_timing"][
            "recall_on_or_before_publication"
        ]
        == 1
    )
    assert report["labels"] == {"verified": 0, "heuristic": 1, "unlabeled": 1}
    assert report["evaluation"]["status"] == "insufficient_verified_labels"
    observations = pd.read_csv(snapshot / "observations.csv", dtype=str).fillna("")
    assert observations.report_id.tolist() == ["0001", "0002"]
    assert observations.heuristic_label.tolist() == ["1", ""]
    assert observations.verified_label.tolist() == ["", ""]
    assert observations.heuristic_recall_id.tolist() == ["0003", ""]
    assert observations.iloc[0]["product"] == "example café kettle"
    assert observations.iloc[0]["manufacturer"] == "example"
    candidates = pd.read_csv(snapshot / "candidates.csv")
    assert candidates.iloc[0]["model_exact"]
    assert candidates.iloc[0]["rank"] == 1
    assert all("PRIVATE-" not in file.read_text() for file in snapshot.glob("*"))
    assert json.loads((snapshot / "summary.json").read_text()) == report
    with pytest.raises(FileExistsError):
        prepare_raw(*source_files, snapshot, LinkageConfig())


def test_raw_rejects_bad_rows_without_publishing(tmp_path, source_files):
    archive, listing = source_files
    with listing.open("a") as file:
        file.write("001,unexpected field count\n")
    snapshot = tmp_path / "processed"
    with pytest.raises(ValueError, match="wrong field count"):
        prepare_raw(archive, listing, snapshot, LinkageConfig())
    assert not snapshot.exists()


def test_dashboard_uses_only_aggregates_by_default(tmp_path, source_files, monkeypatch):
    snapshot = tmp_path / "processed"
    prepare_raw(*source_files, snapshot, LinkageConfig())
    (snapshot / "review_sample.csv").write_text(
        "report_id,recall_id,confidence\nPRIVATE-ID,1,high\n"
    )
    monkeypatch.setenv("RECALLGUARD_SUMMARY", str(snapshot / "summary.json"))
    monkeypatch.delenv("RECALLGUARD_CANDIDATES", raising=False)
    monkeypatch.delenv("RECALLGUARD_MODEL", raising=False)
    entry = Path(__file__).resolve().parents[1] / "dashboard/app.py"
    ui = AppTest.from_file(str(entry)).run()
    assert not ui.exception
    assert [metric.value for metric in ui.metric] == ["2", "1", "1"]
    ui.sidebar.radio[0].set_value("Dataset explorer").run()
    assert not ui.exception
    ui.sidebar.radio[0].set_value("Record linkage").run()
    assert not ui.exception
    assert len(ui.dataframe) == 2
    assert "PRIVATE-ID" not in ui.dataframe[0].value.to_string()
    assert "high" in ui.dataframe[0].value["confidence"].values
    ui.slider[0].set_value(15).run()
    assert set(ui.dataframe[0].value["confidence"]) == {"rejected"}
