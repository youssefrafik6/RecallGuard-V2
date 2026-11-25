# Architecture

Raw CPSC snapshots are normalized into incident and recall tables. Blocking indexes generate candidate pairs for lexical, identity and date scoring. The CLI writes local evidence and a review sample. Reviewer decisions append to SQLite with a snapshot fingerprint and remain separate from model inputs.

The offline training path ingests a separately supplied historical labeled CSV. It fits a feature allowlist on training rows, selects models and thresholds through validation, and uses a separate split for calibration. The model bundle persists preprocessing, calibration, label definitions, evaluation and package versions. The CLI, FastAPI and Streamlit share validation and inference.

DuckDB queries normalized local frames through packaged SQL. API analytics are aggregates. The local data explorer and review interface show source records from the operator's data.

See [evaluation](MODEL_EVALUATION.md), [data pipeline](DATA_PIPELINE.md), and [deployment](DEPLOYMENT.md).
