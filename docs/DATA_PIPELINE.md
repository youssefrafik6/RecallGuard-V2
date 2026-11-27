# Official CPSC data pipeline

Use the [SaferProducts incident archive](https://www.saferproducts.gov/SPDB.zip) and the [complete CPSC recall listing](https://www.cpsc.gov/s3fs-public/recall-data/recalls_recall_listing.csv). Both URLs serve rolling exports. Keep the downloaded bytes locally and compare their SHA-256 hashes to the run manifest when reproducing a particular snapshot. The recall CSV bundled inside the incident ZIP is outside this pipeline's inputs.

## Reproduce a snapshot

From the repository root, create and activate the environment from the README. The reported run used Python 3.13.2 and the core package versions in `constraints-research.txt`.

```bash
python -m pip install -c constraints-research.txt -r requirements-dev.txt -e .
mkdir -p data/raw
curl --fail --location --retry 3 https://www.saferproducts.gov/SPDB.zip \
  --output data/raw/SPDB.zip
curl --fail --location --retry 3 \
  https://www.cpsc.gov/s3fs-public/recall-data/recalls_recall_listing.csv \
  --output data/raw/recalls_recall_listing.csv
unzip -t data/raw/SPDB.zip
recallguard prepare-raw --incident-zip data/raw/SPDB.zip \
  --recalls data/raw/recalls_recall_listing.csv --out data/cpsc-local
RECALLGUARD_SUMMARY=data/cpsc-local/summary.json \
  streamlit run dashboard/app.py --server.address 127.0.0.1
```

Use a fresh output directory per run. The command validates the selected ZIP member while streaming it out, checks its size, validates required headers and CSV record widths, and publishes outputs together after a successful run. Input hashes, encodings, row accounting, dates, and linkage settings appear in `summary.json`. Keep the rolling exports under versioned local paths to preserve exact input bytes.

## Cleaning and exclusions

- The incident reader skips the CPSC disclaimer when present. It tries UTF-8 with optional BOM, then falls back to Windows-1252. The recall export uses UTF-8 with optional BOM.
- Outer whitespace is trimmed and identifiers stay strings, preserving punctuation and leading zeros. Exact duplicates across retained fields collapse. All conflicting rows for a repeated identifier are excluded from linkage pending review. Rows without a recall number remain outside the recall catalog, including standalone safety warnings. Missing and conflicting rows are counted in the manifest and remain in the raw downloads.
- Product and brand names receive HTML entity decoding, Unicode NFKC, case folding, punctuation normalization, and placeholder cleanup. Manufacturer keys also strip common legal suffixes. Missing manufacturer values remain missing. Recall manufacturers are taken from the `Manufacturers` field. The pipeline does not infer manufacturers from importers, distributors, or heading text.
- Incident model values retain token separators. The linker extracts mixed letter–digit codes and compacts punctuation for exact comparisons. Valid UPC/GTIN values are normalized to 14 digits. Serial numbers and submitter metadata are excluded.
- Report, publication, and recall dates are parsed as calendar dates. Missing or invalid dates are counted. Publication dates are retained for timing diagnostics. Incident narratives are excluded from the processing fields and outputs. Recall descriptions contribute identifier and ranking evidence.

## Match evidence and labels

The existing linker blocks by rare product and manufacturer tokens, mixed model codes, and checksum-valid GTINs. The usual shortlist includes up to 18 candidates. Identifier matches can extend that list. The default eligibility gate is 1 to 365 days after the report date. The command accepts `--horizon` for sensitivity analysis.

Date-eligible exact GTIN matches or exact model matches with brand or manufacturer corroboration can qualify as high confidence. Lexical matches use product token overlap, string similarity, manufacturer agreement, and brand agreement. The default high and review lexical thresholds are 0.82 and 0.57. The audit also records edit similarity, character trigram overlap, recall-document TF-IDF cosine, rejection reasons, and rank. Confidence tiers are rules, with no calibrated probability interpretation.

A single high candidate creates a heuristic positive. Several high candidates leave the report unlabeled. An absent candidate, rejected candidate, or manually rejected pair leaves the report outcome unresolved. Verified report-level labels require independent evidence, including sufficient catalog and follow-up coverage for any negative outcome. The official files supply no such labels. Reviewer decisions are appended to a separate SQLite ledger, keyed to the candidate sample SHA-256, and require further adjudication before they inform supervised labels.

| Output | Contents |
| --- | --- |
| `summary.json` | Shareable counts, yearly volume, diagnostics, evaluation status, and input provenance |
| `observations.csv` | Local normalized reports, `heuristic_label`, `heuristic_recall_id`, reserved nullable `verified_label`, and `label_status` |
| `recalls.csv` | Local normalized recall catalog |
| `candidates.csv` | Local ranked candidate pairs and evidence |
| `review_sample.csv` | Local high-scoring examples within each tier for inspection |

The bundled dashboard defaults to aggregate snapshot data and interactive matching against the official recall catalog. For private review on loopback, explicitly set `RECALLGUARD_CANDIDATES` to the generated sample. Keep the record-level artifacts and review ledger local. Raw exports and derived records can contain contextual identifiers. See the [SaferProducts terms](https://www.saferproducts.gov/Business/Acknowledge?source=signIn) and [CPSC privacy notice](https://www.cpsc.gov/About-CPSC/Policies-Statements-and-Directives/Privacy-Policy).

## Evaluation

See the [official-export run report](CPSC_SNAPSHOT_REPORT.md). The historical CSV, linkage audit, and model benchmarks are documented in the [historical model evaluation](MODEL_EVALUATION.md). Use the CLI's explicit `train --data data/training_data.csv` path for historical replication only.

## Archived export replay

An archived CPSC export run read 65,058 incidents and 9,666 recall listings, retained 9,623 recall IDs, and scored 1,144,551 candidate pairs. With model and UPC/GTIN evidence, 146 reports met the unique high-confidence rule. The older-audit recovery check found 204 of 207 date-eligible candidates. The text-only configuration surfaced 170 eligible pairs.
