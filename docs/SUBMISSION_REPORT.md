# Submission report: policy-aware direct snapshot reader

Team: Namit Gawade, Ishaan Singh, Rajdeep Kundu. DBMS semester project.

## Implemented contribution

A restricted Python reader decodes PostgreSQL native binary COPY exports and enforces row policies extracted from the PostgreSQL catalog. It is compared with a PostgreSQL SELECT executed under the same role. The implementation includes a Streamlit demonstration, controlled synthetic data, complete-row correctness checks, repeated timings, CSV output and raw timing samples.

The implementation uses frozen exports, not live heap pages. There are no joins, writes through the reader, transaction recovery or authentication. Security equivalence is evaluated only for the supported expression grammar.

## Experimental setup

- Measurement completed at 2026-10-07T06:43:35.273280+00:00 (UTC; submission date in India: 7 October 2026).
- Execution environment: Windows 11, Python 3.14.3.
- Three dataset sizes: 1,000, 10,000 and 100,000 rows; three roles; three salary thresholds.
- Original ten demonstration rows are preserved. Generated salaries span 30,000â€“120,000; generated department and salary columns each include a deterministic 5% NULL proportion.
- Threshold 0 applies department filtering only. Other thresholds add a salary comparison.
- Two warm-up runs and five measured runs per path and case; sample standard deviation is reported.
- Data export, policy extraction and PostgreSQL baseline use the same transaction. Locks prevent writes and policy changes during each experiment.
- The complete suite rolls back temporary data/policy changes. The permanent demonstration dataset remains at 10,000 rows.
- Raw samples and policy ASTs: `docs/evidence/benchmark_samples.json`. Summary: `docs/evidence/benchmark_results.csv`.

## Actual results

Full-row soundness and completeness passed in **27/27 cases**. The direct reader had lower average latency in **0/27 cases**. A ratio greater than 1 would favor the reader; less than 1 favors PostgreSQL.

| Rows | Role | Min. salary | Visible | PostgreSQL ms (mean Â± SD) | Reader ms (mean Â± SD) | Ratio | Match |
|---|---|---|---|---|---|---|---|
| 1,000 | it_user | 0 | 318 | 0.563 Â± 0.065 | 1.675 Â± 0.008 | 0.336 | True |
| 1,000 | hr_user | 0 | 316 | 0.445 Â± 0.018 | 1.687 Â± 0.019 | 0.264 | True |
| 1,000 | finance_user | 0 | 317 | 0.468 Â± 0.040 | 1.697 Â± 0.028 | 0.276 | True |
| 1,000 | it_user | 70,000 | 166 | 0.416 Â± 0.037 | 1.964 Â± 0.042 | 0.212 | True |
| 1,000 | hr_user | 70,000 | 166 | 0.395 Â± 0.019 | 3.527 Â± 0.896 | 0.112 | True |
| 1,000 | finance_user | 70,000 | 168 | 0.438 Â± 0.030 | 1.972 Â± 0.025 | 0.222 | True |
| 1,000 | it_user | 100,000 | 65 | 0.341 Â± 0.068 | 1.941 Â± 0.029 | 0.175 | True |
| 1,000 | hr_user | 100,000 | 69 | 0.296 Â± 0.039 | 2.007 Â± 0.087 | 0.148 | True |
| 1,000 | finance_user | 100,000 | 64 | 0.294 Â± 0.032 | 1.946 Â± 0.016 | 0.151 | True |
| 10,000 | it_user | 0 | 3168 | 3.812 Â± 1.317 | 17.407 Â± 0.681 | 0.219 | True |
| 10,000 | hr_user | 0 | 3166 | 2.952 Â± 0.088 | 17.344 Â± 0.101 | 0.170 | True |
| 10,000 | finance_user | 0 | 3167 | 2.789 Â± 0.079 | 17.345 Â± 0.236 | 0.161 | True |
| 10,000 | it_user | 70,000 | 1667 | 2.089 Â± 0.221 | 20.221 Â± 1.282 | 0.103 | True |
| 10,000 | hr_user | 70,000 | 1665 | 1.808 Â± 0.160 | 21.161 Â± 2.823 | 0.085 | True |
| 10,000 | finance_user | 70,000 | 1667 | 1.830 Â± 0.112 | 19.899 Â± 0.443 | 0.092 | True |
| 10,000 | it_user | 100,000 | 666 | 1.156 Â± 0.108 | 19.979 Â± 0.245 | 0.058 | True |
| 10,000 | hr_user | 100,000 | 668 | 1.173 Â± 0.035 | 19.422 Â± 0.059 | 0.060 | True |
| 10,000 | finance_user | 100,000 | 664 | 1.153 Â± 0.046 | 19.858 Â± 0.561 | 0.058 | True |
| 100,000 | it_user | 0 | 31668 | 42.454 Â± 17.914 | 173.751 Â± 3.118 | 0.244 | True |
| 100,000 | hr_user | 0 | 31666 | 52.162 Â± 26.646 | 175.741 Â± 5.520 | 0.297 | True |
| 100,000 | finance_user | 0 | 31667 | 66.341 Â± 14.309 | 173.958 Â± 2.425 | 0.381 | True |
| 100,000 | it_user | 70,000 | 16667 | 48.386 Â± 16.665 | 198.427 Â± 2.181 | 0.244 | True |
| 100,000 | hr_user | 70,000 | 16663 | 42.002 Â± 13.436 | 201.640 Â± 8.572 | 0.208 | True |
| 100,000 | finance_user | 70,000 | 16669 | 39.708 Â± 14.459 | 199.639 Â± 2.182 | 0.199 | True |
| 100,000 | it_user | 100,000 | 6666 | 22.923 Â± 17.635 | 199.760 Â± 2.342 | 0.115 | True |
| 100,000 | hr_user | 100,000 | 6665 | 19.906 Â± 12.525 | 198.210 Â± 3.762 | 0.100 | True |
| 100,000 | finance_user | 100,000 | 6666 | 19.968 Â± 12.873 | 198.284 Â± 1.497 | 0.101 | True |

