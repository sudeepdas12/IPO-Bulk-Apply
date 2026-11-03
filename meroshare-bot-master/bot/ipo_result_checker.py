"""CDSC IPO allotment result checker and Meroshare verification engine."""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

BASE_RESULT_URL = "https://iporesult.cdsc.com.np/result"
CDSC_HOME_URL = "https://iporesult.cdsc.com.np/"

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://iporesult.cdsc.com.np",
    "Referer": "https://iporesult.cdsc.com.np/",
    "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "Connection": "keep-alive",
}

FALLBACK_COMPANIES: List[Dict[str, Any]] = [
    {"id": 398, "name": "Him Parbat Hydropower Limited (HPHL)"},
    {"id": 394, "name": "Upper Lohore Khola Hydropower Company Limited"},
    {"id": 390, "name": "Sonapur Minerals and Oil Limited"},
    {"id": 386, "name": "Himalayan Reinsurance Limited"},
    {"id": 384, "name": "Sarbottam Cement Limited (Book Building)"},
    {"id": 382, "name": "Reliable Nepal Life Insurance Limited"},
    {"id": 379, "name": "Vision Lumbini Urja Company Limited"},
    {"id": 375, "name": "Mid Solu Hydropower Limited"},
    {"id": 372, "name": "Sun Nepal Life Insurance Limited"},
    {"id": 368, "name": "Ghorahi Cement Industry Limited"},
    {"id": 365, "name": "Citizen Life Insurance Company Limited"},
    {"id": 360, "name": "Upper Trishuli 3B Hydroelectric Project"},
    {"id": 355, "name": "Bhugol Energy Development Company Limited"},
    {"id": 350, "name": "Mai Khola Hydropower Limited"},
    {"id": 345, "name": "Sanima Middle Tamor Hydropower Limited"},
    {"id": 340, "name": "Asian Hydropower Limited"},
    {"id": 335, "name": "Supermai Hydropower Limited"},
    {"id": 330, "name": "Shuvam Power Limited"},
    {"id": 325, "name": "Barahi Hydropower Public Limited"},
    {"id": 320, "name": "Dordi Khola Hydropower Company Limited"},
]


