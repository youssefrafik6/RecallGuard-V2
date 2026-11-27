# Architecture

Raw CPSC snapshots are normalized into incident and recall tables. Blocking indexes generate candidate pairs for lexical, identity and date scoring. The CLI writes local evidence, a review sample, normalized tables, and a separate aggregate summary. Reviewer decisions append to SQLite with a snapshot fingerprint and remain separate from model inputs.

The offline training path reproduces benchmarks from a separately supplied historical labeled CSV. The raw snapshot has no verified outcomes for supervised fitting. It fits a feature allowlist on training rows, selects models and thresholds through validation, and uses a separate split for calibration. The model bundle persists preprocessing, calibration, label definitions, evaluation and package versions. The CLI, FastAPI and Streamlit share validation and inference.

DuckDB queries normalized local frames through packaged SQL. API analytics are aggregates. The Streamlit overview and dataset explorer read only the aggregate snapshot. The linkage demo scores product fields from published reports against official recall notices. Private review is enabled explicitly with a local candidate sample.

See [evaluation](MODEL_EVALUATION.md), [data pipeline](DATA_PIPELINE.md), and [deployment](DEPLOYMENT.md).
