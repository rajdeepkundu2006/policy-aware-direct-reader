"""One entry point for setup, UI, tests, and submission experiments."""
import argparse
from pathlib import Path
import subprocess
import sys
import psycopg
from psycopg import sql
from config import PROJECT_ROOT, connection_settings


def setup():
    settings = connection_settings()
    database = settings['dbname']
    admin = dict(settings, dbname='postgres')
    with psycopg.connect(**admin, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1 FROM pg_database WHERE datname=%s', (database,))
            if cursor.fetchone() is None:
                cursor.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(database)))
    from database.datasets import initialize_database
    with psycopg.connect(**settings) as connection:
        initialize_database(connection)
    print('Database and demo policies are ready.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', nargs='?', default='app', choices=['app','setup','test','benchmark','suite','data','demo'])
    parser.add_argument('--rows', type=int, default=10000)
    parser.add_argument('--null-percent', type=int, default=5)
    args = parser.parse_args()
    if args.command == 'demo':
        raise SystemExit(subprocess.call([sys.executable, '-m', 'streamlit', 'run', str(PROJECT_ROOT / 'app' / 'demo.py')], cwd=PROJECT_ROOT))
    if args.command == 'test':
        raise SystemExit(subprocess.call([sys.executable, '-m', 'pytest', '-q', '--basetemp', str(PROJECT_ROOT / '.test-tmp')], cwd=PROJECT_ROOT))
    if args.command in {'setup', 'data'}:
        setup()
        if args.command == 'data':
            from database.datasets import generate_dataset
            with psycopg.connect(**connection_settings()) as connection:
                actual = generate_dataset(connection, args.rows, args.null_percent)
            from benchmark.benchmark import export_binary_snapshot
            export_binary_snapshot()
            print(f'Dataset ready: {actual:,} rows.')
        return
    if args.command == 'app':
        # Check credentials and schema without recreating policies on every launch.
        try:
            with psycopg.connect(**connection_settings()) as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT to_regclass('public.employees'), to_regclass('public.reader_generated_ids')")
                    exists = all(cursor.fetchone())
        except psycopg.errors.InvalidCatalogName:
            exists = False
        if not exists:
            setup()
        raise SystemExit(subprocess.call([sys.executable, '-m', 'streamlit', 'run', str(PROJECT_ROOT / 'app' / 'app.py')], cwd=PROJECT_ROOT))
    from benchmark.benchmark import main as smoke, run_suite
    if args.command == 'benchmark':
        smoke()
    else:
        records = run_suite(progress=lambda n, total: print(f'Experiment {n}/{total}', flush=True))
        print(f"Saved {len(records)} cases and docs/SUBMISSION_REPORT.md")


if __name__ == '__main__':
    try:
        main()
    except (psycopg.Error, RuntimeError, ValueError) as exc:
        # Never print connection settings or the password.
        print(f'Cannot continue: {exc}', file=sys.stderr)
        raise SystemExit(1)
