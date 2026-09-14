import os

import psycopg
from psycopg import sql

from database.policy_ast import parse_policy_expression
from reader.snapshot_reader import read_snapshot


DB_CONFIG = {
    "host": os.getenv("PGHOST", "localhost"),
    "port": int(os.getenv("PGPORT", "5432")),
    "dbname": os.getenv("PGDATABASE", "direct_reader_db"),
    "user": os.getenv("PGUSER", "postgres"),
    "password": os.environ["PGPASSWORD"],
}


ROLE_POLICIES = {
    "it_user": "department = 'IT'::text",
    "hr_user": "department = 'HR'::text",
    "finance_user": "department = 'Finance'::text",
}


def get_postgres_rows(role):
    """
    Execute the baseline query through PostgreSQL under the
    requested RLS role.
    """
    with psycopg.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SET ROLE {}").format(sql.Identifier(role))
            )

            cur.execute(
                """
                SELECT id, name, department, salary
                FROM employees
                ORDER BY id
                """
            )

            rows = cur.fetchall()

            if cur.description is None:
                raise RuntimeError(
                    "PostgreSQL query did not return column metadata."
                )

            columns = [desc.name for desc in cur.description]

            return [
                dict(zip(columns, row))
                for row in rows
            ]


def test_postgres_rls_matches_direct_reader():
    """
    Verify that PostgreSQL RLS results match the direct reader
    for all supported project roles.
    """
    snapshot_path = "data/employees.bin"

    for role, expression in ROLE_POLICIES.items():
        postgres_rows = get_postgres_rows(role)

        policy = parse_policy_expression(expression)

        reader_rows = read_snapshot(
            snapshot_path,
            policy,
        )

        assert reader_rows == postgres_rows