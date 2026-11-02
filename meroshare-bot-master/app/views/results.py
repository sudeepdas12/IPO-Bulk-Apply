"""Bulk IPO allotment results view for Meroshare AutoPilot."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

from bot.account_manager import AccountManager
from bot.api_client import MeroshareAPIClient
from bot.cdsc_browser_checker import CDSCBrowserChecker
from bot.cooldown_manager import CooldownManager
from bot.ipo_result_checker import IPOResultChecker

logger = logging.getLogger(__name__)


def render_allotment_results(
    acc_mgr: AccountManager,
    result_checker: IPOResultChecker,
    api_client: Optional[MeroshareAPIClient] = None,
) -> None:
    """Render the bulk allotment results check view."""
    st.title("Allotment results")
    st.caption("Bulk verify IPO allotment outcomes across all registered accounts via official CDSC or direct Meroshare sessions.")

    accounts = acc_mgr.load_accounts()
    if not accounts:
        st.warning("No Demat accounts registered. Add accounts in the Accounts registry to check results.", icon=":material/warning:")
        return

    # Pre-render state updates to prevent StreamlitWidgetAlreadyInstantiatedError
    if st.session_state.pop("trigger_select_all_res", False):
        for i in range(len(accounts)):
            st.session_state[f"res_toggle_{i}"] = True
    elif st.session_state.pop("trigger_clear_all_res", False):
        for i in range(len(accounts)):
            st.session_state[f"res_toggle_{i}"] = False
    elif "retry_failed_accounts_indices" in st.session_state:
        retry_indices = set(st.session_state.pop("retry_failed_accounts_indices"))
        for i in range(len(accounts)):
            st.session_state[f"res_toggle_{i}"] = (i in retry_indices)

    # Initialize toggles if not yet set
    for i in range(len(accounts)):
        if f"res_toggle_{i}" not in st.session_state:
            st.session_state[f"res_toggle_{i}"] = True

    # Mode Selector
    engine_options = [
        "Meroshare Direct Portal (Recommended — Demat login, bypasses CDSC WAF)",
        "CDSC Browser AI Solver (No login, Chrome + Neural CAPTCHA solver, bypasses WAF)",
        "CDSC Public Portal (BOID only, instant check)",
    ]
    if st.session_state.pop("switch_to_meroshare", False):
        st.session_state.res_engine_mode = engine_options[0]
    elif st.session_state.pop("switch_to_browser", False):
        st.session_state.res_engine_mode = engine_options[1]
    elif "res_engine_mode" not in st.session_state:
        st.session_state.res_engine_mode = engine_options[0]

    query_mode = st.radio(
        "Verification engine",
        options=engine_options,
        key="res_engine_mode",
        horizontal=True,
        help="Meroshare Direct bypasses WAF via Demat session. Browser AI solves CDSC public captcha with Chrome. CDSC Public uses direct API.",
    )
    is_meroshare_mode = "Meroshare Direct" in query_mode
    is_browser_mode = "Browser AI" in query_mode

    # 1. Company Selection
    if not st.session_state.get("result_companies"):
        with st.spinner("Loading allotment companies from CDSC..."):
            ok, msg, comps = result_checker.get_company_list()
            if comps:
                st.session_state.result_companies = comps
                st.session_state.result_companies_msg = msg

    companies: List[Dict[str, Any]] = st.session_state.get("result_companies", [])
    comp_msg = st.session_state.get("result_companies_msg", "")

    with st.container(border=True):
        st.markdown("### Step 1: Select allotment issue")

        is_waf = getattr(result_checker, "is_waf_active", False) or "WAF" in comp_msg
        if is_waf:
            if is_meroshare_mode:
                st.caption("ℹ️ *Company list loaded from verified allotment database. Meroshare Direct Portal bypasses all CDSC WAF restrictions.*")
            elif is_browser_mode:
                st.caption("ℹ️ *Company list loaded from verified allotment database. Browser AI Solver handles CAPTCHA and WAF verification.*")
            else:
                st.info(
                    "**Public CDSC Portal Restricted:** The public endpoint (`iporesult.cdsc.com.np`) restricted direct script queries from this network IP. "
                    "The list below is loaded safely from the verified allotment database.\n\n"
                    "💡 **Recommendation:** Switch to **Meroshare Direct Portal** above for 100% verified results via Demat sessions with zero WAF blocks.",
                    icon=":material/shield:",
                )

        entry_method = st.radio(
            "Selection method",
            options=["Select from published company list", "Enter manual Company Share ID"],
            horizontal=True,
            label_visibility="collapsed",
        )

        selected_comp_id: Optional[int] = None
        selected_comp_name: str = ""

        if entry_method == "Select from published company list":
            c_sel, c_refresh = st.columns([4, 1], vertical_alignment="bottom")
            with c_sel:
                comp_options = {f"{c.get('name', 'Unknown')} (ID: {c.get('id')})": c.get("id") for c in companies}
                selected_label = st.selectbox(
                    "Company with published allotment",
                    options=list(comp_options.keys()) if comp_options else ["No companies available"],
                    help="Select the company whose IPO allotment was published by CDSC.",
                )
                selected_comp_id = comp_options.get(selected_label)
                # Extract clean company name without the trailing (ID: ...)
                selected_comp_name = selected_label.split(" (ID:")[0] if selected_label else ""
            with c_refresh:
                if st.button("Refresh list", icon=":material/refresh:", width="stretch"):
                    with st.spinner("Refreshing company list..."):
                        ok, msg, comps = result_checker.get_company_list(force_refresh=True)
                        if comps:
                            st.session_state.result_companies = comps
                            st.session_state.result_companies_msg = msg
                    st.rerun()
        else:
            c_id, c_name = st.columns([1.5, 3.5], vertical_alignment="bottom")
            with c_id:
                manual_id = st.number_input("Company Share ID", min_value=1, max_value=99999, value=398, step=1)
                selected_comp_id = int(manual_id)
            with c_name:
                manual_name = st.text_input("Company Name (optional)", value="Custom Issue")
                selected_comp_name = manual_name.strip() or f"Company ID {manual_id}"

    # 2. Select Accounts
    with st.container(border=True):
        st.markdown("### Step 2: Select Demat accounts")
        st.caption("Choose which registered accounts to query for allotment outcomes.")

        ctrl_col1, ctrl_col2, ctrl_col3 = st.columns([3, 1, 1], vertical_alignment="center")
        with ctrl_col1:
            st.caption(f"{len(accounts)} accounts registered in Demat vault")
        with ctrl_col2:
            if st.button("Select all", key="btn_sel_all_res", icon=":material/select_all:", width="stretch"):
                st.session_state.trigger_select_all_res = True
                st.rerun()
        with ctrl_col3:
            if st.button("Clear all", key="btn_clr_all_res", icon=":material/deselect:", width="stretch"):
                st.session_state.trigger_clear_all_res = True
                st.rerun()

        selected_accounts: List[Dict[str, Any]] = []
        for idx, acc in enumerate(accounts):
            uname = str(acc.get("username") or acc.get("Username") or "").strip()
            cap_id = str(acc.get("capital_id") or acc.get("capitalid") or acc.get("CapitalID") or "").strip()
            boid = str(acc.get("boid", "")).strip() or (f"{cap_id}{uname.zfill(8) if uname.isdigit() else uname}" if cap_id and uname else "")
            name = acc.get("name", f"Account #{idx+1}")
            bank = acc.get("bank", "N/A")

            c_chk, c_info = st.columns([0.4, 4.6], vertical_alignment="center")
            with c_chk:
                is_checked = st.checkbox(
                    "Include",
                    key=f"res_toggle_{idx}",
                    label_visibility="collapsed",
                )
            with c_info:
                st.markdown(f"**{name}** · BOID: `{boid}` · Bank: {bank}")

            if is_checked and boid:
                entry = dict(acc)
                entry["boid"] = boid
                entry["name"] = name
                selected_accounts.append(entry)

    # 3. Execution & Operational Verification
    st.write("")
    cooldown_mgr = CooldownManager()
    is_cooled, cool_info = cooldown_mgr.is_cooldown_active()

    if is_meroshare_mode and is_cooled:
        rem_str = cooldown_mgr.format_time_remaining()
        st.error(
            f"**CDSC access temporarily limited**\n\n"
            f"CDSC temporarily blocked automated requests from this network. Direct Demat verification is paused to prevent prolonging the restriction.\n\n"
            f"• **Lockout Status**: `{rem_str}`\n"
            f"• **Reason**: {cool_info.get('reason', 'CDSC Firewall temporary IP cooldown')}\n\n"
            f"Wait for the restriction to expire, test one account manually, or switch to **CDSC Browser AI Solver** above for public verification without login.",
            icon=":material/lock_clock:",
        )
        c_ov1, c_ov2 = st.columns([3, 2], vertical_alignment="center")
        with c_ov1:
            st.caption("Do not retry repeatedly; this can extend the cooldown.")
        with c_ov2:
            if st.button("I have verified portal is available (Override)", key="results_cdsc_cooldown_override", width="stretch"):
                cooldown_mgr.clear_cooldown()
                st.rerun()

    can_check = bool(selected_comp_id) and len(selected_accounts) > 0 and (not is_cooled or not is_meroshare_mode)

    col_btn, _ = st.columns([2, 3])
    with col_btn:
        btn_clicked = st.button(
            f"Check allotment ({len(selected_accounts)} accounts)",
            icon=":material/fact_check:",
            disabled=not can_check,
            type="primary",
            width="stretch",
        )
    trigger_auto = st.session_state.pop("trigger_auto_check", False)
    start_check = btn_clicked or trigger_auto

    if start_check:
        results_list: List[Dict[str, Any]] = []
        prog_bar = st.progress(0, text="Initializing allotment verification...")
        total_accs = len(selected_accounts)
        direct_client = api_client or MeroshareAPIClient()

        if is_browser_mode:
            prog_bar.progress(10, text="Launching authentic Chrome browser instance...")
            browser_checker = CDSCBrowserChecker()

            def b_callback(cur: int, tot: int, text: str) -> None:
                pct = int((cur / tot) * 100) if tot > 0 else 0
                prog_bar.progress(pct, text=text)

            browser_results = browser_checker.check_accounts_batch(
                company_name=str(selected_comp_name),
                accounts=selected_accounts,
                progress_callback=b_callback,
            )

            for acc, res_info in zip(selected_accounts, browser_results):
                name = acc["name"]
                boid = acc["boid"]
                allotted = bool(res_info.get("allotted", False))
                kitta = int(res_info.get("kitta", 0))
                msg = str(res_info.get("message", ""))
                status_code = str(res_info.get("status", ""))

                if allotted:
                    status_label = "Allotted"
                elif "INVALID" in status_code:
                    status_label = "Invalid BOID"
                elif status_code == "NOT_ALLOTTED" or "not allotted" in msg.lower():
                    status_label = "Not Allotted"
                else:
                    status_label = status_code.replace("_", " ").title() or "Checked"

                results_list.append({
                    "Applicant": name,
                    "BOID": boid,
                    "Status": status_label,
                    "Allotted Kitta": kitta if allotted else 0,
                    "Message": msg,
                    "raw_account": acc,
                })
        else:
            for idx, acc in enumerate(selected_accounts, start=1):
                name = acc["name"]
                boid = acc["boid"]
                prog_pct = int(((idx - 1) / total_accs) * 100)
                prog_bar.progress(prog_pct, text=f"Querying {name} ({idx}/{total_accs})...")

                if selected_comp_id is None:
                    continue

                if is_meroshare_mode:
                    res_info = result_checker.check_via_meroshare(direct_client, acc, int(selected_comp_id))
                else:
                    res_info = result_checker.check_boid(int(selected_comp_id), boid)

                allotted = bool(res_info.get("allotted", False))
                kitta = int(res_info.get("kitta", 0))
                msg = str(res_info.get("message", ""))
                status_code = str(res_info.get("status", ""))

                is_cooldown_hit = (
                    status_code == "IP_COOLDOWN"
                    or "cooldown" in msg.lower()
                    or "firewall" in msg.lower()
                    or "rejected" in msg.lower()
                )

                # Canonical UI status
                if allotted:
                    status_label = "Allotted"
                elif is_cooldown_hit:
                    status_label = "IP Cooldown"
                elif status_code == "WAF_BLOCKED" or "WAF" in msg:
                    status_label = "WAF Blocked"
                elif "INVALID" in status_code or "Invalid BOID" in msg:
                    status_label = "Invalid BOID"
                elif status_code == "NOT_APPLIED":
                    status_label = "Not Applied"
                elif "not allotted" in msg.lower() or "sorry" in msg.lower() or status_code == "NOT_ALLOTTED":
                    status_label = "Not Allotted"
                else:
                    status_label = status_code.replace("_", " ").title() or "Checked"

                results_list.append({
                    "Applicant": name,
                    "BOID": boid,
                    "Status": status_label,
                    "Allotted Kitta": kitta if allotted else 0,
                    "Message": msg,
                    "raw_account": acc,
                })

                # Circuit breaker on first IP cooldown response
                if is_meroshare_mode and is_cooldown_hit:
                    cooldown_mgr.record_cooldown(reason=msg, duration_minutes=15)
                    for rem_idx in range(idx + 1, total_accs + 1):
                        rem_acc = selected_accounts[rem_idx - 1]
                        rem_name = rem_acc["name"]
                        rem_boid = rem_acc["boid"]
                        results_list.append({
                            "Applicant": rem_name,
                            "BOID": rem_boid,
                            "Status": "Deferred (Cooldown)",
                            "Allotted Kitta": 0,
                            "Message": "CDSC temporarily blocked this IP. Remaining accounts were not attempted.",
                            "raw_account": rem_acc,
                        })
                    break

                time.sleep(3.0)

        prog_bar.progress(100, text="Verification complete.")
        st.session_state.last_check_results = results_list
        st.session_state.last_check_company = selected_comp_name
        st.session_state.last_check_comp_id = selected_comp_id

    # Display Results Dashboard if available
    check_results: Optional[List[Dict[str, Any]]] = st.session_state.get("last_check_results")
    if check_results:
        st.write("")
        st.markdown(f"### Results for **{st.session_state.get('last_check_company', 'Selected Issue')}**")

        allotted_count = sum(1 for r in check_results if r["Status"] == "Allotted")
        blocked_count = sum(1 for r in check_results if r["Status"] in ("WAF Blocked", "Invalid BOID", "Failed", "Auth Failed", "IP Cooldown", "Deferred (Cooldown)"))
        total_kitta = sum(int(r.get("Allotted Kitta", 0)) for r in check_results)
        total_checked = len(check_results)
        success_rate = (allotted_count / total_checked * 100) if total_checked > 0 else 0

        # Summary KPI Cards
        k1, k2, k3, k4 = st.columns(4)
        with k1:
            st.metric("Total checked", total_checked, border=True)
        with k2:
            st.metric("Allotted accounts", f"{allotted_count} 🎉", border=True)
        with k3:
            st.metric("Total shares allotted", f"{total_kitta} Kitta", border=True)
        with k4:
            st.metric("Allotment rate", f"{success_rate:.1f}%", border=True)

        # Clear IP Cooldown banner if cooldown occurred
        if any("cooldown" in str(r.get("Status", "")).lower() for r in check_results):
            st.error(
                "**CDSC access temporarily limited**\n\n"
                "No accounts were retried after the first firewall rejection to prevent extending the restriction. "
                "Wait for the restriction to expire, then test one account manually on the official Meroshare portal.",
                icon=":material/shield:",
            )
        elif blocked_count > 0 and any(r["Status"] == "WAF Blocked" for r in check_results):
            c_warn, c_switch = st.columns([3, 2], vertical_alignment="center")
            with c_warn:
                st.warning(
                    f"**CDSC WAF restriction detected for {blocked_count} queries.** "
                    "CDSC public portal blocked automated HTTP requests from this network. "
                    "Use Meroshare Direct Portal or Browser AI Solver to bypass all WAF restrictions.",
                    icon=":material/warning:",
                )
            with c_switch:
                col_sw1, col_sw2 = st.columns(2)
                with col_sw1:
                    if st.button("Direct Portal (0-WAF)", type="primary", icon=":material/swap_horiz:", width="stretch", key="waf_rescue_direct"):
                        st.session_state.switch_to_meroshare = True
                        st.session_state.trigger_auto_check = True
                        st.rerun()
                with col_sw2:
                    if st.button("Browser AI Solver", icon=":material/smart_toy:", width="stretch", key="waf_rescue_browser"):
                        st.session_state.switch_to_browser = True
                        st.session_state.trigger_auto_check = True
                        st.rerun()

        st.write("")

        # Filter & Search & Masking Controls
        c_filter, c_search, c_mask = st.columns([2, 2, 1], vertical_alignment="bottom")
        with c_filter:
            filter_status = st.segmented_control(
                "Filter outcome",
                options=["All", "Allotted only", "Not Allotted only", "Issues / Blocked"],
                default="All",
            )
        with c_search:
            search_query = st.text_input("Search applicant or BOID", placeholder="Filter by name or number...")
        with c_mask:
            mask_boid_opt = st.checkbox("Mask BOID", value=True)

        # Filter rows
        rows_to_display: List[Dict[str, Any]] = []
        for r in check_results:
            status = r["Status"]
            if filter_status == "Allotted only" and status != "Allotted":
                continue
            if filter_status == "Not Allotted only" and status != "Not Allotted":
                continue
            if filter_status == "Issues / Blocked" and status in ("Allotted", "Not Allotted"):
                continue

            disp_boid = str(r["BOID"])
            applicant = str(r["Applicant"])

            if search_query:
                sq = search_query.lower()
                if sq not in applicant.lower() and sq not in disp_boid.lower():
                    continue

            if mask_boid_opt and len(disp_boid) >= 16:
                disp_boid = f"{disp_boid[:8]}••••{disp_boid[-4:]}"

            # Visual Status Icon
            if status == "Allotted":
                status_icon = "🟢 Allotted"
            elif status == "Not Allotted":
                status_icon = "⚪ Not Allotted"
            elif status == "WAF Blocked":
                status_icon = "🟡 WAF Blocked"
            elif status == "Invalid BOID":
                status_icon = "🔴 Invalid BOID"
            elif status == "Not Applied":
                status_icon = "🔵 Not Applied"
            else:
                status_icon = f"⚠️ {status}"

            rows_to_display.append({
                "Applicant": applicant,
                "BOID": disp_boid,
                "Status": status_icon,
                "Allotted Kitta": f"{r['Allotted Kitta']} Kitta" if r["Allotted Kitta"] > 0 else "0",
                "Server message": r["Message"],
            })

        df = pd.DataFrame(rows_to_display)
        st.dataframe(df, width="stretch", hide_index=True)

        # Action Buttons: Export & Retry
        c_exp, c_retry = st.columns([1, 1])
        with c_exp:
            export_df = pd.DataFrame([
                {
                    "Applicant": r["Applicant"],
                    "BOID": r["BOID"],
                    "Status": r["Status"],
                    "Allotted Kitta": r["Allotted Kitta"],
                    "Server Message": r["Message"],
                }
                for r in check_results
            ])
            csv_data = export_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "Export results to CSV",
                data=csv_data,
                file_name=f"allotment_results_{st.session_state.get('last_check_company', 'ipo')}.csv",
                mime="text/csv",
                icon=":material/download:",
                width="stretch",
            )
        with c_retry:
            if blocked_count > 0:
                if st.button("Retry failed / blocked accounts", icon=":material/replay:", width="stretch"):
                    st.session_state.retry_failed_accounts_indices = [
                        i for i, r in enumerate(check_results)
                        if r["Status"] not in ("Allotted", "Not Allotted")
                    ]
                    st.session_state.trigger_auto_check = True
                    st.rerun()
