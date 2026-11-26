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
from recallguard.data import TARGET, load_incidents
from recallguard.inference import (
    LIMITATION,
    configured_model,
    global_features,
    predict,
    predict_batch,
)
from recallguard.inference import IncidentRequest as Input
from recallguard.linkage import LinkageConfig, link
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
def dataset(path: Path):
    return load_incidents(path, labeled=True)


def spreadsheet_safe(value):
    """Keep formula-like text inert when a downloaded CSV opens in a spreadsheet."""
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


@st.cache_data
def candidate_demo():
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
    return link(incidents, recalls, LinkageConfig())


path = os.getenv("RECALLGUARD_MODEL", "")
modified = Path(path).stat().st_mtime_ns if path and Path(path).is_file() else 0
bundle = model(path, modified)
st.sidebar.title("RecallGuard V2")
st.sidebar.caption("CPSC incident research")
page = st.sidebar.radio(
    "Explore",
    [
        "Overview",
        "Recall risk assessment",
        "Batch analysis",
        "Dataset explorer",
        "Record linkage",
        "Model performance",
        "Explainability",
        "About",
    ],
)
st.sidebar.caption("Local model loaded" if bundle else "No local model configured")
st.title(page if page != "Overview" else "Consumer product recall analysis")
st.caption(
    "Retrospective analysis of links between consumer incident reports and CPSC recalls."
)

if page in {"Overview", "Dataset explorer"}:
    try:
        data_path = Path(
            os.getenv("RECALLGUARD_DATA", str(ROOT / "data/training_data.csv"))
        )
        data = dataset(data_path)
    except (OSError, ValueError):
        data = None
        st.info(
            "Set RECALLGUARD_DATA to a local historical CSV to enable dataset analytics."
        )

if page == "Overview":
    if data is not None:
        summary = aggregate(data, "summary").iloc[0]
        left, middle, right = st.columns(3)
        left.metric("Labeled observations", f"{summary.reports:,}")
        middle.metric("Recall-linked labels", f"{summary.linked_reports:,}")
        right.metric("Linked share", f"{data[TARGET].mean():.1%}")
    st.graphviz_chart(
        """
        digraph {
            rankdir=LR;
            bgcolor="transparent";
            node [shape=box, style="rounded,filled", color="#76A8A5",
                  fillcolor="#F0F6F5", fontcolor="#173039", fontname="Helvetica"];
            edge [color="#086D6A"];
            "CPSC exports" -> "Ranked candidates" -> "Review ledger";
            "Historical labels" -> "Offline evaluation" -> "Model artifact" -> "API and dashboard";
        }
        """
    )
    st.subheader("From public reports to review priorities")
    st.write(
        "CPSC incident reports and recall listings have no shared product identifier. "
        "RecallGuard shows how candidate links create labels and how a classifier ranks historical associations."
    )
    st.info("Model evaluation uses a labeled sample of the CPSC records.")
    if bundle:
        metadata = bundle["metadata"]
        report = metadata["comparison"][metadata["selected"]]
        st.subheader("Loaded model holdout")
        st.write(f"{metadata['selected']} · {metadata['design']} split")
        left, right = st.columns(2)
        left.metric("F1", f"{report['f1']:.3f}")
        right.metric("Average precision", f"{report['average_precision']:.3f}")
    st.warning(
        "A high score indicates similarity to historical linked observations. "
        "Future recall and actual hazard require separate evidence."
    )

elif page == "Dataset explorer":
    if data is None:
        st.stop()
    filters, results = st.columns([1, 3])
    with filters:
        categories = st.multiselect("Category", sorted(set(data.category) - {""}))
        maker = st.text_input("Manufacturer contains")
        labels = st.multiselect("Historical linkage label", [0, 1], default=[0, 1])
    view = data.loc[data[TARGET].isin(labels)]
    if categories:
        view = view.loc[view.category.isin(categories)]
    if maker:
        view = view.loc[view.manufacturer.str.contains(maker, case=False, regex=False)]
    with results:
        st.subheader(f"{len(view):,} matching reports")
        st.bar_chart(aggregate(view, "categories").head(12), x="category", y="reports")
        st.bar_chart(
            aggregate(view, "manufacturers").head(12), x="manufacturer", y="reports"
        )
        st.line_chart(aggregate(view, "trends"), x="month", y="reports")
        st.bar_chart(view[TARGET].value_counts())
        columns = [
            "report_date",
            "category",
            "manufacturer",
            "product",
            "description",
            TARGET,
        ]
        st.dataframe(view[columns], hide_index=True, width="stretch")
        st.download_button(
            "Download filtered reports",
            view[columns].map(spreadsheet_safe).to_csv(index=False),
            "recallguard.csv",
            "text/csv",
        )

elif page == "Record linkage":
    st.info("Synthetic example. The product and recall identifiers are fictional.")
    st.write(
        "DEMO-01 reports a Maple Trail lithium lantern. Two candidates share product terms. "
        "The solar lantern listing is rejected because its announcement precedes the report."
    )
    st.dataframe(candidate_demo(), hide_index=True, width="stretch")
    audit_path = Path(
        os.getenv("RECALLGUARD_CANDIDATES", ROOT / "data/processed/review_sample.csv")
    )
    if audit_path.is_file():
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
    st.subheader("About RecallGuard V2")
    st.write(
        "Review candidate links between incident reports and recalls, compare validation splits, "
        "and explore historical associations using local model artifacts and DuckDB aggregates."
    )
    st.write("Python · pandas · scikit-learn · XGBoost · DuckDB · Streamlit · FastAPI")
    st.markdown("[CPSC data sources](https://www.cpsc.gov/Data)")
    st.info(
        "Missed links, report availability, catalog coverage, and product identity ambiguity "
        "limit how far the results generalize."
    )

elif bundle is None and page != "Model performance":
    st.info(
        "Train a model with the CLI and set RECALLGUARD_MODEL to its trusted bundle before launching."
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

elif page == "Recall risk assessment":
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
    sources = (["Loaded model"] if bundle else []) + list(reports)
    if not sources:
        st.info("Train a model or add a V2 benchmark report to view performance.")
        st.stop()
    source = st.selectbox("Evaluation run", sources)
    metadata = (
        bundle["metadata"]
        if source == "Loaded model"
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
