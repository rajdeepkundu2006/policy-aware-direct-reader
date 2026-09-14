from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd
import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from benchmark.benchmark import (  # noqa: E402
    DEFAULT_QUERY,
    DEFAULT_SNAPSHOT_PATH,
    SUPPORTED_ROLES,
    BenchmarkStats,
    CorrectnessResult,
    benchmark_role,
    export_binary_snapshot,
    get_policy_for_role,
)


st.set_page_config(
    page_title="Policy-Aware Direct Snapshot Reader",
    page_icon="DB",
    layout="wide",
    initial_sidebar_state="expanded",
)


st.markdown(
    """
    <style>
    .hero-title {
        font-size: 2.25rem;
        font-weight: 700;
        margin-bottom: 0.2rem;
    }

    .hero-subtitle {
        font-size: 1rem;
        opacity: 0.78;
        margin-bottom: 1rem;
    }

    .path-card {
        border: 1px solid rgba(128,128,128,0.22);
        border-radius: 12px;
        padding: 1rem 1.1rem;
        min-height: 135px;
        background: rgba(128,128,128,0.035);
    }

    .path-title {
        font-size: 1.15rem;
        font-weight: 650;
        margin-bottom: 0.45rem;
    }

    .path-flow {
        font-family: monospace;
        font-size: 0.88rem;
        line-height: 1.55;
        white-space: pre-line;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


st.markdown(
    """
    <div>
        <div class="hero-title">Policy-Aware Direct Snapshot Reader</div>
        <div class="hero-subtitle">
            PostgreSQL DBMS path vs. direct snapshot reader
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.info(
    "Research prototype: a read-only direct reader operates on a frozen "
    "PostgreSQL binary snapshot while applying the database's supported "
    "row-level security policy."
)


# Sidebar
st.sidebar.header("Experiment")

role = st.sidebar.selectbox(
    "User role",
    SUPPORTED_ROLES,
    format_func=lambda value: value.replace("_", " ").title(),
)

warmup_runs = st.sidebar.number_input(
    "Warm-up runs",
    min_value=0,
    max_value=20,
    value=3,
    step=1,
)

measured_runs = st.sidebar.number_input(
    "Measured runs",
    min_value=1,
    max_value=50,
    value=10,
    step=1,
)

st.sidebar.markdown("---")
st.sidebar.caption("Snapshot")

if DEFAULT_SNAPSHOT_PATH.exists():
    st.sidebar.success("employees.bin is available")
else:
    st.sidebar.warning("employees.bin has not been created")


# Architecture
st.subheader("How the two paths differ")

path_col1, path_col2 = st.columns(2)

with path_col1:
    st.markdown(
        """
        <div class="path-card">
            <div class="path-title">PostgreSQL DBMS Path</div>
            <div class="path-flow">
            SQL query
                ↓
            PostgreSQL engine
                ↓
            RLS enforcement
                ↓
            Authorized result
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with path_col2:
    st.markdown(
        """
        <div class="path-card">
            <div class="path-title">Direct Reader Path</div>
            <div class="path-flow">
            employees.bin
                ↓
            Binary parser
                ↓
            Policy evaluator
                ↓
            Authorized result
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# Query
st.subheader("Read Request")

st.code(DEFAULT_QUERY, language="sql")

query_col1, query_col2 = st.columns(2)

with query_col1:
    st.write(f"**Role:** `{role}`")

with query_col2:
    st.write("**Table:** `employees`")


# Actions
action_col1, action_col2 = st.columns(2)

with action_col1:
    refresh_clicked = st.button(
        "Create / Refresh Snapshot",
        use_container_width=True,
    )

with action_col2:
    run_clicked = st.button(
        "Run Full Comparison",
        type="primary",
        use_container_width=True,
    )


if refresh_clicked:
    try:
        with st.spinner("Exporting PostgreSQL binary snapshot..."):
            snapshot = export_binary_snapshot(DEFAULT_SNAPSHOT_PATH)

        st.success(f"Snapshot ready: {snapshot}")

    except Exception as exc:
        st.error("Snapshot export failed.")
        with st.expander("Technical details"):
            st.exception(exc)


if run_clicked:
    try:
        if not DEFAULT_SNAPSHOT_PATH.exists():
            with st.spinner("Creating binary snapshot..."):
                export_binary_snapshot(DEFAULT_SNAPSHOT_PATH)

        with st.spinner(
            "Running PostgreSQL baseline, direct reader, "
            "correctness checks, and timing..."
        ):
            result = benchmark_role(
                role,
                snapshot_path=DEFAULT_SNAPSHOT_PATH,
                warmup_runs=int(warmup_runs),
                measured_runs=int(measured_runs),
            )

        st.session_state["benchmark_result"] = result
        st.session_state["benchmark_role"] = role

        st.success("Experiment completed successfully.")

    except Exception as exc:
        st.error("The experiment could not be completed.")
        with st.expander("Technical details"):
            st.exception(exc)


result = st.session_state.get("benchmark_result")


if result is None:
    st.divider()
    st.subheader("Ready for demonstration")
    st.write(
        "Choose a role, then click **Run Full Comparison**. "
        "The application will show both execution paths, the active policy, "
        "correctness, and measured latency."
    )

else:
    correctness: CorrectnessResult = result["correctness"]
    postgres_stats: BenchmarkStats = result["postgres_stats"]
    reader_stats: BenchmarkStats = result["reader_stats"]

    st.divider()

    # Experiment summary
    st.subheader("Experiment Configuration")

    config_col1, config_col2, config_col3 = st.columns(3)

    config_col1.metric(
        "Role",
        role.replace("_", " ").title(),
    )

    config_col2.metric(
        "Table",
        "employees",
    )

    config_col3.metric(
        "Snapshot",
        "employees.bin",
    )

    # Policy
    st.subheader("Active Row-Level Security Policy")

    try:
        policy = get_policy_for_role(role)
        st.json(policy)
    except Exception as exc:
        st.error("Could not retrieve the extracted policy.")
        with st.expander("Technical details"):
            st.exception(exc)

    # Results
    st.subheader("Execution Results")

    postgres_rows = result["postgres_rows"]
    reader_rows = result["reader_rows"]

    postgres_col, reader_col = st.columns(2)

    with postgres_col:
        st.markdown("### PostgreSQL DBMS")

        st.caption(
            "The SQL query is executed through PostgreSQL and "
            "RLS is enforced by the DBMS."
        )

        if postgres_rows:
            st.dataframe(
                pd.DataFrame(postgres_rows),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.warning("No rows returned.")

        st.write(f"Rows returned: **{len(postgres_rows)}**")

    with reader_col:
        st.markdown("### Direct Reader")

        st.caption(
            "The Python reader scans the frozen binary snapshot "
            "and applies the extracted policy locally."
        )

        if reader_rows:
            st.dataframe(
                pd.DataFrame(reader_rows),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.warning("No rows returned.")

        st.write(f"Rows returned: **{len(reader_rows)}**")

    # Correctness
    st.divider()
    st.subheader("Correctness Oracle")

    st.caption(
        "PostgreSQL is the baseline. The direct reader must not return "
        "forbidden rows or omit rows authorized by PostgreSQL."
    )

    corr_col1, corr_col2, corr_col3 = st.columns(3)

    with corr_col1:
        st.metric(
            "Soundness",
            "PASS" if correctness.soundness else "FAIL",
        )

    with corr_col2:
        st.metric(
            "Completeness",
            "PASS" if correctness.completeness else "FAIL",
        )

    with corr_col3:
        st.metric(
            "Results Match",
            "YES" if correctness.results_match else "NO",
        )

    if correctness.results_match:
        st.success(
            "Correctness check passed: both execution paths returned "
            "equivalent authorized result sets."
        )
    else:
        st.error(
            "Correctness check failed: the two result sets differ."
        )

        mismatch_col1, mismatch_col2 = st.columns(2)

        with mismatch_col1:
            st.markdown("#### PostgreSQL-only rows")
            if correctness.postgres_only_rows:
                st.dataframe(
                    pd.DataFrame(correctness.postgres_only_rows),
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.write("None")

        with mismatch_col2:
            st.markdown("#### Direct-reader-only rows")
            if correctness.reader_only_rows:
                st.dataframe(
                    pd.DataFrame(correctness.reader_only_rows),
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.write("None")

    # Performance
    st.divider()
    st.subheader("Performance")

    perf_col1, perf_col2, perf_col3 = st.columns(3)

    with perf_col1:
        st.metric(
            "PostgreSQL average",
            f"{postgres_stats.average_ms:.3f} ms",
        )

    with perf_col2:
        st.metric(
            "Direct Reader average",
            f"{reader_stats.average_ms:.3f} ms",
        )

    with perf_col3:
        st.metric(
            "Speedup",
            f"{result['speedup']:.3f}x",
        )

    timing_df = pd.DataFrame(
        [
            {
                "Path": "PostgreSQL",
                "Average latency (ms)": postgres_stats.average_ms,
                "Std. deviation (ms)": postgres_stats.standard_deviation_ms,
            },
            {
                "Path": "Direct Reader",
                "Average latency (ms)": reader_stats.average_ms,
                "Std. deviation (ms)": reader_stats.standard_deviation_ms,
            },
        ]
    )

    st.dataframe(
        timing_df,
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("### Average latency comparison")

    chart_df = timing_df.set_index("Path")[["Average latency (ms)"]]
    st.bar_chart(chart_df)

    # Interpretation
    st.subheader("Measured Interpretation")

    if result["speedup"] > 1:
        st.write(
            f"For this measured case, the direct reader had lower average "
            f"latency, with a measured ratio of {result['speedup']:.3f}x."
        )
    elif result["speedup"] < 1:
        st.write(
            f"For this measured case, the direct reader had higher average "
            f"latency, with a measured ratio of {result['speedup']:.3f}x."
        )
    else:
        st.write(
            "For this measured case, the two execution paths had "
            "approximately equal average latency."
        )

    st.caption(
        "This result describes the selected dataset and role only; "
        "it is not a general performance claim."
    )

    with st.expander("Current prototype scope"):
        st.write(
            "Read-only, single-table execution over a frozen PostgreSQL "
            "binary COPY snapshot with the supported row-level policy grammar. "
            "Live heap parsing, joins, writes, concurrent updates, masking, "
            "auditing, arbitrary policy expressions, and LLM-generated heap "
            "parsing are outside this first version."
        )
