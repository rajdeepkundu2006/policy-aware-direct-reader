# INTERFACE_CONTRACT.md

## Policy-Aware Direct Snapshot Reader for Secure Read-Only Query Acceleration

This document is the **single implementation contract** for the first working prototype of the project.

All three team members, their code, and any AI assistants used to support development must treat this document as the source of truth for:
- the database schema,
- role and policy names,
- snapshot format,
- policy representation,
- module boundaries,
- function interfaces,
- input/output formats,
- error behavior,
- benchmark behavior,
- and integration rules.

The goal is to allow the three implementation tracks to proceed in parallel without inventing incompatible interfaces.

---

# 1. Project objective

The prototype investigates whether a direct reader can operate outside PostgreSQL's normal SQL query-execution path while still preserving row-level filtering for supported read-only queries.

The first implementation is deliberately narrow:

- PostgreSQL is the source database and correctness baseline.
- PostgreSQL Row-Level Security (RLS) policies are the source of authorization rules.
- A table is exported once into a frozen PostgreSQL binary COPY snapshot.
- The Python direct reader reads that snapshot without sending the user query through PostgreSQL's SQL execution engine.
- The direct reader applies the corresponding row-level policy itself.
- The benchmark compares PostgreSQL output with direct-reader output.
- Correctness is checked using soundness and completeness.
- Performance is measured using repeated wall-clock latency measurements.
- The prototype is not a live PostgreSQL heap-page reader yet.

The implementation must not claim that the first prototype parses PostgreSQL heap pages or replaces PostgreSQL.

---

# 2. Technology stack

Use the following stack unless the whole team explicitly agrees to a documented change.

## Required

- **Python 3.11+**
- **PostgreSQL 15+**
- **psycopg 3** for PostgreSQL access from Python
- **Streamlit** for the visual demonstration UI
- **pytest** for basic tests

## Standard Python dependencies

The root `requirements.txt` should contain:

```text
psycopg[binary]
streamlit
pandas
pytest
```

The project should remain small and dependency-light.

Do not introduce Django, Flask, SQLAlchemy, Spark, MongoDB, Redis, Docker, or an additional database for the first prototype.

---

# 3. Repository structure

The repository uses these top-level directories:

```text
policy-aware-direct-reader/
│
├── app/
│   └── app.py
│
├── benchmark/
│   └── benchmark.py
│
├── database/
│   ├── 01_schema.sql
│   ├── 02_rls_policies.sql
│   └── 03_policy_extraction.sql
│
├── reader/
│   ├── parser.py
│   ├── policy.py
│   └── snapshot_reader.py
│
├── tests/
│   └── test_smoke.py
│
├── data/
│   └── employees.bin
│
├── results/
│   └── benchmark_results.csv
│
└── docs/
    ├── PaperA_Draft.docx
    ├── PROJECT_CONTEXT.md
    ├── IMPLEMENTATION_PLAN.md
    ├── TEAM_AI_HANDOFF.md
    └── INTERFACE_CONTRACT.md
```

The exact filename of the exported snapshot may change during development, but the default integration filename is:

```text
data/employees.bin
```

The binary snapshot must not be committed to Git once it becomes large. Small demo snapshots may be kept locally. Large/generated data should be ignored through `.gitignore`.

---

# 4. Team ownership and branch contract

The repository has three working branches:

```text
database
reader
benchmark-ui
```

## `database` branch — Namit

Owns:

```text
database/
```

Responsibilities:
- PostgreSQL schema
- sample/synthetic data generation
- roles
- RLS policies
- policy extraction from `pg_policy`
- database setup documentation where needed

## `reader` branch — Ishaan

Owns:

```text
reader/
```

Responsibilities:
- binary snapshot parser
- decoded-row representation
- supported policy interpreter
- direct snapshot reader
- fail-safe behavior for unsupported policies

## `benchmark-ui` branch — Rajdeep

Owns:

```text
benchmark/
app/
```

Responsibilities:
- PostgreSQL baseline execution
- direct-reader invocation
- result comparison
- soundness/completeness checks
- timing
- repeated benchmark runs
- Streamlit demonstration

