# Data pipeline

Download public CSV exports via the [CPSC open data index](https://www.cpsc.gov/Data). Local data paths are configurable. Preserve the export dates and hashes for repeat experiments.

```bash
recallguard prepare --incidents data/raw/IncidentReports.csv \
  --recalls data/raw/recalls_recall_listing.csv --out data/processed
```

The reader recognizes the incident disclaimer preamble, retains only supported columns, preserves string identifiers, parses mixed date formats, and logs invalid dates. Exact duplicates collapse and conflicting IDs are excluded. The recall export supports `Recall Number`, `Date`, `Name of product`, `Recall Heading`, `Manufacturers`, and optional `Description`. Optional incident fields are filled consistently. Normalization applies Unicode NFKC, case folding, punctuation and placeholder handling, and common manufacturer suffix removal.

Each incident generates candidates through rare tokens and two identifier indexes. The model index extracts mixed letter–digit codes from recall product names, headings, and descriptions, then looks up the incident's structured model value. The UPC index checks GTIN checksums and normalizes equivalent zero-padding before lookup. Generic name blocks are capped at 75 recalls and use up to 18 ranked candidates. Eligible dates break ties within identifier tiers before token votes. All retained identifier candidates are scored even when the rank limit is reached, so competing direct matches remain visible. Candidate dates must be strictly after the report and within 365 days by default.

A date-eligible, checksum-valid exact GTIN or an exact model code with manufacturer or brand corroboration can qualify as high confidence. A model code without corroboration qualifies for review. Other pairs use the lexical score, combining product token Jaccard (0.50), string similarity (0.30), exact manufacturer (0.15), and brand tokens in the recall name or heading (0.05). Text-only matches require product token overlap. The default lexical high and review thresholds are 0.82 and 0.57. `--high`, `--review`, and `--horizon` configure the rules. The lexical score and identifier evidence are separate fields in the candidate export.

A unique high candidate produces a proxy positive. Competing high candidates and unresolved rows remain unlabeled. Identifier rules are heuristic because free text may mention unrelated products or numbers. A checksum checks syntax and cannot establish that a GTIN describes the recalled item. A late publication date can also eliminate any apparent lead time relative to public availability.

Outputs include `candidates.csv` with match evidence and rejection reasons, `observations.csv` with a nullable target, `review_sample.csv` with high-scoring examples per status, and `summary.json` with input hashes, configuration and counts. On the local exports, ingestion read 65,058 incidents and 9,666 recall listings. After ID validation, 9,623 recall rows remained. The run produced 1,144,551 candidate pairs, 148 high-confidence pairs, and 146 uniquely linked proxy positives. Two high-confidence pairs shared a report and remained unresolved. The reconstructed labels still require adjudication before supervised training. The earlier capstone files used different rules and a different sample. The CLI's supervised entry point uses the original CPSC-shaped pre-labeled CSV.

The SaferProducts terms allow copying and distribution of posted public information while excluding personally identifiable information. Public reports can contain narrative and contextual identifiers and carry accuracy limitations. Keep raw and derived exports local and review narrative exposure before any redistribution or public demo. The existing MIT license applies to project software. [SaferProducts Terms of Use](https://www.saferproducts.gov/Business/Acknowledge?source=signIn) · [CPSC Privacy and Security Notice](https://www.cpsc.gov/About-CPSC/Policies-Statements-and-Directives/Privacy-Policy)

## Historical reference replay

The earlier 416-pair match audit provides a positive-only regression check for candidate generation. To reproduce the comparison locally, point the CLI to the older audit export.

```bash
recallguard check-linkage --candidates data/processed/candidates.csv \
  --reference /path/to/matches_audit.csv --horizon 365
```

| Reference outcome | Text-only linker | Identifier-aware linker |
| --- | ---: | ---: |
| Candidate pairs recovered, all 416 historical pairs | 337 | 390 |
| Candidate pairs recovered, 207 date-eligible historical pairs | 170 | 204 |
| Date-eligible pairs given review status | 5 | 18 |
| Date-eligible pairs given high confidence | 1 | 115 |

The audit comes from an earlier algorithm and has no representative negatives. Agreement measures coverage of prior candidate links and cannot estimate true precision, recall, or prospective model performance. The strict report-date gate also excludes historical links whose announcement date was on the same day or more than 365 days later.

## V2 review signals and schema

V2 preserves existing date and identifier confidence rules and adds normalized edit similarity, product name trigram Jaccard and TF-IDF cosine over clipped product and narrative text. The vocabulary is fitted on the recall catalog. Document cosine breaks ties after existing rank criteria. The positive-only reference cannot estimate false-link frequency.

The dashboard displays a stratified candidate sample. SQLite `decisions` stores report and recall IDs, candidate snapshot SHA-256, decision, reviewer, optional note and UTC timestamp. Decisions append independently of generated labels. Training uses a separately supplied historical CSV.

DuckDB's `incidents` relation uses `report_date`, `category`, `manufacturer` and nullable binary `label_recalled`. Its `candidates` relation uses `report_id` and `confidence`. Dashboard confidence counts describe the review sample. CLI summaries cover the full run. The supported inputs lack a validated severity field.

## Verified V2 replay

V2 processed 65,058 cleaned incident reports and 9,623 cleaned recall records. It generated 1,144,551 candidate pairs against approximately 626 million possible Cartesian pairs. Among these candidates, 148 received high confidence and 207 received review status. High-confidence uniqueness yielded 146 proxy positives, with competing high candidates kept unresolved.

Of 416 prior reference pairs, 207 fell inside the date gate. V2 surfaced 204 of these 207 date-eligible pairs, including 158 at rank 1 and 180 in the top three. Three were absent from the shortlist. Of the surfaced eligible reference pairs, 115 received high confidence, 18 received review status and 71 were rejected by the confidence rules. The replay measures agreement with historical candidate references and therefore cannot estimate the rate of false matches or missed true matches. The input and reference hashes agree with the archived identifier-aware run.

[Aggregate V2 replay](../results/metrics/v2-linkage.json) · [Historical identifier-aware replay](../results/metrics/linkage_reference_benchmark.json)
