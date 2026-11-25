# RecallGuard V2 resume and interview materials

## Two-line summary

Built a local machine learning research platform for linking consumer product incidents to official recalls and ranking historical recall associations.
Added campaign-purged evaluation, evidence-backed review, versioned inference, a FastAPI service and a Streamlit dashboard.

## Technical resume bullets

- Built identifier-aware entity resolution using exact model and GTIN evidence, bounded candidate generation, date constraints, trigram similarity and TF-IDF, with an independent SQLite review ledger.
- Compared five NLP classifiers across random, grouped and campaign-purged temporal designs. Separate model selection, calibration and testing exposed generalization loss masked by random splits.
- Shipped shared, validated single and batch inference through FastAPI and an eight-page Streamlit dashboard, with DuckDB analytics, reproducible model artifacts, Docker and pytest coverage.

**Technologies** · Python, pandas, NumPy, scikit-learn, XGBoost, Pydantic, RapidFuzz, DuckDB, SQLite, FastAPI, Streamlit, FastEmbed, ONNX Runtime, pytest and Docker.

## Verified quantitative results

Evaluated 3,780 historical observations including 420 proxy positives. The validation-selected family scored F1 0.562 on random rows, 0.174 on campaign-aware grouped rows and 0.098 on the campaign-purged chronological holdout. Temporal AP was 0.111 against a positive-rate baseline of 0.128. See [evaluation](MODEL_EVALUATION.md).

## 30-second explanation

Consumer complaints and government recalls do not share a common product key. I built a candidate linker that shows why records might match and lets reviewers save their judgments independently. I then tested supervised models on historical proxy labels under progressively harder splits and surfaced the results through an API and dashboard. The real contribution is knowing where the model fails and what additional data would support an early-warning claim.

## Two-minute explanation

The linking pipeline normalizes names, dates and manufacturers, blocks on rare terms and known product identifiers, then scores only candidate pairs. It uses date gates and checksum-valid identifiers to preserve interpretable evidence. A separate human-review ledger keeps decisions apart from projected labels. The training side uses a strict feature allowlist and fits text, category and numeric preprocessing only on training rows. Model variants and operating thresholds are selected on validation. A later partition calibrates the selected classifiers before fixed holdout evaluation. Temporal splits purge observable product and recall campaign overlaps. The deployment uses shared Pydantic validation and inference for batch and single requests, plus DuckDB-powered analytics and a local review UI.

## Interview questions

1. Why use blocking, and what happens if the true pair is absent from the shortlist?
2. How do strong GTIN and model signals differ from verified ground truth?
3. What is the purpose of separating validation, calibration and test partitions?
4. What changes between random and campaign-purged temporal splits?
5. How would you test genuine prospective recall prediction?
6. How are model artifacts versioned, and which paths can load them?
7. Why keep adjudication decisions separate from predicted labels?
8. What did MiniLM improve or trade off compared with word TF-IDF?

## Verified linkage result

Processed 65,058 incidents and 9,623 cleaned recalls through 1.14 million blocked candidate pairs. Recovered 204 of 207 date-eligible historical reference pairs, including 158 at rank one. These figures measure agreement with an earlier positive-only match audit. [Linkage replay](DATA_PIPELINE.md#verified-v2-replay)
