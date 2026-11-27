# Independent linkage validation

**Status: pending.** A 200-pair sample was generated from the November 26, 2026 snapshot. Zero independently reviewed decisions were available. The historical positive-only replay, the high-confidence tier, and the 168 heuristic positives provide separate evidence.

## Draw the sample

After running the [raw pipeline](DATA_PIPELINE.md), use these commands from the repository root.

```bash
recallguard sample-review --snapshot data/cpsc-local \
  --out review-work/nov-2026 --seed 42 --per-stratum 50
recallguard evaluate-review --sample review-work/nov-2026
```

| Stratum | Candidate pairs | Sampled |
| --- | ---: | ---: |
| High confidence | 170 | 50 |
| Review tier | 250 | 50 |
| Plausible rejected candidates | 1,373 | 50 |
| Random remainder | 1,229,240 | 50 |
| Total | 1,231,033 | 200 |

The sampler draws uniformly without replacement within each disjoint stratum. The plausible rejected stratum covers date-eligible rejected pairs with a lexical score of at least 0.35 or a matching model code or GTIN. The random remainder gives every other candidate pair a nonzero sampling probability. The manifest records stratum sizes, seed, date horizon and file hashes.

## Review independently

1. Assign the same `review_packet.csv` and a separate copy of `decisions_template.csv` to each of two reviewers. Keep the sampling design, linker confidence, and other reviewer's decisions private until both have submitted. The packet contains source IDs, product fields, dates, and component-level match evidence. Keep the packet, reviewer files, and source records local.
2. Use original CPSC records to compare the incident product against the recall's product and scope. Use `match` for adequate evidence that the product falls within the recall scope, `non_match` for adequate evidence that it does not, and `uncertain` when identity or scope cannot be established. Review product identity separately from the linker's date gate. Record one decision per pair and keep the packet hash.
3. Run the evaluation below. Review disagreements using their assigned pair IDs. Preserve the original decisions. Obtain additional independent evidence before resolving uncertain pairs. The CLI keeps estimates pending when any sampled pair lacks two agreeing, conclusive decisions.

```bash
recallguard evaluate-review --sample review-work/nov-2026 \
  --review review-work/nov-2026/reviewer-a.csv \
  --review review-work/nov-2026/reviewer-b.csv
```

The evaluation reports sample-level exact agreement, Cohen's kappa when defined, disagreements, and agreement by stratum. These describe the deliberately stratified sample. For completed binary review it estimates stratum match totals using the inverse inclusion probability and reports high-tier pair precision and conditional recall within the candidate frame. Simultaneous exact hypergeometric intervals for stratum totals are combined into conservative 95% bounds. No intervals are produced for undefined ratios. These intervals represent sampling uncertainty, conditional on the review decisions.

Candidate-frame recall estimates the share of reviewed-scope matches in the candidate frame that reach the high tier. It cannot measure matches missed during blocking, catalogs' missing products, or population-wide recall. The small sample in the large remainder may yield wide bounds. Independent pair decisions cannot establish report-level negative outcomes and are kept out of supervised training.

The dashboard's optional local reviewer queue remains a case-inspection tool with a separate SQLite ledger. Use the blinded packet and separate reviewer files for this evaluation.
