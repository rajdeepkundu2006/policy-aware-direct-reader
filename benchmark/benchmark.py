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

import statistics
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, cast

import psycopg
from psycopg import sql

from database.policy_ast import extract_policies_from_database
from reader.snapshot_reader import read_snapshot, read_snapshot_reference, PreparedReader
from reader.query import QuerySpec

from config import connection_settings
from database.policy_ast import extract_policies_from_connection
from reader.parser import iter_binary_rows
from collections import Counter
import csv
import tempfile
import json
from datetime import datetime, timezone
from contextlib import nullcontext


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SNAPSHOT_PATH = PROJECT_ROOT / "data" / "employees.bin"

SUPPORTED_ROLES = (
    "it_user",
    "hr_user",
    "finance_user",
)

DEFAULT_QUERY = """
SELECT id, name, department, salary
FROM public.employees
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
    return connection_settings()


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
    query,
    params=None,
) -> list[dict[str, Any]]:
    """Execute a query on an already-role-scoped PostgreSQL connection."""
    with connection.cursor() as cursor:
        cursor.execute(cast(Any, query), params)
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
    query: str | QuerySpec = DEFAULT_QUERY,
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

        if isinstance(query, QuerySpec):
            statement, parameters = query.sql()
            return _execute_postgres_query(connection, statement, parameters)
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
    postgres = list(postgres_rows)
    reader = list(reader_rows)
    columns = tuple(sorted(set().union(*(row.keys() for row in postgres + reader))))
    if any(set(row) != set(columns) for row in postgres + reader):
        raise ValueError('Result rows have inconsistent columns')
    postgres_counts = Counter(tuple(row[c] for c in columns) for row in postgres)
    reader_counts = Counter(tuple(row[c] for c in columns) for row in reader)
    postgres_only = [dict(zip(columns, row)) for row, count in (postgres_counts - reader_counts).items() for _ in range(count)]
    reader_only = [dict(zip(columns, row)) for row, count in (reader_counts - postgres_counts).items() for _ in range(count)]

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

    with get_connection() as connection:
        _export_from_connection(connection, snapshot_path)
    return snapshot_path


def _export_from_connection(connection, snapshot_path):
    """Atomically publish an ordered export; never leave a half-written snapshot."""
    snapshot_path = Path(snapshot_path)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=snapshot_path.parent, delete=False) as output:
            temporary = Path(output.name)
            with connection.cursor() as cursor:
                with cursor.copy('COPY (SELECT id, name, department, salary FROM public.employees ORDER BY id) TO STDOUT WITH (FORMAT binary)') as copy:
                    while chunk := copy.read():
                        output.write(chunk)
        temporary.replace(snapshot_path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()



def run_direct_reader(
    role: str,
    snapshot_path: str | Path = DEFAULT_SNAPSHOT_PATH,
    query: QuerySpec | None = None,
) -> list[dict[str, Any]]:
    """Extract the role policy and run Ishaan's direct reader."""
    policy = get_policy_for_role(role)

    return read_snapshot(
        str(snapshot_path),
        policy,
        query,
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
    connection=None,
    query: QuerySpec | None = None,
) -> dict[str, Any]:
    """
    Run one complete benchmark case for a role.

    Policy extraction is performed before the timed region.
    PostgreSQL and reader results are also validated before timing.
    """
    _validate_role(role)
    query = query or QuerySpec()
    statement, parameters = query.sql()
    snapshot_path = Path(snapshot_path)
    (PROJECT_ROOT / 'data').mkdir(exist_ok=True)

    # The same transaction supplies data, policy definitions, and baseline.
    # SHARE lock blocks writes/policy DDL while repeatable read fixes visibility.
    supplied_connection = connection is not None
    with (nullcontext(connection) if supplied_connection else get_connection()) as connection:
        with connection.cursor() as cursor:
            if not supplied_connection:
                cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
            cursor.execute("SET LOCAL lock_timeout = '10s'")
            cursor.execute('LOCK TABLE public.employees IN SHARE MODE')
        policy_start = time.perf_counter()
        policy = extract_policies_from_connection(connection)[role]
        policy_resolution_ms = (time.perf_counter() - policy_start) * 1000
        with connection.cursor() as cursor:
            cursor.execute('SELECT count(*) FILTER (WHERE department IS NULL), count(*) FILTER (WHERE salary IS NULL) FROM public.employees')
            null_department_rows, null_salary_rows = cursor.fetchone()
        # Private files avoid cross-session refresh races during an experiment.
        with tempfile.TemporaryDirectory(prefix='reader-experiment-', dir=PROJECT_ROOT / 'data') as directory:
            experiment_snapshot = Path(directory) / 'employees.bin'
            _export_from_connection(connection, experiment_snapshot)
            rows_scanned = sum(1 for _ in iter_binary_rows(str(experiment_snapshot)))
            # Keep the public snapshot only as a demonstration artifact.
            snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(experiment_snapshot, snapshot_path)
            with connection.cursor() as cursor:
                cursor.execute(sql.SQL('SET LOCAL ROLE {}').format(sql.Identifier(role)))
            postgres_rows = _execute_postgres_query(connection, statement, parameters)
            preparation_start = time.perf_counter()
            prepared = PreparedReader(policy, query)
            reader_preparation_ms = (time.perf_counter() - preparation_start) * 1000
            scan = prepared.scan(str(experiment_snapshot))
            reader_rows = scan.rows
            reference_rows = read_snapshot_reference(str(experiment_snapshot), policy, query)
            reference_match = reader_rows == reference_rows
            if not reference_match:
                raise RuntimeError('Optimized reader differs from the reference reader.')

            correctness = compare_results(postgres_rows, reader_rows)

            postgres_stats = benchmark_callable(
                lambda: _execute_postgres_query(connection, statement, parameters),
                warmup_runs=warmup_runs,
                measured_runs=measured_runs,
            )

            reader_stats = benchmark_callable(
                lambda: prepared.scan(str(experiment_snapshot)),
                warmup_runs=warmup_runs,
                measured_runs=measured_runs,
            )

        with connection.cursor() as cursor:
            cursor.execute('RESET ROLE')

    speedup = calculate_speedup(
        postgres_stats.average_ms,
        reader_stats.average_ms,
    )

    return {
        "role": role,
        "policy": policy,
        "warmup_runs": warmup_runs,
        "policy_resolution_ms": policy_resolution_ms,
        "rows_scanned": rows_scanned,
        "null_department_rows": null_department_rows,
        "null_salary_rows": null_salary_rows,
        "rows_returned": len(reader_rows),
        "rows_denied": scan.denied,
        "rows_filtered": scan.filtered,
        "rows_limited": scan.limited,
        "query": query.as_dict(),
        "reference_match": reference_match,
        "reader_preparation_ms": reader_preparation_ms,
        "postgres_rows": postgres_rows,
        "reader_rows": reader_rows,
        "correctness": correctness,
        "postgres_stats": postgres_stats,
        "reader_stats": reader_stats,
        "speedup": speedup,
    }


