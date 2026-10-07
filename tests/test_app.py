"""Exercise the comparison flow without changing demo data."""
import os
from config import PROJECT_ROOT
import pytest
from streamlit.testing.v1 import AppTest

pytestmark = pytest.mark.skipif(not os.getenv('PGPASSWORD') or os.getenv('PGPASSWORD') == 'change_me', reason='PostgreSQL credentials are not configured')


def test_guided_ui_and_encoding():
    app = AppTest.from_file(PROJECT_ROOT / 'app' / 'app.py').run(timeout=30)
    assert not app.exception and not app.error
    assert [tab.label for tab in app.tabs] == ['Comparison','Dataset','Benchmarks']
    assert any('&#8595;' in element.value for element in app.markdown)
    assert any(metric.label == 'Synthetic rows' for metric in app.metric)
    assert not any(button.label == 'Create / Refresh Snapshot' for button in app.button)


def test_comparison_and_role_change():
    app = AppTest.from_file(PROJECT_ROOT / 'app' / 'app.py').run(timeout=30)
    app.button(key='run_comparison').click().run(timeout=30)
    assert not app.exception and not app.error
    assert next(metric.value for metric in app.metric if metric.label == 'All row values match') == 'YES'
    app.sidebar.selectbox[0].set_value('hr_user').run(timeout=30)
    assert not any(metric.label == 'All row values match' for metric in app.metric)


def test_query_controls_and_stale_results():
    app = AppTest.from_file(PROJECT_ROOT / 'app' / 'app.py').run(timeout=30)
    app.multiselect(key='query_columns').set_value(['name', 'salary'])
    app.checkbox(key='use_minimum').check().run(timeout=30)
    app.number_input(key='query_minimum').set_value(70000)
    app.number_input(key='query_limit').set_value(4)
    app.run(timeout=30)
    app.button(key='run_comparison').click().run(timeout=30)
    assert not app.exception and not app.error
    result = app.session_state['benchmark_result']
    assert result['correctness'].results_match
    assert len(result['reader_rows']) <= 4
    assert all(list(row) == ['name', 'salary'] and row['salary'] >= 70000 for row in result['reader_rows'])
    app.text_input(key='query_name').set_value('Bob').run(timeout=30)
    assert not any(metric.label == 'All row values match' for metric in app.metric)
    app.multiselect(key='query_columns').set_value([]).run(timeout=30)
    assert app.button(key='run_comparison').disabled
