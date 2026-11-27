"""RecallGuard local research dashboard."""

import hashlib
import json
import os
from io import BytesIO
from pathlib import Path
from sqlite3 import Error as SQLiteError

import pandas as pd
import streamlit as st
from pydantic import ValidationError

from recallguard.analytics import aggregate
from recallguard.batch import read_batch
from recallguard.inference import (
    LIMITATION,
    configured_model,
    global_features,
    predict,
    predict_batch,
)
from recallguard.inference import IncidentRequest as Input
from recallguard.linkage import LinkageConfig, link
from recallguard.raw import SCHEMA_VERSION
from recallguard.review import ReviewDecision, record_review

ROOT = Path(os.getenv("RECALLGUARD_WORKSPACE", Path(__file__).resolve().parents[1]))
st.set_page_config(page_title="RecallGuard V2", page_icon="▣", layout="wide")
st.markdown(
    """
    <style>
    .block-container {max-width: 1180px; padding-top: 3rem;}
    [data-testid="stMetric"] {border: 1px solid #768b9840; border-radius: 12px; padding: 1rem;}
    [data-testid="stSidebar"] {border-right: 1px solid #768b9840;}
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def model(path: str, modified: int):
    return configured_model()


@st.cache_data
def snapshot_summary(path: Path, modified: int):
    return json.loads(path.read_text())


@st.cache_data
def candidate_demo(horizon_days: int):
    incidents = pd.DataFrame(
        [
            {
                "report_id": "DEMO-01",
                "product": "Maple Trail lithium lantern",
                "manufacturer": "Maple Trail LLC",
                "brand": "Maple Trail",
                "report_date": pd.Timestamp("2025-01-01"),
            }
        ]
    )
    recalls = pd.DataFrame(
        [
            {
                "recall_id": "DEMO-101",
                "product": "Maple Trail lithium lantern",
                "manufacturer": "Maple Trail",
                "heading": "Maple Trail lantern recall",
                "recall_date": pd.Timestamp("2025-02-01"),
            },
            {
                "recall_id": "DEMO-102",
                "product": "Maple Trail solar lantern",
                "manufacturer": "Maple Trail",
                "heading": "Maple Trail lantern recall",
                "recall_date": pd.Timestamp("2024-11-01"),
            },
        ]
    )
    return link(incidents, recalls, LinkageConfig(horizon_days=horizon_days))


path = os.getenv("RECALLGUARD_MODEL", "")
modified = Path(path).stat().st_mtime_ns if path and Path(path).is_file() else 0
bundle = model(path, modified)
st.sidebar.title("RecallGuard V2")
st.sidebar.caption("CPSC incident research")
page = st.sidebar.radio(
    "Explore",
    [
        "Overview",
        "Historical association scoring",
        "Batch analysis",
        "Dataset explorer",
        "Record linkage",
        "Model performance",
        "Explainability",
        "About",
    ],
)
st.sidebar.caption("Historical model loaded" if bundle else "No local model configured")
st.title(page if page != "Overview" else "Consumer product recall analysis")
st.caption(
    "Retrospective analysis of links between consumer incident reports and CPSC recalls."
)

if page in {"Overview", "Dataset explorer"}:
    configured = os.getenv("RECALLGUARD_SUMMARY")
    summary_path = (
        Path(configured)
        if configured
        else ROOT / "results/metrics/cpsc-raw-2026-11-26.json"
    )
    try:
        summary = snapshot_summary(summary_path, summary_path.stat().st_mtime_ns)
        if (
            not isinstance(summary, dict)
            or summary.get("schema_version") != SCHEMA_VERSION
        ):
            raise ValueError("Unsupported CPSC summary schema")
    except (OSError, ValueError):
        summary = None
        st.info("Set RECALLGUARD_SUMMARY to the summary.json produced by prepare-raw.")

if page == "Overview":
    if summary is not None:
        left, middle, right = st.columns(3)
        left.metric("Incident reports", f"{summary['incidents']['retained_rows']:,}")
        middle.metric("Recall records", f"{summary['recalls']['retained_rows']:,}")
        right.metric("Heuristic links", f"{summary['labels']['heuristic']:,}")
        st.caption(
            "Source: local CPSC snapshot"
            if configured
            else "Source: CPSC snapshot downloaded November 26, 2026"
        )
    st.write(
        "RecallGuard ranks candidate links between submitted incident reports and "
        "CPSC recalls. The Record linkage page demonstrates how the ranking works."
    )
    st.info(
        "The official exports supply no verified outcome labels for supervised evaluation."
    )

elif page == "Dataset explorer":
    if summary is None:
        st.stop()
    st.subheader("Incident reports by report year")
    annual = pd.Series(summary["reports_by_year"], name="Reports").sort_index()
    if annual.empty:
        st.info("No years meet the publication threshold for this snapshot.")
    else:
        st.bar_chart(annual)
    st.caption("Years with fewer than 10 reports are omitted.")
    st.subheader("Label status")
    st.dataframe(pd.Series(summary["labels"], name="Reports"), width="stretch")
    st.subheader("Candidate confidence")
    st.dataframe(
        pd.Series(summary["linkage"]["confidence_counts"], name="Pairs"),
        width="stretch",
    )
    st.caption(
        "Confidence reflects linkage rules. Linkage precision and recall require independent review."
    )

elif page == "Record linkage":
    st.info("Synthetic example. The product and recall identifiers are fictional.")
    st.write(
        "DEMO-01 reports a Maple Trail lithium lantern. Two candidates share product terms. "
        "The solar lantern listing is rejected because its announcement precedes the report."
    )
    horizon = st.slider("Days after report eligible for linkage", 1, 365, 365)
    st.dataframe(candidate_demo(horizon), hide_index=True, width="stretch")
    review_sample_path = os.getenv("RECALLGUARD_CANDIDATES")
    if review_sample_path and (audit_path := Path(review_sample_path)).is_file():
        st.subheader("Local CPSC candidate audit")
        snapshot = audit_path.read_bytes()
        preview = pd.read_csv(
            BytesIO(snapshot), dtype={"report_id": str, "recall_id": str}
        )
        status = st.selectbox(
            "Candidate confidence", ["All", "high", "review", "rejected"]
        )
        st.caption(
            "Showing up to 30 high-scoring cases per status. This sample is for review."
        )
        visible = (
            preview if status == "All" else preview.loc[preview.confidence.eq(status)]
        )
        st.dataframe(visible, hide_index=True, width="stretch")
        st.dataframe(aggregate(preview, "confidence"), hide_index=True)
        if not visible.empty:
            choice = st.selectbox(
                "Candidate to review",
                visible.index,
                format_func=lambda i: (
                    f"{visible.at[i, 'report_id']} / {visible.at[i, 'recall_id']}"
                ),
            )
            with st.form("review"):
                reviewer = st.text_input("Reviewer label", max_chars=80)
                decision = st.selectbox("Decision", ["uncertain", "match", "non_match"])
                note = st.text_area("Evidence note", max_chars=1000)
                if st.form_submit_button("Save decision"):
                    try:
                        review = ReviewDecision(
                            snapshot=hashlib.sha256(snapshot).hexdigest(),
                            report_id=visible.at[choice, "report_id"],
                            recall_id=visible.at[choice, "recall_id"],
                            decision=decision,
                            reviewer=reviewer.strip(),
                            note=note,
                        )
                        record_review(
                            Path(
                                os.getenv(
                                    "RECALLGUARD_REVIEWS",
                                    ROOT / "data/processed/reviews.sqlite",
                                )
                            ),
                            review,
                        )
                    except (ValidationError, OSError, SQLiteError):
                        st.error(
                            "Enter a reviewer label and check local storage permissions."
                        )
                    else:
                        st.success(
                            "Decision recorded separately from candidate scores."
                        )

elif page == "About":
    st.subheader("Youssef Rafik · Southern Connecticut State University")
    st.write(
        "Bachelor of Science in Data Science capstone, Spring 2026. The original project "
        "connected public incident reports to official recall listings and compared NLP classifiers. "
        "V2 adds reproducible split comparisons, candidate review, local model artifacts, DuckDB analytics and a shared API."
    )
    st.write("Python · pandas · scikit-learn · XGBoost · DuckDB · Streamlit · FastAPI")
    st.markdown("[CPSC data sources](https://www.cpsc.gov/Data)")
    st.info(
        "Missed links, report availability, catalog coverage, and product identity ambiguity "
        "limit how far the results generalize."
    )

elif bundle is None and page != "Model performance":
    st.info(
        "Optional historical scoring view. Configure a trusted historical model to use it."
    )

elif page == "Batch analysis":
    st.caption(
        "Upload 1–100 incidents. Accepted columns are product, description, category, brand, manufacturer, and product_type."
    )
    upload = st.file_uploader("Incident CSV", type=["csv"])
    if upload and st.button("Score incidents", type="primary"):
        try:
            if upload.size > 2_000_000:
                raise ValueError("File must be smaller than 2 MB")
            batch = read_batch(upload)
            results = pd.DataFrame(
                [
                    {"row": index, **result.model_dump(exclude={"contributions"})}
                    for index, result in enumerate(
                        predict_batch(bundle, batch), start=1
                    )
                ]
            )
        except (ValueError, UnicodeError) as exc:
            st.error(f"CSV validation failed: {exc}")
        else:
            st.dataframe(results, hide_index=True)
            st.download_button(
                "Download scores",
                results.to_csv(index=False),
                "recallguard-scores.csv",
                "text/csv",
            )

elif page == "Historical association scoring":
    with st.form("assessment"):
        product = st.text_input("Product description", max_chars=16000)
        description = st.text_area("Incident description", max_chars=16000)
        left, right = st.columns(2)
        category = left.text_input("Product category", max_chars=240)
        brand = right.text_input("Brand", max_chars=240)
        manufacturer = left.text_input("Manufacturer", max_chars=240)
        product_type = right.text_input("Product type", max_chars=240)
        submitted = st.form_submit_button("Assess review priority", type="primary")
    if submitted:
        try:
            request = Input(
                product=product,
                description=description,
                category=category,
                brand=brand,
                manufacturer=manufacturer,
                product_type=product_type,
            )
        except ValidationError:
            st.error("Enter a product description or an incident description.")
        else:
            result = predict(bundle, request)
            left, right = st.columns(2)
            left.metric("Review priority", result.priority)
            right.metric("Association score", f"{result.priority_score:.3f}")
            st.caption(LIMITATION)
            if result.contributions:
                st.bar_chart(
                    pd.DataFrame([item.model_dump() for item in result.contributions]),
                    x="feature",
                    y="effect",
                    horizontal=True,
                )
                st.caption(
                    "Contributions describe the model's base score. They do not establish causes."
                )

elif page == "Model performance":
    reports = {
        path.stem.removeprefix("v2-").title(): path
        for path in sorted((ROOT / "results/metrics").glob("v2-*.json"))
        if path.stem in {"v2-random", "v2-group", "v2-chronological"}
    }
    st.info("Historical proxy benchmarks from the old sampled dataset.")
    sources = (["Loaded historical model"] if bundle else []) + list(reports)
    if not sources:
        st.info("Train a model or add a V2 benchmark report to view performance.")
        st.stop()
    source = st.selectbox("Evaluation run", sources)
    metadata = (
        bundle["metadata"]
        if source == "Loaded historical model"
        else json.loads(reports[source].read_text())
    )
    comparisons = metadata["comparison"]
    st.write(
        f"{metadata['dataset']} · {metadata['design']} holdout · seed {metadata['seed']}"
    )
    criterion = "F1" if metadata.get("selection") == "f1" else "average precision"
    st.caption(
        f"Selected using validation {criterion}: {metadata['selected']}. "
        "Positive labels are rare and the dataset was sampled."
    )
    fields = [
        "variant",
        "precision",
        "recall",
        "f1",
        "average_precision",
        "roc_auc",
        "brier",
    ]
    with st.expander("Partition dates and label counts"):
        st.dataframe(pd.DataFrame(metadata["partitions"]).T)
        st.caption(
            f"Rows excluded by the evaluation protocol: {metadata['excluded_rows']:,}"
        )
    st.dataframe(pd.DataFrame(comparisons).T[fields], width="stretch")
    family = st.selectbox(
        "Inspect model",
        list(comparisons),
        index=list(comparisons).index(metadata["selected"]),
    )
    report = comparisons[family]
    st.dataframe(
        pd.DataFrame(
            report["confusion_matrix"],
            index=["Actual 0", "Actual 1"],
            columns=["Predicted 0", "Predicted 1"],
        )
    )
    st.dataframe(
        pd.DataFrame(report["top_k"]).T.reset_index(drop=True), hide_index=True
    )
    st.caption(f"Validation-selected high-priority cutoff: {report['threshold']:.3f}")
    if report.get("category_analysis"):
        with st.expander("Held-out metrics by category"):
            st.caption("Slices with at least 20 test examples and both labels.")
            st.dataframe(report["category_analysis"], hide_index=True)
    for title, field, x in [
        ("Precision-recall", "pr_curve", "recall"),
        ("Receiver operating characteristic", "roc_curve", "false_positive_rate"),
        ("Reliability", "reliability", "mean_score"),
        ("Validation threshold trade-off", "threshold_analysis", "threshold"),
    ]:
        st.subheader(title)
        curve = pd.DataFrame(report[field])
        if field == "reliability":
            curve["perfect_calibration"] = curve[x]
        st.line_chart(curve, x=x)

elif page == "Explainability":
    values = pd.DataFrame(global_features(bundle))
    st.caption(
        "Coefficients or tree feature importance describe how the selected estimator uses inputs. "
        "Individual contributions are available after scoring a report."
    )
    if values.empty:
        st.info("The current estimator does not expose global feature weights.")
    else:
        st.bar_chart(values, x="feature", y="weight", horizontal=True)
