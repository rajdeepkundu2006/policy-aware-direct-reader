"""
Integrated benchmark and correctness harness.

Project paths:
    PostgreSQL DBMS baseline
        vs.
    Direct snapshot reader

The module:
- connects to PostgreSQL,
- executes the baseline query under an RLS role,
- extracts the project's Policy AST,
- exports a real PostgreSQL binary COPY snapshot,
- runs Ishaan's direct reader,
- compares result sets using soundness/completeness,
- measures latency and standard deviation.
"""

from __future__ import annotations

import os
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

import psycopg
from psycopg import sql

from database.policy_ast import extract_policies_from_database
from reader.snapshot_reader import read_snapshot

from typing import Any, Callable, Iterable, cast


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SNAPSHOT_PATH = PROJECT_ROOT / "data" / "employees.bin"

SUPPORTED_ROLES = (
    "it_user",
    "hr_user",
    "finance_user",
)

DEFAULT_QUERY = """
SELECT id, name, department, salary
FROM employees
ORDER BY id;
""".strip()


@dataclass
class CorrectnessResult:
    soundness: bool
    completeness: bool
    results_match: bool
    postgres_only_rows: list[dict[str, Any]]
    reader_only_rows: list[dict[str, Any]]


@dataclass
class BenchmarkStats:
    samples_ms: list[float]
    average_ms: float
    standard_deviation_ms: float


def _get_connection_kwargs() -> dict[str, Any]:
    """Read PostgreSQL connection settings from environment variables."""
    password = os.getenv("PGPASSWORD")
    if not password:
        raise RuntimeError(
            "PGPASSWORD is not set. Set it in the current terminal "
            "before running the project."
        )

    return {
        "host": os.getenv("PGHOST", "localhost"),
        "port": int(os.getenv("PGPORT", "5432")),
        "dbname": os.getenv("PGDATABASE", "direct_reader_db"),
        "user": os.getenv("PGUSER", "postgres"),
        "password": password,
    }


def get_connection() -> psycopg.Connection:
    """Create a connection to the project's PostgreSQL database."""
    return psycopg.connect(**_get_connection_kwargs())


def _validate_role(role: str) -> None:
    if role not in SUPPORTED_ROLES:
        raise ValueError(
            f"Unsupported role {role!r}. "
            f"Expected one of: {', '.join(SUPPORTED_ROLES)}"
        )


def _execute_postgres_query(
    connection: psycopg.Connection,
    query: str,
) -> list[dict[str, Any]]:
    """Execute a query on an already-role-scoped PostgreSQL connection."""
    with connection.cursor() as cursor:
        cursor.execute(cast(Any, query))
        rows = cursor.fetchall()
        if cursor.description is None:
            raise RuntimeError(
                "PostgreSQL query did not return column metadata."
            )
        column_names = [description.name for description in cursor.description]

    return [
        {column: value for column, value in zip(column_names, row)}
        for row in rows
    ]


def run_postgres_query(
    role: str,
    query: str = DEFAULT_QUERY,
) -> list[dict[str, Any]]:
    """
    Execute the DBMS baseline under the requested RLS role.

    The connection is created as postgres and then SET ROLE is used so the
    query is evaluated with the project's restricted role.
    """
    _validate_role(role)

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("SET ROLE {}").format(sql.Identifier(role))
            )

        return _execute_postgres_query(connection, query)


def normalize_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert rows into the canonical project representation and sort by id."""
    normalized = [
        {
            "id": row["id"],
            "name": row["name"],
            "department": row["department"],
            "salary": row["salary"],
        }
        for row in rows
    ]
    normalized.sort(key=lambda row: row["id"])
    return normalized


def _rows_by_id(
    rows: Iterable[dict[str, Any]],
) -> dict[Any, dict[str, Any]]:
    return {row["id"]: row for row in rows}


def compare_results(
    postgres_rows: Iterable[dict[str, Any]],
    reader_rows: Iterable[dict[str, Any]],
) -> CorrectnessResult:
    """
    Compare direct-reader output against the PostgreSQL baseline.

    Soundness:
        reader_rows is a subset of postgres_rows.

    Completeness:
        postgres_rows is a subset of reader_rows.

    Results match only when both conditions hold.
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

    return CorrectnessResult(
        soundness=soundness,
        completeness=completeness,
        results_match=soundness and completeness,
        postgres_only_rows=postgres_only,
        reader_only_rows=reader_only,
    )


def load_policy_map() -> dict[str, dict]:
    """
    Extract the real PostgreSQL RLS policies and convert them to the
    project's canonical policy AST map.
    """
    kwargs = _get_connection_kwargs()

    return extract_policies_from_database(
        host=kwargs["host"],
        port=kwargs["port"],
        database=kwargs["dbname"],
        user=kwargs["user"],
        password=kwargs["password"],
    )


def get_policy_for_role(role: str) -> dict:
    """Return the parsed policy AST for one supported project role."""
    _validate_role(role)

    policies = load_policy_map()

    try:
        return policies[role]
    except KeyError as exc:
        raise RuntimeError(
            f"No PostgreSQL RLS policy was extracted for role {role!r}."
        ) from exc


