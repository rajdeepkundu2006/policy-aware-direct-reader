"""Reproducible synthetic data; preserve original rows and track generated IDs."""
from psycopg import sql


def initialize_database(connection):
    from pathlib import Path
    root = Path(__file__).resolve().parent
    with connection.cursor() as cursor:
        cursor.execute((root / '01_schema.sql').read_text())
        cursor.execute((root / '02_rls_policies.sql').read_text())
        cursor.execute('ALTER TABLE public.employees ALTER COLUMN department DROP NOT NULL, ALTER COLUMN salary DROP NOT NULL')
        cursor.execute('CREATE TABLE IF NOT EXISTS public.reader_generated_ids (id integer PRIMARY KEY REFERENCES public.employees(id) ON DELETE CASCADE)')


def generate_dataset(connection, total_rows=10000, null_percent=5):
    if not 10 <= total_rows <= 1000000 or not 0 <= null_percent <= 25:
        raise ValueError('Use 10 to 1,000,000 rows and 0 to 25 percent NULLs.')
    with connection.cursor() as cursor:
        cursor.execute('LOCK TABLE public.employees IN ACCESS EXCLUSIVE MODE')
        cursor.execute('DELETE FROM public.employees WHERE id IN (SELECT id FROM public.reader_generated_ids)')
        cursor.execute('SELECT count(*), COALESCE(max(id), 0) FROM public.employees')
        original_count, maximum = cursor.fetchone()
        amount = max(0, total_rows - original_count)
        if maximum + amount > 2147483647:
            raise ValueError('Generated IDs would overflow INTEGER')
        cursor.execute("""
            WITH inserted AS (
                INSERT INTO public.employees (id, name, department, salary)
                SELECT %s + n, 'Employee ' || n,
                       CASE WHEN n %% 100 < %s THEN NULL
                            ELSE (ARRAY['IT','HR','Finance'])[1 + n %% 3] END,
                       CASE WHEN (n + 37) %% 100 < %s THEN NULL
                            ELSE 30000 + ((n * 7919::bigint) %% 90001)::integer END
                FROM generate_series(1, %s) AS series(n)
                RETURNING id
            ) INSERT INTO public.reader_generated_ids SELECT id FROM inserted
        """, (maximum, null_percent, null_percent, amount))
        cursor.execute('ANALYZE public.employees')
        cursor.execute('SELECT count(*) FROM public.employees')
        return cursor.fetchone()[0]


def set_demo_threshold(connection, minimum_salary=0):
    if not 0 <= minimum_salary <= 200000:
        raise ValueError('Invalid salary threshold')
    with connection.cursor() as cursor:
        for role, department in [('it_user','IT'), ('hr_user','HR'), ('finance_user','Finance')]:
            expression = sql.SQL('department = {}').format(sql.Literal(department))
            if minimum_salary:
                expression += sql.SQL(' AND salary >= {}').format(sql.Literal(minimum_salary))
            cursor.execute(sql.SQL('ALTER POLICY {} ON public.employees USING ({})').format(
                sql.Identifier('employees_' + role.removesuffix('_user') + '_policy'), expression))
