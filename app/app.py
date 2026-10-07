"""Compare PostgreSQL RLS with the direct snapshot reader."""
from __future__ import annotations
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import streamlit as st
from benchmark.benchmark import SUPPORTED_ROLES, benchmark_role, export_binary_snapshot, get_connection, result_record, run_suite
from database.datasets import generate_dataset, set_demo_threshold
from reader.query import QuerySpec, COLUMNS

st.set_page_config(page_title='Policy-Aware Direct Snapshot Reader', page_icon=':bar_chart:', layout='wide')
st.markdown('''<style>
.path-card {border:1px solid rgba(128,128,128,.25);border-radius:12px;padding:18px;}
.path-title {font-size:1.1rem;font-weight:650;margin-bottom:14px;}
.path-flow {font-family:monospace;line-height:1.7;}
.path-arrow {color:#8caeff;font-size:1.3rem;line-height:1.2;}
.result-description {min-height:48px;color:#a4a8af;font-size:.9rem;line-height:1.5;margin:0 0 12px;}
</style>''', unsafe_allow_html=True)
st.title('Policy-Aware Direct Snapshot Reader')
st.caption('PostgreSQL row-level security and local binary snapshot filtering')


def database_summary():
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute('''SELECT count(*), count(*) FILTER (WHERE g.id IS NOT NULL),
                                     count(*) FILTER (WHERE e.department IS NULL),
                                     count(*) FILTER (WHERE e.salary IS NULL)
                              FROM public.employees e LEFT JOIN public.reader_generated_ids g USING (id)''')
            total, generated, null_department, null_salary = cursor.fetchone()
    return dict(total=total, generated=generated, original=total-generated,
                null_department=null_department, null_salary=null_salary)

try:
    summary = database_summary()
except Exception as exc:
    st.error(f'Could not read the project database: {exc}')
    st.stop()

if 'notice' in st.session_state:
    st.success(st.session_state.pop('notice'))

st.sidebar.header('Access control')
role = st.sidebar.selectbox('Role', SUPPORTED_ROLES,
                           format_func=lambda value: {'it_user':'IT', 'hr_user':'HR', 'finance_user':'Finance'}[value])
st.sidebar.caption('Visibility is determined by the selected database role.')
with st.sidebar.expander('Timing settings'):
    warmup_runs = st.number_input('Warm-up runs', min_value=0, max_value=20, value=3,
                                  help='Untimed repetitions to warm caches before measuring.')
    measured_runs = st.number_input('Measured runs', min_value=1, max_value=50, value=10,
                                    help='Timed repetitions used for the average and standard deviation.')
st.sidebar.divider()
st.sidebar.metric('Current PostgreSQL rows', f"{summary['total']:,}")
st.sidebar.caption('Snapshot refreshed automatically for each comparison.')

compare_tab, dataset_tab, batch_tab = st.tabs(['Comparison', 'Dataset', 'Benchmarks'])

