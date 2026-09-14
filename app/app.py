"""
Streamlit demonstration application for the
Policy-Aware Direct Snapshot Reader project.

The UI is designed around the final research comparison:

PostgreSQL DBMS path
        VS
Direct Reader path

The direct-reader integration is optional until
reader/snapshot_reader.py becomes available.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd
import streamlit as st


# ---------------------------------------------------------------------------
# Make project-root imports work when Streamlit launches app/app.py
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from benchmark.benchmark import (  # noqa: E402
    DEFAULT_QUERY,
    SUPPORTED_ROLES,
    compare_results,
    run_postgres_query,
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
    "Comparison of the conventional PostgreSQL DBMS path "
    "and the policy-aware direct snapshot reader."
)

st.info(
    "The first prototype uses a frozen PostgreSQL binary snapshot. "
    "The direct-reader panel will become active when the reader module "
    "is integrated."
)


# ---------------------------------------------------------------------------
# Request controls
# ---------------------------------------------------------------------------

st.subheader("Query Configuration")

role = st.selectbox(
    "Select role",
    SUPPORTED_ROLES,
)

st.code(DEFAULT_QUERY, language="sql")

run_button = st.button(
    "Run PostgreSQL Baseline",
    type="primary",
)


# ---------------------------------------------------------------------------
# PostgreSQL baseline execution
# ---------------------------------------------------------------------------

if run_button:
    try:
        postgres_rows = run_postgres_query(role)

        st.session_state["postgres_rows"] = postgres_rows
        st.session_state["selected_role"] = role

    except Exception as exc:
        st.error(
            "PostgreSQL baseline execution failed."
        )

        st.exception(exc)


# ---------------------------------------------------------------------------
# Display PostgreSQL result
# ---------------------------------------------------------------------------

postgres_rows = st.session_state.get("postgres_rows")

if postgres_rows is not None:

    st.divider()

    st.subheader("PostgreSQL DBMS Path")

    st.caption(
        "This result is produced by executing the SQL query through "
        "PostgreSQL under the selected role."
    )

    if postgres_rows:
        postgres_df = pd.DataFrame(postgres_rows)
        st.dataframe(
            postgres_df,
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.warning("PostgreSQL returned zero rows.")

    st.write(f"Rows returned: **{len(postgres_rows)}**")


# ---------------------------------------------------------------------------
# Direct reader placeholder
# ---------------------------------------------------------------------------

st.divider()

st.subheader("Direct Reader Path")

reader_module_path = PROJECT_ROOT / "reader" / "snapshot_reader.py"

if reader_module_path.exists():

    st.success(
        "reader/snapshot_reader.py exists. "
        "Direct-reader integration can now be connected."
    )

    st.caption(
        "The actual function interface is connected after the reader "
        "implementation is available and verified."
    )

else:

    st.warning(
        "The direct reader is not integrated yet. "
        "This panel will become active when Ishaan's reader implementation "
        "is available."
    )


# ---------------------------------------------------------------------------
# Correctness placeholder
# ---------------------------------------------------------------------------

st.divider()

st.subheader("Correctness")

if postgres_rows is None:

    st.write(
        "Run the PostgreSQL baseline first. "
        "The correctness oracle requires both result sets."
    )

else:

    st.write(
        "The correctness oracle will compare PostgreSQL and direct-reader "
        "results using soundness and completeness once the reader is integrated."
    )

    col1, col2, col3 = st.columns(3)

    col1.metric("Soundness", "Pending")
    col2.metric("Completeness", "Pending")
    col3.metric("Results Match", "Pending")


# ---------------------------------------------------------------------------
# Performance placeholder
# ---------------------------------------------------------------------------

st.divider()

st.subheader("Performance")

st.write(
    "The final interface will report PostgreSQL average latency, "
    "reader average latency, standard deviations, and speedup."
)

col1, col2, col3 = st.columns(3)

col1.metric("PostgreSQL", "Pending")
col2.metric("Direct Reader", "Pending")
col3.metric("Speedup", "Pending")