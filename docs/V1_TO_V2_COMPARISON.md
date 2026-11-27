# RecallGuard V1 and V2

The Spring 2026 capstone by Youssef Rafik studied whether CPSC incident reports resemble reports associated with official recalls. This audit uses public V1 commit `b721216` and the original capstone baseline `ef0feb2`. V2 also reuses research code from the earlier benchmark at `c6f3760`.

| Component | V1 | V2 |
| --- | --- | --- |
| Dataset | CPSC-style CSV with 3,780 observations and 420 historical positives. Git did not contain complete raw lineage or the original recipe. | Explicit column validation, preamble parsing, date handling, duplicate detection, SHA-256 provenance and local-only research inputs. |
| Linkage | Match rules, confidence and recall indices are visible in the labeled CSV. | Reuses identifier-aware blocking and date gates. Adds ranked similarities, reviewer evidence and a separate decision ledger. |
| Modeling | Streamlit trains text and structured estimators at startup. The original methods include keyword features, SMOTE and a composite risk score. | Offline fit, validation-only selection, separate sigmoid calibration and holdout scoring. Uses a leakage-sensitive allowlist and versioned artifacts. |
| Generalization | Original random split. A later benchmark showed a temporal drop. | Random, grouped and temporal benchmarks with stricter campaign grouping. MiniLM and word TF-IDF share the same temporal split. |
| Serving | Single Streamlit monolith. | Eight dashboard pages, common inference, bounded batches, DuckDB aggregates, Docker and CI. |

## Historical metric provenance

The capstone reported Linear SVM F1 0.688 and category-specific F1 0.784. Exact historical split membership and environment are unavailable.

The later benchmark recorded held-out F1 0.562 random, 0.402 product-grouped, and 0.019 chronological with product-proxy purging. These figures come from the validation-selected families in [archived benchmark JSON](../results/metrics/historical_proxy_benchmark.json) at `c6f3760`. That study used seed 42 and recorded the dataset fingerprint. See [archived evaluation methodology](historical/PORTFOLIO_MODEL_EVALUATION.md). A later campaign-purged replay is [archived separately](../results/metrics/temporal_generalization_benchmark.json).

## Target and limitations

V2 classifies retrospective associations with proxy labels. The reuse of historical data and related splits limits claims about generalization. Grouping covers observable product and campaign proxies. Prospective evaluation requires publication-time data, matured outcomes, independent adjudication and a new frozen period.
