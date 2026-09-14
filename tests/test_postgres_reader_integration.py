import os
import psycopg

from reader.snapshot_reader import read_snapshot
from database.policy_ast import parse_policy_expression


DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "policy_reader",
    "user": "postgres",
    "password": os.environ["PGPASSWORD"],
}


ROLE_POLICIES = {
    "it_user": ("department = 'IT'::text", "itpass"),
    "hr_user": ("department = 'HR'::text", "hrpass"),
    "finance_user": ("department = 'Finance'::text", "financepass"),
}


def get_postgres_rows(role, password):
    with psycopg.connect(
        host="localhost",
        port=5432,
        dbname="policy_reader",
        user=role,
        password=password,
    ) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, name, department, salary "
                "FROM employees ORDER BY id"
            )
            columns = [desc.name for desc in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]


def test_postgres_rls_matches_direct_reader():
    snapshot_path = "data/employees.bin"

    for role, (expression, password) in ROLE_POLICIES.items():
        postgres_rows = get_postgres_rows(role, password)

        policy = parse_policy_expression(expression)
        reader_rows = read_snapshot(snapshot_path, policy)

        assert reader_rows == postgres_rows