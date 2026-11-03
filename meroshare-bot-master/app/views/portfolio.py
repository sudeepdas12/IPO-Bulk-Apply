"""Multi-Account Portfolio Aggregator for family Demat accounts."""

from __future__ import annotations

import csv
import datetime
import io
import logging
import time
from typing import Any, Dict, List, Optional

import streamlit as st

from bot.account_manager import AccountManager
from bot.api_client import MeroshareAPIClient
from bot.cooldown_manager import CooldownManager

logger = logging.getLogger(__name__)


def render_portfolio(acc_mgr: AccountManager, api_client: Optional[MeroshareAPIClient] = None) -> None:
    """Render the consolidated multi-account Demat portfolio view."""
    st.title("My Demat Portfolio")
    st.caption("Consolidated stock holdings, kitta units, and market valuation across all registered Demat accounts.")

    if api_client is None:
        api_client = MeroshareAPIClient()

    accounts = acc_mgr.load_accounts()
    if not accounts:
        st.warning(
            "No accounts found in your secure vault. Please add your Demat accounts in the Accounts tab first.",
            icon=":material/account_circle:",
        )
        if st.button("Go to Accounts Manager", icon=":material/group_add:", width="stretch"):
            st.session_state.nav_target = "Accounts"
            st.rerun()
        return

    # Session storage for synced portfolio data
    if "portfolio_data" not in st.session_state:
        st.session_state.portfolio_data = None
    if "portfolio_synced_at" not in st.session_state:
        st.session_state.portfolio_synced_at = None

    # Top Controls Card
    with st.container(border=True):
        st.subheader("Sync Portfolio Holdings", divider=False)
        st.caption(
            f"Query live holdings for up to {len(accounts)} registered Demat accounts directly from Meroshare CDSC."
        )

        cooldown_mgr = CooldownManager()
        is_cooled, cool_info = cooldown_mgr.is_cooldown_active()
        if is_cooled:
            rem_str = cooldown_mgr.format_time_remaining()
            st.error(
                f"**CDSC access temporarily limited**\n\n"
                f"CDSC temporarily blocked automated requests from this network. Portfolio sync is paused to prevent prolonging the restriction.\n\n"
                f"• **Lockout Status**: `{rem_str}`\n"
                f"• **Reason**: {cool_info.get('reason', 'CDSC Firewall temporary IP cooldown')}\n\n"
                f"Wait for the restriction to expire, then test one account manually on the official Meroshare portal.",
                icon=":material/lock_clock:",
            )
            c_ov1, c_ov2 = st.columns([3, 2], vertical_alignment="center")
            with c_ov1:
                st.caption("Do not retry repeatedly; this can extend the cooldown.")
            with c_ov2:
                if st.button("I have verified portal is available (Override)", key="port_cdsc_cooldown_override", width="stretch"):
                    cooldown_mgr.clear_cooldown()
                    st.rerun()

        col_sel_all, col_sync_btn = st.columns([1, 2])
        with col_sel_all:
            select_all = st.checkbox("Select All Accounts", value=True, key="port_select_all")

        # Account checklist
        selected_accounts: List[Dict[str, Any]] = []
        with st.expander("Filter Specific Accounts", expanded=not select_all):
            cols = st.columns(3)
            for idx, acc in enumerate(accounts):
                acc_name = acc.get("name", f"Account #{idx+1}")
                user = acc.get("username", "")
                with cols[idx % 3]:
                    is_checked = select_all or st.checkbox(
                        f"{acc_name} ({user})",
                        value=select_all,
                        key=f"port_acc_check_{idx}",
                        disabled=select_all,
                    )
                    if is_checked:
                        selected_accounts.append(acc)

        if select_all:
            selected_accounts = accounts

        with col_sync_btn:
            sync_btn = st.button(
                f"Sync Demat Portfolios ({len(selected_accounts)} Selected)",
                type="primary",
                icon=":material/sync:",
                width="stretch",
                disabled=len(selected_accounts) == 0 or is_cooled,
            )

    # Sync Execution
    if sync_btn and selected_accounts:
        _execute_portfolio_sync(selected_accounts, api_client)

    # Display Results if available
    portfolio_data = st.session_state.get("portfolio_data")
    if portfolio_data:
        _render_portfolio_summary_and_tables(portfolio_data)
    else:
        st.info(
            "Click **Sync Demat Portfolios** above to query your live share holdings and valuation from Meroshare.",
            icon=":material/info:",
        )


