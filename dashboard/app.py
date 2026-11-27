"""RecallGuard local research dashboard."""

import hashlib
import json
import os
from io import BytesIO, StringIO
from pathlib import Path
from sqlite3 import Error as SQLiteError

import pandas as pd
import streamlit as st

from recallguard.demo import (
    FIELDS,
    MAX_BYTES,
    OVERVIEW,
    SCENARIOS,
    batch_results,
    demo_csv,
    match_demo,
    parse_upload,
)
from recallguard.raw import SCHEMA_VERSION

public_demo = globals().get("PUBLIC_DEMO", False)
ROOT = Path(__file__).resolve().parents[1]
if not public_demo:
    ROOT = Path(os.getenv("RECALLGUARD_WORKSPACE", ROOT))
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
    from recallguard.review import ReviewDecision, record_review

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
    sample = next(iter(SCENARIOS.values()))
    return match_demo([dict(zip(FIELDS, sample))], horizon_days)


path = "" if public_demo else os.getenv("RECALLGUARD_MODEL", "")
modified = Path(path).stat().st_mtime_ns if path and Path(path).is_file() else 0
bundle = model(path, modified) if path else None
st.sidebar.title("RecallGuard V2")
st.sidebar.caption("CPSC incident research")
page = st.sidebar.radio(
    "Views",
    [
        "Overview",
        "Interactive product matching"
        if public_demo
        else "Historical association scoring",
        "Batch analysis",
        "Dataset explorer",
        "Record linkage",
        "Model performance",
        "Explainability",
        "About",
    ],
)
st.sidebar.caption(
    "Public demo · read-only"
    if public_demo
    else "Historical model loaded"
    if bundle
    else "Local mode · no model configured"
)
st.title(page if page != "Overview" else "Consumer product recall analysis")
st.caption(
    "Record linkage and retrospective analysis of U.S. consumer product safety reports."
)

