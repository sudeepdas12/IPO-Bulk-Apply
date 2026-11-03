"""Apply IPO guided 3-step workflow view for Meroshare AutoPilot."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Literal

import streamlit as st

from bot.account_manager import AccountManager
from bot.cdsc_issue_scraper import CDSCIssueScraper
from bot.cooldown_manager import CooldownManager
from bot.executor import IPOExecutor
from bot.history_manager import HistoryManager
from bot.models import ResultState
from bot.notifications import send_run_summary

IP_COOLDOWN_STATUS = "IP_COOLDOWN"
DEFERRED_IP_COOLDOWN_STATUS = "DEFERRED_IP_COOLDOWN"


def render_apply_workflow(
    acc_mgr: AccountManager,
    history_mgr: HistoryManager,
    cdsc_scraper: CDSCIssueScraper,
    executor: IPOExecutor,
) -> None:
    """Render the guided 3-step IPO application process."""
    st.title("Apply IPO")
    st.caption("Guided three-step operation to execute multi-account applications with safety controls.")

    accounts = acc_mgr.load_accounts()
    if not accounts:
        with st.container(border=True):
            st.warning("No Demat accounts registered. Please add accounts in the Accounts registry before applying.", icon=":material/warning:")
            if st.button("Go to accounts registry", icon=":material/group:", width="content"):
                st.session_state.nav_target = "Accounts"
                st.rerun()
        return

    # Pre-render state updates to prevent StreamlitWidgetAlreadyInstantiatedError
    if st.session_state.pop("trigger_select_all_act", False):
        for i in range(len(accounts)):
            st.session_state[f"act_toggle_{i}"] = True
    elif st.session_state.pop("trigger_clear_all_act", False):
        for i in range(len(accounts)):
            st.session_state[f"act_toggle_{i}"] = False

    # Ensure selection state keys exist for all accounts
    for i in range(len(accounts)):
        if f"act_toggle_{i}" not in st.session_state:
            st.session_state[f"act_toggle_{i}"] = True

    # -------------------------------------------------------------
    # Step 1: Choose IPO
    # -------------------------------------------------------------
    with st.container(border=True):
        st.markdown("### Step 1: Choose IPO")
        st.caption("Select an active market issue from CDSC or specify a company name manually.")

        # Fetch CDSC live issues if not loaded
        if "cdsc_issues" not in st.session_state or not st.session_state.cdsc_issues:
            with st.spinner("Fetching active issues..."):
                ok, _, fetched_issues = cdsc_scraper.fetch_current_issues()
                if ok:
                    st.session_state.cdsc_issues = fetched_issues

        live_issues: List[Dict[str, Any]] = st.session_state.get("cdsc_issues", [])

        if live_issues:
            for idx, issue in enumerate(live_issues):
                cname = issue.get("company_name", "")
                scrip = issue.get("scrip", "")
                is_selected = (st.session_state.get("target_company_input", "").strip() == cname.strip())

                with st.container(border=True):
                    c_info, c_action = st.columns([4, 1.2], vertical_alignment="center")
                    with c_info:
                        b_type = issue.get("issue_type", "IPO")
                        b_grp = issue.get("target_group", "General Public")
                        days_left = issue.get("days_left", 0)
                        sub_ratio = issue.get("sub_ratio", 0.0)

                        st.markdown(f"**{cname}** `{scrip}` · `{b_type}` · `{b_grp}`")
                        st.caption(
                            f"Closes: **{issue.get('close_date', 'N/A')}** ({days_left}d left) · "
                            f"Subscribed: **{sub_ratio:.2f}x** · "
                            f"Applicants: **{issue.get('applicants', 0):,}**"
                        )
                    with c_action:
                        if is_selected:
                            st.badge("Selected", icon=":material/check:", color="green")
                        else:
                            if st.button("Select issue", key=f"sel_issue_{idx}", icon=":material/check_circle:", width="stretch"):
                                st.session_state.target_company_input = cname
                                st.session_state.selected_issue_data = issue
                                st.rerun()

        # Fallback manual text input
        with st.expander("Manual company name override", expanded=(not bool(live_issues))):
            target_input = st.text_input(
                "Company name or ticker",
                value=st.session_state.get("target_company_input", ""),
                help="Type the full or partial company name as it appears in Meroshare.",
            )
            if target_input != st.session_state.get("target_company_input", ""):
                st.session_state.target_company_input = target_input

    # -------------------------------------------------------------
    # Step 2: Choose Accounts
    # -------------------------------------------------------------
    selected_target = st.session_state.get("target_company_input", "").strip()

    with st.container(border=True):
        st.markdown("### Step 2: Choose accounts")
        st.caption("Select applicant accounts for this application round.")

        # Account search & bulk selection controls
        col_ctrl1, col_ctrl2, col_ctrl3, col_kitta = st.columns([3, 1, 1, 1.5], vertical_alignment="bottom")
        with col_ctrl1:
            search_query = st.text_input("Filter accounts", placeholder="Search by name, username, or bank...", label_visibility="collapsed")
        with col_ctrl2:
            if st.button("Select all", icon=":material/select_all:", width="stretch"):
                st.session_state.trigger_select_all_act = True
                st.rerun()
        with col_ctrl3:
            if st.button("Clear all", icon=":material/deselect:", width="stretch"):
                st.session_state.trigger_clear_all_act = True
                st.rerun()
        with col_kitta:
            override_kitta = st.number_input("Override kitta", min_value=10, max_value=1000, value=10, step=10)

        # Filtered accounts list
        filtered_accounts = []
        for idx, acc in enumerate(accounts):
            name = acc.get("name", "")
            uname = acc.get("username", "")
            bank = acc.get("bank", "")
            q = search_query.lower().strip()
            if not q or (q in name.lower() or q in uname.lower() or q in bank.lower()):
                filtered_accounts.append((idx, acc))

        st.write("")

        # Responsive Account Cards
        for orig_idx, acc in filtered_accounts:
            with st.container(border=True):
                c_chk, c_meta, c_kitta = st.columns([0.5, 3.5, 1], vertical_alignment="center")
                with c_chk:
                    st.checkbox(
                        "Select",
                        key=f"act_toggle_{orig_idx}",
                        label_visibility="collapsed",
                    )
                with c_meta:
                    st.markdown(f"**{acc.get('name', 'Account')}** · `{acc.get('username')}`")
                    st.caption(f"Bank: {acc.get('bank', 'N/A')} · DP: {acc.get('capital_id', 'N/A')}")
                with c_kitta:
                    acc_kitta = acc.get("kitta", "10")
                    st.markdown(f"**{acc_kitta} Kitta**")

    # -------------------------------------------------------------
    # Step 3: Review and Apply
    # -------------------------------------------------------------
    selected_accounts = [
        accounts[i]
        for i in range(len(accounts))
        if st.session_state.get(f"act_toggle_{i}", False)
    ]

    total_shares = sum(
        int(a.get("kitta", override_kitta)) if str(a.get("kitta", "")).isdigit() else override_kitta
        for a in selected_accounts
    )
    estimated_amount = total_shares * 100  # standard NPR 100 per share

    with st.container(border=True):
        st.markdown("### Step 3: Review and apply")
        st.caption("Verify configuration parameters and authorization before submission.")

        r1, r2, r3, r4 = st.columns(4)
        with r1:
            st.metric("Target issue", selected_target or "None chosen", border=True)
        with r2:
            st.metric("Selected applicants", len(selected_accounts), border=True)
        with r3:
            st.metric("Total shares", f"{total_shares:,} Kitta", border=True)
        with r4:
            st.metric("Estimated outlay", f"NPR {estimated_amount:,}", border=True)

        st.write("")

        # Safety & Mode Controls
        col_mode, col_dry = st.columns([2, 2], vertical_alignment="center")
        with col_mode:
            exec_engine = st.selectbox(
                "Execution engine",
                options=["Direct REST API (Instant)", "Playwright Browser (Browser Automation)"],
                index=0,
                help="Direct REST API completes in milliseconds. Playwright simulates a real browser.",
            )
            mode = "api" if "REST" in exec_engine else "playwright"
        with col_dry:
            is_dry_run = st.checkbox(
                "Dry-run preview mode (recommended for testing)",
                value=False,
                help="Validates credentials and company availability without submitting the final application.",
            )

        confirm_auth = st.checkbox(
            "I authorize Meroshare AutoPilot to submit IPO applications for the selected accounts.",
            value=False,
        )

        cooldown_mgr = getattr(executor, "cooldown_mgr", CooldownManager())
        is_cooled, cool_info = cooldown_mgr.is_cooldown_active()

        if is_cooled and not is_dry_run:
            rem_str = cooldown_mgr.format_time_remaining()
            st.error(
                f"**CDSC access temporarily limited**\n\n"
                f"CDSC temporarily blocked automated requests from this network. Execution is paused to prevent prolonging the restriction.\n\n"
                f"• **Lockout Status**: `{rem_str}`\n"
                f"• **Reason**: {cool_info.get('reason', 'CDSC Firewall temporary IP cooldown')}\n\n"
                f"Wait for the restriction to expire, then test one account manually on the official Meroshare portal.",
                icon=":material/lock_clock:",
            )
            c_ov1, c_ov2 = st.columns([3, 2], vertical_alignment="center")
            with c_ov1:
                st.caption("Do not retry repeatedly; this can extend the cooldown.")
            with c_ov2:
                if st.button("I have verified portal is available (Override)", key="apply_cdsc_cooldown_override", width="stretch"):
                    cooldown_mgr.clear_cooldown()
                    st.rerun()

        st.write("")

        # Validation Checks before submission
        can_submit = (
            bool(selected_target)
            and len(selected_accounts) > 0
            and (confirm_auth or is_dry_run)
            and (not is_cooled or is_dry_run)
        )

        btn_label = "Run dry-run preview" if is_dry_run else "Submit live application"
        btn_icon = ":material/visibility:" if is_dry_run else ":material/rocket_launch:"

        if st.button(btn_label, icon=btn_icon, disabled=not can_submit, width="stretch"):
            _execute_application_run(
                selected_accounts=selected_accounts,
                target_company=selected_target,
                override_kitta=override_kitta,
                mode=mode,
                dry_run=is_dry_run,
                executor=executor,
                history_mgr=history_mgr,
            )


def _execute_application_run(
    selected_accounts: List[Dict[str, Any]],
    target_company: str,
    override_kitta: int,
    mode: str,
    dry_run: bool,
    executor: IPOExecutor,
    history_mgr: HistoryManager,
) -> None:
    """Execute application run across accounts with live progress container and circuit breaker."""
    total = len(selected_accounts)
    cooldown_mgr = getattr(executor, "cooldown_mgr", CooldownManager())
    pace_delay = max(getattr(executor, "delay", 3.0), 2.5)

    st.markdown("---")
    st.markdown("#### Execution progress")

    progress_bar = st.progress(0, text="Initializing execution engine...")
    status_container = st.empty()
    details_container = st.container(border=True)

    applied_count = 0
    skipped_count = 0
    failed_count = 0
    circuit_breaker_triggered = False
    details_log: List[Dict[str, Any]] = []

    executor.mode = mode

    for idx, acc in enumerate(selected_accounts, start=1):
        name = acc.get("name", f"Account #{idx}")
        progress_pct = int(((idx - 1) / total) * 100)
        progress_bar.progress(progress_pct, text=f"Processing {name} ({idx}/{total})...")

        acc_kitta = int(acc.get("kitta", override_kitta)) if str(acc.get("kitta", "")).isdigit() and int(acc.get("kitta", 0)) > 0 else override_kitta
        apply_kitta = override_kitta if override_kitta != 10 else acc_kitta

        if mode == "api":
            status, msg = executor._apply_via_api(acc, target_company, apply_kitta, dry_run=dry_run)
        else:
            status, msg = executor._apply_via_playwright(acc, target_company, apply_kitta, dry_run=dry_run)

        # Detect cooldown
        is_cooldown = (
            status == IP_COOLDOWN_STATUS
            or "cooldown" in msg.lower()
            or "firewall rejected" in msg.lower()
            or "rejected" in msg.lower()
        )
        if is_cooldown:
            status = IP_COOLDOWN_STATUS

        detail = {
            "account": name,
            "username": acc.get("username", ""),
            "bank": acc.get("bank", ""),
            "status": status,
            "message": msg,
            "timestamp": time.strftime("%H:%M:%S"),
        }
        details_log.append(detail)

        # Categorize
        badge_color: Literal["red", "orange", "yellow", "blue", "green", "violet", "gray", "grey", "primary"]
        if status == ResultState.SUCCESS.value:
            applied_count += 1
            badge_color = "green"
        elif status in (ResultState.SKIPPED.value, ResultState.ALREADY_APPLIED.value, ResultState.NO_ISSUE.value, "DRY_RUN"):
            skipped_count += 1
            badge_color = "blue" if status == "DRY_RUN" else "orange"
        elif status == IP_COOLDOWN_STATUS:
            failed_count += 1
            badge_color = "red"
        else:
            failed_count += 1
            badge_color = "red"

        with details_container:
            c1, c2, c3 = st.columns([2, 1, 4])
            with c1:
                st.markdown(f"**{name}**")
            with c2:
                st.badge(status, color=badge_color)
            with c3:
                st.caption(msg)

        # Circuit breaker on first IP cooldown response
        if is_cooldown and not dry_run:
            circuit_breaker_triggered = True
            cooldown_mgr.record_cooldown(reason=msg, duration_minutes=15)
            # Defer all remaining accounts without attempting
            for rem_idx in range(idx + 1, total + 1):
                rem_acc = selected_accounts[rem_idx - 1]
                rem_name = rem_acc.get("name", f"Account #{rem_idx}")
                rem_msg = "CDSC temporarily blocked this IP. Remaining accounts were not attempted."
                rem_detail = {
                    "account": rem_name,
                    "username": rem_acc.get("username", ""),
                    "bank": rem_acc.get("bank", ""),
                    "status": DEFERRED_IP_COOLDOWN_STATUS,
                    "message": rem_msg,
                    "timestamp": time.strftime("%H:%M:%S"),
                }
                details_log.append(rem_detail)
                skipped_count += 1

                with details_container:
                    d1, d2, d3 = st.columns([2, 1, 4])
                    with d1:
                        st.markdown(f"**{rem_name}**")
                    with d2:
                        st.badge(DEFERRED_IP_COOLDOWN_STATUS, color="orange")
                    with d3:
                        st.caption(rem_msg)
            break

        time.sleep(pace_delay)

    progress_bar.progress(100, text="Execution completed.")

    # Log to History Manager if not pure dry run
    if not dry_run:
        history_mgr.log_run(
            company_name=target_company,
            engine="API" if mode == "api" else "Playwright",
            total=total,
            applied=applied_count,
            skipped=skipped_count,
            failed=failed_count,
            details=details_log,
        )

        # Mobile notification if configured
        bot_tok = st.session_state.get("telegram_token", "")
        chat_id = st.session_state.get("telegram_chat_id", "")
        if bot_tok and chat_id:
            applied_items = [d for d in details_log if d["status"] == ResultState.SUCCESS.value]
            skipped_items = [d for d in details_log if d["status"] != ResultState.SUCCESS.value and d["status"] != ResultState.FAILED.value]
            failed_items = [d for d in details_log if d["status"] == ResultState.FAILED.value]
            send_run_summary(bot_tok, chat_id, target_company, total, applied_items, skipped_items, failed_items)

    # Final summary container
    with status_container.container(border=True):
        if circuit_breaker_triggered:
            st.error(
                "**CDSC access temporarily limited**\n\n"
                "CDSC temporarily blocked automated requests from this network. "
                "No accounts were retried after the first firewall rejection to prevent extending the restriction. "
                "Wait for the restriction to expire, then test one account manually on the official Meroshare portal.",
                icon=":material/shield:",
            )
        else:
            st.success(
                f"Execution finished for {target_company}: {applied_count} applied, {skipped_count} skipped, {failed_count} failed.",
                icon=":material/check_circle:",
            )
            if failed_count > 0:
                st.error(f"{failed_count} account(s) encountered errors. Check details above.", icon=":material/error:")

        col_c1, col_c2 = st.columns(2)
        with col_c1:
            if st.button("Check allotment results", icon=":material/fact_check:", width="stretch", key="nav_to_res_btn"):
                st.session_state.nav_target = "Allotment results"
                st.rerun()
        with col_c2:
            if st.button("View run history audit", icon=":material/history:", width="stretch", key="nav_to_hist_btn"):
                st.session_state.nav_target = "Run history"
                st.rerun()
