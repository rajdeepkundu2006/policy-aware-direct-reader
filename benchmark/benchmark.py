"""
Benchmark and correctness utilities for the
Policy-Aware Direct Snapshot Reader project.

This module currently provides:
- PostgreSQL baseline execution
- result normalization
- soundness/completeness checks
- latency measurement
- benchmark statistics

The direct-reader integration will be connected once
reader/snapshot_reader.py is available on the integrated branch.
"""

from __future__ import annotations

import os
import statistics
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable

import psycopg
from psycopg import sql


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_QUERY = """
SELECT id, name, department, salary
FROM employees
ORDER BY id;
""".strip()

SUPPORTED_ROLES = (
    "it_user",
    "hr_user",
    "finance_user",
)


# ---------------------------------------------------------------------------
# Result data structures
# ---------------------------------------------------------------------------

@dataclass
class CorrectnessResult:
    """Result of comparing PostgreSQL and direct-reader outputs."""

    soundness: bool
    completeness: bool
    results_match: bool
    postgres_only_rows: list[dict[str, Any]]
    reader_only_rows: list[dict[str, Any]]


@dataclass
class BenchmarkStats:
    """Timing statistics for one execution path."""

    samples_ms: list[float]
    average_ms: float
    standard_deviation_ms: float


# ---------------------------------------------------------------------------
# PostgreSQL connection
# ---------------------------------------------------------------------------

def get_connection() -> psycopg.Connection:
    """
    Create a PostgreSQL connection using environment variables.

    Expected environment variables:

        PGHOST      default: localhost
        PGPORT      default: 5432
        PGDATABASE  default: direct_reader_db
        PGUSER      default: postgres
        PGPASSWORD  required

    The password must never be committed to Git.
    """
    password = os.getenv("PGPASSWORD")

    if not password:
        raise RuntimeError(
            "PGPASSWORD is not set. "
            "Set your PostgreSQL password in the current shell "
            "before running the benchmark."
        )

    return psycopg.connect(
        host=os.getenv("PGHOST", "localhost"),
        port=int(os.getenv("PGPORT", "5432")),
        dbname=os.getenv("PGDATABASE", "direct_reader_db"),
        user=os.getenv("PGUSER", "postgres"),
        password=password,
    )


# ---------------------------------------------------------------------------
# PostgreSQL baseline
# ---------------------------------------------------------------------------

def _validate_role(role: str) -> None:
    """Validate that the requested role is part of the project contract."""
    if role not in SUPPORTED_ROLES:
        raise ValueError(
            f"Unsupported role: {role!r}. "
            f"Expected one of: {', '.join(SUPPORTED_ROLES)}"
        )