## Shared files

The team should minimize direct simultaneous edits to:

```text
README.md
requirements.txt
docs/*.md
tests/
```

Changes to shared contracts must be coordinated before merging.

---

# 5. Database schema

The first prototype uses **one table only**.

Use this exact schema:

```sql
CREATE TABLE employees (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    department TEXT NOT NULL,
    salary INTEGER NOT NULL
);
```

The four columns have these meanings:

| Column | Type | Meaning |
|---|---|---|
| `id` | INTEGER | Unique employee identifier |
| `name` | TEXT | Employee name |
| `department` | TEXT | Organizational department |
| `salary` | INTEGER | Integer salary value |

Do not add additional columns until the first end-to-end prototype works.

The initial reader and policy interpreter must assume this schema.

---

# 6. Required demonstration data

The first smoke-test dataset must contain at least these rows:

```text
id | name   | department | salary
---+--------+------------+-------
1  | Alice  | HR         | 50000
2  | Bob    | IT         | 70000
3  | Carol  | HR         | 55000
4  | David  | Finance    | 80000
5  | Eve    | IT         | 75000
6  | Frank  | Finance    | 72000
7  | Grace  | HR         | 62000
8  | Henry  | IT         | 68000
9  | Irene  | Finance    | 76000
10 | Jack   | IT         | 71000
```

This dataset exists so that the first implementation is easy to reason about visually.

Later benchmark datasets may scale to:

- 10,000 rows
- 100,000 rows
- 1,000,000 rows

The exact larger-data generator belongs to the database branch.

---

# 7. PostgreSQL roles

Create these PostgreSQL roles for the demonstration:

```text
it_user
hr_user
finance_user
```

Each role must represent a user with access to one department.

The intended visibility rules are:

```text
it_user       -> department = 'IT'
hr_user       -> department = 'HR'
finance_user  -> department = 'Finance'
```

These exact role names should be used by the benchmark and UI.

Do not use `current_user` inside the first policy implementation. The policy interpreter should receive the logical role explicitly as part of the application request.

---

# 8. PostgreSQL RLS configuration

Enable row-level security on `employees`.

The intended policy behavior is:

```text
IT role       sees only IT rows
HR role       sees only HR rows
Finance role  sees only Finance rows
```

The database implementation should define RLS policies that correspond to these rules.

The exact PostgreSQL SQL should live in:

```text
database/02_rls_policies.sql
```

The benchmark must treat PostgreSQL's result for a role as the baseline/oracle.

Do not treat a hand-written Python policy as the ground truth when PostgreSQL gives a real result.

---

# 9. Policy source of truth

The conceptual source of truth is PostgreSQL's RLS configuration.

The database branch must extract the policy definition from PostgreSQL's catalog using the `pg_policy` relation and `pg_get_expr`.

The extraction query should follow this pattern:

```sql
SELECT
    polname,
    polcmd,
    polroles,
    pg_get_expr(polqual, polrelid) AS using_expr
FROM pg_policy
WHERE polrelid = 'employees'::regclass;
```

The actual query may be extended with additional metadata if necessary, but the first implementation must obtain the policy expression from PostgreSQL rather than asking a developer to manually type the same rule into Python.

---

# 10. Supported policy grammar

The first prototype supports only a small, explicit subset of row-level policy expressions.

## Supported

### Equality

```text
department = 'IT'
```

```text
department = 'HR'
```

### Numeric range comparisons

```text
salary >= 70000
```

```text
salary < 80000
```

Supported comparison operators:

```text
=
<
<=
>
>=
```

### Boolean combinations

```text
department = 'IT' AND salary >= 70000
```

```text
department = 'IT' OR department = 'HR'
```

Nested combinations of the supported comparisons using:

```text
AND
OR
```

may be supported when the parser can represent them unambiguously.

## Not supported in Paper A

Do not attempt these in the first implementation:

```text
subqueries
functions
joins
arbitrary SQL expressions
session-context functions
current_user
current_setting
database writes
```

