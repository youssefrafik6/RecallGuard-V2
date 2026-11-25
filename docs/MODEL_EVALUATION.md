# V2 model evaluation

## Protocol

The historical sample contains 3,780 reports and 420 proxy positives. V2 compares three designs using seed 42 and uses the same report-date boundaries for the MiniLM probe and chronological full experiment. For grouped and chronological splits, connected components join normalized product/manufacturer identities, eligible model/GTIN identities and historical recall campaign IDs. The chronological evaluation removes earlier rows that share a group with any later partition. Random rows give a permissive comparison.

The training code fits Word and character TF-IDF, separate fielded text, categorical encodings and text length from training only. The feature allowlist excludes dates, recall IDs, label confidence, and match rules. Candidate configurations cover class weighting, regularization, training-only random oversampling, NB smoothing and XGBoost positive weights. Validation average precision selects a variant per model family and the winning non-dummy family. An independent calibration partition fits a sigmoid on that variant's raw score. A negative calibration slope yields a constant calibration model. The high-priority threshold maximizes proxy F1 on validation. Test metrics are computed after these choices are frozen. Test figures are descriptive for one split and were drawn from the same historical sample previously studied.

The experiment JSON tracks input hash, package versions, training time, configuration, fit and validation inference timings, classification and calibration metrics, top-K, confusion matrices, curves and slices. Joblib bundles remain local. See [V1 experiment provenance](V1_TO_V2_COMPARISON.md#historical-metric-provenance) for the earlier F1 figures.

## Held-out results

The table reports each validation-selected non-dummy model.

| Test design | Selected model | Precision | Recall | F1 | Average precision | ROC AUC | Brier |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Random rows | Logistic regression | 0.592 | 0.536 | 0.562 | 0.551 | 0.845 | 0.068 |
| Campaign-aware product groups | Linear SVM | 0.115 | 0.361 | 0.174 | 0.123 | 0.553 | 0.097 |
| Chronological with campaign purging | Linear SVM | 0.121 | 0.082 | 0.098 | 0.111 | 0.418 | 0.116 |

The chronological AP of 0.111 fell below the test positive rate of 0.128. The fixed threshold returned eight of 97 positives and produced 58 false positives. The top 25 returned two positives (precision 0.08, recall 0.021). Its confusion matrix was `[[601, 58], [89, 8]]` with rows as actual classes and columns as predictions. Chronological F1 exceeded the earlier report's 0.019 under a different grouping and search protocol, so the difference does not establish superior deployment performance. The group-aware result was also lower than the earlier product-proxy split.

[Random report](../results/metrics/v2-random.json) · [Grouped report](../results/metrics/v2-group.json) · [Chronological report](../results/metrics/v2-chronological.json) · [Temporal shift audit](../results/metrics/v2-temporal-audit.json)

## Shift and label quality

The campaign-purged temporal run excludes 476 rows and has no observed campaign overlap between the test set and earlier folds. Training contains 23 positives across 1,269 reports. The test period contains 97 positives across 756 reports. Some covariates shift too. Test text includes 6.4% unseen token occurrences and 424 nonblank manufacturer rows unseen in training. Median publication delay in the test period was 20 days. Text mentioning recalls remains a potential leakage channel because historical narratives can be edited. These observations help explain why calibration and threshold choice may transfer poorly. They do not identify a single cause.

Review-derived labels are not used automatically. A prospective follow-up should separate availability from report time, fix an outcome maturity window, adjudicate positives and plausible negatives, and use an unseen forecast period.

## Reproduction

For the benchmark environment use Python 3.13 and install with the observed numerical package constraints.

```bash
python -m pip install -c constraints-research.txt -r requirements-dev.txt -e .
recallguard train --design all --feature-set compare --group-campaigns --out results/runs
recallguard audit-temporal --group-campaigns
python -m pip install -c constraints-research.txt -r requirements-nlp.txt
python scripts/benchmark_embeddings.py --representation word --out results/local/nlp-word.json
python scripts/benchmark_embeddings.py --representation minilm --out results/local/nlp-minilm.json
```

MiniLM is a frozen 384-dimensional English encoder run via ONNX on CPU. Only the classifier is fitted to the V2 data. TF-IDF's vocabulary is fitted on training. The experiment compares the same logistic grid and calibration protocol using each text representation. MiniLM downloads weights into the ignored model cache and embeds narratives locally. The inference timing is average batch latency per test row and includes text features and scoring. Peak RSS is a single-process high-water mark, including package and encoder overhead. Resource measurements are hardware-dependent. The embedding probe is separate from the production artifact path. [FastEmbed supported models](https://qdrant.github.io/fastembed/examples/Supported_Models/)

## MiniLM versus word TF-IDF

Both runs evaluated the same held-out dates and used the same 756 reports with 97 proxy positives. The benchmark used the Apple Silicon CPU with two ONNX Runtime threads.

| Representation | Precision | Recall | F1 | AP | Brier | Development time | Test ms/row | Peak RSS | Encoder + compressed classifier |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Word TF-IDF | 0.200 | 0.216 | 0.208 | 0.168 | 0.113 | 0.57 s | 0.19 | 249 MB | 0.15 MB |
| Frozen MiniLM | 0.157 | 0.454 | 0.233 | 0.141 | 0.115 | 458 s | 125 | 830 MB | 90.39 MB |

MiniLM recalled 44 positives with 237 false positives. TF-IDF recalled 21 with 84 false positives. MiniLM had higher F1 at the validation-selected threshold, while TF-IDF ranked better by AP, used less memory, and ran much faster. The sparse classifier benchmark's winner was chosen independently across representations and families by validation AP. The embedding probe is exploratory on the same historical sample, and will need independent confirmation. Development time includes training and development-set transforms and excludes encoder initialization.

[Word TF-IDF report](../results/metrics/v2-nlp-word.json) · [MiniLM report](../results/metrics/v2-nlp-minilm.json)
