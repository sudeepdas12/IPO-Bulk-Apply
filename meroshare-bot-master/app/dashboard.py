"""Master dashboard coordinator for Meroshare AutoPilot using modern Streamlit pages navigation."""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root and meroshare-bot-master to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

import streamlit as st

from app.views.accounts import render_accounts_registry
from app.views.apply import render_apply_workflow
from app.views.history import render_history_audit
from app.views.overview import render_overview
from app.views.portfolio import render_portfolio
from app.views.results import render_allotment_results
from app.views.settings import render_settings_view
from bot.account_manager import AccountManager
from bot.cdsc_issue_scraper import CDSCIssueScraper
from bot.executor import IPOExecutor
from bot.history_manager import HistoryManager
from bot.ipo_result_checker import IPOResultChecker

# -------------------------------------------------------------
# Global Page Configuration & Modern SaaS Styling
# -------------------------------------------------------------
st.set_page_config(
    page_title="Meroshare AutoPilot",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.html("""
<style>
/* Modern Financial SaaS Typography & Surface Elevation */
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

/* Main View Page Surface & Typography */
.stApp {
    background-color: #F8FAFC !important;
    color: #0F172A !important;
}

html, body, [class*="css"] {
    font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    letter-spacing: -0.01em;
}

/* Crisp White Elevated Cards for Main View Page */
div[data-testid="stVerticalBlock"] > div[data-testid="stContainer"][border="true"],
div[data-testid="stContainer"][data-border="true"] {
    background: #FFFFFF !important;
    border: 1px solid #E2E8F0 !important;
    border-radius: 10px !important;
    box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.04), 0 1px 2px -1px rgba(0, 0, 0, 0.03) !important;
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
}

div[data-testid="stContainer"][data-border="true"]:hover {
    border-color: #CBD5E1 !important;
    box-shadow: 0 4px 12px -2px rgba(0, 0, 0, 0.06), 0 2px 4px -2px rgba(0, 0, 0, 0.04) !important;
}

/* Stat KPI Cards with Accent Top Bar */
div[data-testid="stMetric"] {
    background: #FFFFFF !important;
    border: 1px solid #E2E8F0 !important;
    border-top: 3px solid #2563EB !important;
    border-radius: 8px !important;
    padding: 0.9rem 1.2rem !important;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04) !important;
}

div[data-testid="stMetricValue"] {
    font-weight: 700 !important;
    color: #0F172A !important;
}

div[data-testid="stMetricLabel"] {
    font-weight: 600 !important;
    color: #64748B !important;
}

/* Primary Action Buttons */
button[kind="primary"] {
    background: linear-gradient(135deg, #2563EB 0%, #1D4ED8 100%) !important;
    border: 1px solid rgba(255, 255, 255, 0.2) !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    color: #FFFFFF !important;
    box-shadow: 0 2px 8px 0 rgba(37, 99, 235, 0.3) !important;
    transition: all 0.2s ease !important;
}

button[kind="primary"]:hover {
    box-shadow: 0 4px 14px 0 rgba(37, 99, 235, 0.45) !important;
    transform: translateY(-1px) !important;
}

button[kind="secondary"] {
    background: #FFFFFF !important;
    border: 1px solid #CBD5E1 !important;
    border-radius: 8px !important;
    font-weight: 500 !important;
    color: #1E293B !important;
    transition: all 0.2s ease !important;
}

button[kind="secondary"]:hover {
    background: #F8FAFC !important;
    border-color: #94A3B8 !important;
}

/* Distinct Dark Midnight Navy Sidebar */
section[data-testid="stSidebar"] {
    border-right: 1px solid #1E3A5F !important;
    background: #0A192F !important;
}

section[data-testid="stSidebar"] * {
    color: #F8FAFC !important;
}

section[data-testid="stSidebar"] hr {
    border-color: #1E3A5F !important;
}

section[data-testid="stSidebar"] a {
    color: #E2E8F0 !important;
}

section[data-testid="stSidebar"] a:hover {
    color: #38BDF8 !important;
}

/* Slim Professional Scrollbars */
::-webkit-scrollbar {
    width: 6px;
    height: 6px;
}
::-webkit-scrollbar-track {
    background: #F8FAFC;
}
::-webkit-scrollbar-thumb {
    background: #CBD5E1;
    border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover {
    background: #94A3B8;
}
</style>
""")


# -------------------------------------------------------------
# Cached Singletons
# -------------------------------------------------------------
@st.cache_resource
def get_account_manager() -> AccountManager:
    return AccountManager()


@st.cache_resource
def get_history_manager() -> HistoryManager:
    return HistoryManager()


@st.cache_resource
def get_cdsc_scraper() -> CDSCIssueScraper:
    return CDSCIssueScraper()


@st.cache_resource
def get_result_checker() -> IPOResultChecker:
    return IPOResultChecker()


@st.cache_resource
def get_executor() -> IPOExecutor:
    return IPOExecutor(mode="api", delay=0.2)


acc_mgr = get_account_manager()
history_mgr = get_history_manager()
cdsc_scraper = get_cdsc_scraper()
result_checker = get_result_checker()
executor = get_executor()


# -------------------------------------------------------------
# Page Wrapper Functions for st.navigation
# -------------------------------------------------------------
def view_overview() -> None:
    render_overview(acc_mgr, history_mgr, cdsc_scraper)


def view_apply() -> None:
    render_apply_workflow(acc_mgr, history_mgr, cdsc_scraper, executor)


def view_results() -> None:
    render_allotment_results(acc_mgr, result_checker, api_client=executor.api_client)


def view_portfolio() -> None:
    render_portfolio(acc_mgr, api_client=executor.api_client)


def view_accounts() -> None:
    render_accounts_registry(acc_mgr)


def view_history() -> None:
    render_history_audit(history_mgr)


def view_settings() -> None:
    render_settings_view()


# -------------------------------------------------------------
# Navigation Hierarchy (6 Clean Dedicated Pages)
# -------------------------------------------------------------
page_overview = st.Page(
    view_overview,
    title="Overview",
    icon=":material/dashboard:",
    default=True,
)
page_apply = st.Page(
    view_apply,
    title="Apply IPO",
    icon=":material/rocket_launch:",
)
page_results = st.Page(
    view_results,
    title="Allotment results",
    icon=":material/fact_check:",
)
page_portfolio = st.Page(
    view_portfolio,
    title="My Portfolio",
    icon=":material/pie_chart:",
)
page_accounts = st.Page(
    view_accounts,
    title="Accounts",
    icon=":material/group:",
)
page_history = st.Page(
    view_history,
    title="Run history",
    icon=":material/history:",
)
page_settings = st.Page(
    view_settings,
    title="Settings",
    icon=":material/tune:",
)

pg = st.navigation(
    {
        "Operations": [page_overview, page_apply, page_results, page_portfolio],
        "Management": [page_accounts, page_history, page_settings],
    }
)


# -------------------------------------------------------------
# Sidebar Header & Branding
# -------------------------------------------------------------
with st.sidebar:
    st.html("""
    <div style="padding: 4px 0 8px 0;">
        <div style="display:flex; align-items:center; gap:10px;">
            <div style="background: linear-gradient(135deg, #2563EB, #38BDF8); width:34px; height:34px; border-radius:8px; display:flex; align-items:center; justify-content:center; box-shadow: 0 0 12px rgba(56, 189, 248, 0.35);">
                <span style="font-size:18px;">📈</span>
            </div>
            <div>
                <div style="font-weight:700; font-size:15px; color:#F8FAFC; line-height:1.2;">Meroshare AutoPilot</div>
                <div style="display:flex; align-items:center; gap:5px; margin-top:3px;">
                    <span style="height:7px; width:7px; background-color:#10B981; border-radius:50%; display:inline-block; box-shadow:0 0 6px #10B981;"></span>
                    <span style="font-size:11px; font-weight:600; color:#94A3B8; text-transform:uppercase; letter-spacing:0.04em;">Gateway Ready</span>
                </div>
            </div>
        </div>
    </div>
    """)
    st.divider()


# Handle programmatic page switching if requested
if "nav_target" in st.session_state and st.session_state.nav_target:
    target = st.session_state.nav_target
    st.session_state.nav_target = None
    if target in ("Apply IPO", "Apply"):
        st.switch_page(page_apply)
    elif target in ("Accounts", "Registry"):
        st.switch_page(page_accounts)
    elif target in ("Overview", "Dashboard"):
        st.switch_page(page_overview)
    elif target in ("Allotment results", "Results"):
        st.switch_page(page_results)
    elif target in ("My Portfolio", "Portfolio"):
        st.switch_page(page_portfolio)
    elif target in ("Run history", "History"):
        st.switch_page(page_history)
    elif target in ("Settings", "Preferences"):
        st.switch_page(page_settings)


# Run active page
pg.run()


# -------------------------------------------------------------
# Single Professional Footer
# -------------------------------------------------------------
st.write("")
st.divider()
st.caption("Meroshare AutoPilot • Developed by Er. Sudeep Das • 2026")
