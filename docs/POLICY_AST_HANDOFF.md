# Policy AST Handoff

## Purpose

This document defines the policy representation produced by the database-side
policy extraction code and consumed by the direct reader.

PostgreSQL is the source of truth for RLS policies.

The database-side flow is:

PostgreSQL `pg_policy`
-> `pg_get_expr()`
-> policy expression
-> `parse_policy_expression()`
-> canonical Policy AST

## Canonical Policy Representation

A simple comparison is represented as:

```python
{
    "type": "comparison",
    "column": "department",
    "operator": "=",
    "value": "IT",
}
```

A numeric comparison is represented as:

```python
{
    "type": "comparison",
    "column": "salary",
    "operator": ">=",
    "value": 70000,
}
```

Logical policies use:

```python
{
    "type": "logical",
    "operator": "AND",
    "left": {...},
    "right": {...},
}
```

OR policies use the same structure with:

```python
"operator": "OR"
```

## Current Policies

The current `employees` table has three read policies:

| Role | Policy |
|---|---|
| `it_user` | `department = 'IT'` |
| `hr_user` | `department = 'HR'` |
| `finance_user` | `department = 'Finance'` |

Their canonical ASTs are:

```python
{
    "it_user": {
        "type": "comparison",
        "column": "department",
        "operator": "=",
        "value": "IT",
    },
    "hr_user": {
        "type": "comparison",
        "column": "department",
        "operator": "=",
        "value": "HR",
    },
    "finance_user": {
        "type": "comparison",
        "column": "department",
        "operator": "=",
        "value": "Finance",
    },
}
```

## Supported Policy Subset

Comparison operators:

```text
=
<
<=
>
>=
```

Logical operators:

```text
AND
OR
```

Supported columns:

```text
id
name
department
salary
```

Unsupported PostgreSQL policy expressions raise `PolicyParseError`.

Unsupported expressions must not be silently ignored or converted into an
allow-all policy.

## Reader Contract

The reader should consume the canonical AST directly.

The reader does not need to parse PostgreSQL expressions such as:

```text
(department = 'IT'::text)
```

The database-side code converts the PostgreSQL expression into the canonical
AST.

The reader-side evaluator evaluates that AST against decoded snapshot rows.

## Validation

The database-side implementation has been tested against the real
`policy_reader` PostgreSQL database.

The extracted policies were:

```text
finance_user -> department = 'Finance'
hr_user -> department = 'HR'
it_user -> department = 'IT'
```

The policy AST unit tests pass.

The PostgreSQL extraction test runs when `PGPASSWORD` is provided through the
environment.