## Interpretation

These measurements do not support a speed advantage for this Python implementation on this local workload. The prototype demonstrates policy-aware filtering and correctness for the tested cases. Sequential Python decoding and per-row predicate evaluation add work; PostgreSQL is a mature optimized engine. An increasingly selective policy still requires the reader to scan the entire file.

These observations identify future optimization work rather than justify an acceleration claim. No experimental values are fabricated or copied from the proposal.

## Validation

Validation completed: **47 tests passed** with PostgreSQL configured; **38 passed and 9 skipped** with credentials absent.

The project regression suite includes full-row changes and duplicate detection; SQL operator precedence, parentheses and escaped strings; rejection of unsupported expressions; validation of all AST branches; NULL filtering; PUBLIC/inherited/permissive/restrictive policies; SELECT command filtering; default deny; fresh export after a salary change; and real comparisons for all roles. PostgreSQL modifications made by regression tests are rolled back.

Streamlit was exercised with its AppTest harness for initial rendering, full comparison and role switching. Tests can be reproduced with `run.cmd test` and experiments with `run.cmd suite`.

## Limits of the evidence

- Timings exclude connection establishment, role switching, export, policy extraction and correctness comparison. Policy-resolution latency is recorded separately.
- PostgreSQL trials run first and Python trials second, after warm-ups. Caches are warm and trial order is not randomized.
- PostgreSQL performs ORDER BY id; the reader receives data ordered during export, outside its timed region.
- Only one machine, one schema and a small grammar are tested. These results cannot establish general DBMS security equivalence or performance.
- Integer comparisons and text equality are supported. Arbitrary SQL, session functions, LIKE, NOT, IS NULL, text ranges and nondeterministic text collations are rejected.
- The role selector assumes a trusted demonstrator; filesystem access to the unfiltered snapshot is outside the protection provided by the policy evaluator.
- Very large results are materialized in memory. The UI previews 500 rows but validates the complete result.

## Run and demonstrate

From the project folder, run `run.cmd`. The launcher reads local `.env` settings and uses `.venv`. Open Compare results, choose a role and click Run comparison. Dataset controls and the submission suite are available below the results. See the root README for first-time setup and all one-command actions.

The original `PaperA_Draft.docx` remains the proposal draft. This report supplies measured implementation/results content; the draft's planned acceleration is a hypothesis, not the experimental conclusion.