Also do not attempt to build a general SQL parser.

---

# 11. Fail-safe behavior

This is a security requirement.

If the direct reader encounters a policy it cannot confidently parse or evaluate, it must **not** ignore the policy.

The required behavior is:

```text
unsupported policy
       ↓
reader refuses to serve rows
       ↓
return empty result or explicit refusal
```

For the first prototype, use:

```python
PolicyParseError
```

internally and convert that into a safe failure at the application layer.

The reader must never silently behave as though no policy exists.

The following is forbidden:

```python
except Exception:
    return all_rows
```

The reader must never fall back to unfiltered output.

---

# 12. Internal policy representation

After extraction and parsing, policies must be converted to a small Python representation.

Use this canonical representation for a single comparison:

```python
{
    "type": "comparison",
    "column": "department",
    "operator": "=",
    "value": "IT"
}
```

For a numeric example:

```python
{
    "type": "comparison",
    "column": "salary",
    "operator": ">=",
    "value": 70000
}
```

For an AND expression:

```python
{
    "type": "logical",
    "operator": "AND",
    "left": {
        "type": "comparison",
        "column": "department",
        "operator": "=",
        "value": "IT"
    },
    "right": {
        "type": "comparison",
        "column": "salary",
        "operator": ">=",
        "value": 70000
    }
}
```

For OR, use:

```python
"operator": "OR"
```

This structure is the contract between policy extraction/parsing and the direct reader.

Do not invent a second incompatible policy format.

---

# 13. Row representation

Once a binary record is decoded, the reader must represent it as a Python dictionary with exactly these keys:

```python
{
    "id": 2,
    "name": "Bob",
    "department": "IT",
    "salary": 70000
}
```

The field names must match the database column names.

The direct reader returns a list:

```python
list[dict]
```

Example:

```python
[
    {
        "id": 2,
        "name": "Bob",
        "department": "IT",
        "salary": 70000
    },
    {
        "id": 5,
        "name": "Eve",
        "department": "IT",
        "salary": 75000
    }
]
```

---

# 14. NULL handling

The future synthetic datasets may include NULL values in policy-relevant fields.

The first prototype must not accidentally treat SQL NULL as an ordinary Python value that always behaves like a normal comparison.

When a policy comparison involves a NULL value, the implementation must reproduce the PostgreSQL baseline behavior for the supported policy grammar.

For example, conceptually:

```text
NULL = 'IT'
```

must not be treated as Python string equality.

The implementation should model SQL three-valued behavior sufficiently for the supported expressions.

Any correctness discrepancy involving NULL is a real bug and must be investigated.

---

# 15. Snapshot format

The reader must operate on a **frozen PostgreSQL native binary COPY snapshot**.

The intended export operation is conceptually:

```sql
COPY employees TO 'employees.bin' WITH (FORMAT binary);
```

The exact path should be adapted to the local PostgreSQL environment and filesystem permissions.

Do not change the project to CSV for the main implementation.

CSV may be used temporarily during debugging, but it is not the project snapshot format.

The first Paper A prototype is a snapshot reader, not a live heap-page reader.

---

# 16. Binary parser responsibilities

`reader/parser.py` is responsible only for:

1. Opening the binary snapshot.
2. Reading PostgreSQL binary COPY structure.
3. Decoding supported field types:
   - INTEGER
   - TEXT
4. Producing row dictionaries.
5. Handling the binary stream safely.
6. Detecting malformed/incompatible input.

It should not contain authorization logic.

The parser answers:

> “What row is represented by these bytes?”

It does not answer:

> “Is this row allowed?”

This separation is intentional.

---

# 17. Policy interpreter responsibilities

`reader/policy.py` is responsible for:

1. Representing the supported policy AST.
2. Evaluating a policy against one decoded row.
3. Handling equality/range comparisons.
4. Handling AND/OR.
5. Handling NULL semantics for supported comparisons.
6. Raising a controlled error for unsupported policy forms.

Example conceptual API:

```python
evaluate_policy(row, policy_ast) -> bool
```

