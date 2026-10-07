"""Create a reviewable submission report from measured benchmark results."""
import csv
import json
import platform
from pathlib import Path
import sys
from config import PROJECT_ROOT


def write_report():
    csv_path = PROJECT_ROOT / 'results' / 'benchmark_results.csv'
    if not csv_path.exists():
        raise RuntimeError('Run the submission suite before writing a report.')
    with csv_path.open(encoding='utf-8') as file:
        rows = list(csv.DictReader(file))
    metadata = json.loads((PROJECT_ROOT / 'results' / 'benchmark_samples.json').read_text())
    successes = sum(row['results_match'] == 'True' for row in rows)
    table = '\n'.join(
        f"| {int(r['dataset_size']):,} | {r['role']} | {int(r['minimum_salary']):,} | {r['visible_rows']} | "
        f"{float(r['postgres_avg_ms']):.3f} ± {float(r['postgres_stddev_ms']):.3f} | "
        f"{float(r['reader_avg_ms']):.3f} ± {float(r['reader_stddev_ms']):.3f} | "
        f"{float(r['speedup']):.3f} | {r['results_match']} |" for r in rows)
    faster = sum(float(r['speedup']) > 1 for r in rows)
    report = f'''# Submission report: policy-aware direct snapshot reader

Team: Namit Gawade, Ishaan Singh, Rajdeep Kundu. DBMS semester project.

## Implemented contribution

A restricted Python reader decodes PostgreSQL native binary COPY exports and enforces row policies extracted from the PostgreSQL catalog. It is compared with a PostgreSQL SELECT executed under the same role. The implementation includes a Streamlit demonstration, controlled synthetic data, complete-row correctness checks, repeated timings, CSV output and raw timing samples.

The implementation uses frozen exports, not live heap pages. There are no joins, writes through the reader, transaction recovery or authentication. Security equivalence is evaluated only for the supported expression grammar.

## Experimental setup

- Measurement completed at {metadata['measured_at_utc']} (UTC; submission date in India: 7 October 2026).
- Execution environment: {platform.system()} {platform.release()}, Python {platform.python_version()}.
- Three dataset sizes: 1,000, 10,000 and 100,000 rows; three roles; three salary thresholds.
- Original ten demonstration rows are preserved. Generated salaries span 30,000–120,000; generated department and salary columns each include a deterministic 5% NULL proportion.
- Threshold 0 applies department filtering only. Other thresholds add a salary comparison.
- Two warm-up runs and five measured runs per path and case; sample standard deviation is reported.
- Data export, policy extraction and PostgreSQL baseline use the same transaction. Locks prevent writes and policy changes during each experiment.
- The complete suite rolls back temporary data/policy changes. The permanent demonstration dataset remains at 10,000 rows.
- Raw samples and policy ASTs: `docs/evidence/benchmark_samples.json`. Summary: `docs/evidence/benchmark_results.csv`.

## Actual results

Full-row soundness and completeness passed in **{successes}/{len(rows)} cases**. The direct reader had lower average latency in **{faster}/{len(rows)} cases**. A ratio greater than 1 would favor the reader; less than 1 favors PostgreSQL.

| Rows | Role | Min. salary | Visible | PostgreSQL ms (mean ± SD) | Reader ms (mean ± SD) | Ratio | Match |
|---|---|---|---|---|---|---|---|
{table}

## Interpretation

These measurements do not support a speed advantage for this Python implementation on this local workload. The prototype demonstrates policy-aware filtering and correctness for the tested cases. Sequential Python decoding and per-row predicate evaluation add work; PostgreSQL is a mature optimized engine. An increasingly selective policy still requires the reader to scan the entire file.

These observations identify future optimization work rather than justify an acceleration claim. No experimental values are fabricated or copied from the proposal.

## Validation

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

From the project folder, run `run.cmd`. The launcher reads local `.env` settings and uses `.venv`. Open Compare results, choose a role and click Run comparison. Separate tabs contain dataset controls and batch benchmarks. See the root README for first-time setup and all one-command actions.

The original `PaperA_Draft.docx` remains the proposal draft. This report supplies measured implementation/results content; the draft's planned acceleration is a hypothesis, not the experimental conclusion.
'''
    path = PROJECT_ROOT / 'docs' / 'SUBMISSION_REPORT.md'
    path.write_text(report, encoding='utf-8')
    return path
