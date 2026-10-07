"""Real PostgreSQL comparisons; skip cleanly without local credentials."""
import os
import pytest
from config import load_environment
from benchmark.benchmark import benchmark_role, SUPPORTED_ROLES
load_environment()
pytestmark = pytest.mark.skipif(not os.getenv('PGPASSWORD') or os.getenv('PGPASSWORD') == 'change_me', reason='PostgreSQL credentials are not configured')

@pytest.mark.parametrize('role', SUPPORTED_ROLES)
def test_postgres_rls_matches_direct_reader(role, tmp_path):
    result = benchmark_role(role, snapshot_path=tmp_path / 'employees.bin', warmup_runs=0, measured_runs=1)
    assert result['postgres_rows'] == result['reader_rows']
    assert result['correctness'].results_match
    assert result['rows_scanned'] == result['rows_returned'] + result['rows_denied']
