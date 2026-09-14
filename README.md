# Policy-Aware Direct Snapshot Reader for Secure Read-Only Query Acceleration

Team: Namit Gawade, Ishaan Singh, Rajdeep Kundu  
Department of Computer Science and Engineering, Vellore Institute of Technology, Vellore, India

## Project idea

We are investigating whether a restricted direct reader can serve read-only queries from a frozen PostgreSQL binary snapshot while preserving row-level filtering equivalent to PostgreSQL Row-Level Security (RLS).

This is **not** a replacement for PostgreSQL and is **not** a live PostgreSQL heap-page parser in the first version. PostgreSQL remains the baseline database, the source of RLS policy definitions, and the correctness oracle. The Python reader operates on a frozen binary snapshot exported from PostgreSQL.

## Current first-version scope

- Read-only queries
- Single table
- Frozen PostgreSQL binary COPY snapshot
- Row-level filtering
- Policies derived from PostgreSQL `pg_policy`
- Supported policy subset: equality, simple ranges, AND/OR over fixed attributes
- Fail-safe behaviour for unsupported policy constructs
- Correctness comparison against PostgreSQL using soundness and completeness
- Latency benchmarking with average and standard deviation

## Explicitly out of scope for version 1

- Joins
- Transactions and concurrent writes
- Column masking
- Audit logging
- Arbitrary SQL policy AST parsing
- Session-context functions such as `current_user` / `current_setting`
- Live PostgreSQL heap-page parsing
- LLM-generated raw heap-page parsing

## Intended architecture

```text
                 +----------------------+
                 |      Streamlit UI    |
                 +----------+-----------+
                            |
                       role + query
                            |
              +-------------+-------------+
              |                           |
              v                           v
      +---------------+           +------------------+
      |   PostgreSQL  |           |  Direct Reader   |
      |    baseline   |           |     (Python)     |
      |               |           |                  |
      | RLS enforced  |           | frozen snapshot  |
      +-------+-------+           +--------+---------+
              |                            |
              v                            v
        DBMS result                 policy-filtered result
              |                            |
              +-------------+--------------+
                            v
                  +-------------------+
                  | Correctness Oracle|
                  | + Benchmark       |
                  +-------------------+
```

## Collaboration

Use GitHub as the shared source of truth. Work should be divided by module so teammates can work concurrently on separate branches. Merge small, focused changes instead of waiting for one person to finish the entire project.

Suggested branch names:

- `feature/database-rls`
- `feature/direct-reader`
- `feature/benchmark-ui`
- `docs/...`

Before coding, read `docs/PROJECT_CONTEXT.md` and `docs/IMPLEMENTATION_PLAN.md`.

## Important scientific rule

Performance is a hypothesis, not a guaranteed result. The project must report whatever the controlled experiments show, including cases where the direct reader is slower.