class IPOResultChecker:
    """Advanced bulk IPO allotment checker for CDSC Nepal (iporesult.cdsc.com.np)."""

    is_waf_active: bool = False

    def __init__(self, timeout: int = 15, cache_file_path: Optional[str] = None):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(BROWSER_HEADERS)
        self._cached_companies: Optional[List[Dict[str, Any]]] = None
        self._warmed = False
        self.is_waf_active = False

        if cache_file_path:
            self._cache_file = Path(cache_file_path)
        else:
            base_dir = Path(__file__).resolve().parent.parent
            self._cache_file = base_dir / "data" / "cached_allotment_companies.json"

    def _warm_session(self) -> None:
        """Warm session by hitting home URL to receive preliminary cookies."""
        if self._warmed:
            return
        try:
            warm_headers = self.session.headers.copy()
            warm_headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            warm_headers["Sec-Fetch-Dest"] = "document"
            warm_headers["Sec-Fetch-Mode"] = "navigate"
            self.session.get(CDSC_HOME_URL, headers=warm_headers, timeout=self.timeout)
            self._warmed = True
        except Exception as e:
            logger.debug("Session warm failed: %s", e)

    def _load_fallback_companies(self) -> List[Dict[str, Any]]:
        """Load company list from local disk cache or fallback constant."""
        if self._cache_file.exists():
            try:
                with open(self._cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list) and len(data) > 0:
                        return data
            except Exception as e:
                logger.warning("Could not read disk company cache: %s", e)
        return list(FALLBACK_COMPANIES)

    def _save_cache_companies(self, companies: List[Dict[str, Any]]) -> None:
        """Persist fresh company list to local disk cache."""
        try:
            self._cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._cache_file, "w", encoding="utf-8") as f:
                json.dump(companies, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning("Could not persist company cache: %s", e)

    def _is_waf_response(self, resp: requests.Response) -> bool:
        """Check if response triggered CDSC F5 BIG-IP WAF block or challenge."""
        if resp.status_code in (403, 429):
            return True
        text = resp.text.strip()
        if any(marker in text for marker in ["Request Rejected", "Forbidden", "bobcmn", "TSPD"]):
            return True
        content_type = resp.headers.get("content-type", "").lower()
        if "text/html" in content_type and not (text.startswith("{") or text.startswith("[")):
            return True
        if text.startswith("<") and not (text.startswith("{") or text.startswith("[")):
            return True
        return False

    def get_company_list(self, force_refresh: bool = False) -> Tuple[bool, str, List[Dict[str, Any]]]:
        """
        Fetch uploaded company shares from CDSC portal.
        Falls back seamlessly to local cache if CDSC WAF firewall rejects the connection.
        Returns: (success: bool, message: str, company_list: List[Dict])
        """
        if not force_refresh and self._cached_companies:
            return True, "Loaded from cache", self._cached_companies

        self._warm_session()
        url = f"{BASE_RESULT_URL}/companyShares/fileUploaded"

        try:
            resp = self.session.get(url, timeout=self.timeout)
            if resp.status_code == 200 and not self._is_waf_response(resp):
                try:
                    data = resp.json()
                    companies = data.get("body", [])
                    if companies:
                        self._cached_companies = companies
                        self.is_waf_active = False
                        self._save_cache_companies(companies)
                        return True, f"Fetched {len(companies)} companies live from CDSC", companies
                except Exception:
                    pass

            if self._is_waf_response(resp):
                self.is_waf_active = True
                fallback = self._load_fallback_companies()
                self._cached_companies = fallback
                return (
                    True,
                    f"CDSC WAF active (Cloud/Foreign IP restricted). Loaded {len(fallback)} companies from offline database.",
                    fallback,
                )

            # Other status code
            fallback = self._load_fallback_companies()
            self._cached_companies = fallback
            return True, f"Server returned {resp.status_code}. Loaded {len(fallback)} companies from offline cache.", fallback

        except Exception as e:
            logger.warning("CDSC result connection error: %s", e)
            self.is_waf_active = True
            fallback = self._load_fallback_companies()
            self._cached_companies = fallback
            return True, f"Network offline. Loaded {len(fallback)} companies from offline cache.", fallback

    def check_boid(self, company_share_id: int, boid: str) -> Dict[str, Any]:
        """
        Check allotment result for a single 16-digit BOID.
        Returns:
            {
                "boid": str,
                "allotted": bool,
                "kitta": int,
                "status": str ("ALLOTTED" | "NOT_ALLOTTED" | "INVALID_BOID" | "WAF_BLOCKED" | "FAILED"),
                "message": str,
                "raw": dict
            }
        """
        clean_boid = re.sub(r"\D", "", str(boid).strip())
        if len(clean_boid) != 16:
            return {
                "boid": boid,
                "allotted": False,
                "kitta": 0,
                "status": "INVALID_BOID",
                "message": f"Invalid BOID length ({len(clean_boid)} digits, expected 16)",
                "raw": {},
            }

        url = f"{BASE_RESULT_URL}/result/check"
        payload: Dict[str, Any] = {
            "companyShareId": int(company_share_id),
            "boid": clean_boid,
        }
        headers = self.session.headers.copy()
        headers["Content-Type"] = "application/json"

        try:
            resp = self.session.post(url, json=payload, headers=headers, timeout=self.timeout)
            if self._is_waf_response(resp):
                self.is_waf_active = True
                return {
                    "boid": clean_boid,
                    "allotted": False,
                    "kitta": 0,
                    "status": "WAF_BLOCKED",
                    "message": "CDSC WAF Firewall rejected request (VPN or Cloud IP blocked)",
                    "raw": {},
                }

            if resp.status_code == 200:
                try:
                    data = resp.json()
                    success = bool(data.get("success", False))
                    msg = str(data.get("message", "")).strip()

                    # Extract kitta from message e.g. "allotted 10 units"
                    kitta = 0
                    kitta_match = re.search(r"allotted\s*([0-9]+)\s*(units|shares|kitta)", msg, re.I)
                    if kitta_match:
                        kitta = int(kitta_match.group(1))
                    elif success and ("congratulation" in msg.lower() or "allotted" in msg.lower()):
                        kitta = 10

                    allotted = bool(success or kitta > 0 or ("allotted" in msg.lower() and "not allotted" not in msg.lower()))
                    status = "ALLOTTED" if allotted else ("NOT_ALLOTTED" if "not allotted" in msg.lower() or "sorry" in msg.lower() else "FAILED")

                    return {
                        "boid": clean_boid,
                        "allotted": allotted,
                        "kitta": kitta,
                        "status": status,
                        "message": msg or ("Allotted" if allotted else "Not Allotted"),
                        "raw": data,
                    }
                except Exception:
                    pass

            return {
                "boid": clean_boid,
                "allotted": False,
                "kitta": 0,
                "status": "FAILED",
                "message": f"Server status {resp.status_code}",
                "raw": {},
            }

        except Exception as e:
            return {
                "boid": clean_boid,
                "allotted": False,
                "kitta": 0,
                "status": "FAILED",
                "message": f"Connection error: {str(e)}",
                "raw": {},
            }

    def check_bulk(
        self,
        company_share_id: int,
        accounts: List[Dict[str, Any]],
        progress_callback: Optional[Callable[[int, int, str, Dict[str, Any]], None]] = None,
        delay: float = 0.4,
    ) -> Dict[str, Any]:
        """Check IPO result for multiple Demat accounts in bulk."""
        allotted_list: List[Dict[str, Any]] = []
        not_allotted_list: List[Dict[str, Any]] = []
        waf_blocked_list: List[Dict[str, Any]] = []
        errors_list: List[Dict[str, Any]] = []
        details_list: List[Dict[str, Any]] = []
        total_kitta = 0

        total = len(accounts)

        for idx, acc in enumerate(accounts, start=1):
            name = acc.get("name", f"Account #{idx}")
            boid = acc.get("boid", "").strip()
            if not boid:
                cap = str(acc.get("capital_id", "")).strip()
                usr = str(acc.get("username", "")).strip()
                boid = f"{cap}{usr}"

            res = self.check_boid(company_share_id, boid)

            detail = {
                "name": name,
                "boid": boid,
                "allotted": res["allotted"],
                "kitta": res["kitta"],
                "status": res["status"],
                "message": res["message"],
            }
            details_list.append(detail)

            if res["status"] == "ALLOTTED":
                allotted_list.append(detail)
                total_kitta += res["kitta"]
            elif res["status"] == "NOT_ALLOTTED":
                not_allotted_list.append(detail)
            elif res["status"] == "WAF_BLOCKED":
                waf_blocked_list.append(detail)
            else:
                errors_list.append(detail)

            if progress_callback:
                progress_callback(idx, total, name, detail)

            time.sleep(delay)

        return {
            "total": total,
            "allotted": allotted_list,
            "not_allotted": not_allotted_list,
            "waf_blocked": waf_blocked_list,
            "errors": errors_list,
            "total_kitta": total_kitta,
            "details": details_list,
        }

    def check_via_meroshare(
        self,
        api_client: Any,
        account: Dict[str, Any],
        company_share_id: int,
    ) -> Dict[str, Any]:
        """
        Alternative: Check allotment status directly through logged-in Meroshare session.
        Bypasses CDSC Result WAF completely by querying webbackend.cdsc.com.np directly!
        """
        cap = str(account.get("capital_id", "") or account.get("capitalid", "")).strip()
        usr = str(account.get("username", "")).strip()
        pwd = str(account.get("password", "")).strip()
        name = str(account.get("name", usr or "Account"))
        boid = account.get("boid") or f"{cap}{usr.zfill(8) if usr.isdigit() else usr}"

        if not (cap and usr and pwd):
            fail_msg = "Missing account credentials for Meroshare login"
            if not pwd:
                fail_msg = "Password missing or encrypted on another PC (DPAPI machine-lock). Re-enter password or switch to CDSC Browser AI Solver."
            return {
                "name": name,
                "boid": boid,
                "allotted": False,
                "kitta": 0,
                "status": "AUTH_FAILED",
                "message": fail_msg,
            }

        ok, msg, token = api_client.login(cap, usr, pwd)
        if not ok or not token:
            if "cooldown" in msg.lower() or "firewall" in msg.lower() or "rejected" in msg.lower():
                return {
                    "name": name,
                    "boid": boid,
                    "allotted": False,
                    "kitta": 0,
                    "status": "IP_COOLDOWN",
                    "message": msg,
                }
            return {
                "name": name,
                "boid": boid,
                "allotted": False,
                "kitta": 0,
                "status": "AUTH_FAILED",
                "message": f"Meroshare login failed: {msg}",
            }

        # Check report or active form
        status_info = None
        if hasattr(api_client, "get_application_report"):
            status_info = api_client.get_application_report(token, company_share_id)
        if not status_info:
            status_info = api_client.check_application_status(token, company_share_id)

        if not status_info:
            return {
                "name": name,
                "boid": boid,
                "allotted": False,
                "kitta": 0,
                "status": "NOT_APPLIED",
                "message": "No application record found for this company in Demat account",
            }

        status_name = str(status_info.get("statusName", "")).upper()
        status_desc = str(status_info.get("statusDescription", ""))
        allotted_kitta = int(status_info.get("allottedKitta") or status_info.get("allotedKitta") or 0)
        applied_kitta = int(status_info.get("appliedKitta") or 0)

        allotted = "ALLOT" in status_name and "NOT" not in status_name
        if allotted and allotted_kitta == 0:
            allotted_kitta = applied_kitta or 10

        status_label = "ALLOTTED" if allotted else ("NOT_ALLOTTED" if "NOT ALLOT" in status_name else status_name)

        return {
            "name": name,
            "boid": boid,
            "allotted": allotted,
            "kitta": allotted_kitta if allotted else 0,
            "status": status_label,
            "message": status_desc or status_name,
        }
