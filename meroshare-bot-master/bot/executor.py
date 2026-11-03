"""Coordinates applying for IPOs across multiple accounts using either REST API or Playwright."""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from bot.api_client import MeroshareAPIClient
from bot.cooldown_manager import CooldownManager
from bot.models import ResultState

logger = logging.getLogger("IPOExecutor")


class IPOExecutor:
    """Coordinates applying for IPOs across multiple accounts using either REST API or Playwright."""

    def __init__(
        self,
        mode: str = "api",
        delay: float = 3.0,
        stop_on_ip_cooldown: bool = True,
        cooldown_mgr: Optional[CooldownManager] = None,
    ):
        self.mode = mode.lower()
        self.delay = delay
        self.stop_on_ip_cooldown = stop_on_ip_cooldown
        self.cooldown_mgr = cooldown_mgr or CooldownManager()
        self.api_client = MeroshareAPIClient()

    def run(
        self,
        accounts: List[Dict[str, Any]],
        company_name: str,
        kitta: int = 10,
        dry_run: bool = False,
        progress_callback: Optional[Callable[[int, int, str, str, str], None]] = None,
    ) -> Dict[str, Any]:
        """
        Execute application process over list of accounts.
        Reuses browser instance in Playwright mode for multi-account processing.
        Supports dry_run safety preview mode.
        """
        applied_list: List[Dict[str, Any]] = []
        skipped_list: List[Dict[str, Any]] = []
        failed_list: List[Dict[str, Any]] = []
        details_list: List[Dict[str, Any]] = []

        total = len(accounts)

        # Pre-execution check: block immediately if CDSC IP cooldown is active
        active, cooldown_info = self.cooldown_mgr.is_cooldown_active()
        if active and not dry_run:
            rem_str = self.cooldown_mgr.format_time_remaining()
            reason = cooldown_info.get("reason", "CDSC IP cooldown active")
            for acc in accounts:
                name = str(acc.get("name", "Account")).strip()
                acc_kitta = int(acc.get("kitta", kitta)) if str(acc.get("kitta", "")).isdigit() else kitta
                cooldown_detail: Dict[str, Any] = {
                    "account": name,
                    "name": name,
                    "username": acc.get("username", ""),
                    "bank": acc.get("bank", ""),
                    "kitta": acc_kitta,
                    "status": ResultState.DEFERRED_IP_COOLDOWN.value,
                    "message": f"Execution blocked: CDSC IP cooldown active ({rem_str}). Reason: {reason}",
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
                details_list.append(cooldown_detail)
                skipped_list.append(cooldown_detail)
            return {
                "total": total,
                "applied": [],
                "skipped": skipped_list,
                "failed": [],
                "details": details_list,
                "dry_run": dry_run,
                "blocked_by_cooldown": True,
            }

        # For Playwright mode, launch browser once to reuse across all accounts
        browser = None
        playwright_inst = None
        if "playwright" in self.mode:
            try:
                from playwright.sync_api import sync_playwright
                playwright_inst = sync_playwright().start()
                browser = playwright_inst.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
                )
            except Exception as exc:
                logger.error("Failed to start pooled Playwright browser: %s", exc)
                browser = None

        try:
            for idx, acc in enumerate(accounts, start=1):
                name = str(acc.get("name", f"Account #{idx}")).strip()
                acc_company = str(acc.get("company", "")).strip()
                target_company = company_name.strip() or acc_company
                acc_kitta = int(acc.get("kitta", kitta)) if str(acc.get("kitta", "")).isdigit() else kitta

                if progress_callback:
                    progress_callback(idx, total, name, "STARTING", f"Processing {name} ({idx}/{total})...")

                if self.mode == "api":
                    status, msg = self._apply_via_api(acc, target_company, acc_kitta, dry_run=dry_run)
                else:
                    status, msg = self._apply_via_playwright(
                        acc, target_company, acc_kitta, browser=browser, dry_run=dry_run
                    )

                is_cooldown = (
                    status == ResultState.IP_COOLDOWN.value
                    or "cooldown" in msg.lower()
                    or "firewall" in msg.lower()
                    or "rejected" in msg.lower()
                )
                if is_cooldown:
                    status = ResultState.IP_COOLDOWN.value

                detail: Dict[str, Any] = {
                    "account": name,
                    "name": name,
                    "username": acc.get("username", ""),
                    "bank": acc.get("bank", ""),
                    "kitta": acc_kitta,
                    "status": status,
                    "message": msg,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
                details_list.append(detail)

                if status == ResultState.SUCCESS.value:
                    applied_list.append(detail)
                elif status in (ResultState.SKIPPED.value, ResultState.ALREADY_APPLIED.value, ResultState.NO_ISSUE.value, "DRY_RUN"):
                    skipped_list.append(detail)
                else:
                    failed_list.append(detail)

                if progress_callback:
                    progress_callback(idx, total, name, status, msg)

                # Circuit breaker: stop on first IP cooldown response
                if is_cooldown and self.stop_on_ip_cooldown and not dry_run:
                    self.cooldown_mgr.record_cooldown(reason=msg, duration_minutes=15)
                    logger.warning("Circuit breaker fired for account %s: stopping remaining accounts.", name)
                    for rem_idx in range(idx + 1, total + 1):
                        rem_acc = accounts[rem_idx - 1]
                        rem_name = str(rem_acc.get("name", f"Account #{rem_idx}")).strip()
                        rem_kitta = int(rem_acc.get("kitta", kitta)) if str(rem_acc.get("kitta", "")).isdigit() else kitta
                        rem_detail = {
                            "account": rem_name,
                            "name": rem_name,
                            "username": rem_acc.get("username", ""),
                            "bank": rem_acc.get("bank", ""),
                            "kitta": rem_kitta,
                            "status": ResultState.DEFERRED_IP_COOLDOWN.value,
                            "message": "CDSC temporarily blocked this IP. Remaining accounts were not attempted.",
                            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                        }
                        details_list.append(rem_detail)
                        skipped_list.append(rem_detail)
                        if progress_callback:
                            progress_callback(
                                rem_idx, total, rem_name, ResultState.DEFERRED_IP_COOLDOWN.value,
                                "CDSC temporarily blocked this IP. Remaining accounts were not attempted.",
                            )
                    break

                time.sleep(self.delay)

        finally:
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass
            if playwright_inst:
                try:
                    playwright_inst.stop()
                except Exception:
                    pass

        return {
            "total": total,
            "applied": applied_list,
            "skipped": skipped_list,
            "failed": failed_list,
            "details": details_list,
            "dry_run": dry_run,
        }

    def _apply_via_api(
        self,
        acc: Dict[str, Any],
        company_query: str,
        kitta: int,
        dry_run: bool = False,
    ) -> Tuple[str, str]:
        """Apply for one account via high-speed REST API with dry-run support."""
        cap_id = str(acc.get("capital_id") or acc.get("capitalid") or acc.get("CapitalID") or "").strip()
        username = str(acc.get("username") or acc.get("Username") or "").strip()
        password = str(acc.get("password") or acc.get("Password") or "").strip()
        crn = str(acc.get("crn") or acc.get("CRN") or "").strip()
        pin = str(acc.get("txn_pin") or acc.get("TXN_PIN") or "").strip()
        target_bank = str(acc.get("bank") or acc.get("Bank") or "").strip()

        # 1. Login
        ok, msg, token = self.api_client.login(cap_id, username, password)
        if not ok or not token:
            if "cooldown" in msg.lower() or "firewall" in msg.lower() or "rejected" in msg.lower():
                return ResultState.IP_COOLDOWN.value, msg
            return ResultState.AUTH_FAILED.value, f"Login failed: {msg}"

        # 2. Get user profile
        user_info = self.api_client.get_user_details(token)
        if not user_info:
            return ResultState.FAILED.value, "Could not fetch user Demat details"

        # 3. Get applicable issues
        try:
            issues = self.api_client.get_applicable_issues(token)
        except Exception as exc:
            return ResultState.NETWORK_ERROR.value, f"Failed to retrieve open issues: {exc}"

        if not issues:
            return ResultState.NO_ISSUE.value, "No open IPO/FPO issues currently available"

        target_issue: Optional[Dict[str, Any]] = None
        if company_query:
            query = company_query.lower()
            clean_query = re.sub(r"\(.*?\)", "", query).strip()
            for issue in issues:
                cname = str(issue.get("companyName", "")).lower()
                scrip = str(issue.get("scrip", "")).lower()
                clean_cname = re.sub(r"\(.*?\)", "", cname).strip()
                if (
                    query == scrip
                    or (scrip and scrip in query)
                    or query in cname
                    or cname in query
                    or (clean_query and clean_query in clean_cname)
                    or (clean_cname and clean_cname in clean_query)
                ):
                    target_issue = issue
                    break
        else:
            target_issue = issues[0]

        if not target_issue:
            available = [str(i.get("companyName", "Unknown")) for i in issues]
            return ResultState.NO_ISSUE.value, f"Company '{company_query}' not open. Currently open: {', '.join(available)}"

        raw_share_id = target_issue.get("companyShareId")
        if raw_share_id is None:
            return ResultState.FAILED.value, "Company share ID was missing in issue data"

        try:
            company_share_id = int(raw_share_id)
        except (ValueError, TypeError):
            return ResultState.FAILED.value, f"Invalid company share ID: {raw_share_id}"

        company_label = target_issue.get("companyName") or target_issue.get("scrip") or "IPO"

        # 4. Check if already applied
        status_info = self.api_client.check_application_status(token, company_share_id)
        if status_info:
            action = status_info.get("actionStatus", "").lower()
            status_desc = status_info.get("statusName", "")
            if "apply" not in action and status_desc:
                return ResultState.ALREADY_APPLIED.value, f"Already applied ({status_desc})"

        # 5. Get user banks
        try:
            banks = self.api_client.get_banks(token)
        except Exception as exc:
            return ResultState.FAILED.value, f"Could not fetch bank accounts: {exc}"

        if not banks:
            return ResultState.FAILED.value, "No registered bank account found for this user in Meroshare"

        selected_bank: Optional[Dict[str, Any]] = None
        if target_bank:
            norm_target = re.sub(r"[^a-zA-Z0-9]", "", target_bank).lower()
            for b in banks:
                b_name = re.sub(r"[^a-zA-Z0-9]", "", b.get("bankName", "")).lower()
                if norm_target in b_name or b_name in norm_target:
                    selected_bank = b
                    break

        if not selected_bank:
            selected_bank = banks[0]

        # Dry Run Mode Check
        if dry_run:
            bank_label = selected_bank.get("bankName", "Bank")
            return "DRY_RUN", f"[Preview] Validated for {company_label} ({kitta} Kitta) via {bank_label}"

        # 6. Submit application
        applied_ok, apply_msg = self.api_client.apply_ipo(
            token=token,
            user_details=user_info,
            bank_info=selected_bank,
            company_share_id=company_share_id,
            kitta=kitta,
            crn=crn,
            txn_pin=pin,
        )

        if applied_ok:
            return ResultState.SUCCESS.value, f"Successfully applied for {company_label} ({kitta} Kitta)"

        if "already" in apply_msg.lower():
            return ResultState.ALREADY_APPLIED.value, apply_msg

        return ResultState.FAILED.value, apply_msg

    def _apply_via_playwright(
        self,
        acc: Dict[str, Any],
        company_query: str,
        kitta: int,
        browser: Any = None,
        dry_run: bool = False,
    ) -> Tuple[str, str]:
        """Apply for one account via Playwright browser automation."""
        from bot.func import SkippableIpoStateError, apply_share, gotoAsba, ipo_selector, login

        dp_id = str(acc.get("capital_id") or acc.get("capitalid") or acc.get("CapitalID") or "").strip()
        dp_id_num = dp_id[3:] if dp_id.startswith("130") else dp_id
        username = str(acc.get("username") or acc.get("Username") or "").strip()
        password = str(acc.get("password") or acc.get("Password") or "").strip()
        bank = str(acc.get("bank") or acc.get("Bank") or "").strip()
        crn = str(acc.get("crn") or acc.get("CRN") or "").strip()
        txn_pin = str(acc.get("txn_pin") or acc.get("TXN_PIN") or "").strip()
        branch = str(acc.get("branch") or acc.get("Branch") or "").strip()

        should_close_browser = False
        playwright_local = None

        try:
            if browser is None:
                from playwright.sync_api import sync_playwright
                playwright_local = sync_playwright().start()
                browser = playwright_local.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
                )
                should_close_browser = True

            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
            )
            page = context.new_page()

            try:
                page.goto("https://meroshare.cdsc.com.np", wait_until="domcontentloaded", timeout=15000)
                page.wait_for_selector("#selectBranch", timeout=10000)
                login(page, dp_id_num, username, password)

                issue_count = gotoAsba(page)
                if issue_count <= 0:
                    return ResultState.NO_ISSUE.value, "No open IPO/FPO issues found"

                branch_hint = branch.strip()
                ipo_selector(page, issue_count, 1, company_query)

                if dry_run:
                    return "DRY_RUN", f"[Preview] Page reached apply screen for {company_query or 'Issue'} ({kitta} Kitta)"

                apply_share(page, bank, str(kitta), crn, txn_pin, branch_hint)
                return ResultState.SUCCESS.value, f"Successfully applied for {company_query or 'Issue'} ({kitta} Kitta)"

            except SkippableIpoStateError as e:
                return ResultState.ALREADY_APPLIED.value, str(e)
            except Exception as e:
                return ResultState.FAILED.value, str(e)
            finally:
                context.close()

        except Exception as outer_e:
            return ResultState.FAILED.value, f"Browser error: {outer_e}"

        finally:
            if should_close_browser and browser:
                try:
                    browser.close()
                except Exception:
                    pass
            if playwright_local:
                try:
                    playwright_local.stop()
                except Exception:
                    pass