def run_postgres_query(
    role: str,
    query: str = DEFAULT_QUERY,
) -> list[dict[str, Any]]:
    """
    Execute the baseline query through PostgreSQL under the requested role.

    PostgreSQL remains the correctness baseline.

    We connect as the postgres administrative user and temporarily use
    SET ROLE so PostgreSQL evaluates the query under the project's
    non-administrative RLS role.

    Parameters
    ----------
    role:
        One of it_user, hr_user, finance_user.

    query:
        Read-only SQL query against employees.

    Returns
    -------
    list[dict[str, Any]]
        Rows normalized to the project's standard row representation.
    """
    _validate_role(role)

    with get_connection() as conn:
        with conn.cursor() as cur:
            # PostgreSQL identifiers cannot safely be inserted into SQL
            # using normal string interpolation. psycopg.sql.Identifier()
            # safely quotes the role name.
            cur.execute(
                sql.SQL("SET ROLE {}").format(sql.Identifier(role))
            )

            cur.execute(query)

            rows = cur.fetchall()

            column_names = [desc.name for desc in cur.description]

            # Restore the original role before leaving the connection.
            cur.execute("RESET ROLE")

    return [
        {
            column: value
            for column, value in zip(column_names, row)
        }
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Result normalization
# ---------------------------------------------------------------------------

EXPECTED_COLUMNS = (
    "id",
    "name",
    "department",
    "salary",
)


def normalize_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Normalize rows into the canonical project representation.

    Rows are sorted by id so that comparisons do not depend on
    incidental result ordering.
    """
    normalized: list[dict[str, Any]] = []

    for row in rows:
        normalized_row = {
            "id": row["id"],
            "name": row["name"],
            "department": row["department"],
            "salary": row["salary"],
        }
        normalized.append(normalized_row)

    normalized.sort(key=lambda item: item["id"])
    return normalized


# ---------------------------------------------------------------------------
# Correctness
# ---------------------------------------------------------------------------

def _rows_by_id(
    rows: Iterable[dict[str, Any]],
) -> dict[Any, dict[str, Any]]:
    """Index normalized rows by primary key."""
    return {row["id"]: row for row in rows}


def compare_results(
    postgres_rows: Iterable[dict[str, Any]],
    reader_rows: Iterable[dict[str, Any]],
) -> CorrectnessResult:
    """
    Compare direct-reader output with PostgreSQL output.

    Definitions used by the project:

        Soundness:
            every row returned by the direct reader is also
            authorized according to PostgreSQL.

        Completeness:
            every row returned by PostgreSQL is also returned
            by the direct reader.

        Results match:
            both soundness and completeness hold.

    PostgreSQL is treated as the baseline/oracle.
    """
    postgres = normalize_rows(postgres_rows)
    reader = normalize_rows(reader_rows)

    postgres_map = _rows_by_id(postgres)
    reader_map = _rows_by_id(reader)

    postgres_only = [
        postgres_map[row_id]
        for row_id in sorted(set(postgres_map) - set(reader_map))
    ]

    reader_only = [
        reader_map[row_id]
        for row_id in sorted(set(reader_map) - set(postgres_map))
    ]

    soundness = len(reader_only) == 0
    completeness = len(postgres_only) == 0
    results_match = soundness and completeness

    return CorrectnessResult(
        soundness=soundness,
        completeness=completeness,
        results_match=results_match,
        postgres_only_rows=postgres_only,
        reader_only_rows=reader_only,
    )


# ---------------------------------------------------------------------------
# Benchmarking
# ---------------------------------------------------------------------------

def benchmark_callable(
    function: Callable[[], Any],
    *,
    warmup_runs: int = 3,
    measured_runs: int = 10,
) -> BenchmarkStats:
    """
    Measure a callable repeatedly.

    Warm-up executions are excluded from the reported measurements.

    Timing uses time.perf_counter(), which is appropriate for measuring
    elapsed wall-clock duration in Python.
    """
    if warmup_runs < 0:
        raise ValueError("warmup_runs must be >= 0")

    if measured_runs <= 0:
        raise ValueError("measured_runs must be > 0")

    # Warm-up.
    for _ in range(warmup_runs):
        function()

    samples_ms: list[float] = []

    for _ in range(measured_runs):
        start = time.perf_counter()
        function()
        end = time.perf_counter()

        elapsed_ms = (end - start) * 1000.0
        samples_ms.append(elapsed_ms)

    average_ms = statistics.mean(samples_ms)

    # statistics.stdev() requires at least two samples.
    if len(samples_ms) >= 2:
        standard_deviation_ms = statistics.stdev(samples_ms)
    else:
        standard_deviation_ms = 0.0

    return BenchmarkStats(
        samples_ms=samples_ms,
        average_ms=average_ms,
        standard_deviation_ms=standard_deviation_ms,
    )


def calculate_speedup(
    postgres_average_ms: float,
    reader_average_ms: float,
) -> float:
    """
    Calculate direct-reader speedup relative to PostgreSQL.

    speedup = PostgreSQL average / reader average

    > 1 means the direct reader is faster.
    = 1 means approximately equal.
    < 1 means the direct reader is slower.
    """
    if reader_average_ms <= 0:
        raise ValueError("reader_average_ms must be greater than zero")

    return postgres_average_ms / reader_average_ms


# ---------------------------------------------------------------------------
# PostgreSQL baseline demonstration
# ---------------------------------------------------------------------------

def demo_postgres(role: str = "it_user") -> None:
    """
    Small command-line demonstration of the PostgreSQL baseline.

    This is intentionally useful before the direct reader is integrated.
    """
    print("=" * 60)
    print("POSTGRESQL BASELINE")
    print("=" * 60)
    print(f"Role: {role}")
    print(f"Query: {DEFAULT_QUERY}")
    print()

    rows = run_postgres_query(role)

    print("Rows returned by PostgreSQL:")
    for row in rows:
        print(row)

    print()
    print(f"Rows returned: {len(rows)}")
    print("=" * 60)


if __name__ == "__main__":
    demo_postgres("it_user")