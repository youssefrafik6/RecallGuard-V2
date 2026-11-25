# Local deployment

Run from the repository root with Python 3.11 or 3.13. On macOS, XGBoost may require `brew install libomp`.

```bash
python -m pip install -r requirements-dev.txt -e .
export RECALLGUARD_DATA=data/training_data.csv
export RECALLGUARD_MODEL=results/runs/chronological.joblib
uvicorn recallguard.api:app --host 127.0.0.1
# In a second shell
streamlit run dashboard/app.py --server.address 127.0.0.1
```

Set those paths only when the files are available. Missing prerequisites return HTTP 503 on dependent endpoints. Invalid inference bodies return HTTP 422.

| Endpoint | Response |
| --- | --- |
| `GET /health` | Service status and model availability |
| `GET /model-info` | Selected model, split, fields and interpretation limit |
| `POST /predict` | Review score, band and available model contributions |
| `POST /batch-predict` | Ordered predictions for an `incidents` array of 1–100 records |
| `GET /analytics/summary` | Counts, labels and missing values |
| `GET /analytics/categories` | Category counts and rank |
| `GET /docs` | OpenAPI interface |

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/predict -H 'Content-Type: application/json' \
  -d '{"product":"Electric kettle","description":"The base overheated.","category":"Kitchen"}'
```

## Container

Run `docker compose up --build`. Both service ports bind to loopback. Compose mounts the workspace read-only. Set paths such as `RECALLGUARD_DATA=/workspace/data/training_data.csv`. Reviewer decisions use a dedicated volume. In native runs, use `RECALLGUARD_REVIEWS` to override the local SQLite path.

Train a compatible bundle in the same dependency environment that serves it.

```bash
docker build -t recallguard-v2:local .
mkdir -p results/runs
docker run --rm --user "$(id -u):$(id -g)" \
  -v "$PWD/data:/data:ro" -v "$PWD/results/runs:/runs" \
  recallguard-v2:local recallguard train --data /data/training_data.csv \
  --design chronological --group-campaigns --out /runs
```

The serving UID needs read access to the trusted bundle. Joblib uses executable deserialization. Load bundles only from a trusted operator's training run. External hosting would require authentication, request limits, review roles and a data redistribution review.
