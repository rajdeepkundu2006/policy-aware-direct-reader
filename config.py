"""Load ignored local configuration without exposing credentials."""
import os
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent

def load_environment():
    path = PROJECT_ROOT / '.env'
    if not path.exists():
        return
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, sep, value = line.partition('=')
        if not sep or key.strip() not in {'PGHOST','PGPORT','PGDATABASE','PGUSER','PGPASSWORD'}:
            raise ValueError('Invalid .env entry; use .env.example.')
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {chr(34), chr(39)}:
            value = value[1:-1]
        os.environ.setdefault(key.strip(), value)

load_environment()

def connection_settings():
    if not os.getenv('PGPASSWORD') or os.getenv('PGPASSWORD') == 'change_me':
        raise RuntimeError('Enter your PostgreSQL password in the project .env file first.')
    return dict(host=os.getenv('PGHOST','localhost'), port=int(os.getenv('PGPORT','5432')),
                dbname=os.getenv('PGDATABASE','direct_reader_db'), user=os.getenv('PGUSER','postgres'),
                password=os.environ['PGPASSWORD'], connect_timeout=10)
