"""Settings and preferences view for Meroshare AutoPilot."""

from __future__ import annotations

import sys

import streamlit as st

from bot.notifications import test_telegram_connection


def render_settings_view() -> None:
    """Render the configuration, preferences, and notifications view."""
    st.title("Settings")
    st.caption("Configure runtime behavior, mobile notifications, and system parameters.")

    # Execution Engine Configuration
    with st.container(border=True):
        st.markdown("### Execution parameters")
        st.caption("Fine-tune connection timeouts and execution pacing.")

        s_col1, s_col2 = st.columns(2)
        with s_col1:
            st.selectbox(
                "Default execution engine",
                options=["Direct REST API (Instant)", "Playwright Browser (Browser Automation)"],
                index=0,
                help="REST API is ultra-fast and recommended. Playwright runs Chromium.",
            )
        with s_col2:
            st.slider(
                "Inter-account pacing delay (seconds)",
                min_value=0.05,
                max_value=2.0,
                value=0.2,
                step=0.05,
                help="Gentle delay between submitting different applicant accounts to avoid server throttling.",
            )

    # Vault Security & Encryption At Rest
    from bot.account_manager import AccountManager
    acc_mgr = AccountManager()
    with st.container(border=True):
        st.markdown("### Credential vault security")
        st.caption("Protect passwords, transaction PINs, and CRNs with Windows DPAPI encryption.")

        is_enc = acc_mgr.is_vault_encrypted()
        sec_col1, sec_col2 = st.columns([3, 2])
        with sec_col1:
            if is_enc:
                st.success("🔒 **Vault Encryption Active:** Passwords and PINs in `demats.txt` are encrypted on disk with your Windows User Key (DPAPI).", icon=":material/lock:")
            else:
                st.warning("⚠️ **Plaintext Storage:** Credentials in `demats.txt` are currently stored in plaintext. Encrypt to protect against unauthorized disk inspection.", icon=":material/lock_open:")
        with sec_col2:
            if is_enc:
                if st.button("Convert to Plaintext (Decrypt)", icon=":material/lock_open:", width="stretch"):
                    acc_mgr.decrypt_vault()
                    st.toast("Vault decrypted to plaintext.", icon="🔓")
                    st.rerun()
            else:
                if st.button("Encrypt Vault (Windows DPAPI)", type="primary", icon=":material/lock:", width="stretch"):
                    acc_mgr.encrypt_vault()
                    st.toast("Vault successfully encrypted with DPAPI!", icon="🔒")
                    st.rerun()

    # Vault & Audit History Backup / Export Container
    import csv
    import io
    import json

    from bot.history_manager import HistoryManager
    hist_mgr = HistoryManager()
    with st.container(border=True):
        st.markdown("### Vault backup & data export")
        st.caption("Export decrypted account credentials and application audit logs for migration to another PC or disaster recovery.")

        bak_col1, bak_col2 = st.columns(2)
        with bak_col1:
            st.markdown("**Account Vault Backup (CSV)**")
            st.caption("Exports decrypted credentials into standard CSV format for importing into another PC.")
            all_accs = acc_mgr.load_accounts()
            if all_accs:
                csv_buf = io.StringIO()
                writer = csv.writer(csv_buf)
                writer.writerow(["Name", "Capital_ID", "Username", "Password", "Bank_Name", "Default_Kitta", "CRN", "TXN_PIN", "Branch", "Company"])
                for a in all_accs:
                    writer.writerow([
                        a.get("name", ""),
                        a.get("capital_id", ""),
                        a.get("username", ""),
                        a.get("password", ""),
                        a.get("bank", ""),
                        a.get("kitta", "10"),
                        a.get("crn", ""),
                        a.get("txn_pin", ""),
                        a.get("branch", ""),
                        a.get("company", ""),
                    ])
                st.download_button(
                    label=f"Export Vault CSV ({len(all_accs)} Accounts)",
                    data=csv_buf.getvalue(),
                    file_name="demats_vault_backup.csv",
                    mime="text/csv",
                    icon=":material/download:",
                    width="stretch",
                )
            else:
                st.info("No accounts currently configured in vault.", icon=":material/info:")

        with bak_col2:
            st.markdown("**Application Audit History (JSON)**")
            st.caption("Exports all previous IPO application execution records, allotments, and result logs.")
            history_records = hist_mgr.get_history()
            history_json_str = json.dumps(history_records, indent=2, ensure_ascii=False)
            st.download_button(
                label=f"Export History JSON ({len(history_records)} Runs)",
                data=history_json_str,
                file_name="ipo_history_backup.json",
                mime="application/json",
                icon=":material/history:",
                width="stretch",
                disabled=len(history_records) == 0,
            )

    # Mobile Notifications Container
    with st.container(border=True):
        st.markdown("### Mobile notifications")
        st.caption("Receive instant batch completion summaries directly on Telegram.")

        st.session_state.telegram_token = st.text_input(
            "Telegram bot token",
            value=st.session_state.get("telegram_token", ""),
            type="password",
            placeholder="e.g. 123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ",
        )
        st.session_state.telegram_chat_id = st.text_input(
            "Telegram chat ID",
            value=st.session_state.get("telegram_chat_id", ""),
            placeholder="e.g. 987654321",
        )

        if st.button("Send test alert", icon=":material/send:", width="content"):
            tok = st.session_state.telegram_token.strip()
            cid = st.session_state.telegram_chat_id.strip()
            if tok and cid:
                with st.spinner("Dispatching test alert..."):
                    ok, msg = test_telegram_connection(tok, cid)
                    if ok:
                        st.success("Test notification delivered successfully to Telegram.", icon=":material/check_circle:")
                    else:
                        st.error(f"Failed to send alert: {msg}", icon=":material/error:")
            else:
                st.warning("Please specify both Bot Token and Chat ID.", icon=":material/warning:")

    # System Diagnostics & Info
    with st.container(border=True):
        st.markdown("### System diagnostics")
        d1, d2, d3 = st.columns(3)
        with d1:
            st.caption("Python runtime")
            st.markdown(f"**Python {sys.version.split()[0]}**")
        with d2:
            st.caption("Operating platform")
            st.markdown(f"**{sys.platform.title()}**")
        with d3:
            st.caption("Application version")
            st.markdown("**Meroshare AutoPilot v0.0.9**")

        st.divider()
        st.caption(
            "Designed and engineered for high reliability in Nepal Capital Market. "
            "Complies with CDSC Meroshare API schemas and banking C-ASBA specifications."
        )