with compare_tab:
    st.subheader('Compare the current dataset')
    counts = st.columns(3)
    counts[0].metric('Rows in PostgreSQL', f"{summary['total']:,}")
    counts[1].metric('Original demo rows', f"{summary['original']:,}")
    counts[2].metric('Synthetic rows', f"{summary['generated']:,}")
    st.caption('Source: PostgreSQL employees table. Snapshot format: binary COPY.')
    with st.expander('How the two paths work'):
        for column, title, steps in zip(st.columns(2), ['PostgreSQL DBMS path', 'Direct reader path'],
                                       [['SQL query', 'PostgreSQL engine', 'RLS enforcement', 'Authorized result'],
                                        ['PostgreSQL binary export', 'Binary parser', 'Policy evaluator', 'Authorized result']]):
            flow = '<div class="path-arrow">&#8595;</div>'.join(f'<div>{step}</div>' for step in steps)
            column.markdown(f'<div class="path-card"><div class="path-title">{title}</div><div class="path-flow">{flow}</div></div>', unsafe_allow_html=True)
    with st.expander('Query controls', expanded=True):
        selected_columns = st.multiselect('Returned columns', COLUMNS, default=list(COLUMNS), key='query_columns')
        salary_columns = st.columns(2)
        with salary_columns[0]:
            use_minimum = st.checkbox('Minimum salary', key='use_minimum')
            minimum = st.number_input('Salary at least', min_value=-2147483648, max_value=2147483647,
                                      value=0, disabled=not use_minimum, key='query_minimum')
        with salary_columns[1]:
            use_maximum = st.checkbox('Maximum salary', key='use_maximum')
            maximum = st.number_input('Salary at most', min_value=-2147483648, max_value=2147483647,
                                      value=120000, disabled=not use_maximum, key='query_maximum')
        exact_name = st.text_input('Exact employee name', key='query_name', help='Empty means any name. Matching is case-sensitive.')
        row_limit = st.number_input('Maximum returned rows', min_value=0, max_value=1000000, value=0,
                                   key='query_limit', help='0 means all matching rows. Results are ordered by employee ID.')
    query = None
    try:
        query = QuerySpec(tuple(selected_columns), minimum if use_minimum else None,
                          maximum if use_maximum else None, exact_name if exact_name else None,
                          row_limit if row_limit else None)
    except ValueError as exc:
        st.error(str(exc))
    with st.expander('Query and measurement details'):
        if query is not None:
            st.code(query.sql(literals=True)[0].as_string(), language='sql')
        st.write('Both paths use the same role, data and extracted policy. Timings include execution and result collection; '
                 'connection setup, snapshot export, policy extraction, predicate preparation and correctness checks are outside the timed region. '
                 'Warm-ups are untimed. PostgreSQL trials run before reader trials.')

    if st.button('Run comparison', type='primary', width='stretch', key='run_comparison', disabled=query is None):
        st.session_state.pop('benchmark_result', None)
        try:
            with st.spinner('Exporting current data, comparing authorized rows, and measuring latency...'):
                st.session_state['benchmark_result'] = benchmark_role(role, warmup_runs=int(warmup_runs), measured_runs=int(measured_runs), query=query)
        except Exception as exc:
            st.error(f'The comparison could not be completed: {exc}')

    result = st.session_state.get('benchmark_result')
    if result is not None and (result['role'] != role or query is None or result.get('query') != query.as_dict()):
        result = None
    if result is None:
        st.info('No comparison results.')
    else:
        st.divider()
        st.subheader('Authorized employee rows')
        # Headers, descriptions, tables and counts each occupy their own shared row.
        # Description wrapping therefore cannot shift only one table downward.
        headings = st.columns(2)
        headings[0].markdown('### PostgreSQL DBMS')
        headings[1].markdown('### Direct reader')
        descriptions = st.columns(2)
        descriptions[0].markdown('<div class="result-description">PostgreSQL runs the SQL query and applies RLS.</div>', unsafe_allow_html=True)
        descriptions[1].markdown('<div class="result-description">Python decodes the exported rows and applies the policy.</div>', unsafe_allow_html=True)
        tables = st.columns(2)
        for column, rows in zip(tables, [result['postgres_rows'], result['reader_rows']]):
            column.dataframe(pd.DataFrame(rows[:500], columns=result['query']['columns']),
                             width='stretch', height=350, hide_index=True)
        returned = st.columns(2)
        returned[0].caption(f"{len(result['postgres_rows']):,} authorized rows")
        returned[1].caption(f"{len(result['reader_rows']):,} authorized rows")
        st.caption('Showing up to 500 rows per table. Every returned row is included in the correctness check.')

        correctness = result['correctness']
        st.subheader('Correctness')
        checks = st.columns(3)
        checks[0].metric('No extra rows (soundness)', 'PASS' if correctness.soundness else 'FAIL')
        checks[1].metric('No missing rows (completeness)', 'PASS' if correctness.completeness else 'FAIL')
        checks[2].metric('All row values match', 'YES' if correctness.results_match else 'NO')
        if correctness.results_match:
            st.success('Both paths returned the same authorized rows and field values.')
        else:
            st.error('Result mismatch. Performance comparison is not valid for this case.')
            with st.expander('Rows that differ'):
                st.write('PostgreSQL-only rows', correctness.postgres_only_rows)
                st.write('Reader-only rows', correctness.reader_only_rows)
        with st.expander('Policy and reader scan details'):
            st.json(result['policy'])
            scans = st.columns(5)
            for col, title, key in zip(scans, ['Scanned','Returned','Denied by RLS','Query filtered','Limit excluded'], ['rows_scanned','rows_returned','rows_denied','rows_filtered','rows_limited']):
                col.metric(title, f"{result[key]:,}")
            st.caption(f"Predicate preparation: {result['reader_preparation_ms']:.3f} ms. Reference reader match: {'YES' if result['reference_match'] else 'NO'}.")
            st.caption(f"Policy extraction took {result['policy_resolution_ms']:.3f} ms, outside the scan timings.")

        st.subheader('Measured performance')
        pg, reader = result['postgres_stats'], result['reader_stats']
        timing = st.columns(3)
        timing[0].metric('PostgreSQL average', f'{pg.average_ms:.3f} ms')
        timing[1].metric('Reader average', f'{reader.average_ms:.3f} ms')
        ratio = result['speedup']
        timing[2].metric('PostgreSQL / reader latency', f'{ratio:.3f}x')
        if ratio >= 1:
            st.write(f'The reader was {ratio:.2f} times faster in this measurement.')
        else:
            st.write(f'PostgreSQL was {1/ratio:.2f} times faster in this measurement.')
        frame = pd.DataFrame([{'Path':'PostgreSQL', 'Average ms':pg.average_ms, 'Standard deviation ms':pg.standard_deviation_ms},
                              {'Path':'Direct reader', 'Average ms':reader.average_ms, 'Standard deviation ms':reader.standard_deviation_ms}])
        st.bar_chart(frame.set_index('Path')[['Average ms']])
        st.caption('Latency ratio = PostgreSQL / reader. Values above 1 favor the reader; below 1 favor PostgreSQL.')
        with st.expander('Timing samples and CSV export'):
            st.dataframe(frame, hide_index=True)
            st.caption('CSV fields: timing statistics, row counts, policy and correctness.')
            record = dict(result_record(result), policy_ast=json.dumps(result['policy']),
                          null_department_rows=result['null_department_rows'], null_salary_rows=result['null_salary_rows'])
            st.download_button('Download comparison summary (CSV)', pd.DataFrame([record]).to_csv(index=False), 'comparison_summary.csv', 'text/csv')

