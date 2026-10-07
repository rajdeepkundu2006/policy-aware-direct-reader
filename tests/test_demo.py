"""The teacher demo must work without PostgreSQL or credentials."""
import pytest
from config import PROJECT_ROOT
from demo.replay import replay_role
from streamlit.testing.v1 import AppTest

@pytest.mark.parametrize('role',['it_user','hr_user','finance_user'])
def test_real_reader_matches_recorded_baseline(role, monkeypatch):
    import benchmark.benchmark as benchmark
    monkeypatch.setattr(benchmark,'get_connection',lambda:pytest.fail('Offline demo contacted PostgreSQL'))
    evidence,case,rows,correctness=replay_role(role)
    assert correctness.results_match
    assert rows == case['postgres_rows']
    assert evidence['summary']['total'] == 10000


def test_offline_ui_without_database(monkeypatch):
    import benchmark.benchmark as benchmark
    monkeypatch.setattr(benchmark,'get_connection',lambda:pytest.fail('Offline demo contacted PostgreSQL'))
    app=AppTest.from_file(PROJECT_ROOT/'app'/'demo.py').run(timeout=30)
    assert not app.exception
    app.button[0].click().run(timeout=30)
    assert not app.exception
    assert next(metric.value for metric in app.metric if metric.label=='Full results match') == 'YES'


def test_changed_snapshot_is_rejected(tmp_path,monkeypatch):
    import shutil
    import demo.replay as replay
    shutil.copyfile(replay.DEMO_ROOT/'evidence.json',tmp_path/'evidence.json')
    (tmp_path/'employees.bin').write_bytes(b'changed data')
    monkeypatch.setattr(replay,'DEMO_ROOT',tmp_path)
    with pytest.raises(ValueError,match='does not match'):
        replay.load_evidence()
