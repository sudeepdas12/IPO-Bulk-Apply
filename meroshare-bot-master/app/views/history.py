"""Audit history view for Meroshare AutoPilot."""

from __future__ import annotations

import json
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from bot.history_manager import HistoryManager


@st.dialog("Clear history confirmation")
def clear_history_dialog(history_mgr: HistoryManager) -> None:
    """Destructive confirmation to erase historical run logs."""
    st.warning("Are you sure you want to permanently erase all application run history?", icon=":material/warning:")
    confirm = st.checkbox("Yes, permanently clear audit logs.")
    if st.button("Clear history", icon=":material/delete_forever:", disabled=not confirm, width="stretch"):
        history_mgr.clear()
        st.success("History logs cleared.", icon=":material/check_circle:")
        st.rerun()


def render_history_audit(history_mgr: HistoryManager) -> None:
    """Render the execution history audit view."""
    st.title("Run history")
    st.caption("Immutable audit log of historical application batches and execution outcomes.")

    records = history_mgr.get_history()

    # Toolbar
    c_search, c_clear, c_export = st.columns([3, 1, 1], vertical_alignment="center")
    with c_search:
        search_query = st.text_input("Filter history", placeholder="Search by company or engine...", label_visibility="collapsed")
    with c_clear:
        if st.button("Clear history", icon=":material/delete:", disabled=len(records) == 0, width="stretch"):
            clear_history_dialog(history_mgr)
    with c_export:
        if records:
            json_data = json.dumps(records, indent=2).encode("utf-8")
            st.download_button(
                "Export JSON",
                data=json_data,
                file_name="application_history.json",
                mime="application/json",
                icon=":material/download:",
                width="stretch",
            )

    st.write("")

    filtered = []
    for r in records:
        comp = r.get("company", "").lower()
        eng = r.get("engine", "").lower()
        q = search_query.lower().strip()
        if not q or (q in comp or q in eng):
            filtered.append(r)

    if filtered:
        for idx, run in enumerate(filtered):
            with st.container(border=True):
                h1, h2, h3, h4 = st.columns([3, 1.5, 1.5, 1.5], vertical_alignment="center")
                with h1:
                    st.markdown(f"#### {run.get('company', 'Unknown Issue')}")
                    st.caption(f"Run ID: `{run.get('id', 'N/A')}` · {run.get('timestamp', 'N/A')}")
                with h2:
                    st.badge(f"Engine: {run.get('engine', 'API')}", icon=":material/terminal:", color="blue")
                with h3:
                    st.markdown(f"Applied: **{run.get('applied', 0)}** / {run.get('total', 0)}")
                    if run.get("skipped", 0) > 0:
                        st.caption(f"Skipped: {run.get('skipped')}")
                with h4:
                    if run.get("failed", 0) == 0:
                        st.badge("All successful", icon=":material/check_circle:", color="green")
                    else:
                        st.badge(f"{run.get('failed')} failed", icon=":material/warning:", color="red")

                # Expandable Per-Account Breakdown Table
                details: List[Dict[str, Any]] = run.get("details", [])
                if details:
                    with st.expander("View per-account details", expanded=False):
                        detail_rows = []
                        for d in details:
                            status_val = d.get("status", "UNKNOWN")
                            detail_rows.append({
                                "Account": d.get("account", ""),
                                "Username": d.get("username", ""),
                                "Bank": d.get("bank", ""),
                                "Status": status_val,
                                "Message": d.get("message", ""),
                                "Timestamp": d.get("timestamp", ""),
                            })
                        detail_df = pd.DataFrame(detail_rows)
                        st.dataframe(detail_df, width="stretch", hide_index=True)
    else:
        with st.container(border=True):
            st.info("No historical records matching the filter criteria.", icon=":material/info:")
