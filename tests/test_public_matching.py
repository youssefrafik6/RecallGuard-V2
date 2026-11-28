"""Exercise the public-only matching tools without historical artifacts."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from recallguard.demo import MAX_BYTES, batch_results, demo_csv, parse_upload

ENTRY = Path(__file__).resolve().parents[1] / "dashboard/public.py"


@pytest.mark.parametrize(
    ("payload", "problem"),
    [
        (b"x" * (MAX_BYTES + 1), "64 KiB"),
        (b"product,report_date\n" + b"Lamp,2025-01-01\n" * 51, "50 incident"),
        (b"product,report_date,description\n", "unique columns"),
        (b"product,product,report_date\n", "unique columns"),
        (b"product\nLamp", "unique columns"),
        (b'product,report_date\n"Lamp,2025-01-01', "quoting"),
        (b"product,report_date\nLamp,2025-01-01,unexpected", "number of fields"),
        (b"product,report_date\n\xff", "UTF-8"),
        (b"product,report_date\n", "at least one"),
        (b"product,report_date\nLamp,2025-02-29", "date is invalid"),
        (b"product,report_date\nLamp,tomorrow", "YYYY-MM-DD"),
        (b"product,report_date,upc\nLamp,2025-01-01,2001234567894", "checksum-valid"),
        (b"product,report_date\n,2025-01-01", "product is required"),
        (b"product,report_date\n" + b"x" * 121 + b",2025-01-01", "120 printable"),
    ],
)
def test_batch_rejects_invalid_input(payload, problem):
    with pytest.raises(ValueError, match=problem):
        batch_results(parse_upload(payload), 365)


def test_public_matching_and_explanations():
    ui = AppTest.from_file(str(ENTRY), default_timeout=45).run()
    ui.sidebar.radio[0].set_value("Interactive product matching").run()
    ui.button[0].click().run()
    assert not ui.exception
    assert ui.dataframe[0].value.iloc[0]["recall_id"] == "24-181"
    ui.text_input[1].set_value("2025-02-30")
    ui.button[0].click().run()
    assert "invalid" in ui.error[0].value

    ui.sidebar.radio[0].set_value("Explainability").run()
    assert not ui.exception
    assert [metric.value for metric in ui.metric][:2] == ["1", "High"]
    assert "24-181" in ui.selectbox[1].options[0]
    assert "Date eligible: yes" in " ".join(c.value for c in ui.caption)
    ui.slider[0].set_value(1).run()
    assert ui.metric[1].value == "Rejected"
    assert "Date eligible: no" in " ".join(c.value for c in ui.caption)


def test_public_batch_example_upload_validation_and_download():
    ui = AppTest.from_file(str(ENTRY), default_timeout=45).run()
    ui.sidebar.radio[0].set_value("Batch analysis").run()
    ui.button[0].click().run()
    assert not ui.exception
    assert ui.dataframe[-1].value.report_id.nunique() == 3
    assert set(ui.dataframe[-1].value.query("rank == 1").recall_id) == {
        "24-181",
        "24-159",
        "25-052",
    }
    next(item for item in ui.radio if item.label == "Input source").set_value(
        "Upload product CSV"
    ).run()
    ui.button[0].click().run()
    assert "Choose a product CSV" in ui.error[0].value
    ui.get("file_uploader")[0].upload("invalid.csv", b"product\nexample").run()
    ui.button[0].click().run()
    assert "unique columns" in ui.error[0].value

    payload = demo_csv().encode() + b"=PRIVATE-TEXT,2025-01-01,,,,\n"
    ui.get("file_uploader")[0].upload("products.csv", payload, "text/csv").run()
    ui.button[0].click().run()
    assert not ui.exception and not ui.error
    actual = ui.dataframe[0].value
    assert actual.report_id.nunique() == 4
    assert "PRIVATE-TEXT" not in actual.to_csv(index=False)
    assert set(actual.loc[actual.report_id.eq("INPUT-04"), "confidence"]) <= {
        "no candidate",
        "rejected",
    }
    assert ui.get("download_button")[-1].label == "Download linkage results"
