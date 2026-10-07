"""Teacher demonstration: no PostgreSQL installation or credentials required."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import pandas as pd
import streamlit as st
from demo.replay import load_evidence, replay_role

st.set_page_config(page_title='DBMS Project Demonstration', page_icon=':bar_chart:', layout='wide')
st.title('Policy-Aware Direct Snapshot Reader')
st.info('Offline review demo: Python runs the real snapshot reader. PostgreSQL results and latency measurements were recorded previously; no database is contacted here.')
evidence = load_evidence()
st.caption(f"Evidence captured: {evidence['captured_at_utc']} | Synthetic employees only")
role = st.selectbox('View role', ['it_user','hr_user','finance_user'], format_func=lambda r:r.replace('_user','').upper())
columns = st.columns(3)
columns[0].metric('Snapshot rows', f"{evidence['summary']['total']:,}")
columns[1].metric('Original demo rows', evidence['summary']['original'])
columns[2].metric('Generated employees', f"{evidence['summary']['generated']:,}")
if st.button('Run local reader and verify saved baseline', type='primary', width='stretch'):
    _, case, rows, correctness = replay_role(role)
    st.session_state['replay'] = dict(role=role, case=case, rows=rows, correctness=correctness)
result=st.session_state.get('replay')
if result and result['role'] == role:
    checks=st.columns(3)
    checks[0].metric('Soundness', 'PASS' if result['correctness'].soundness else 'FAIL')
    checks[1].metric('Completeness', 'PASS' if result['correctness'].completeness else 'FAIL')
    checks[2].metric('Full results match', 'YES' if result['correctness'].results_match else 'NO')
    headings=st.columns(2)
    headings[0].subheader('Recorded PostgreSQL result')
    headings[1].subheader('Reader executed now')
    tables=st.columns(2)
    for column, rows in zip(tables,[result['case']['postgres_rows'],result['rows']]):
        column.dataframe(pd.DataFrame(rows[:500]), width='stretch', height=350, hide_index=True)
    st.caption(f"{len(result['rows']):,} authorized rows. Tables show up to 500; every row is checked against the saved baseline.")
    with st.expander('Extracted policy'):
        st.json(result['case']['policy'])
    st.subheader('Previously measured latency')
    st.caption('Both paths were measured on the original project machine. These timings are not measured by this offline replay.')
    measured=result['case']['measurement']
    timings=st.columns(2)
    timings[0].metric('Recorded PostgreSQL average', f"{measured['postgres_avg_ms']:.3f} ms")
    timings[1].metric('Recorded reader average', f"{measured['reader_avg_ms']:.3f} ms")
with st.expander('All 27 recorded research cases'):
    frame=pd.DataFrame(evidence['suite'])
    st.dataframe(frame,hide_index=True)
    st.download_button('Download recorded benchmark summaries',frame.to_csv(index=False),'benchmark_results.csv','text/csv')
st.write('For new PostgreSQL queries, larger datasets or fresh database timings, run the live app with run.cmd and local PostgreSQL. This offline demo checks the bundled frozen snapshot only.')
