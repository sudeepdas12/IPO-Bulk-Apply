"""Settings and preferences view for Meroshare AutoPilot with config.ini persistence."""

from __future__ import annotations

import configparser
import sys
from pathlib import Path

import streamlit as st

from bot.notifications import test_telegram_connection


def _get_config_path() -> Path:
    candidates = [
        Path.cwd() / "config.ini",
        Path.cwd() / "meroshare-bot-master" / "config.ini",
        Path(__file__).resolve().parent.parent.parent / "config.ini",
    ]
    return next((p for p in candidates if p.exists()), candidates[0])


def _load_config() -> configparser.ConfigParser:
    config = configparser.ConfigParser()
    p = _get_config_path()
    if p.exists():
        config.read(str(p), encoding="utf-8")
    return config


def _save_config(config: configparser.ConfigParser) -> None:
    p = _get_config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        config.write(f)


def render_settings_view() -> None:
    """Render the configuration, preferences, and notifications view."""
    st.title("Settings")
    st.caption("Configure runtime behavior, mobile notifications, and system parameters.")

    config = _load_config()

    # Execution Engine Configuration
    with st.container(border=True):
        st.markdown("### Execution parameters")
        st.caption("Fine-tune connection timeouts and execution pacing.")

        saved_engine = config.get("general", "engine", fallback="api").lower()
        engine_options = ["Direct REST API (Instant)", "Playwright Browser (Browser Automation)"]
        default_engine_idx = 1 if "playwright" in saved_engine else 0

        saved_fast = config.getboolean("general", "fast_mode", fallback=False)

        s_col1, s_col2 = st.columns(2)
        with s_col1:
            chosen_engine = st.selectbox(
                "Default execution engine",
                options=engine_options,
                index=default_engine_idx,
                key="settings_engine_select",
                help="REST API is ultra-fast and recommended. Playwright runs Chromium.",
            )
        with s_col2:
            pace_delay = st.slider(
                "Inter-account pacing delay (seconds)",
                min_value=0.05,
                max_value=2.0,
                value=0.1 if saved_fast else 0.25,
                step=0.05,
                key="settings_pace_delay_slider",
                help="Gentle delay between submitting different applicant accounts to avoid server throttling.",
            )

        c_save_exec, _ = st.columns([1.5, 3])
        with c_save_exec:
            if st.button("Save Execution Preferences", icon=":material/save:", width="stretch"):
                if not config.has_section("general"):
                    config.add_section("general")
                new_engine_val = "playwright" if "Playwright" in chosen_engine else "api"
                config.set("general", "engine", new_engine_val)
                config.set("general", "fast_mode", "true" if pace_delay <= 0.1 else "false")
                _save_config(config)
                st.toast("Execution parameters saved to config.ini", icon="💾")

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

    # Factory Reset / Clean Distribution Container
    with st.container(border=True):
        st.markdown("### Prepare clean distribution (Factory reset)")
        st.caption("Wipe all saved accounts and audit history to prepare a clean, plug-and-play package for another PC or user.")

        confirm_wipe = st.checkbox(
            "I have exported my accounts and want to erase all stored credentials from this folder for clean distribution.",
            key="confirm_clean_wipe",
        )
        if st.button("Wipe All Stored Accounts & History", type="secondary", icon=":material/delete_forever:", disabled=not confirm_wipe, width="stretch"):
            acc_mgr.save_accounts([], encrypt_secrets=False)
            hist_mgr.clear()
            st.success("All accounts and audit histories wiped! The folder is now completely clean and ready for distribution.", icon=":material/check_circle:")
            st.rerun()

    # Mobile Notifications Container
    with st.container(border=True):
        st.markdown("### Mobile notifications")
        st.caption("Receive instant batch completion summaries directly on Telegram.")

        config = _load_config()
        saved_tok = config.get("telegram", "bot_token", fallback="") if config.has_section("telegram") else ""
        saved_cid = config.get("telegram", "chat_id", fallback="") if config.has_section("telegram") else ""

        curr_tok = st.session_state.get("telegram_token") or saved_tok
        curr_cid = st.session_state.get("telegram_chat_id") or saved_cid

        tok_input = st.text_input(
            "Telegram bot token",
            value=curr_tok,
            type="password",
            placeholder="e.g. 123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ",
            key="settings_tg_token_field",
        )
        cid_input = st.text_input(
            "Telegram chat ID",
            value=curr_cid,
            placeholder="e.g. 987654321",
            key="settings_tg_cid_field",
        )

        st.session_state.telegram_token = tok_input
        st.session_state.telegram_chat_id = cid_input

        # Save to config.ini button
        c_btn1, c_btn2 = st.columns([1, 1])
        with c_btn1:
            if st.button("Save Notifications to config.ini", icon=":material/save:", width="stretch"):
                if not config.has_section("telegram"):
                    config.add_section("telegram")
                config.set("telegram", "enabled", "true" if tok_input and cid_input else "false")
                config.set("telegram", "bot_token", tok_input)
                config.set("telegram", "chat_id", cid_input)
                _save_config(config)
                st.toast("Telegram credentials persisted to config.ini!", icon="💾")
                st.success("Telegram credentials persisted to config.ini!", icon=":material/check_circle:")

        with c_btn2:
            if st.button("Send test alert", icon=":material/send:", width="stretch"):
                tok = tok_input.strip()
                cid = cid_input.strip()
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