def export_binary_snapshot(
    snapshot_path: str | Path = DEFAULT_SNAPSHOT_PATH,
) -> Path:
    """
    Export the employees table using PostgreSQL's native binary COPY format.

    psycopg COPY TO STDOUT is used so PostgreSQL writes the binary stream
    to the local file under the Python process's permissions.
    """
    snapshot_path = Path(snapshot_path)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)

    copy_command = """
        COPY employees TO STDOUT WITH (FORMAT binary)
    """

    with get_connection() as connection:
        with connection.cursor() as cursor:
            with cursor.copy(copy_command) as copy:
                with snapshot_path.open("wb") as output_file:
                    while True:
                        chunk = copy.read()
                        if not chunk:
                            break
                        output_file.write(chunk)

    return snapshot_path


def run_direct_reader(
    role: str,
    snapshot_path: str | Path = DEFAULT_SNAPSHOT_PATH,
) -> list[dict[str, Any]]:
    """Extract the role policy and run Ishaan's direct reader."""
    policy = get_policy_for_role(role)

    return read_snapshot(
        str(snapshot_path),
        policy,
    )


def benchmark_callable(
    function: Callable[[], Any],
    *,
    warmup_runs: int = 3,
    measured_runs: int = 10,
) -> BenchmarkStats:
    """Measure a callable repeatedly using wall-clock time."""
    if warmup_runs < 0:
        raise ValueError("warmup_runs must be >= 0")

    if measured_runs <= 0:
        raise ValueError("measured_runs must be > 0")

    for _ in range(warmup_runs):
        function()

    samples_ms: list[float] = []

    for _ in range(measured_runs):
        start = time.perf_counter()
        function()
        elapsed = (time.perf_counter() - start) * 1000.0
        samples_ms.append(elapsed)

    average_ms = statistics.mean(samples_ms)

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
    """Return PostgreSQL average latency divided by reader latency."""
    if reader_average_ms <= 0:
        raise ValueError("reader_average_ms must be greater than zero")

    return postgres_average_ms / reader_average_ms


def benchmark_role(
    role: str,
    *,
    snapshot_path: str | Path = DEFAULT_SNAPSHOT_PATH,
    warmup_runs: int = 3,
    measured_runs: int = 10,
) -> dict[str, Any]:
    """
    Run one complete benchmark case for a role.

    Policy extraction is performed before the timed region.
    PostgreSQL and reader results are also validated before timing.
    """
    _validate_role(role)
    snapshot_path = Path(snapshot_path)

    if not snapshot_path.exists():
        export_binary_snapshot(snapshot_path)

    policy = get_policy_for_role(role)

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("SET ROLE {}").format(sql.Identifier(role))
            )

        postgres_rows = _execute_postgres_query(connection, DEFAULT_QUERY)

        reader_rows = read_snapshot(
            str(snapshot_path),
            policy,
        )

        correctness = compare_results(postgres_rows, reader_rows)

        postgres_stats = benchmark_callable(
            lambda: _execute_postgres_query(connection, DEFAULT_QUERY),
            warmup_runs=warmup_runs,
            measured_runs=measured_runs,
        )

        reader_stats = benchmark_callable(
            lambda: read_snapshot(str(snapshot_path), policy),
            warmup_runs=warmup_runs,
            measured_runs=measured_runs,
        )

    speedup = calculate_speedup(
        postgres_stats.average_ms,
        reader_stats.average_ms,
    )

    return {
        "role": role,
        "postgres_rows": postgres_rows,
        "reader_rows": reader_rows,
        "correctness": correctness,
        "postgres_stats": postgres_stats,
        "reader_stats": reader_stats,
        "speedup": speedup,
    }


def main() -> None:
    """Small command-line smoke test."""
    role = "it_user"

    print("=" * 70)
    print("POLICY-AWARE DIRECT READER - INTEGRATED SMOKE TEST")
    print("=" * 70)

    snapshot = export_binary_snapshot()
    print(f"Snapshot: {snapshot}")

    result = benchmark_role(
        role,
        warmup_runs=1,
        measured_runs=3,
    )

    correctness: CorrectnessResult = result["correctness"]
    postgres_stats: BenchmarkStats = result["postgres_stats"]
    reader_stats: BenchmarkStats = result["reader_stats"]

    print(f"Role: {role}")
    print()
    print("PostgreSQL result:")
    for row in result["postgres_rows"]:
        print(row)

    print()
    print("Direct reader result:")
    for row in result["reader_rows"]:
        print(row)

    print()
    print(f"Soundness:       {'PASS' if correctness.soundness else 'FAIL'}")
    print(f"Completeness:    {'PASS' if correctness.completeness else 'FAIL'}")
    print(f"Results match:   {'YES' if correctness.results_match else 'NO'}")

    print()
    print(f"PostgreSQL avg:  {postgres_stats.average_ms:.3f} ms")
    print(f"PostgreSQL std:  {postgres_stats.standard_deviation_ms:.3f} ms")
    print(f"Reader avg:      {reader_stats.average_ms:.3f} ms")
    print(f"Reader std:      {reader_stats.standard_deviation_ms:.3f} ms")
    print(f"Speedup:         {result['speedup']:.3f}x")


if __name__ == "__main__":
    main()