def _execute_portfolio_sync(accounts: List[Dict[str, Any]], api_client: MeroshareAPIClient) -> None:
    """Query each account's portfolio via Meroshare API and aggregate results with circuit breaker."""
    progress_bar = st.progress(0, text="Initializing portfolio sync...")
    status_box = st.empty()
    cooldown_mgr = CooldownManager()

    consolidated_scrips: Dict[str, Dict[str, Any]] = {}
    account_breakdown: List[Dict[str, Any]] = []

    total_accs = len(accounts)
    success_count = 0
    fail_count = 0
    circuit_breaker_triggered = False

    # Initialize batch browser context to allow fast (~0.2s) WAF-bypassed portfolio fetching
    browser_proc = None
    browser_page = None
    playwright_ctx = None
    try:
        from bot.cdsc_browser_checker import find_browser_executable, find_free_port
        from playwright.sync_api import sync_playwright
        import subprocess, tempfile

        exe = find_browser_executable()
        if exe:
            port = find_free_port()
            tmp_dir = tempfile.mkdtemp(prefix="ms_batch_port_")
            browser_proc = subprocess.Popen(
                [exe, f"--remote-debugging-port={port}", f"--user-data-dir={tmp_dir}", "--headless=new", "about:blank"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(1.0)
            playwright_ctx = sync_playwright().start()
            browser_conn = playwright_ctx.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            browser_page = browser_conn.contexts[0].new_page()
            browser_page.goto("https://meroshare.cdsc.com.np/", timeout=15000)
    except Exception as exc:
        logger.warning("Could not pre-initialize batch browser session for portfolio: %s", exc)

    try:
        for idx, acc in enumerate(accounts):
            acc_name = acc.get("name", f"Account #{idx+1}")
            cap_id = str(acc.get("capital_id") or acc.get("capitalid") or acc.get("CapitalID") or "").strip()
            user = str(acc.get("username") or acc.get("Username") or "").strip()
            pwd = str(acc.get("password") or acc.get("Password") or "").strip()

            # Fallback to extract DP ID if 16-digit BOID is present
            if not cap_id and acc.get("boid"):
                boid_clean = "".join(filter(str.isdigit, str(acc.get("boid"))))
                if len(boid_clean) == 16:
                    cap_id = boid_clean[:8]
                    if not user:
                        user = boid_clean[8:]

            if not cap_id:
                fail_count += 1
                account_breakdown.append({
                    "account_name": acc_name,
                    "username": user,
                    "status": "FAILED",
                    "error": "Capital ID / DP code is missing in account configuration. Please edit this account in Accounts tab.",
                    "items": [],
                    "total_value": 0.0,
                    "total_units": 0,
                })
                continue

            progress_pct = int(((idx) / total_accs) * 100)
            progress_bar.progress(progress_pct, text=f"Querying [{idx+1}/{total_accs}]: {acc_name} ({user})...")

            # Login
            ok, msg, token = api_client.login(cap_id, user, pwd)
            if not ok or not token:
                fail_count += 1
                is_cooldown = "cooldown" in msg.lower() or "firewall" in msg.lower() or "rejected" in msg.lower()
                acc_status = "IP_COOLDOWN" if is_cooldown else "FAILED"

                account_breakdown.append({
                    "account_name": acc_name,
                    "username": user,
                    "status": acc_status,
                    "error": msg,
                    "items": [],
                    "total_value": 0.0,
                    "total_units": 0,
                })

                # Circuit breaker: stop on first IP cooldown response
                if is_cooldown:
                    circuit_breaker_triggered = True
                    cooldown_mgr.record_cooldown(reason=msg, duration_minutes=15)
                    # Defer remaining accounts
                    for rem_idx in range(idx + 1, total_accs):
                        rem_acc = accounts[rem_idx]
                        rem_name = rem_acc.get("name", f"Account #{rem_idx+1}")
                        rem_user = rem_acc.get("username", "")
                        account_breakdown.append({
                            "account_name": rem_name,
                            "username": rem_user,
                            "status": "DEFERRED_IP_COOLDOWN",
                            "error": "CDSC temporarily blocked this IP. Remaining accounts were not attempted.",
                            "items": [],
                            "total_value": 0.0,
                            "total_units": 0,
                        })
                    break
                continue

            # Get own detail for demat / boid and clientCode
            user_detail = api_client.get_user_details(token)
            demat = ""
            client_code = ""
            if user_detail:
                demat = str(user_detail.get("demat") or user_detail.get("boid") or "")
                client_code = str(user_detail.get("clientCode") or "")

            # Query portfolio with authentic browser fallback if CDSC WAF blocks direct REST endpoint
            account_creds = {"capital_id": cap_id, "username": user, "password": pwd}
            port_res = api_client.get_portfolio(
                token,
                demat=demat,
                client_code=client_code,
                account_creds=account_creds,
                browser_page=browser_page,
            )
            if not port_res:
                fail_count += 1
                account_breakdown.append({
                    "account_name": acc_name,
                    "username": user,
                    "status": "FAILED",
                    "error": "Failed to load portfolio response from Meroshare (CDSC firewall or session rejected)",
                    "items": [],
                    "total_value": 0.0,
                    "total_units": 0,
                })
                continue

            success_count += 1

            # Extract portfolio list (CDSC uses meroShareMyPortfolio as primary key)
            items = (
                port_res.get("meroShareMyPortfolio")
                or port_res.get("meroSharePortfolio")
                or port_res.get("object")
                or []
            )
            if isinstance(items, dict):
                items = [items]

            raw_val = (
                port_res.get("totalValueOfLastTransPrice")
                or port_res.get("totalValueOfPrevClosingPrice")
                or port_res.get("totalValueAsOfPreviousClosingPrice")
                or 0.0
            )
            acc_total_value = float(raw_val) if raw_val else 0.0
            acc_total_units = 0
            parsed_items: List[Dict[str, Any]] = []

            for it in items:
                scrip = str(it.get("script") or it.get("scrip") or "").strip().upper()
                if not scrip:
                    continue

                desc = str(it.get("scriptDesc") or it.get("companyName") or scrip).strip()
                units = int(float(it.get("currentBalance") or it.get("balance") or 0))
                ltp = float(it.get("lastTransactionPrice") or it.get("previousClosingPrice") or 0.0)
                val = float(
                    it.get("valueOfLastTransPrice")
                    or it.get("valueOfPrevClosingPrice")
                    or it.get("valueAsOfLastTransactionPrice")
                    or (units * ltp)
                )

                acc_total_units += units
                parsed_items.append({
                    "scrip": scrip,
                    "company_name": desc,
                    "units": units,
                    "ltp": ltp,
                    "value": val,
                })

                # Merge into consolidated scrips
                if scrip not in consolidated_scrips:
                    consolidated_scrips[scrip] = {
                        "scrip": scrip,
                        "company_name": desc,
                        "total_units": 0,
                        "ltp": ltp,
                        "total_value": 0.0,
                        "holdings": [],
                    }

                consolidated_scrips[scrip]["total_units"] += units
                consolidated_scrips[scrip]["total_value"] += val
                consolidated_scrips[scrip]["holdings"].append(f"{acc_name}: {units:,}")
                if ltp > 0:
                    consolidated_scrips[scrip]["ltp"] = ltp

            account_breakdown.append({
                "account_name": acc_name,
                "username": user,
                "status": "SUCCESS",
                "error": "",
                "items": parsed_items,
                "total_value": acc_total_value if acc_total_value > 0 else sum(i["value"] for i in parsed_items),
                "total_units": acc_total_units,
            })

            time.sleep(1.0)
    finally:
        if browser_page:
            try:
                browser_page.close()
            except Exception:
                pass
        if playwright_ctx:
            try:
                playwright_ctx.stop()
            except Exception:
                pass
        if browser_proc:
            try:
                browser_proc.kill()
            except Exception:
                pass

    progress_bar.progress(100, text="Portfolio sync complete!")
    if circuit_breaker_triggered:
        status_box.error(
            "CDSC access temporarily limited. No accounts were retried after the first firewall rejection. "
            "Wait for the restriction to expire, then test one account manually on the official Meroshare portal.",
            icon=":material/shield:",
        )
    else:
        status_box.success(
            f"Synced {success_count} account(s) successfully ({fail_count} failed).",
            icon=":material/check_circle:",
        )

    st.session_state.portfolio_data = {
        "consolidated": list(consolidated_scrips.values()),
        "accounts": account_breakdown,
        "synced_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    st.rerun()


def _render_portfolio_summary_and_tables(data: Dict[str, Any]) -> None:
    """Render high-level KPIs and consolidated holding tables."""
    consolidated = data.get("consolidated", [])
    accounts = data.get("accounts", [])
    synced_at = data.get("synced_at", "")

    total_valuation = sum(float(item.get("total_value", 0.0)) for item in consolidated)
    total_shares = sum(int(item.get("total_units", 0)) for item in consolidated)
    total_scrips = len(consolidated)
    successful_accs = sum(1 for a in accounts if a.get("status") == "SUCCESS")

    st.markdown(f"**Last Synced:** `{synced_at}`")

    # Top KPI Metrics Cards
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric(
            label="Total Portfolio Valuation",
            value=f"Rs. {total_valuation:,.2f}",
            delta=None,
        )
    with m2:
        st.metric(
            label="Total Shares (Kitta)",
            value=f"{total_shares:,}",
            delta=None,
        )
    with m3:
        st.metric(
            label="Unique Scrips Held",
            value=f"{total_scrips}",
            delta=None,
        )
    with m4:
        st.metric(
            label="Accounts Synced",
            value=f"{successful_accs}/{len(accounts)}",
            delta=None,
        )

    tab_consol, tab_accs = st.tabs(["Consolidated Holdings", "Per-Account Breakdown"])

    with tab_consol:
        if consolidated:
            # Sort by total value descending
            sorted_scrips = sorted(consolidated, key=lambda x: float(x.get("total_value", 0.0)), reverse=True)

            table_rows: List[Dict[str, Any]] = []
            for item in sorted_scrips:
                table_rows.append({
                    "Scrip": item["scrip"],
                    "Company Name": item["company_name"],
                    "Total Units": f"{item['total_units']:,}",
                    "LTP (NPR)": f"{item['ltp']:,.2f}",
                    "Total Value (NPR)": f"{item['total_value']:,.2f}",
                    "Holdings By Account": ", ".join(item["holdings"]),
                })

            st.dataframe(table_rows, width="stretch", hide_index=True)

            # CSV Download Button
            csv_buf = io.StringIO()
            writer = csv.writer(csv_buf)
            writer.writerow(["Scrip", "Company Name", "Total Units", "LTP (NPR)", "Total Value (NPR)", "Holdings By Account"])
            for r in table_rows:
                writer.writerow([r["Scrip"], r["Company Name"], r["Total Units"], r["LTP (NPR)"], r["Total Value (NPR)"], r["Holdings By Account"]])

            st.download_button(
                label="Download Consolidated Portfolio CSV",
                data=csv_buf.getvalue(),
                file_name="my_demat_portfolio.csv",
                mime="text/csv",
                icon=":material/download:",
                width="stretch",
            )
        else:
            st.info("No active stock holdings found across the selected accounts.", icon=":material/info:")

    with tab_accs:
        for acc in accounts:
            acc_name = acc["account_name"]
            user = acc["username"]
            status = acc["status"]
            items = acc["items"]
            acc_val = acc["total_value"]
            acc_units = acc["total_units"]

            status_icon = "🟢" if status == "SUCCESS" else "🔴"
            with st.expander(f"{status_icon} **{acc_name}** (`{user}`) — Rs. {acc_val:,.2f} ({acc_units:,} units)"):
                if status == "FAILED":
                    st.error(f"Sync error: {acc.get('error', 'Unknown error')}")
                elif not items:
                    st.caption("No shares currently held in this Demat account.")
                else:
                    acc_table = []
                    for it in items:
                        acc_table.append({
                            "Scrip": it["scrip"],
                            "Company": it["company_name"],
                            "Units": f"{it['units']:,}",
                            "LTP (NPR)": f"{it['ltp']:,.2f}",
                            "Market Value (NPR)": f"{it['value']:,.2f}",
                        })
                    st.dataframe(acc_table, width="stretch", hide_index=True)
