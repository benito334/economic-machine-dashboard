"""Streamlit entry point for the Indicators Machine.

Phase 1C will replace this status view with the full diagnostic terminal. This
entry point intentionally remains read-only so it can run beside ingestion.
"""
from __future__ import annotations

import os
from pathlib import Path

import duckdb
import streamlit as st


DB_PATH = Path(
    os.environ.get(
        "DB_PATH",
        "/mnt/data/db/all_weather/indicators_machine/signals.duckdb",
    )
)


st.set_page_config(page_title="Indicators Machine", layout="wide")
st.title("Indicators Machine")
st.caption("Phase 1A signal-store status")

if not DB_PATH.exists():
    st.info("The signal database has not been created yet. Run the pipeline first.")
    st.stop()

try:
    with duckdb.connect(str(DB_PATH), read_only=True) as conn:
        latest = conn.execute(
            """
            SELECT * EXCLUDE (ingested_at)
            FROM signals
            QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY as_of DESC) = 1
            ORDER BY force, id
            """
        ).df()
except Exception as exc:
    st.warning(f"The signal store is temporarily unavailable: {exc}")
    st.stop()

if latest.empty:
    st.info("The signal database is empty. Run the pipeline to ingest signals.")
else:
    metric_columns = st.columns(3)
    metric_columns[0].metric("Latest signals", len(latest))
    metric_columns[1].metric("Forces", latest["force"].nunique())
    metric_columns[2].metric("Stale signals", int(latest["is_stale"].sum()))
    st.dataframe(latest, use_container_width=True, hide_index=True)
