# Local deployment

Run from the repository root with Python 3.11 or 3.13. On macOS, XGBoost may require `brew install libomp`.

```bash
python -m pip install -r requirements-dev.txt -e .
uvicorn recallguard.api:app --host 127.0.0.1
# In a second shell
streamlit run dashboard/app.py --server.address 127.0.0.1
```

Set `RECALLGUARD_SUMMARY` to a completed raw snapshot summary to replace the bundled dashboard data. The default demo uses aggregate data and fictional examples. `RECALLGUARD_CANDIDATES` enables record-level review on a private, loopback deployment. Set `RECALLGUARD_DATA` and `RECALLGUARD_MODEL` only for local historical API and scoring comparisons. Missing prerequisites return HTTP 503 on dependent endpoints. Invalid inference bodies return HTTP 422.

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

## Streamlit Community Cloud

The public entry point is `dashboard/public.py`. It uses the tracked aggregate snapshot and archived model metrics. The public path ignores local workspace, model, data, candidate and SQLite overrides. It has no upload or review form. Use `dashboard/app.py` for trusted private local analysis.

1. Open [Streamlit Community Cloud](https://share.streamlit.io/) and connect the GitHub account with access to the repository.
2. Choose **Create app**, then **Deploy from repo**. Use repository `youssefrafik6/RecallGuard-V2`, branch `main` after the portfolio pull request is merged, and file `dashboard/public.py`. To preview the unmerged changes, select `codex/portfolio-demo-validation` instead.
3. In **Advanced settings**, select **Python 3.13** or **Python 3.14**. Leave Secrets empty. Community Cloud loads the pinned `dashboard/requirements.txt` adjacent to the entry point.
4. Deploy. Verify the overview metrics, adjust the date window in **Record linkage**, and confirm **Model performance** shows historical benchmarks. Open the assigned URL in a signed-out browser before sharing it. If needed, set visibility to public under the app's Sharing settings. Keep the preview branch available until a permanent app is deployed from `main`.

[Deploy an app](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy) · [App dependencies](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies) · [Sharing](https://docs.streamlit.io/deploy/streamlit-community-cloud/share-your-app)

Run the same read-only entry locally without any raw downloads.

```bash
python -m pip install -r dashboard/requirements.txt
streamlit run dashboard/public.py --server.address 127.0.0.1
```
