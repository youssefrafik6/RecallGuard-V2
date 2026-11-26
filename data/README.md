# Local data

Store the official CPSC downloads in `data/raw/`. Run `recallguard prepare-raw` into a new directory beneath `data/` for each snapshot. Keep record-level candidate and review outputs local. The Streamlit demo can use the aggregate `summary.json` from any completed snapshot.

`data/training_data.csv` remains an operator-supplied input for historical benchmark reproduction. See the [data pipeline](../docs/DATA_PIPELINE.md).
