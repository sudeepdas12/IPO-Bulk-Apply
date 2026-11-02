from typing import Any, Dict, List, Tuple

from playwright.sync_api import sync_playwright

from bot.func import login


def fetch_open_issues_with_browser(
    capital_id: str,
    username: str,
    password: str,
    headless: bool = True,
    timeout_ms: int = 25000,
) -> Tuple[bool, str, List[Dict[str, Any]]]:
    """
    Log into Meroshare using Chromium and retrieve all active open issues from the ASBA page.
    Returns: (success: bool, message: str, issues: List[Dict])
    """
    dp_id_num = capital_id[3:] if capital_id.startswith("130") else capital_id
    issues = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=headless,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
            )
            page = browser.new_page(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page.goto("https://meroshare.cdsc.com.np", wait_until="domcontentloaded", timeout=timeout_ms)

            # Wait for branch dropdown
            try:
                page.wait_for_selector("#selectBranch", timeout=10000)
            except Exception:
                browser.close()
                return False, "Meroshare login portal failed to load. Please check your internet connection.", []

            # Perform login
            try:
                login(page, dp_id_num, username, password)
            except Exception as e:
                browser.close()
                return False, f"Login interaction error: {str(e)}", []

            try:
                page.wait_for_selector(".header-menu__link, .toast-message, .alert", timeout=6000)
            except Exception:
                pass

            # Check if login failed (error alert or still on login page)
            toasts = page.query_selector_all(".toast-message, .alert, .text-danger, mat-error")
            for t in toasts:
                if t.is_visible():
                    err_txt = t.inner_text().strip()
                    if err_txt and ("invalid" in err_txt.lower() or "attempt" in err_txt.lower() or "error" in err_txt.lower()):
                        browser.close()
                        return False, f"Login rejected: {err_txt}", []

            # Verify navigation to dashboard
            if "#/login" in page.url and not page.query_selector(".header-menu__link"):
                browser.close()
                return False, "Login failed: Credentials were not accepted by Meroshare.", []

            # Navigate directly to ASBA via client-side routing
            try:
                asba_link = page.locator("a[href*='#/asba'], a[routerlink*='asba'], a:has-text('ASBA')").first
                if asba_link.is_visible():
                    asba_link.click(timeout=2000)
                else:
                    page.evaluate("() => { window.location.hash = '#/asba'; }")
            except Exception:
                page.goto("https://meroshare.cdsc.com.np/#/asba", wait_until="domcontentloaded", timeout=timeout_ms)

            try:
                page.wait_for_selector(".company-name, .blank-slate, table, .tooltipster-fall", timeout=7000)
            except Exception:
                pass

            # Find company elements
            company_cards = page.query_selector_all(".company-name")

            for idx, card in enumerate(company_cards, start=1):
                raw_text = card.inner_text().strip()
                lines = [line.strip() for line in raw_text.split("\n") if line.strip()]
                company_name = lines[0] if lines else f"Issue #{idx}"
                share_type = lines[1] if len(lines) > 1 else "Ordinary Shares"
                sub_type = lines[2] if len(lines) > 2 else "General Public"

                card_text = ""
                try:
                    card_text = (card.evaluate("el => (el.closest('.row') || el.closest('.company-list') || el.closest('div')).innerText") or "").lower()
                except Exception:
                    pass

                has_apply = "apply" in card_text or "re-apply" in card_text or "reapply" in card_text

                issues.append({
                    "id": idx,
                    "companyName": company_name,
                    "scrip": company_name,
                    "shareTypeName": share_type,
                    "subGroup": sub_type,
                    "has_apply_btn": has_apply,
                    "raw": raw_text,
                })

            browser.close()

            if not issues:
                return True, "Connected to ASBA page successfully, but no open IPO/FPO issues are currently active.", []

            return True, f"Successfully found {len(issues)} open issue(s).", issues

    except Exception as e:
        return False, f"Error scanning issues: {str(e)}", []
