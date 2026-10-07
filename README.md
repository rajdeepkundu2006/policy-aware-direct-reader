# Policy-Aware Direct Snapshot Reader

Python and PostgreSQL prototype for comparing row-level security with local filtering of a frozen binary COPY snapshot.

## Run

Requires Python 3.10+ and a running PostgreSQL instance.

```powershell
.\run.cmd
```

On first launch, the script creates `.venv` and installs dependencies. It creates `.env` from `.env.example` when missing. Enter the local PostgreSQL settings in `.env`, then launch again. Credentials and generated files are ignored by Git.

```dotenv
PGHOST=localhost
PGPORT=5432
PGDATABASE=direct_reader_db
PGUSER=postgres
PGPASSWORD=your_local_password
```

The setup account needs permission to create the database and roles, export all rows and switch to the restricted roles. Existing environment variables override `.env`.

For macOS/Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python manage.py app
```

## Application

- **Comparison:** PostgreSQL executes a SELECT under IT, HR or Finance role. Python scans a fresh binary export and applies the extracted policy. The interface displays both result tables, full-row correctness and repeated timing statistics.
- **Dataset:** Configure synthetic row count, NULL percentage and a department/salary access rule. Original rows are preserved; previously generated rows are replaced.
- **Benchmarks:** Measure three roles, three dataset sizes and three salary thresholds. Data and policy changes are rolled back. CSV summaries and raw samples are written to the ignored `results/` directory.

## Commands

```powershell
.\run.cmd test
.\run.cmd benchmark
.\run.cmd suite
.\run.cmd data --rows 100000 --null-percent 5
.\run.cmd setup
```

`setup` creates the database if missing, applies the schema and resets the three named policies to department-only filtering. `data` runs setup before generating rows. Regular app startup preserves existing policies. Regression tests use rolled-back PostgreSQL transactions.

## Structure

| Path | Responsibility |
|---|---|
| `config.py`, `manage.py`, `run.cmd` | Local configuration and launch commands |
| `database/` | Schema, RLS policies, catalog extraction and synthetic datasets |
| `reader/` | Binary COPY decoding, policy validation and filtering |
| `benchmark/` | PostgreSQL baseline, correctness comparison and timing |
| `app/` | Streamlit interface |
| `tests/` | Unit, UI and PostgreSQL integration tests |

## Supported scope

One table, read-only queries and a frozen PostgreSQL binary COPY export. Policies support integer comparisons, text equality, constants, parentheses, AND and OR. SELECT/ALL policy composition includes PUBLIC and inherited role privileges, permissive OR and restrictive AND. Unsupported expressions are rejected before scanning.

Live comparisons use a repeatable-read transaction and table lock so the export, policies and baseline agree. Complete values and duplicate counts are compared; matching IDs alone are insufficient. The parser requires the four-column employees schema, UTF8 and deterministic text collations.

The role selector assumes a trusted local operator. Raw snapshot filesystem access, authentication, live heap pages, joins and arbitrary SQL policies are outside this prototype.

## Timing

Both paths include result collection. Connection setup, role switching, export, policy extraction and correctness checks are excluded from timed scans. Policy extraction is reported separately. PostgreSQL sorts by primary key; the export is ordered before timed reader scans. Warm-ups warm caches, and PostgreSQL trials precede reader trials. Performance depends on dataset size, policy and machine conditions.

## Tests

```bash
python -m pytest -q --basetemp .test-tmp
```

Database-dependent tests skip when credentials are absent. With credentials configured, connection failures are reported. GitHub Actions runs the tests without database credentials.
