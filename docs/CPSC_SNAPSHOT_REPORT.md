# CPSC snapshot report · November 26, 2026

I downloaded and validated the official SaferProducts incident archive and the complete CPSC recall listing. This run used the existing ranker, a 365-day report-date linkage window, and the input hashes and settings in the [aggregate run manifest](../results/metrics/cpsc-raw-2026-11-26.json). See the [reproduction instructions](DATA_PIPELINE.md).

## Input accounting

| Count | Incident reports | Recall listings |
| --- | ---: | ---: |
| Parsed | 70,000 | 10,141 |
| Missing primary identifier | 0 | 3 |
| Duplicate rows collapsed | 0 | 7 |
| Conflicting rows excluded | 0 | 33 |
| Retained | 70,000 | 10,098 |
| Retained with missing product name | 0 | 529 |
| Retained with missing manufacturer | 0 | 7,131 |

The excluded recall conflicts span 16 recall numbers. Report dates run from March 11, 2011 through November 8, 2026. Report publication dates run from July 26, 2011 through November 25, 2026. Retained recall dates run from June 7, 1973 through November 12, 2026. The retained rows had no missing or unparseable values in these date fields.

## Linkage and label coverage

| Measure | Count |
| --- | ---: |
| Candidate pairs scored | 1,231,033 |
| Reports with at least one candidate | 69,882 |
| Reports without a candidate | 118 |
| High-confidence pairs | 170 |
| Review-tier pairs | 250 |
| Rejected pairs | 1,230,613 |
| Reports with competing high candidates | 1 |
| Reports with a single high candidate and a heuristic positive | 168 |
| Reports left unlabeled | 69,832 |
| Independently verified positive or negative outcomes | 0 |

Of the high-confidence pairs, 159 qualified through a model code plus brand or manufacturer agreement, seven through exact checksum-valid GTIN, and four through product similarity with brand or manufacturer agreement. Among the 168 heuristic positives, 31 recall announcements occurred on or before public release of the corresponding incident report. The 137 later announcements describe timing among selected heuristic links.

### Historical candidate replay

An earlier algorithm generated the 416 positive-only reference pairs in the local capstone match audit. The reference SHA-256 is `ff832a34d97c9ced2968d195d57230ec53fa293b5bdfad880a8684a704f5d754`. The replay recovered 387 of 416 reference pairs overall. Of the 207 reference pairs eligible by the recorded dates, 201 appeared in the candidate audit, 158 ranked first, and 180 ranked in the top three. Among the 201 surfaced eligible pairs, 115 received high confidence, 18 received review status, and 68 were rejected. The archived V2 run surfaced 204 of the 207 eligible pairs. The snapshot and text processing differ across runs.

```bash
recallguard check-linkage --candidates data/cpsc-local/candidates.csv \
  --reference /path/to/historical-matches_audit.csv --horizon 365
```

These figures measure agreement with earlier algorithmic candidates. Linkage precision, recall, and false-link rates remain unknown. The candidate shortlist, excluded catalog conflicts, sparse manufacturer data, missing or noisy identifiers, and unrelated identifiers in recall descriptions can all affect coverage. A mostly rejected candidate set says little about report-level outcome prevalence.

## Supervised evaluation decision

The snapshot contains zero verified positives and zero verified negatives. Supervised training and evaluation were skipped. The historical model benchmarks remain available for comparison under their original sampled proxy-label definitions. This run provides no estimate of prospective performance.

An evaluation of future recall outcomes would need independently adjudicated labels, a defined observation horizon with complete follow-up, and inputs available as of the scoring date. Training and model selection would need earlier publication cohorts with mature outcomes, with a later independent test period and product and recall-campaign groups held apart. Pair rejections and missing links cannot establish report-level negatives.
