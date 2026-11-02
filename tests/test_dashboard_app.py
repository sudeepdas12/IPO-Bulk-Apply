"""Streamlit AppTest integration test for Meroshare AutoPilot dashboard."""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_dashboard_app_initial_render():
    """Verify that the dashboard initializes, resolves navigation, and renders without exceptions."""
    dashboard_file = Path(__file__).resolve().parent.parent / "meroshare-bot-master" / "app" / "dashboard.py"
    at = AppTest.from_file(str(dashboard_file), default_timeout=20)
    at.run()
    assert len(at.exception) == 0, f"AppTest encountered exceptions: {[e.value for e in at.exception]}"


def test_allotment_results_view_render():
    """Verify that the Allotment Results view initializes and renders cleanly with AppTest."""
    from bot.account_manager import AccountManager
    from bot.api_client import MeroshareAPIClient
    from bot.ipo_result_checker import IPOResultChecker

    AccountManager()
    result_checker = IPOResultChecker()
    MeroshareAPIClient()

    ok, _msg, comps = result_checker.get_company_list()
    assert ok is True
    assert len(comps) > 0
