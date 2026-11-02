"""Browser-assisted CDSC Allotment Verifier using Playwright CDP & ddddocr neural solver."""

from __future__ import annotations

import base64
import logging
import os
import re
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


def find_free_port() -> int:
    """Find an available TCP port for Chrome remote debugging."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return int(s.getsockname()[1])


def find_browser_executable() -> Optional[str]:
    """Locate Google Chrome or Microsoft Edge executable on Windows/Linux/macOS."""
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium-browser",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ]
    for p in candidates:
        if Path(p).exists():
            return p
    return None


class CDSCBrowserChecker:
    """
    Automated CDSC Allotment Checker that bypasses F5 BIG-IP WAF by running
    through an authentic Windows browser with neural CAPTCHA solving.
    """

    def __init__(self, timeout: int = 15):
        self.timeout = timeout
        self._ocr = None

    def _get_ocr(self) -> Any:
        if self._ocr is None:
            try:
                import ddddocr
                self._ocr = ddddocr.DdddOcr(show_ad=False)
            except Exception as e:
                logger.warning("Could not initialize ddddocr: %s", e)
        return self._ocr

    def check_accounts_batch(
        self,
        company_name: str,
        accounts: List[Dict[str, Any]],
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Verify allotment outcomes for a list of accounts on iporesult.cdsc.com.np.
        Returns list of result dictionaries.
        """
        results: List[Dict[str, Any]] = []
        browser_exe = find_browser_executable()
        if not browser_exe:
            for acc in accounts:
                results.append({
                    "boid": acc.get("boid", ""),
                    "allotted": False,
                    "kitta": 0,
                    "status": "FAILED",
                    "message": "Chrome or Edge browser executable not found on system.",
                })
            return results

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            for acc in accounts:
                results.append({
                    "boid": acc.get("boid", ""),
                    "allotted": False,
                    "kitta": 0,
                    "status": "FAILED",
                    "message": "Playwright is not installed in the environment.",
                })
            return results

        port = find_free_port()
        temp_dir = tempfile.mkdtemp(prefix="cdsc_run_")

        cmd = [
            browser_exe,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={temp_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "https://iporesult.cdsc.com.np/",
        ]

        proc = subprocess.Popen(cmd)
        time.sleep(2.5)

        ocr = self._get_ocr()

        try:
            with sync_playwright() as p:
                browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
                context = browser.contexts[0]
                page = context.pages[0] if context.pages else context.new_page()

                # Wait for main page to be interactive
                page.wait_for_selector("#companyShare", timeout=15000)

                # Select company
                page.click("#companyShare")
                time.sleep(0.4)

                # Search company in ng-select
                clean_target = re.sub(r"[^\w\s]", "", company_name.lower())
                found_option = False

                # Read all options
                options = page.locator(".ng-dropdown-panel .ng-option").all()
                for opt in options:
                    opt_text = opt.inner_text().strip()
                    clean_opt = re.sub(r"[^\w\s]", "", opt_text.lower())
                    if clean_target in clean_opt or clean_opt in clean_target:
                        opt.click()
                        found_option = True
                        break

                if not found_option and options:
                    # Select first option if exact match not found
                    options[0].click()

                time.sleep(0.3)

                total = len(accounts)
                for idx, acc in enumerate(accounts):
                    cap = str(acc.get("capital_id") or acc.get("capitalid") or acc.get("CapitalID") or "").strip()
                    usr = str(acc.get("username") or acc.get("Username") or "").strip()
                    raw_boid = acc.get("boid") or (f"{cap}{usr}" if cap and usr else "")
                    clean_boid = re.sub(r"\D", "", str(raw_boid).strip())
                    if len(clean_boid) < 16 and cap and usr:
                        clean_boid = f"{cap}{usr.zfill(8)}"

                    applicant_name = acc.get("name", f"Account #{idx+1}")
                    if progress_callback:
                        progress_callback(idx + 1, total, f"Checking [{idx+1}/{total}]: {applicant_name} ({clean_boid})")

                    if len(clean_boid) != 16:
                        results.append({
                            "boid": clean_boid,
                            "allotted": False,
                            "kitta": 0,
                            "status": "INVALID_BOID",
                            "message": f"Invalid BOID length ({len(clean_boid)} digits, expected 16)",
                        })
                        continue

                    # Fill BOID
                    page.fill("#boid", clean_boid)

                    # Solve Captcha with retry (up to 3 attempts)
                    checked = False
                    for _attempt in range(3):
                        captcha_img = page.wait_for_selector("img[src^='data:image/png']", timeout=5000)
                        src = captcha_img.get_attribute("src") or ""
                        if "," in src and ocr:
                            b64 = src.split(",")[1]
                            code = ocr.classification(base64.b64decode(b64))
                            page.fill("#userCaptcha", code)
                            time.sleep(0.2)

                        # Submit
                        page.click("button[type='submit']")
                        time.sleep(1.2)

                        # Check result text
                        alerts = page.evaluate("""() => {
                            const els = document.querySelectorAll('.alert, p.text-success, p.text-danger, .result');
                            return Array.from(els).map(e => (e.innerText || '').trim()).filter(Boolean);
                        }""")

                        alert_str = " ".join(alerts)

                        if "invalid captcha" in alert_str.lower() or "captcha not matched" in alert_str.lower():
                            # Click captcha refresh button if available
                            try:
                                page.click("button.btn i.fa-sync, button.btn i.fa-redo, button.btn:has-text('Refresh')")
                                time.sleep(0.5)
                            except Exception:
                                pass
                            continue

                        # Parse allotment outcome
                        kitta = 0
                        allotted = False
                        status = "NOT_ALLOTTED"

                        kitta_match = re.search(r"allotted\s*([0-9]+)\s*(units|shares|kitta)", alert_str, re.I)
                        if kitta_match:
                            kitta = int(kitta_match.group(1))
                            allotted = True
                            status = "ALLOTTED"
                        elif "congratulation" in alert_str.lower() or ("allotted" in alert_str.lower() and "not allotted" not in alert_str.lower()):
                            allotted = True
                            kitta = 10
                            status = "ALLOTTED"
                        elif "sorry" in alert_str.lower() or "not allotted" in alert_str.lower():
                            status = "NOT_ALLOTTED"
                        elif "invalid boid" in alert_str.lower():
                            status = "INVALID_BOID"
                        else:
                            status = "NOT_ALLOTTED"

                        results.append({
                            "boid": clean_boid,
                            "allotted": allotted,
                            "kitta": kitta,
                            "status": status,
                            "message": alert_str or ("Allotted" if allotted else "Not Allotted"),
                        })
                        checked = True
                        break

                    if not checked:
                        results.append({
                            "boid": clean_boid,
                            "allotted": False,
                            "kitta": 0,
                            "status": "FAILED",
                            "message": "Captcha validation retry exhausted.",
                        })

                    time.sleep(0.3)

        except Exception as exc:
            logger.error("CDSC browser verification error: %s", exc)
            for acc in accounts[len(results):]:
                results.append({
                    "boid": acc.get("boid", ""),
                    "allotted": False,
                    "kitta": 0,
                    "status": "FAILED",
                    "message": f"Browser verification error: {exc}",
                })
        finally:
            try:
                proc.terminate()
                proc.kill()
            except Exception:
                pass

        return results
