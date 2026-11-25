# RecallGuard V2 implementation summary

## Implemented and verified

- V1 audit, historical result provenance and preservation of upstream MIT attribution.
- CPSC export normalization, schema and date checks, candidate generation, identifier-aware scoring, ranking and local review storage.
- Five-family sparse ML comparison with validation-only selection, independent calibration and held-out evaluation. Separate optional CPU-only MiniLM probe uses an equivalent temporal protocol.
- Versioned local inference, single and batch APIs, analytics, a Streamlit dashboard, test coverage, Docker image and Compose configuration.
- DuckDB queries for incident summary, category rank, temporal trends, manufacturers and review-sample confidence distributions.

The architecture and endpoints are documented in [architecture](ARCHITECTURE.md) and [deployment](DEPLOYMENT.md). For experiment results and interpretation, see [evaluation](MODEL_EVALUATION.md).

## Implemented but not verified

- GitHub Actions has a Python 3.11/3.13 matrix. Hosted execution requires a push after publication approval.
- The project uses single-operator local review. Multi-user review and production-scale throughput have no verification.

## Not implemented

- Prospective early-warning validation, a new external gold-standard dataset and automatic incorporation of human review decisions into training.
- Managed model registry or hosted service. The project uses filesystem artifacts and structured versioned JSON in place of MLflow.
- Transformer fine-tuning and production embedding-backed serving. MiniLM is a standalone experiment.
- Severity aggregates because the supported normalized inputs lack a validated field.

## Verification

- Data validation and full linkage completed on local CPSC exports. V2 surfaced 204 of 207 eligible historical reference pairs, with 158 ranked first. See [full replay](DATA_PIPELINE.md#verified-v2-replay).
- Historical sample training completed for random, campaign-aware grouped and campaign-purged chronological evaluation. Chronological holdout F1 was 0.098 and AP was 0.111 against prevalence 0.128.
- Local FastAPI calls returned successful health, model information, prediction, ordered batch, aggregate summaries, category results and OpenAPI responses using a saved research model. Tests cover malformed inputs and missing prerequisites.
- Streamlit pages and individual scoring were checked using AppTest. A review submission created a separate and correctly keyed SQLite decision. Chrome rendered overview and performance pages using a saved model.
- Docker built locally, Compose validated, both server health checks returned HTTP 200 in an isolated container, and the installed wheel exposed its packaged DuckDB SQL. The image smoke used no external dataset.
- The tracked candidate release contains code, documentation, screenshots of aggregate views and aggregate results. Local CPSC snapshots, research exports, review records and model weights remain excluded. Historical MIT attribution was preserved.

- The CPU embedding benchmark completed. MiniLM had F1 0.233 and AP 0.141, while word TF-IDF had F1 0.208 and AP 0.168. Both used the same campaign-purged holdout. [NLP results and resource comparison](MODEL_EVALUATION.md#minilm-versus-word-tf-idf)

## Publication

The release branch is prepared locally. The separate GitHub repository is intended to remain private and empty pending explicit approval to upload and publish the code. The original repository is the read-only research reference.

Public release is gated on approval. Any future raw or derived dataset distribution requires its own rights and privacy review. No such payload is included in the release branch.