The return value means:

```text
True  -> row is authorized
False -> row is not authorized
```

The policy interpreter must not read files and must not connect to PostgreSQL.

---

# 18. Direct reader responsibilities

`reader/snapshot_reader.py` is responsible for composing the parser and policy interpreter.

Canonical conceptual API:

```python
read_snapshot(
    snapshot_path: str,
    policy: dict
) -> list[dict]
```

The function must:

1. Open the snapshot.
2. Decode each row using the parser.
3. Evaluate the policy.
4. Return only authorized rows.

Conceptually:

```python
for row in parse_snapshot(snapshot_path):
    if evaluate_policy(row, policy):
        results.append(row)
```

Do not place PostgreSQL SQL execution inside this function.

The direct reader must not query PostgreSQL for each row.

Policy lookup may occur before the scan, but per-row authorization should be performed locally.

---

# 19. Role handling

The role is part of the application-level request.

Canonical conceptual request:

```python
{
    "role": "it_user",
    "table": "employees",
    "snapshot_path": "data/employees.bin"
}
```

The application/benchmark obtains the appropriate policy for that role and passes the parsed policy to the reader.

For the first version, the reader does not need to know how PostgreSQL sessions authenticate users.

This keeps the reader independent of PostgreSQL runtime session state.

---

# 20. Query scope

The first version supports one logical query form:

```sql
SELECT * FROM employees;
```

The research focus is not general SQL processing.

The role policy acts as the row-level filter.

Do not implement arbitrary WHERE clauses yet.

Optional later extension:

```sql
SELECT * FROM employees WHERE salary >= 70000;
```

but only after the core project works.

For the first end-to-end demonstration, all rows are scanned from the snapshot and authorization determines which rows are emitted.

---

# 21. PostgreSQL baseline interface

The benchmark/UI layer must execute the logical baseline query through PostgreSQL.

Canonical conceptual API:

```python
run_postgres_query(
    connection,
    role,
    query
) -> list[dict]
```

The returned rows must be normalized to the same dictionary representation used by the direct reader:

```python
{
    "id": ...,
    "name": ...,
    "department": ...,
    "salary": ...
}
```

This enables direct structural comparison rather than comparing formatted terminal strings.

---

# 22. Correctness comparison

The benchmark/UI layer must compare:

```text
PostgreSQL result
        VS
Direct reader result
```

after normalizing row order.

The comparison must not rely on the order in which rows happen to be returned.

Canonical approach:

```python
sorted(postgres_rows, key=lambda r: r["id"])
```

and:

```python
sorted(reader_rows, key=lambda r: r["id"])
```

Then compare the normalized lists.

The primary correctness result is:

```text
results_match = postgres_rows == reader_rows
```

for the supported query/policy cases.

---

# 23. Soundness

Define soundness as:

> No row returned by the direct reader is a row that PostgreSQL would deny for the same role and state.

Operationally:

```text
direct_reader_rows ⊆ postgres_rows
```

If a direct-reader row does not exist in the PostgreSQL baseline result, soundness fails.

The UI should explicitly report:

```text
Soundness: PASS
```

or:

```text
Soundness: FAIL
```

---

# 24. Completeness

Define completeness as:

> No row that PostgreSQL would permit for the same role and state is omitted by the direct reader.

Operationally:

```text
postgres_rows ⊆ direct_reader_rows
```

If PostgreSQL returns a row that the direct reader omits, completeness fails.

The UI should explicitly report:

```text
Completeness: PASS
```

or:

```text
Completeness: FAIL
```

---

# 25. Overall correctness

The direct reader passes the correctness test only when both hold:

```text
soundness = PASS
completeness = PASS
```

Equivalent condition:

```text
normalized_postgres_rows == normalized_reader_rows
```

The visual UI should show all three:

```text
Soundness:       PASS
Completeness:    PASS
Results match:   YES
```

---

# 26. Benchmark requirements

The benchmark must measure:

1. PostgreSQL query latency.
2. Direct-reader latency.
3. Average latency over repeated runs.
4. Standard deviation over repeated runs.