if page in {"Overview", "Dataset explorer"}:
    configured = None if public_demo else os.getenv("RECALLGUARD_SUMMARY")
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
    st.write(
        "RecallGuard connects CPSC incident reports with candidate recall listings. "
        "Explore the evidence behind each candidate and see how historical models were evaluated."
    )
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
    if public_demo:
        st.subheader("Try the fictional catalog")
        st.write(
            "Start with Interactive product matching, run three cases in Batch analysis, "
            "or inspect the evidence behind a rank in Explainability."
        )
    st.subheader("From source files to review")
    st.graphviz_chart("""
        digraph {
            graph [rankdir=LR, bgcolor="transparent"]
            node [shape=box, style="rounded,filled", color="#6c9c97", fillcolor="#edf7f5"]
            "Official CPSC exports" -> "Normalize and block" -> "Rank and preserve evidence" -> "Independent review"
        }
    """)
    st.info(
        "Independently verified outcomes: zero. "
        "Historical model evaluation uses a separate sample with linkage labels."
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
    example = candidate_demo(horizon)
    columns = ["rank", "recall_id", "days_to_recall", "confidence", "score", "reason"]
    st.dataframe(example[columns], hide_index=True, width="stretch")
    with st.expander("Matching evidence"):
        st.write(
            "The lexical score combines product tokens, name similarity, manufacturer, and brand evidence."
        )
        st.dataframe(example.drop(columns=columns), hide_index=True, width="stretch")
    review_sample_path = None if public_demo else os.getenv("RECALLGUARD_CANDIDATES")
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

elif public_demo and page == "Interactive product matching":
    st.info("Fictional recall catalog. Enter fictional product details only.")
    scenario = st.selectbox("Start with an example", list(SCENARIOS))
    product, day, maker, brand, model_code, gtin = SCENARIOS[scenario]
    with st.form(f"public-match-{scenario}"):
        name_column, date_column = st.columns([2, 1])
        product = name_column.text_input("Product name", value=product, max_chars=120)
        day = date_column.text_input(
            "Report date (YYYY-MM-DD)", value=day, max_chars=10
        )
        left, right = st.columns(2)
        maker = left.text_input("Manufacturer", value=maker, max_chars=120)
        brand = right.text_input("Brand", value=brand, max_chars=120)
        model_code = left.text_input("Model code", value=model_code, max_chars=120)
        gtin = right.text_input("GTIN / UPC", value=gtin, max_chars=120)
        horizon = st.slider("Eligibility window after report (days)", 1, 365, 365)
        submitted = st.form_submit_button("Find candidates", type="primary")
    if submitted:
        row = dict(
            product=product,
            report_date=day,
            manufacturer=maker,
            brand=brand,
            model=model_code,
            upc=gtin,
        )
        try:
            audit = match_demo([row], horizon)
        except ValueError as exc:
            st.error(str(exc))
        else:
            if audit.empty:
                st.info(
                    "No candidate passed the blocking step in the fictional catalog."
                )
            else:
                st.dataframe(audit[OVERVIEW[1:]], hide_index=True)
    st.caption(
        "Scores measure lexical similarity. Identifier and date rules also affect rank."
    )

elif public_demo and page == "Batch analysis":
    st.info(
        "Fictional recall catalog. Use fictional rows only. Uploads are processed in session memory."
    )
    st.download_button(
        "Download example CSV",
        demo_csv(),
        "fictional-incidents.csv",
        "text/csv",
        on_click="ignore",
    )
    source = st.radio(
        "Input source",
        ["Three fictional reports", "Upload fictional CSV"],
        horizontal=True,
    )
    if source == "Three fictional reports":
        st.dataframe(
            pd.read_csv(StringIO(demo_csv()), dtype=str).fillna(""), hide_index=True
        )
    upload = (
        st.file_uploader("Fictional incident CSV", type=["csv"], max_upload_size=1)
        if source == "Upload fictional CSV"
        else None
    )
    st.caption(
        "Maximum 64 KiB and 50 rows. Required columns are product and report_date (YYYY-MM-DD). Optional columns are manufacturer, brand, model, and upc."
    )
    horizon = st.slider("Eligibility window after report (days)", 1, 365, 365)
    if st.button("Match reports", type="primary"):
        try:
            if source == "Three fictional reports":
                payload = demo_csv().encode()
            else:
                if upload is None:
                    raise ValueError("Choose a fictional CSV first.")
                if upload.size > MAX_BYTES:
                    raise ValueError("The CSV exceeds 64 KiB.")
                payload = upload.getvalue()
            results = batch_results(parse_upload(payload), horizon)
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.dataframe(results, hide_index=True)
            st.download_button(
                "Download linkage results",
                results.to_csv(index=False),
                "fictional-linkage-results.csv",
                "text/csv",
                on_click="ignore",
            )
    st.caption(
        "Report IDs follow input row order. Results contain catalog values and linkage evidence, with uploaded text excluded."
    )

elif public_demo and page == "Explainability":
    st.info("Fictional examples scored by the same linker used in the CPSC pipeline.")
    scenario = st.selectbox("Fictional report", list(SCENARIOS))
    horizon = st.slider("Eligibility window after report (days)", 1, 365, 365)
    audit = match_demo([dict(zip(FIELDS, SCENARIOS[scenario]))], horizon)
    st.write(f"Report product: **{SCENARIOS[scenario][0]}**")
    st.markdown(
        f"**Date eligibility:** the recall must occur 1–{horizon} days after the report. "
        "Within that window, an exact checksum-valid GTIN can yield High confidence. "
        "An exact model code requires brand or manufacturer corroboration for High. "
        "Name-based matches require shared product tokens."
    )
    st.caption(
        "Ranking sorts by confidence tier, exact GTIN, exact model code, lexical score, "
        "document similarity, then recall ID."
    )
    if audit.empty:
        st.info(
            "No candidate passed blocking, so there is no pair-level evidence or ranking."
        )
    else:
        labels = audit.set_index("recall_id")["recall_product"]
        candidate = st.selectbox(
            "Candidate to inspect",
            list(labels.index),
            format_func=lambda key: f"{key} · {labels[key]}",
        )
        pair = audit.set_index("recall_id").loc[candidate]
        eligible = 0 < pair.days_to_recall <= horizon
        left, middle, right = st.columns(3)
        left.metric("Rank", int(pair["rank"]))
        middle.metric("Confidence tier", pair.confidence.title())
        right.metric("Lexical score", f"{pair.score:.3f}")
        st.write(f"**Rule result:** {pair.reason}")
        st.caption(
            f"Recall date offset: {pair.days_to_recall:+d} days · Date eligible: {'yes' if eligible else 'no'}"
        )
        weighted = [
            ("Product token overlap", "token_overlap", 0.50),
            ("Name similarity", "name_similarity", 0.30),
            ("Exact manufacturer", "manufacturer_exact", 0.15),
            ("Brand in recall text", "brand_in_recall", 0.05),
        ]
        st.dataframe(
            pd.DataFrame(
                [
                    (label, float(pair[field]), weight, float(pair[field]) * weight)
                    for label, field, weight in weighted
                ],
                columns=["Lexical feature", "Value", "Weight", "Weighted value"],
            ),
            hide_index=True,
        )
        st.dataframe(
            pd.DataFrame(
                [
                    ("Exact GTIN", "Yes" if pair.gtin_exact else "No"),
                    ("Exact model", "Yes" if pair.model_exact else "No"),
                    ("Blocking votes", str(pair.block_votes)),
                    (
                        "Document similarity (tie-breaker)",
                        f"{pair.document_tfidf_cosine:.3f}",
                    ),
                    ("Edit similarity (diagnostic)", f"{pair.edit_similarity:.3f}"),
                    (
                        "Trigram overlap (diagnostic)",
                        f"{pair.char_trigram_jaccard:.3f}",
                    ),
                ],
                columns=["Additional evidence", "Value"],
            ),
            hide_index=True,
        )
        st.caption(
            "Weights describe the linkage formula. The lexical score is a similarity measure."
        )

elif bundle is None and page != "Model performance":
    st.info(
        "This view requires a trusted historical model in a local deployment. "
        "The Model performance page shows recorded benchmarks without a model file."
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
