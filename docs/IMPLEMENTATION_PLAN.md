# Implementation Plan

## Milestone 0 - End-to-end prototype

Goal: prove the full architecture with a tiny dataset.

Required result:

```text
PostgreSQL result == Direct Reader result
```

and the demo should show both paths.

## Milestone 1 - Database side

Create a single table in PostgreSQL, load sample data, create two or more roles, and enable RLS.

Start with simple policies such as:

```sql
USING (department = 'IT')
```

and

```sql
USING (department = 'HR')
```

Verify directly in PostgreSQL that each role sees the expected rows.

## Milestone 2 - Snapshot export

Export the table using PostgreSQL binary COPY format into `data/`.

The generated snapshot should normally remain untracked by Git if it is treated as a build artifact.

## Milestone 3 - Python direct reader

Implement a reader that:

1. opens the binary snapshot
2. decodes records using the known schema
3. evaluates a supported policy predicate
4. returns only authorized rows
5. logs ALLOWED / DENIED decisions in debug/demo mode

Start with one simple equality policy before implementing AND/OR and ranges.

## Milestone 4 - Policy extraction

Connect Python to PostgreSQL and retrieve policy definitions from `pg_policy` using `pg_get_expr(polqual, polrelid)`.

Translate only the explicitly supported expression subset into the internal policy representation.

Unsupported constructs must fail safely.

## Milestone 5 - Correctness oracle

Run the same logical request through PostgreSQL and the direct reader. Compare result sets using stable row identifiers.

Report:

- soundness
- completeness
- exact result-set match

Include NULL test cases.

## Milestone 6 - Benchmark

Run repeated timing trials for both paths. Record average and standard deviation.

Keep the data state fixed during each comparison.

## Milestone 7 - Visual demo

Build a small Streamlit app that lets the teacher:

- choose a role
- run the logical query
- view PostgreSQL output
- view direct-reader output
- view row filtering decisions
- see correctness status
- see latency results

## Team collaboration rule

Work in parallel by module. Avoid multiple people editing the same file at the same time.

Every branch should:

1. pull/rebase from the shared default branch before starting a substantial change
2. make a focused commit
3. push the branch
4. open a pull request
5. get another teammate to review before merging when practical

Do not commit passwords, local database credentials, `.env` files, virtual environments, generated snapshots, or large result artifacts unless explicitly agreed.
