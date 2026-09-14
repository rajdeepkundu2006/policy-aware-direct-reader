"""
Streamlit demonstration UI for the
Policy-Aware Direct Snapshot Reader project.

The application demonstrates two execution paths:

1. Conventional PostgreSQL DBMS path
   SQL -> PostgreSQL -> RLS -> result

2. Direct-reader path
   employees.bin -> Python parser -> policy evaluation -> result

The UI compares:
- PostgreSQL result
- Direct-reader result
- Soundness
- Completeness
- Result equality
- Average latency
- Standard deviation
- Speedup
"""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd
import streamlit as st


# ---------------------------------------------------------------------------
# Project-root import setup
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Policy-Aware Direct Snapshot Reader",
    page_icon="DB",
    layout="wide",
)


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.title("Policy-Aware Direct Snapshot Reader")

st.write(
    "Experimental comparison between the conventional PostgreSQL "
    "DBMS execution path and the policy-aware direct snapshot reader."
)

st.info(
    "Current prototype scope: one table, read-only queries, "
    "PostgreSQL binary COPY snapshot, and supported row-level policies."
)


# ---------------------------------------------------------------------------
# Sidebar / experiment configuration
# ---------------------------------------------------------------------------

st.sidebar.header("Experiment Configuration")

role = st.sidebar.selectbox(
    "Select role",
    SUPPORTED_ROLES,
    format_func=lambda value: value.replace("_", " ").title(),
)

measured_runs = st.sidebar.number_input(
    "Measured benchmark runs",
    min_value=1,
    max_value=30,
    value=10,
    step=1,
)

warmup_runs = st.sidebar.number_input(
    "Warm-up runs",
    min_value=0,
    max_value=10,
    value=3,
    step=1,
)

st.sidebar.markdown("---")
st.sidebar.write("Snapshot")

if DEFAULT_SNAPSHOT_PATH.exists():
    st.sidebar.success("employees.bin exists")
else:
    st.sidebar.warning("employees.bin not created yet")


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------

st.subheader("Logical Query")

st.code(
    DEFAULT_QUERY,
    language="sql",
)

st.caption(
    "The same logical read is evaluated through PostgreSQL and through "
    "the direct reader for comparison."
)


# ---------------------------------------------------------------------------
# Buttons
# ---------------------------------------------------------------------------

button_col1, button_col2 = st.columns(2)

with button_col1:
    create_snapshot_button = st.button(
        "Create / Refresh Binary Snapshot",
        use_container_width=True,
    )

with button_col2:
    run_button = st.button(
        "Run Full Comparison",
        type="primary",
        use_container_width=True,
    )


# ---------------------------------------------------------------------------
# Snapshot creation
# ---------------------------------------------------------------------------

if create_snapshot_button:
    try:
        with st.spinner("Creating PostgreSQL binary snapshot..."):
            snapshot_path = export_binary_snapshot()

        st.success(
            f"Binary snapshot created successfully: {snapshot_path}"
        )

    except Exception as exc:
        st.error("Binary snapshot creation failed.")

        with st.expander("Show error details"):
            st.exception(exc)


# ---------------------------------------------------------------------------
# Full experiment
# ---------------------------------------------------------------------------

