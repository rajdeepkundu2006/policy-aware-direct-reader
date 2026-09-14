# Team AI Handoff

Use this file as the minimum context when asking another AI assistant about the implementation.

We are a 3-person DBMS/database systems course team building **Policy-Aware Direct Snapshot Reader for Secure Read-Only Query Acceleration**.

The project asks whether a read-only direct reader can preserve PostgreSQL row-level security while avoiding the normal SQL query-execution path for a restricted workload.

### Current version

- Language: Python
- Database: PostgreSQL
- UI: Streamlit
- Snapshot format: PostgreSQL native binary COPY
- Scope: single table, read-only, frozen snapshot
- Security: PostgreSQL RLS policies are the source of policy definitions; supported policy subset is intentionally small
- Baseline: normal PostgreSQL query under the same role/data state
- Correctness: compare result sets for soundness and completeness
- Performance: repeated wall-clock timings; average and standard deviation

### Important limitation

This first version does **not** parse live PostgreSQL heap pages. That is future work.

### Intended architecture

PostgreSQL baseline + Policy Store + Direct Snapshot Reader + Correctness Oracle/Benchmark Harness + small visual UI.

### Research discipline

Do not invent experimental speedups. Performance is a hypothesis. Do not claim arbitrary SQL/RLS policy support. Do not claim the project replaces PostgreSQL. Do not claim live storage-page access in version 1.

Read `docs/PROJECT_CONTEXT.md` for full context and `docs/IMPLEMENTATION_PLAN.md` for the current implementation sequence.
