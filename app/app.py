"""A guided demonstration of PostgreSQL RLS and the direct snapshot reader."""
from __future__ import annotations
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import streamlit as st
from benchmark.benchmark import DEFAULT_QUERY, SUPPORTED_ROLES, benchmark_role, export_binary_snapshot, get_connection, result_record, run_suite
from database.datasets import generate_dataset, set_demo_threshold

st.set_page_config(page_title='Policy-Aware Direct Snapshot Reader', page_icon=':bar_chart:', layout='wide')
st.markdown('''<style>
.path-card {border:1px solid rgba(128,128,128,.25);border-radius:12px;padding:18px;}
.path-title {font-size:1.1rem;font-weight:650;margin-bottom:14px;}
.path-flow {font-family:monospace;line-height:1.7;}
.path-arrow {color:#8caeff;font-size:1.3rem;line-height:1.2;}
.result-description {min-height:48px;color:#a4a8af;font-size:.9rem;line-height:1.5;margin:0 0 12px;}
</style>''', unsafe_allow_html=True)
st.title('Policy-Aware Direct Snapshot Reader')
st.caption('DBMS semester project | PostgreSQL RLS compared with a Python binary snapshot reader')
st.caption('Evaluator without PostgreSQL? Run run.cmd demo for the local reader replay, or open demo/index.html for saved evidence.')


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

st.sidebar.header('Compare one role')
role = st.sidebar.selectbox('Role', SUPPORTED_ROLES,
                           format_func=lambda value: {'it_user':'IT', 'hr_user':'HR', 'finance_user':'Finance'}[value])
st.sidebar.caption('This chooses whose rows are visible. It does not change the database dataset.')
with st.sidebar.expander('Timing settings'):
    warmup_runs = st.number_input('Warm-up runs', min_value=0, max_value=20, value=3,
                                  help='Untimed repetitions to warm caches before measuring.')
    measured_runs = st.number_input('Measured runs', min_value=1, max_value=50, value=10,
                                    help='Timed repetitions used for the average and standard deviation.')
st.sidebar.divider()
st.sidebar.metric('Current PostgreSQL rows', f"{summary['total']:,}")
st.sidebar.caption('Every comparison automatically exports fresh PostgreSQL data. No manual snapshot refresh is needed.')

compare_tab, dataset_tab, batch_tab = st.tabs(['1. Compare results', '2. Change dataset', '3. Batch benchmarks'])

