# Local model artifacts

The training CLI writes a versioned pipeline bundle and JSON metadata under
`results/runs/` by default. Use an explicit operator-controlled path with
`RECALLGUARD_MODEL`. Joblib bundles must come from a trusted local training run.
API requests and dashboard uploads accept incident data only.
