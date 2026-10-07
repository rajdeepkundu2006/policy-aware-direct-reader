# Policy-Aware Direct Snapshot Reader

DBMS Theory Case Study by **Namit Gawade, Ishaan Singh and Rajdeep Kundu**, VIT Vellore.

A working Python prototype compares PostgreSQL Row-Level Security with local filtering of a frozen PostgreSQL binary COPY snapshot. All **27 measured research cases** returned matching complete rows. PostgreSQL was faster on the larger datasets in this suite; a separate ten-row experiment favored the reader. The project studies correctness and performance rather than claiming a universal speedup.

## For the evaluator

**[Read the one-page case study](output/pdf/DBMS_Case_Study.pdf)**. It includes the title, overview, problem, methodology, features, final outcome and measured evidence requested for the submission.

You do not need PostgreSQL to review the project:

| Review option | Requirements | What it does |
|---|---|---|
| Open `demo/index.html` after downloading the repository | Any browser | Displays actual saved results, policies and row previews. It does not execute either path. |
| Run `run.cmd demo` from the downloaded project folder | Python 3.10+ and internet for first-time package installation | Runs the **real Python reader** against the included 10,000-row synthetic binary snapshot and checks every result against a recorded PostgreSQL baseline. No PostgreSQL, password or `.env` is needed. |
| Run `run.cmd` | Python and local PostgreSQL | Runs fresh database comparisons, data generation and new timings. |

GitHub displays HTML as source: download/clone the repository, then open `demo/index.html` locally. On Windows, `run.cmd demo` creates the Python environment when needed and launches the offline app. Open the local URL it prints. Press Ctrl+C to stop it.

On macOS/Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python manage.py demo
```

Recorded PostgreSQL results and timings are explicitly labelled in both review modes. Offline replay does not perform a new PostgreSQL experiment or measure its current latency. The bundled data is the project's synthetic employee dataset, not private employee records.

## Submission evidence

- [One-page case study PDF](output/pdf/DBMS_Case_Study.pdf)
- [Complete measured report](docs/SUBMISSION_REPORT.md)
- [27-case CSV](docs/evidence/benchmark_results.csv) and [raw timing samples with policy ASTs](docs/evidence/benchmark_samples.json)
- [Captured test output](docs/evidence/test_results.txt): 47 tests passed with PostgreSQL configured
- [Performance explanation](docs/PERFORMANCE_EXPLANATION.md): the same reader wins at ten rows and loses on larger scans
- [Offline demo evidence](demo/evidence.json) and [real PostgreSQL binary export](demo/employees.bin)

No publication or acceptance is claimed. The outcome is the working prototype, controlled experiments and reproducible project demonstration. The older paper draft describes the proposal; the case study and measured report describe the completed work.

## Start the live project

Install PostgreSQL and Python 3.10+ first. Open a terminal in this folder and run:

```powershell
.\run.cmd
```

The launcher uses the single `.venv` and creates `.env` from `.env.example` if needed. Edit `.env` once with your own database settings, then run again. Use a local administrator account that can create the project database/roles, export all rows and switch to demo roles. Keep your password local. `.env` and virtual environments are ignored by Git.

```dotenv
PGHOST=localhost
PGPORT=5432
PGDATABASE=direct_reader_db
PGUSER=postgres
PGPASSWORD=your_local_password
```

Existing environment variables override `.env`. A quoted password can preserve leading/trailing whitespace. The file uses simple key/value settings, not shell syntax.

## Live demonstration workflow

1. **Compare results**: choose IT, HR or Finance on the left, then click **Run comparison**. Database counts, aligned result tables, complete-row correctness and measured latency appear. Snapshot export is automatic.
2. **Change dataset**: optionally select a row count, missing-value percentage and access rule. **Apply dataset and access rule** writes generated employees into PostgreSQL and updates the three demo policies. Return to Compare results to measure it.
3. **Batch benchmarks**: click **Run all 27 benchmark cases** for three sizes, three salary rules and three roles. Changes are temporary and rolled back. Sidebar timings apply only to single comparisons; the batch uses two warm-ups and five timed repetitions per case.

The current captured demonstration uses 10,000 rows: ten original sample employees and 9,990 generated employees. The generator preserves original rows and replaces only its own tracked rows. Dataset sizes up to 1,000,000 are available. If preserved rows exceed the requested size, the actual retained count is reported.

The comparison CSV contains summary timings, counts, policy and correctness, not employee data. The batch CSV contains 27 summaries. Files under `results/` are local generated outputs; the reviewed submission measurements are also retained under `docs/evidence/` for GitHub.

## One-command tools

```powershell
.\run.cmd demo
.\run.cmd test
.\run.cmd benchmark
.\run.cmd suite
.\run.cmd data --rows 100000 --null-percent 5
.\run.cmd setup
```

`setup` creates a missing database, applies the schema and resets the three named demo policies to department-only filtering. `data` performs setup before generating rows. Regular live app startup preserves existing policies. Regression tests modify PostgreSQL only inside transactions that are rolled back. Without credentials, 38 tests pass and nine database-dependent tests skip.

To refresh the teacher demo from an approved synthetic live dataset, run `.venv\Scripts\python.exe scripts/capture_demo.py`. To rebuild the PDF, install `requirements-docs.txt` and run `scripts/create_case_study.py`; document tools are separate from application dependencies.

## Implementation and guarantees within scope

```text
PostgreSQL employees and pg_policy
       |                   |
  binary COPY export   parsed policy tree
       |                   |
       +------ Python decoder and filter ------ authorized rows

