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
