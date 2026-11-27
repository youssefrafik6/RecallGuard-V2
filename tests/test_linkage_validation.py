"""Design-weighted evaluation and public-demo isolation."""

import json
from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

from recallguard.linkage_validation import (
    evaluate_pairs,
    match_count_interval,
    sample_pairs,
)


def test_review_draw_and_agreement(tmp_path):
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    statuses = ["high", "review", "rejected", "rejected", "rejected", "rejected"]
    pd.DataFrame(
        {
            "report_id": [f"R{i}" for i in range(len(statuses))],
            "recall_id": "C1",
            "confidence": statuses,
            "days_to_recall": [15, 15, 15, 15, -8, -10],
            "score": [0.9, 0.6, 0.4, 0.42, 0.9, 0.0],
            "model_exact": False,
            "gtin_exact": False,
            "reason": "",
            "rank": 1,
            "block_votes": 0,
        }
    ).to_csv(snapshot / "candidates.csv", index=False)
    for name, key, ids, date in (
        ("observations.csv", "report_id", [f"R{i}" for i in range(6)], "report_date"),
        ("recalls.csv", "recall_id", ["C1"], "recall_date"),
    ):
        pd.DataFrame(
            {key: ids, "product": "Lamp", "manufacturer": "Test", date: "2026-01-01"}
        ).to_csv(snapshot / name, index=False)
    (snapshot / "summary.json").write_text(
        json.dumps({"config": {"horizon_days": 365}})
    )

    out = tmp_path / "sample"
    manifest = sample_pairs(snapshot, out, seed=42, per_stratum=1)
    assert sample_pairs(snapshot, tmp_path / "replay", 42, 1) == manifest
    assert sum(item["population"] for item in manifest["strata"].values()) == 6
    assert evaluate_pairs(out, []) == {
        "status": "validation_pending",
        "sampled_pairs": 4,
    }
    packet = pd.read_csv(out / "review_packet.csv")
    assert not {"confidence", "stratum", "reason", "score"} & set(packet)
    design = pd.read_csv(out / "design.csv").set_index("pair_id")
    first = pd.read_csv(out / "decisions_template.csv")
    first["decision"] = first.pair_id.map(design.stratum).map(
        {
            "high": "match",
            "uncertain": "non_match",
            "plausible_nonmatch": "match",
            "random_remainder": "non_match",
        }
    )
    second = first.copy()
    second.loc[0, "decision"] = "uncertain"
    paths = [tmp_path / "first.csv", tmp_path / "second.csv"]
    first.to_csv(paths[0], index=False)
    second.to_csv(paths[1], index=False)
    result = evaluate_pairs(out, paths)
    assert result["status"] == "validation_pending"
    assert result["disagreements"] == 1
    assert "candidate_frame_recall" not in result
    first.to_csv(paths[1], index=False)
    result = evaluate_pairs(out, paths)
    assert result["sample_cohen_kappa"] == 1
    assert result["high_tier_precision"] == 1
    assert result["high_tier_precision_95ci"] == [1, 1]
    assert result["candidate_frame_recall"] == 1 / 3
    assert match_count_interval(5, 5, 2, 0.025) == (2, 2)


def test_public_entrypoint_never_reads_local_operator_overrides(tmp_path, monkeypatch):
    unsafe = tmp_path / "local.csv"
    unsafe.write_text("report_id,recall_id,confidence\nPRIVATE-NARRATIVE,1,high\n")
    ledger = tmp_path / "writable.sqlite"
    monkeypatch.setenv("RECALLGUARD_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("RECALLGUARD_SUMMARY", str(unsafe))
    monkeypatch.setenv("RECALLGUARD_CANDIDATES", str(unsafe))
    monkeypatch.setenv("RECALLGUARD_MODEL", str(unsafe))
    monkeypatch.setenv("RECALLGUARD_REVIEWS", str(ledger))
    public = Path(__file__).resolve().parents[1] / "dashboard/public.py"
    ui = AppTest.from_file(str(public)).run()
    assert [metric.value for metric in ui.metric] == ["70,000", "10,098", "168"]
    for page in ui.sidebar.radio[0].options:
        ui.sidebar.radio[0].set_value(page).run()
        assert not ui.exception
        assert not ui.get("file_uploader")
        assert not any(field.label == "Reviewer label" for field in ui.text_input)
        if page == "Record linkage":
            assert len(ui.dataframe) == 2
            assert set(ui.dataframe[0].value.recall_id) == {"DEMO-101", "DEMO-102"}
    assert not ledger.exists()


def test_local_dashboard_handles_missing_files(tmp_path, monkeypatch):
    monkeypatch.setenv("RECALLGUARD_SUMMARY", str(tmp_path / "missing.json"))
    monkeypatch.setenv("RECALLGUARD_MODEL", str(tmp_path / "missing.joblib"))
    entry = Path(__file__).resolve().parents[1] / "dashboard/app.py"
    ui = AppTest.from_file(str(entry)).run()
    assert not ui.exception
    assert any("RECALLGUARD_SUMMARY" in item.value for item in ui.info)
    ui.sidebar.radio[0].set_value("Dataset explorer").run()
    assert not ui.exception
    ui.sidebar.radio[0].set_value("Historical association scoring").run()
    assert not ui.exception
    assert any("trusted historical model" in item.value for item in ui.info)