PostgreSQL SELECT under SET ROLE --------------- reference rows
                         |
              full-row comparison and repeated timing
```

| Module | Responsibility |
|---|---|
| `config.py`, `manage.py`, `run.cmd` | Configuration and one-command launch/setup/testing |
| `database/*.sql`, `database/datasets.py` | Table, policies and deterministic synthetic data |
| `database/policy_ast.py` | Restricted grammar and applicable SELECT policy composition |
| `reader/` | Binary COPY decoding, complete AST validation and filtering |
| `benchmark/benchmark.py` | Consistent export/baseline, complete-row comparison, timings and outputs |
| `app/app.py`, `app/demo.py`, `demo/replay.py` | Live demonstration and PostgreSQL-free reader replay |
| `tests/` | Unit, UI, offline and real PostgreSQL regression tests |

Live comparisons export fresh ordered data, extract policies and run the baseline in one repeatable-read transaction with a table lock. Private temporary snapshots prevent concurrent session file races. Complete field values and duplicate counts are checked, rather than IDs alone.

Supported policies include integer comparisons, text equality, constants, parentheses, AND and OR. Applicable SELECT/ALL policies include PUBLIC and inherited role privileges; permissive policies combine with OR and restrictive policies with AND. Every AST branch is validated before scanning. Unsupported constructs fail closed. No applicable permissive policy means deny all. Demo roles must not own the table or bypass RLS. The reader requires the exact four-column schema, UTF8 and deterministic text collations.

## Limits and interpretation

This is a trusted local demonstration: the role selector is not authentication, and raw snapshot filesystem access is outside its protection. Live heap parsing, joins, writes through the reader, session-dependent predicates and arbitrary SQL policies are unsupported. The reader scans every row and materializes permitted results in memory.

Timings exclude connection setup, role switching, export, policy extraction and correctness comparison. Policy extraction is reported separately. PostgreSQL timings include execution, fetching and row materialization; Python timings include decoding, policy checks and result collection. PostgreSQL orders by primary key; the snapshot is ordered before timed reader scans. Trials use warm caches and fixed PostgreSQL-before-Python order. Results describe one local workload, not general performance or security equivalence.

Permissive/restrictive composition follows [PostgreSQL's policy rules](https://www.postgresql.org/docs/current/sql-createpolicy.html).