with compare_tab:
    st.subheader('Compare the current dataset')
    st.write('Choose a role on the left, then run the comparison. To change how many rows are in PostgreSQL, use the Change dataset tab.')
    counts = st.columns(3)
    counts[0].metric('Rows in PostgreSQL', f"{summary['total']:,}")
    counts[1].metric('Original demo rows', f"{summary['original']:,}")
    counts[2].metric('Synthetic rows', f"{summary['generated']:,}")
    st.caption('The generated employees are stored in PostgreSQL first. The binary snapshot is exported from those same database rows.')
    with st.expander('How the two paths work'):
        for column, title, steps in zip(st.columns(2), ['PostgreSQL DBMS path', 'Direct reader path'],
                                       [['SQL query', 'PostgreSQL engine', 'RLS enforcement', 'Authorized result'],
                                        ['PostgreSQL binary export', 'Binary parser', 'Policy evaluator', 'Authorized result']]):
            flow = '<div class="path-arrow">&#8595;</div>'.join(f'<div>{step}</div>' for step in steps)
            column.markdown(f'<div class="path-card"><div class="path-title">{title}</div><div class="path-flow">{flow}</div></div>', unsafe_allow_html=True)
    with st.expander('Query and measurement details'):
        st.code(DEFAULT_QUERY, language='sql')
        st.write('Both paths use the same role, data and extracted policy. Timings include execution and result collection; '
                 'connection setup, snapshot export, policy extraction and correctness checks are outside the timed region. '
                 'Warm-ups are untimed. PostgreSQL trials run before reader trials.')

    if st.button('Run comparison', type='primary', width='stretch', key='run_comparison'):
        st.session_state.pop('benchmark_result', None)
        try:
            with st.spinner('Exporting current data, comparing authorized rows, and measuring latency...'):
                st.session_state['benchmark_result'] = benchmark_role(role, warmup_runs=int(warmup_runs), measured_runs=int(measured_runs))
        except Exception as exc:
            st.error(f'The comparison could not be completed: {exc}')

    result = st.session_state.get('benchmark_result')
    if result is not None and result['role'] != role:
        result = None
    if result is None:
        st.info('Ready: run a comparison to see both result tables, correctness and latency.')
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
            column.dataframe(pd.DataFrame(rows[:500], columns=['id','name','department','salary']),
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
            st.error('The results differ. Treat these performance numbers as an invalid correctness case.')
            with st.expander('Rows that differ'):
                st.write('PostgreSQL-only rows', correctness.postgres_only_rows)
                st.write('Reader-only rows', correctness.reader_only_rows)
        with st.expander('Policy and reader scan details'):
            st.json(result['policy'])
            scans = st.columns(3)
            for col, title, key in zip(scans, ['Scanned','Returned','Denied'], ['rows_scanned','rows_returned','rows_denied']):
                col.metric(title, f"{result[key]:,}")
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
        st.caption('Lower latency is better. A small dataset can favor Python; larger scans can favor PostgreSQL. This is a measured result, not a guaranteed speedup.')
        with st.expander('Timing samples and CSV export'):
            st.dataframe(frame, hide_index=True)
            st.write('This CSV contains one summary row for this role and dataset: timings, row counts, policy and correctness. It does not export the employee table.')
            record = dict(result_record(result), policy_ast=json.dumps(result['policy']),
                          null_department_rows=result['null_department_rows'], null_salary_rows=result['null_salary_rows'])
            st.download_button('Download comparison summary (CSV)', pd.DataFrame([record]).to_csv(index=False), 'comparison_summary.csv', 'text/csv')

with dataset_tab:
    st.subheader('Change the data used in the demonstration')
    st.write(f"PostgreSQL currently contains **{summary['total']:,} employees**: **{summary['original']:,} original** and **{summary['generated']:,} synthetic** rows.")
    st.write('Use this only when you want a different dataset size or access rule. Applying it writes synthetic employees into PostgreSQL, '
             'updates the three demo policies, and exports employees.bin. Then return to Compare results.')
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
    st.caption('Original rows are preserved. Only synthetic rows previously created by this generator are replaced. '
               'This changes the data; it does not run a timed comparison.')
    if apply_dataset:
        try:
            with st.spinner('Writing synthetic employees into PostgreSQL and exporting the snapshot...'):
                with get_connection() as connection:
                    count = generate_dataset(connection, total_rows, null_percent)
                    set_demo_threshold(connection, threshold)
                export_binary_snapshot()
            st.session_state.pop('benchmark_result', None)
            st.session_state['notice'] = f'Dataset updated: {count:,} employees. Open Compare results and click Run comparison.'
            st.rerun()
        except Exception as exc:
            st.error(f'Dataset update failed: {exc}')

with batch_tab:
    st.subheader('Run the 27-case research benchmark')
    st.write('This optional batch is for your submission report. It automatically tests all three roles, '
             '1,000 / 10,000 / 100,000 rows, and three salary rules. You do not need to change the dataset manually first.')
    st.info('Batch changes are temporary. Your current demonstration data and policies are restored afterward.')
    st.caption('Uses 2 warm-ups and 5 timed runs per path for each case. The sidebar timing settings apply only to single comparisons.')
    if st.button('Run all 27 benchmark cases', key='run_batch'):
        st.session_state.pop('suite_records', None)
        try:
            progress = st.progress(0)
            with st.spinner('Measuring 27 cases; this may take a minute...'):
                st.session_state['suite_records'] = run_suite(progress=lambda n,total: progress.progress(n/total))
            st.success('Saved the CSV, raw timing samples and submission report. Your demonstration dataset is unchanged.')
        except Exception as exc:
            st.error(f'Batch benchmark failed: {exc}')
    records = st.session_state.get('suite_records')
    if records is None:
        saved = PROJECT_ROOT / 'results' / 'benchmark_results.csv'
        if saved.exists():
            records = pd.read_csv(saved).to_dict('records')
            st.caption('Showing previously saved batch results. Run the batch again to replace them.')
    if records:
        frame = pd.DataFrame(records)
        st.dataframe(frame, hide_index=True)
        st.download_button('Download all benchmark cases (CSV)', frame.to_csv(index=False), 'benchmark_results.csv', 'text/csv')
        st.line_chart(frame[frame.minimum_salary == 0].pivot(index='dataset_size', columns='role', values='speedup'))
        st.caption('Ratio above 1 favors the reader; below 1 favors PostgreSQL.')

st.caption('Scope: trusted local demo; one table, read-only queries, frozen binary COPY snapshots and a restricted policy grammar. No live heap-page parsing.')
