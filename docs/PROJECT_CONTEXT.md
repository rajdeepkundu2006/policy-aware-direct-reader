# Project Context for Team and AI Assistants

## 1. Current paper

Working title: **Policy-Aware Direct Snapshot Reader for Secure Read-Only Query Acceleration**

Authors: Namit Gawade, Ishaan Singh, Rajdeep Kundu

Affiliation: Department of Computer Science and Engineering, Vellore Institute of Technology, Vellore, India

## 2. Research question

Can a simplified direct-access path for read-only queries preserve row-level security while reducing some of the overhead of the normal DBMS query-execution path?

The project does **not** claim that row retrieval itself is novel. PostgreSQL already retrieves rows. The difference being investigated is the execution path and the location of the security check.

Normal path:

```text
SQL query -> PostgreSQL parser -> planner -> permission/RLS checks -> execution -> storage -> result
```

Prototype direct path:

```text
frozen PostgreSQL binary snapshot -> Python decoder -> row-level policy check -> result
```

## 3. Existing-work motivation

The project builds on two lines of work that are usually discussed separately:

1. Direct storage access / database bypass for read-heavy analytics, motivated in the project by the 2026 Jailbreak paper.
2. Fine-grained / row-level access control enforced in or around the DBMS query path.

The gap being investigated is whether a direct reader can preserve row-level filtering without routing the query through the full normal query engine.

Do not make an absolute claim that no prior system has ever combined these ideas. Use wording such as: “In the literature reviewed for this project, we did not find a system combining these goals in this form.”

## 4. Version-1 implementation scope

The first implementation intentionally uses a **frozen pre-exported PostgreSQL binary snapshot**, not live PostgreSQL heap pages.

The snapshot is produced using PostgreSQL native binary COPY format.

The reader is a trusted Python process. End users are assumed not to have direct filesystem access to the snapshot. Protecting the raw snapshot from an attacker with filesystem access is out of scope for version 1.

The table is single-table and read-only. No joins, concurrent writes, transactions, column masking, audit logging, or arbitrary policy expressions are required for the first implementation.

## 5. Policy source

PostgreSQL RLS policies are defined in PostgreSQL and extracted from its own policy catalog (`pg_policy`). The intended extraction uses `pg_get_expr(polqual, polrelid)` to obtain a readable policy expression.

Do not silently treat arbitrary SQL policy expressions as supported. The first version supports only a restricted subset such as:

- equality conditions
- simple numeric/string range conditions
- AND / OR combinations over fixed attributes

Unsupported constructs should fail safely rather than be ignored.

## 6. Core data flow

```text
1. Create or import synthetic table in PostgreSQL.
2. Define RLS policies for several roles.
3. Extract policies from pg_policy into the Python Policy Store.
4. Export the table to a frozen PostgreSQL binary COPY snapshot.
5. Run the logical query through PostgreSQL for the baseline.
6. Run the direct reader on the frozen snapshot for the same role/query.
7. Compare outputs.
8. Measure latency repeatedly.
9. Report correctness and performance results.
```

## 7. Correctness definitions

The DBMS result is the reference for supported cases.

- **Soundness:** the direct reader does not return rows that the DBMS would forbid.
- **Completeness:** the direct reader does not omit rows that the DBMS would permit.

The implementation must explicitly test rows containing NULL in policy-relevant columns because SQL three-valued logic can create mismatches if NULL is handled incorrectly.

## 8. Performance evaluation

Measure wall-clock latency for both paths across dataset sizes and selectivity levels. Repeat trials and report the average and standard deviation.

Policy-resolution cost should be separated from per-row predicate evaluation cost when it is a one-time-per-query operation.

A faster direct reader is a hypothesis, not a preset conclusion.

## 9. Dataset plan

Synthetic single-table data. Target scale range for evaluation: approximately 10,000 to 1,000,000 rows, depending on stage. Include several roles with distinct visibility policies and a controlled proportion of NULL values in policy-relevant attributes.

Begin development with a tiny dataset (for example 10–20 rows) so the complete pipeline can be validated before scaling up.

## 10. Future extensions

Potential future work includes:

- live PostgreSQL heap-page parsing
- broader policy-expression support
- session-context predicates
- column masking
- audit logging
- multi-table/join support
- stronger filesystem threat model
- LLM-assisted reader generation

Do not present these future items as current capabilities.

## 11. Terminology to keep consistent

Preferred terms:

- policy-aware direct snapshot reader
- frozen binary snapshot
- PostgreSQL baseline
- row-level security (RLS)
- Policy Store
- direct reader
- correctness oracle
- soundness and completeness
- read-only

Avoid calling version 1 a “live storage reader” or “full database bypass” without qualification.

## 12. What the teacher should be able to see

The demo should show the same logical request executed through two paths:

1. PostgreSQL baseline: PostgreSQL applies RLS and returns authorized rows.
2. Direct reader: Python opens the binary snapshot, decodes rows, applies the extracted policy, and returns authorized rows.

The UI should display both outputs side-by-side or sequentially, show the direct-reader row filtering decisions, confirm whether the result sets match, and show measured latency.