with dataset_tab:
    st.subheader('Dataset configuration')
    st.write(f"PostgreSQL currently contains **{summary['total']:,} employees**: **{summary['original']:,} original** and **{summary['generated']:,} synthetic** rows.")
    st.caption('Dataset changes update PostgreSQL rows, access policies and the binary snapshot.')
    st.caption(f"Current NULL values: {summary['null_department']:,} departments and {summary['null_salary']:,} salaries. "
               'Rows with NULL policy attributes may be denied by SQL comparisons.')
    sizes = [10, 1000, 10000, 100000, 1000000]
    with st.form('dataset'):
        total_rows = st.selectbox('Total employee rows', sizes, index=sizes.index(summary['total']) if summary['total'] in sizes else 2)
        null_percent = st.slider('Generated rows with missing department or salary (%)', 0, 25, 5,
                                 help='Applies separately to each column in the generated rows. Original rows are preserved.')
        threshold = st.selectbox('Access rule for every role', [0, 70000, 100000],
                                 format_func=lambda n: 'Own department only' if n == 0 else f'Own department and salary at least {n:,}')
        apply_dataset = st.form_submit_button('Apply dataset and access rule')
    st.caption('Original rows are preserved; generated rows are replaced.')
    if apply_dataset:
        try:
            with st.spinner('Writing synthetic employees into PostgreSQL and exporting the snapshot...'):
                with get_connection() as connection:
                    count = generate_dataset(connection, total_rows, null_percent)
                    set_demo_threshold(connection, threshold)
                export_binary_snapshot()
            st.session_state.pop('benchmark_result', None)
            st.session_state['notice'] = f'Dataset updated: {count:,} employees.'
            st.rerun()
        except Exception as exc:
            st.error(f'Dataset update failed: {exc}')

with batch_tab:
    st.subheader('Benchmark matrix')
    st.caption('27 cases: three roles, three dataset sizes (1,000 / 10,000 / 100,000), and three salary thresholds.')
    st.info('Dataset and policy changes are rolled back after the benchmark.')
    st.caption('Each case uses 2 warm-ups and 5 measured repetitions per path.')
    if st.button('Run all 27 benchmark cases', key='run_batch'):
        st.session_state.pop('suite_records', None)
        try:
            progress = st.progress(0)
            with st.spinner('Measuring 27 cases; this may take a minute...'):
                st.session_state['suite_records'] = run_suite(progress=lambda n,total: progress.progress(n/total))
            st.success('Benchmark complete. CSV and raw timing samples saved.')
        except Exception as exc:
            st.error(f'Batch benchmark failed: {exc}')
    records = st.session_state.get('suite_records')
    if records is None:
        saved = PROJECT_ROOT / 'results' / 'benchmark_results.csv'
        if saved.exists():
            records = pd.read_csv(saved).to_dict('records')
            st.caption('Saved benchmark results.')
    if records:
        frame = pd.DataFrame(records)
        st.dataframe(frame, hide_index=True)
        st.download_button('Download all benchmark cases (CSV)', frame.to_csv(index=False), 'benchmark_results.csv', 'text/csv')
        st.line_chart(frame[frame.minimum_salary == 0].pivot(index='dataset_size', columns='role', values='speedup'))
        st.caption('Ratio above 1 favors the reader; below 1 favors PostgreSQL.')

st.caption('Table: employees | Format: PostgreSQL binary COPY | Queries: read-only')