Use `time.perf_counter()` for Python-side timing.

Do not present one timing measurement as a final performance result.

Initial benchmark configuration:

```text
warm-up runs:    3
measured runs:  10
```

These values can later be increased for formal evaluation.

The benchmark should keep the environment constant as much as practical.

---

# 27. Policy resolution timing

Policy resolution and per-row evaluation are conceptually different costs.

For the first implementation:

- policy extraction/parsing may happen once before the benchmarked scan;
- row-policy evaluation occurs during the direct scan.

Where practical, record these separately:

```text
policy_resolution_ms
reader_scan_ms
total_reader_time_ms
```

This prevents policy catalog lookup from being confused with per-row security enforcement.

The final paper should report this distinction when data is available.

---

# 28. Performance comparison

For each benchmark case, collect at least:

```text
dataset_size
role
visible_row_count
postgres_avg_ms
postgres_stddev_ms
reader_avg_ms
reader_stddev_ms
speedup
soundness
completeness
results_match
```

Speedup should be calculated as:

```text
speedup = postgres_avg_ms / reader_avg_ms
```

Interpretation:

```text
speedup > 1   -> reader is faster
speedup = 1   -> approximately equal
speedup < 1   -> reader is slower
```

Do not manufacture or assume a positive speedup.

The research question is whether a measurable performance benefit survives after adding policy enforcement.

---

# 29. Benchmark output format

The preferred machine-readable output is:

```text
results/benchmark_results.csv
```

with columns:

```text
dataset_size
role
visible_rows
postgres_avg_ms
postgres_stddev_ms
reader_avg_ms
reader_stddev_ms
speedup
soundness
completeness
results_match
```

Example:

```text
dataset_size,role,visible_rows,postgres_avg_ms,postgres_stddev_ms,reader_avg_ms,reader_stddev_ms,speedup,soundness,completeness,results_match
10,it_user,4,2.31,0.12,1.85,0.09,1.2486,true,true,true
```

The exact measured numbers are examples only.

Never hard-code fake benchmark results into the application.

---

# 30. Streamlit UI contract

`app/app.py` is the visual demonstration layer.

The UI must allow the teacher to select:

```text
Role:
IT / HR / Finance
```

The UI must provide a button equivalent to:

```text
Run Comparison
```

After execution, display these sections:

## A. Request

```text
Role: it_user
Table: employees
Query: SELECT * FROM employees
```

## B. PostgreSQL result

Display the rows returned by the DBMS baseline.

## C. Direct reader result

Display the rows returned by the direct reader.

## D. Reader scan information

At minimum:

```text
Rows scanned
Rows returned
Rows denied
```

## E. Correctness

Display:

```text
Soundness: PASS/FAIL
Completeness: PASS/FAIL
Results Match: YES/NO
```

## F. Performance

Display:

```text
PostgreSQL average latency
Direct reader average latency
Standard deviation for each
Speedup
```

The UI should make the difference between the two execution paths visually obvious.

---

# 31. Demonstration flow

The first teacher demo should use a small dataset.

Example:

```text
Select role: IT

Run Comparison
```

Expected logical outcome:

```text
PostgreSQL:
Bob
Eve
Henry
Jack

Direct Reader:
Bob
Eve
Henry
Jack

Soundness: PASS
Completeness: PASS
Results Match: YES
```

Then demonstrate another role:

```text
Select role: HR
```

Expected rows:

```text
Alice
Carol
Grace
```

Then demonstrate Finance:

```text
David
Frank
Irene
```

This proves that the direct reader is applying different row-level policies rather than returning a single hard-coded subset.

---

# 32. Direct-reader demonstration logging

The UI or console should make the direct path understandable.

For a small demo, show a trace such as:

```text
Row 1: HR       -> DENIED
Row 2: IT       -> ALLOWED
Row 3: HR       -> DENIED
Row 4: Finance  -> DENIED
Row 5: IT       -> ALLOWED
```

For large benchmarks, do not render every row to the screen.

The logging exists mainly for teacher demonstration and debugging.