if run_button:
    try:
        with st.spinner(
            "Running PostgreSQL baseline, direct reader, "
            "correctness check, and benchmark..."
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
        st.error("The experiment failed.")

        with st.expander("Show error details"):
            st.exception(exc)


# ---------------------------------------------------------------------------
# Display result
# ---------------------------------------------------------------------------

result = st.session_state.get("benchmark_result")


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------

if result is None:
    st.divider()

    st.subheader("Ready for Demonstration")

    st.write(
        "Select a role from the sidebar and click "
        "**Run Full Comparison**."
    )

    st.markdown(
        """
### What the application demonstrates

**PostgreSQL DBMS path**

SQL query  
↓  
PostgreSQL  
↓  
RLS enforcement  
↓  
Authorized rows

**Direct-reader path**

employees.bin  
↓  
Python binary parser  
↓  
Policy evaluator  
↓  
Authorized rows

The two results are then compared for correctness and timed for performance.
"""
    )


# ---------------------------------------------------------------------------
# Result state
# ---------------------------------------------------------------------------

else:
    correctness: CorrectnessResult = result["correctness"]
    postgres_stats: BenchmarkStats = result["postgres_stats"]
    reader_stats: BenchmarkStats = result["reader_stats"]

    # =======================================================================
    # Experiment configuration
    # =======================================================================

    st.divider()

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

    # =======================================================================
    # Active policy
    # =======================================================================

    st.subheader("Active Row-Level Security Policy")

    try:
        policy = get_policy_for_role(role)
        st.json(policy)

    except Exception as exc:
        st.error("Unable to retrieve the extracted policy.")

        with st.expander("Show policy error"):
            st.exception(exc)

    # =======================================================================
    # Execution results
    # =======================================================================

    st.subheader("Execution Results")

    postgres_col, reader_col = st.columns(2)

    # -----------------------------------------------------------------------
    # PostgreSQL
    # -----------------------------------------------------------------------

    with postgres_col:
        st.markdown("### PostgreSQL DBMS Path")

        st.caption(
            "The query is executed through PostgreSQL and "
            "PostgreSQL applies RLS."
        )

        postgres_rows = result["postgres_rows"]

        if postgres_rows:
            postgres_df = pd.DataFrame(postgres_rows)

            st.dataframe(
                postgres_df,
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.warning(
                "PostgreSQL returned zero authorized rows."
            )

        st.metric(
            "Rows returned",
            len(postgres_rows),
        )

    # -----------------------------------------------------------------------
    # Direct reader
    # -----------------------------------------------------------------------

    with reader_col:
        st.markdown("### Direct Reader Path")

        st.caption(
            "The Python reader scans the frozen binary snapshot "
            "and applies the policy locally."
        )

        reader_rows = result["reader_rows"]

        if reader_rows:
            reader_df = pd.DataFrame(reader_rows)

            st.dataframe(
                reader_df,
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.warning(
                "The direct reader returned zero authorized rows."
            )

        st.metric(
            "Rows returned",
            len(reader_rows),
        )

    # =======================================================================
    # Correctness
    # =======================================================================

    st.divider()

    st.subheader("Correctness Oracle")

    st.write(
        "PostgreSQL is treated as the baseline. "
        "The direct-reader result is compared against it."
    )

    correctness_col1, correctness_col2, correctness_col3 = st.columns(3)

    # -----------------------------------------------------------------------
    # Soundness
    # -----------------------------------------------------------------------

    with correctness_col1:
        st.metric(
            "Soundness",
            "PASS" if correctness.soundness else "FAIL",
        )

        if correctness.soundness:
            st.success("No unauthorized direct-reader rows detected.")
        else:
            st.error("Direct reader returned an unauthorized row.")

    # -----------------------------------------------------------------------
    # Completeness
    # -----------------------------------------------------------------------

    with correctness_col2:
        st.metric(
            "Completeness",
            "PASS" if correctness.completeness else "FAIL",
        )

        if correctness.completeness:
            st.success("No PostgreSQL-authorized rows were omitted.")
        else:
            st.error("Direct reader omitted an authorized row.")

    # -----------------------------------------------------------------------
    # Overall match
    # -----------------------------------------------------------------------

    with correctness_col3:
        st.metric(
            "Results Match",
            "YES" if correctness.results_match else "NO",
        )

        if correctness.results_match:
            st.success("PostgreSQL and direct-reader results match.")
        else:
            st.error("PostgreSQL and direct-reader results differ.")

    # -----------------------------------------------------------------------
    # Mismatch details
    # -----------------------------------------------------------------------

    if not correctness.results_match:
        st.warning(
            "The two execution paths produced different result sets."
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

    # =======================================================================
    # Performance
    # =======================================================================

    st.divider()

    st.subheader("Performance")

    performance_col1, performance_col2, performance_col3 = st.columns(3)

    performance_col1.metric(
        "PostgreSQL Average",
        f"{postgres_stats.average_ms:.3f} ms",
    )

    performance_col2.metric(
        "Direct Reader Average",
        f"{reader_stats.average_ms:.3f} ms",
    )

    performance_col3.metric(
        "Speedup",
        f"{result['speedup']:.3f}x",
    )

    # -----------------------------------------------------------------------
    # Detailed timing table
    # -----------------------------------------------------------------------

    timing_df = pd.DataFrame(
        [
            {
                "Execution Path": "PostgreSQL",
                "Average Latency (ms)": postgres_stats.average_ms,
                "Standard Deviation (ms)": (
                    postgres_stats.standard_deviation_ms
                ),
            },
            {
                "Execution Path": "Direct Reader",
                "Average Latency (ms)": reader_stats.average_ms,
                "Standard Deviation (ms)": (
                    reader_stats.standard_deviation_ms
                ),
            },
        ]
    )

    st.dataframe(
        timing_df,
        use_container_width=True,
        hide_index=True,
    )

    # -----------------------------------------------------------------------
    # Chart
    # -----------------------------------------------------------------------

    st.markdown("### Average Latency Comparison")

    chart_df = timing_df.set_index("Execution Path")[
        ["Average Latency (ms)"]
    ]

    st.bar_chart(chart_df)

    # =======================================================================
    # Interpretation
    # =======================================================================

    st.markdown("### Interpretation")

    if result["speedup"] > 1:
        st.write(
            f"For this measured case, the direct reader was "
            f"{result['speedup']:.3f}x as fast as the PostgreSQL path "
            f"according to average latency."
        )

    elif result["speedup"] < 1:
        st.write(
            f"For this measured case, the direct reader was slower "
            f"than the PostgreSQL path. The measured speedup value was "
            f"{result['speedup']:.3f}x."
        )

    else:
        st.write(
            "For this measured case, the two execution paths had "
            "approximately equal average latency."
        )

    st.caption(
        "This is a measured result for the selected dataset and role; "
        "it is not a general performance claim about PostgreSQL."
    )