"""Regression coverage for security, full-row equality, and snapshot consistency."""
import os
from pathlib import Path
import struct
import pytest
from benchmark.benchmark import compare_results, benchmark_role, get_connection
from database.policy_ast import parse_policy_expression, build_policy_map, extract_policies_from_connection, PolicyParseError
from database.datasets import generate_dataset, set_demo_threshold
from reader.policy import evaluate_policy, UnsupportedPolicyError
from reader.snapshot_reader import read_snapshot


def test_full_row_and_duplicate_comparison():
    row = dict(id=1, name='Alice', department='HR', salary=50000)
    changed = dict(row, salary=51000)
    result = compare_results([row], [changed])
    assert not result.soundness and not result.completeness and not result.results_match
    assert not compare_results([row], [row, row]).soundness
    assert not compare_results([row, row], [row]).completeness


@pytest.mark.parametrize('expression,expected', [
    ("department = 'HR' OR department = 'IT' AND salary >= 70000", True),
    ("(department = 'HR' OR department = 'IT') AND salary >= 70000", False),
    ("(((department = 'HR'))) OR salary >= 70000", True),
    ("name = 'O''Brien AND (OR)'::text", True),
])
def test_sql_precedence_parentheses_and_quotes(expression, expected):
    row = dict(id=1, name="O'Brien AND (OR)", department='HR', salary=50000)
    assert evaluate_policy(row, parse_policy_expression(expression)) is expected


@pytest.mark.parametrize('expression', [
    "department LIKE '%IT%'", "department = 'IT' junk", "(salary >= 10", "salary > 10)",
    "department > 'IT'", "salary = 'abc'", "current_user = 'it_user'", "salary != 1", "", "salary = 1::text"
])
def test_unsupported_sql_is_rejected(expression):
    with pytest.raises(PolicyParseError):
        parse_policy_expression(expression)


def test_complete_validation_even_for_empty_snapshot(tmp_path):
    path = tmp_path / 'empty.bin'
    path.write_bytes(b'PGCOPY\n\xff\r\n\x00' + struct.pack('!IIh', 0, 0, -1))
    policy = dict(type='logical', operator='OR', left=dict(type='constant', value=True),
                  right=dict(type='comparison', column='department', operator='LIKE', value='IT'))
    with pytest.raises(UnsupportedPolicyError):
        read_snapshot(str(path), policy)


def test_policy_composition_and_command_filtering():
    policies = build_policy_map([
        dict(role_name='it_user', using_expr="department = 'IT'", permissive=True),
        dict(role_name='it_user', using_expr="department = 'HR'", permissive=True),
        dict(role_name='it_user', using_expr='salary >= 70000', permissive=False),
        dict(role_name='it_user', using_expr='unsupported()', polcmd='w'),
    ])
    assert evaluate_policy(dict(department='HR', salary=80000), policies['it_user'])
    assert not evaluate_policy(dict(department='HR', salary=None), policies['it_user'])
    restrictive_only = build_policy_map([dict(role_name='it_user', using_expr='salary >= 1', permissive=False)])
    assert not evaluate_policy(dict(salary=80000), restrictive_only['it_user'])


@pytest.fixture
def live_connection():
    if not os.getenv('PGPASSWORD') or os.getenv('PGPASSWORD') == 'change_me':
        pytest.skip('PostgreSQL credentials are not configured')
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
            cursor.execute("SET LOCAL lock_timeout = '10s'")
            cursor.execute('LOCK TABLE public.employees IN ACCESS EXCLUSIVE MODE')
        try:
            yield connection
        finally:
            connection.rollback()


def test_live_public_inherited_and_restrictive_policies(live_connection, tmp_path):
    connection = live_connection
    with connection.cursor() as cursor:
        cursor.execute('CREATE ROLE reader_regression_parent')
        cursor.execute('GRANT reader_regression_parent TO it_user')
        cursor.execute("INSERT INTO public.employees SELECT COALESCE(max(id), 0) + 1, 'Inherited policy regression', 'HR', 90000 FROM public.employees")
        cursor.execute("CREATE POLICY reader_regression_inherited ON public.employees FOR SELECT TO reader_regression_parent USING (department = 'HR')")
        cursor.execute("CREATE POLICY reader_regression_public ON public.employees FOR SELECT TO PUBLIC USING (department = 'Finance')")
        cursor.execute('CREATE POLICY reader_regression_restrictive ON public.employees AS RESTRICTIVE FOR SELECT TO PUBLIC USING (salary >= 70000)')
        cursor.execute("CREATE POLICY reader_regression_update ON public.employees FOR UPDATE TO PUBLIC USING (name LIKE '%')")
    result = benchmark_role('it_user', connection=connection, snapshot_path=tmp_path / 'snapshot.bin', warmup_runs=0, measured_runs=1)
    assert result['correctness'].results_match
    assert {r['department'] for r in result['reader_rows']} == {'IT', 'HR', 'Finance'}
    assert any(r['name'] == 'Inherited policy regression' for r in result['reader_rows'])
    assert all(r['salary'] >= 70000 for r in result['reader_rows'])


def test_live_generation_nulls_and_fresh_snapshot(live_connection, tmp_path):
    connection = live_connection
    generate_dataset(connection, 1000, 10)
    set_demo_threshold(connection, 70000)
    path = tmp_path / 'stale.bin'
    path.write_bytes(b'stale invalid snapshot')
    with connection.cursor() as cursor:
        cursor.execute("UPDATE public.employees SET salary=123456 WHERE name='Bob'")
        cursor.execute('SELECT count(*) FROM public.employees WHERE department IS NULL OR salary IS NULL')
        assert cursor.fetchone()[0] > 0
    result = benchmark_role('it_user', connection=connection, snapshot_path=path, warmup_runs=0, measured_runs=1)
    assert result['rows_scanned'] == 1000
    assert result['correctness'].results_match
    assert next(row['salary'] for row in result['reader_rows'] if row['name'] == 'Bob') == 123456


def test_live_default_deny_and_unsupported_policy(live_connection, tmp_path):
    connection = live_connection
    with connection.cursor() as cursor:
        cursor.execute('DROP POLICY employees_it_policy ON public.employees')
    result = benchmark_role('it_user', connection=connection, snapshot_path=tmp_path / 'snapshot.bin', warmup_runs=0, measured_runs=1)
    assert result['reader_rows'] == result['postgres_rows'] == []
    with connection.cursor() as cursor:
        cursor.execute("CREATE POLICY reader_regression_bad ON public.employees FOR SELECT TO it_user USING (name LIKE '%')")
    with pytest.raises(PolicyParseError):
        benchmark_role('it_user', connection=connection, snapshot_path=tmp_path / 'snapshot.bin', warmup_runs=0, measured_runs=1)
