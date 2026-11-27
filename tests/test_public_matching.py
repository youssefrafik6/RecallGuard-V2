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
    ui = AppTest.from_file(str(ENTRY)).run()
    ui.sidebar.radio[0].set_value("Interactive product matching").run()
    ui.button[0].click().run()
    assert not ui.exception
    assert ui.dataframe[0].value.iloc[0]["recall_id"] == "DEMO-101"
    ui.text_input[1].set_value("2025-02-30")
    ui.button[0].click().run()
    assert "invalid" in ui.error[0].value
    ui.selectbox[0].set_value("Product with no candidate").run()
    ui.button[0].click().run()
    assert "No candidate" in ui.info[-1].value

    ui.sidebar.radio[0].set_value("Explainability").run()
    assert not ui.exception
    assert [metric.value for metric in ui.metric] == ["1", "High", "1.000"]
    assert ui.dataframe[0].value["Weighted value"].sum() == 1.0
    ui.selectbox[1].set_value("DEMO-102").run()
    assert ui.metric[1].value == "Rejected"
    assert any("Date eligible: no" in caption.value for caption in ui.caption)
    ui.selectbox[0].set_value("Kettle with an exact GTIN").run()
    assert ui.metric[1].value == "High"
    assert (
        ui.dataframe[1].value.set_index("Additional evidence").at["Exact GTIN", "Value"]
        == "Yes"
    )
    ui.slider[0].set_value(1).run()
    assert ui.metric[1].value == "Rejected"
    ui.selectbox[0].set_value("Product with no candidate").run()
    assert "no pair-level evidence" in ui.info[-1].value


def test_public_batch_example_upload_validation_and_download():
    ui = AppTest.from_file(str(ENTRY)).run()
    ui.sidebar.radio[0].set_value("Batch analysis").run()
    ui.button[0].click().run()
    assert not ui.exception
    assert ui.dataframe[-1].value.report_id.nunique() == 3
    assert "no candidate" in ui.dataframe[-1].value.confidence.values
    next(item for item in ui.radio if item.label == "Input source").set_value(
        "Upload fictional CSV"
    ).run()
    ui.button[0].click().run()
    assert "Choose a fictional CSV" in ui.error[0].value
    ui.get("file_uploader")[0].upload("invalid.csv", b"product\nexample").run()
    ui.button[0].click().run()
    assert "unique columns" in ui.error[0].value

    payload = demo_csv().encode() + b"=PRIVATE-TEXT,2025-01-01,,,,\n"
    ui.get("file_uploader")[0].upload("fictional.csv", payload, "text/csv").run()
    ui.button[0].click().run()
    assert not ui.exception and not ui.error
    actual = ui.dataframe[0].value
    assert actual.report_id.nunique() == 4
    assert "PRIVATE-TEXT" not in actual.to_csv(index=False)
    assert ui.get("download_button")[-1].label == "Download linkage results"