CSV_COLUMNS = ['dataset_size', 'role', 'minimum_salary', 'null_percent', 'visible_rows',
               'selectivity', 'postgres_avg_ms', 'postgres_stddev_ms', 'reader_avg_ms',
               'reader_stddev_ms', 'speedup', 'policy_resolution_ms', 'warmup_runs',
               'measured_runs', 'soundness', 'completeness', 'results_match',
               'query_minimum_salary', 'query_maximum_salary', 'exact_name', 'selected_columns',
               'row_limit', 'rows_denied', 'rows_filtered', 'rows_limited', 'reader_preparation_ms', 'reference_match']


def result_record(result, minimum_salary=None, null_percent=None):
    pg, reader, correctness = result['postgres_stats'], result['reader_stats'], result['correctness']
    return dict(dataset_size=result['rows_scanned'], role=result['role'],
                minimum_salary=minimum_salary, null_percent=null_percent,
                visible_rows=result['rows_returned'],
                selectivity=result['rows_returned'] / max(1, result['rows_scanned']),
                postgres_avg_ms=pg.average_ms, postgres_stddev_ms=pg.standard_deviation_ms,
                reader_avg_ms=reader.average_ms, reader_stddev_ms=reader.standard_deviation_ms,
                speedup=result['speedup'], policy_resolution_ms=result['policy_resolution_ms'],
                warmup_runs=result.get('warmup_runs', 3), measured_runs=len(pg.samples_ms),
                soundness=correctness.soundness, completeness=correctness.completeness,
                results_match=correctness.results_match,
                query_minimum_salary=result['query']['minimum_salary'],
                query_maximum_salary=result['query']['maximum_salary'], exact_name=result['query']['exact_name'],
                selected_columns=','.join(result['query']['columns']), row_limit=result['query']['limit'],
                rows_denied=result['rows_denied'], rows_filtered=result['rows_filtered'], rows_limited=result['rows_limited'],
                reader_preparation_ms=result['reader_preparation_ms'], reference_match=result['reference_match'])


def save_records(records, path=None):
    path = Path(path or PROJECT_ROOT / 'results' / 'benchmark_results.csv')
    path.parent.mkdir(exist_ok=True, parents=True)
    with path.open('w', newline='', encoding='utf-8') as output:
        writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(records)
    return path


def run_suite(sizes=(1000, 10000, 100000), thresholds=(0, 70000, 100000), null_percent=5,
              warmup_runs=2, measured_runs=5, progress=None):
    """Run controlled scenarios, then roll back all data and policy changes."""
    from database.datasets import generate_dataset, set_demo_threshold
    records = []
    samples = []
    with get_connection() as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
                cursor.execute("SET LOCAL lock_timeout = '10s'")
                cursor.execute('LOCK TABLE public.employees IN ACCESS EXCLUSIVE MODE')
            for size in sizes:
                generate_dataset(connection, size, null_percent)
                for threshold in thresholds:
                    set_demo_threshold(connection, threshold)
                    for role in SUPPORTED_ROLES:
                        result = benchmark_role(role, connection=connection,
                                                warmup_runs=warmup_runs, measured_runs=measured_runs)
                        records.append(result_record(result, threshold, null_percent))
                        samples.append(dict(records[-1], postgres_samples_ms=result['postgres_stats'].samples_ms,
                                            reader_samples_ms=result['reader_stats'].samples_ms,
                                            policy=result['policy']))
                        if progress:
                            progress(len(records), len(sizes) * len(thresholds) * len(SUPPORTED_ROLES))
                        if not result['correctness'].results_match:
                            raise RuntimeError('Correctness failed; benchmark suite stopped.')
        finally:
            connection.rollback()
    # Restore the demonstration artifact after rolling back suite data.
    export_binary_snapshot()
    save_records(records)
    (PROJECT_ROOT / 'results' / 'benchmark_samples.json').write_text(
        json.dumps(dict(measured_at_utc=datetime.now(timezone.utc).isoformat(), cases=samples), indent=2),
        encoding='utf-8')
    return records


def main():
    for role in SUPPORTED_ROLES:
        result = benchmark_role(role, warmup_runs=1, measured_runs=3)
        print(role, 'match:', result['correctness'].results_match,
              'visible:', result['rows_returned'], 'speedup:', round(result['speedup'], 3))


if __name__ == '__main__':
    main()
