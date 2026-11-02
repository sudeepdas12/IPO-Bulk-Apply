"""Overview dashboard view for Meroshare AutoPilot."""

from __future__ import annotations

from typing import Any, Dict, List, Literal

import streamlit as st

from bot.account_manager import AccountManager
from bot.cdsc_issue_scraper import CDSCIssueScraper
from bot.history_manager import HistoryManager


def render_overview(
    acc_mgr: AccountManager,
    history_mgr: HistoryManager,
    cdsc_scraper: CDSCIssueScraper,
) -> None:
    """Render the streamlined operations overview page."""
    accounts = acc_mgr.load_accounts()
    history = history_mgr.get_history()

    # Clean Header with Primary CTA
    col_head, col_action = st.columns([3.5, 1.2], vertical_alignment="center")
    with col_head:
        st.title("Operations overview")
        st.caption("Live CDSC market scanner, Demat accounts portfolio summary, and recent activity.")
    with col_action:
        if st.button("Apply for IPO", icon=":material/rocket_launch:", type="primary", width="stretch"):
            st.session_state.nav_target = "Apply IPO"
            st.rerun()

    st.write("")

    # Unified 4-Column KPI Stats Row
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    with kpi1:
        st.metric("Registered Demats", len(accounts), border=True)
    with kpi2:
        unique_banks = len(set(a.get("bank", "").strip() for a in accounts if a.get("bank")))
        st.metric("Connected banks", unique_banks, border=True)
    with kpi3:
        st.metric("Completed runs", len(history), border=True)
    with kpi4:
        gw_status = st.session_state.get("gateway_status", "Online")
        st.metric("CDSC gateway", gw_status, delta="Operational", delta_color="normal", border=True)

    st.write("")

    # Section 1: Active Market Issues
    col_iss_title, col_iss_btn = st.columns([4, 1.2], vertical_alignment="center")
    with col_iss_title:
        st.markdown("### Active market issues")
        st.caption("Live issues currently open for application on the CDSC / NEPSE portal.")
    with col_iss_btn:
        if st.button("Refresh issues", icon=":material/refresh:", width="stretch"):
            cdsc_scraper._cached_issues = None
            with st.spinner("Fetching live issues..."):
                ok, _, live_issues = cdsc_scraper.fetch_current_issues()
                if ok:
                    st.session_state.cdsc_issues = live_issues
            st.rerun()

    # Fetch live issues if not loaded
    if "cdsc_issues" not in st.session_state or not st.session_state.cdsc_issues:
        with st.spinner("Connecting to CDSC market scanner..."):
            ok, _, fetched_issues = cdsc_scraper.fetch_current_issues()
            if ok:
                st.session_state.cdsc_issues = fetched_issues

    issues: List[Dict[str, Any]] = st.session_state.get("cdsc_issues", [])

    if issues:
        for idx, issue in enumerate(issues):
            is_gp = issue.get("is_general_public", False)
            badge_color: Literal["green", "orange"] = "green" if is_gp else "orange"
            target_group = issue.get("target_group", "General Public")
            issue_type = issue.get("issue_type", "IPO")
            days_left = issue.get("days_left", 0)
            sub_ratio = issue.get("sub_ratio", 0.0)

            with st.container(border=True):
                c_title, c_badges = st.columns([3, 2], vertical_alignment="center")
                with c_title:
                    st.markdown(f"#### {issue.get('company_name', 'Unknown')}")
                    scrip = issue.get("scrip")
                    if scrip:
                        st.caption(f"Ticker: `{scrip}` · Issue manager: {issue.get('issue_manager', 'N/A')}")
                with c_badges:
                    b1, b2, b3 = st.columns(3)
                    with b1:
                        st.badge(issue_type, icon=":material/category:", color="blue")
                    with b2:
                        st.badge(target_group, icon=":material/group:", color=badge_color)
                    with b3:
                        countdown_text = f"{days_left}d left" if days_left > 0 else "Closing today"
                        st.badge(countdown_text, icon=":material/schedule:", color="gray")

                # Metrics Row for Issue
                m1, m2, m3, m4, m_btn = st.columns([1, 1, 1, 1, 1.2], vertical_alignment="center")
                with m1:
                    st.caption("Issued units")
                    st.markdown(f"**{issue.get('issued_units', 0):,}**")
                with m2:
                    st.caption("Applied units")
                    st.markdown(f"**{issue.get('applied_units', 0):,}**")
                with m3:
                    st.caption("Subscription")
                    st.markdown(f"**{sub_ratio:.2f}x**")
                with m4:
                    st.caption("Applicants")
                    st.markdown(f"**{issue.get('applicants', 0):,}**")
                with m_btn:
                    if st.button("Apply now", key=f"ov_apply_{idx}", icon=":material/rocket_launch:", width="stretch"):
                        st.session_state.target_company_input = issue.get("company_name", "")
                        st.session_state.selected_issue_data = issue
                        st.session_state.nav_target = "Apply IPO"
                        st.rerun()
    else:
        with st.container(border=True):
            st.info("No active market issues currently open on CDSC.", icon=":material/info:")

    st.write("")

    # Section 2: Recent Execution Activity
    st.markdown("### Recent execution runs")
    if history:
        for run in history[:3]:
            with st.container(border=True):
                r_col1, r_col2, r_col3 = st.columns([3, 2, 1.5], vertical_alignment="center")
                with r_col1:
                    st.markdown(f"**{run.get('company', 'Unknown Issue')}**")
                    st.caption(f"{run.get('timestamp', 'N/A')} · Engine: {run.get('engine', 'API')}")
                with r_col2:
                    st.markdown(f"Applied: **{run.get('applied', 0)}** / {run.get('total', 0)}")
                    if run.get("skipped", 0) > 0:
                        st.caption(f"Skipped / Already applied: {run.get('skipped')}")
                with r_col3:
                    if run.get("failed", 0) == 0:
                        st.badge("Completed", icon=":material/check_circle:", color="green")
                    else:
                        st.badge(f"{run.get('failed')} failed", icon=":material/warning:", color="red")
    else:
        st.caption("No recent application batches. Submitting an application will show its summary here.")