---

# 33. Snapshot consistency

The snapshot represents a frozen data state at time T.

The benchmark must compare PostgreSQL and the direct reader against the same logical data state.

Do not modify the source table between the export and the corresponding correctness comparison.

The first prototype is not responsible for live update synchronization.

---

# 34. Trust model

The first prototype assumes:

- the direct reader runs in a trusted process;
- end users cannot independently access the snapshot file;
- the snapshot file is not directly served to users;
- policy definitions obtained from PostgreSQL are trusted;
- filesystem-level attacks are outside the project scope.

Therefore:

```text
User
  ↓
Application
  ↓
Reader
  ↓
Snapshot
```

is the intended model.

This project is not claiming to defend against a user who can simply open `employees.bin` themselves.

---

# 35. What is explicitly out of scope

Do not add these before the Paper A prototype is stable:

```text
live PostgreSQL heap-page parsing
database writes
transactions
concurrent updates
joins
multiple tables
column masking
audit logging
arbitrary SQL AST evaluation
current_user
current_setting
LLM-generated heap-page parser
distributed execution
another DBMS
```

These are future research directions or later extensions.

---

# 36. Definition of "done" for the first prototype

The first prototype is considered end-to-end functional when all of the following are true:

### Database

- PostgreSQL `employees` table exists.
- Sample data exists.
- RLS is enabled.
- IT, HR, and Finance roles produce different authorized result sets.
- Policy definitions can be extracted from `pg_policy`.

### Snapshot

- `employees` can be exported in PostgreSQL binary COPY format.
- The resulting snapshot can be read independently by the Python reader.

### Reader

- Binary records decode correctly.
- Rows are represented as dictionaries with the agreed schema.
- A supported policy can be evaluated.
- Unauthorized rows are omitted.
- Unsupported policies fail safely.

### Correctness

- PostgreSQL and direct-reader outputs can be compared.
- Soundness can be computed.
- Completeness can be computed.
- Matching result sets produce PASS.

### Benchmark

- Both paths can be timed.
- Multiple runs are performed.
- Average and standard deviation are recorded.
- Speedup is calculated without assuming the outcome.

### UI

- Teacher can select a role.
- Teacher can run the comparison.
- Teacher can see PostgreSQL output.
- Teacher can see direct-reader output.
- Teacher can see correctness status.
- Teacher can see timing.

---

# 37. Integration rules

When merging branches:

## Rule 1

The agreed interfaces in this file take priority over local implementation preferences.

## Rule 2

Do not change the row dictionary schema casually.

Required keys:

```text
id
name
department
salary
```

## Rule 3

Do not change role names casually.

Required roles:

```text
it_user
hr_user
finance_user
```

## Rule 4

Do not introduce a second policy representation.

Use the policy AST structure defined in this file.

## Rule 5

Do not make the reader query PostgreSQL once per row.

The purpose of the direct reader is to operate on the snapshot locally.

## Rule 6

Do not bypass the policy when parsing fails.

Failure must be safe.

## Rule 7

Do not commit fake benchmark values.

All displayed performance numbers must come from actual executions.

## Rule 8

Do not claim live heap parsing until it is actually implemented and tested.

---

# 38. Temporary mocks are allowed during parallel development

Because the team works on three branches simultaneously, temporary mocks are allowed.

For example, Ishaan may initially test the reader with a small sample snapshot or controlled parser fixture.

Rajdeep may initially test the UI with mock result dictionaries.

Namit may initially provide a simple static policy fixture before the real PostgreSQL catalog extraction is integrated.

However:

**Mocks are development scaffolding only.**

The final end-to-end demonstration must use:

```text
real PostgreSQL
+
real PostgreSQL RLS
+
real PostgreSQL binary COPY snapshot
+
real Python direct reader
+
real comparison
+
real measured timings
```

---

# 39. Recommended implementation order within each branch

## Database branch

```text
1. Create schema.
2. Insert sample data.
3. Create roles.
4. Enable RLS.
5. Create policies.
6. Verify PostgreSQL output per role.
7. Extract pg_policy expressions.
8. Produce a stable parsed policy representation.
9. Test with the direct-reader contract.
```

## Reader branch

```text
1. Create row representation.
2. Build binary parser.
3. Decode the complete smoke-test snapshot.
4. Build policy AST evaluator.
5. Add equality support.
6. Add numeric comparisons.
7. Add AND/OR.
8. Add NULL-aware behavior.
9. Add fail-safe unsupported-policy handling.
10. Expose read_snapshot().
```

## Benchmark/UI branch

```text
1. Build normalized result comparison.
2. Implement soundness.
3. Implement completeness.
4. Implement PostgreSQL timing.
5. Implement reader timing.
6. Add repeated trials.
7. Write CSV output.
8. Build Streamlit page.
9. Connect real database path.
10. Connect real reader path.
11. Display comparison and performance.
```

---

# 40. AI-assistant instructions

Any AI assistant helping a team member with this project must:

1. Read this document before proposing architecture or code.
2. Treat the current project as a **Python + PostgreSQL** prototype.
3. Respect the frozen PostgreSQL binary snapshot limitation.
4. Respect the one-table `employees` schema.
5. Respect the exact role names.
6. Respect the supported policy grammar.
7. Keep parsing, policy evaluation, and benchmark/UI responsibilities separated.
8. Never silently broaden the scope to joins, live heap parsing, writes, or arbitrary SQL.
9. Never invent benchmark results.
10. Never claim an optimization is a measured improvement without measurements.
11. Never weaken the fail-safe policy behavior.
12. Prefer small, understandable code suitable for a student research prototype.
13. Explain why a proposed code change fits the architecture before introducing a major dependency or redesign.
14. When uncertain about an interface, consult this file rather than inventing a new interface.

---

# 41. Relationship to the paper

This contract implements the Paper A design described in the current draft:

```text
Policy Store
    ↓
Direct Storage Reader
    ↓
Correctness Oracle + Benchmark Harness
```

The paper's current scope is:

- read-only queries,
- one table,
- row filtering,
- frozen binary snapshot,
- policies derived from `pg_policy`.

The paper explicitly leaves live heap parsing, joins, masking, audit logging, arbitrary policy expressions, session-context functions, and LLM-generated parsing outside the first version.

The implementation must remain aligned with those boundaries.

---

# 42. Final architecture

The complete first prototype should eventually look like:

```text
                         ┌───────────────────────┐
                         │      Streamlit UI     │
                         │                       │
                         │ role + Run Comparison │
                         └───────────┬───────────┘
                                     │
                    ┌────────────────┴────────────────┐
                    │                                 │
                    ▼                                 ▼
          ┌──────────────────┐             ┌────────────────────┐
          │    PostgreSQL    │             │   Direct Reader    │
          │                  │             │                    │
          │ SQL execution    │             │ snapshot.bin       │
          │ RLS enforcement  │             │ binary parser      │
          │ storage access   │             │ policy interpreter │
          └────────┬─────────┘             └─────────┬──────────┘
                   │                                  │
                   │                                  │
                   └──────────────┬───────────────────┘
                                  ▼
                     ┌────────────────────────┐
                     │ Correctness Comparator │
                     │                        │
                     │ Soundness              │
                     │ Completeness           │
                     │ Result equality        │
                     └────────────┬───────────┘
                                  │
                                  ▼
                     ┌────────────────────────┐
                     │ Benchmark Harness      │
                     │                        │
                     │ Average latency         │
                     │ Standard deviation     │
                     │ Speedup                 │
                     └────────────────────────┘

PostgreSQL security metadata:
pg_policy
    ↓
Policy extraction
    ↓
Policy AST
    ↓
Direct Reader policy interpreter
```

The research comparison is therefore not:

```text
SELECT vs SELECT
```

It is:

```text
NORMAL DBMS EXECUTION PATH
        vs
DIRECT SNAPSHOT READER + LOCAL POLICY ENFORCEMENT
```

while requiring the two paths to produce equivalent authorized results for the supported cases.
