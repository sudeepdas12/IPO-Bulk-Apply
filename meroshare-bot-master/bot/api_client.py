"""High-speed, resilient REST API client for Meroshare CDSC Nepal."""

from __future__ import annotations

import datetime
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

try:
    from curl_cffi import requests as c_requests
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False

from bot.cooldown_manager import CooldownManager
from bot.models import MeroshareNetworkError

logger = logging.getLogger("MeroshareAPIClient")
BASE_URL = "https://webbackend.cdsc.com.np/api"


class MeroshareAPIClient:
    """High-speed, retry-resilient REST API client for Meroshare CDSC Nepal."""

    def __init__(self, timeout: int = 15, max_retries: int = 3, retry_backoff: float = 0.5):
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self._capitals_cache: Optional[List[Dict[str, Any]]] = None
        self._init_session()

    def _init_session(self) -> None:
        """Initialize or reset HTTP session with authentic Chrome impersonation."""
        if HAS_CURL_CFFI:
            self.session = c_requests.Session(impersonate="chrome124")
        else:
            self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://meroshare.cdsc.com.np",
            "Referer": "https://meroshare.cdsc.com.np/",
        })

    def _request_with_retry(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        json_payload: Optional[Dict[str, Any]] = None,
    ) -> requests.Response:
        """Executes HTTP request with exponential backoff on transient network faults."""
        last_error: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                if method.upper() == "GET":
                    return self.session.get(url, headers=headers, timeout=self.timeout)
                elif method.upper() == "POST":
                    return self.session.post(url, json=json_payload, headers=headers, timeout=self.timeout)
                else:
                    return self.session.request(method, url, json=json_payload, headers=headers, timeout=self.timeout)
            except Exception as exc:
                last_error = exc
                wait_time = self.retry_backoff * (2 ** (attempt - 1))
                logger.warning(
                    "Network error on %s %s (attempt %d/%d): %s. Retrying in %.1fs...",
                    method, url, attempt, self.max_retries, exc, wait_time,
                )
                time.sleep(wait_time)

        raise MeroshareNetworkError(f"Request failed after {self.max_retries} attempts: {last_error}")

    def get_capitals(self) -> List[Dict[str, Any]]:
        """Fetch and cache list of all DP / Capital institutions."""
        if self._capitals_cache is not None:
            return self._capitals_cache

        url = f"{BASE_URL}/meroShare/capital/"
        try:
            resp = self._request_with_retry("GET", url)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    self._capitals_cache = data
                    return self._capitals_cache
            logger.warning("Capitals endpoint responded with status %d", resp.status_code)
        except MeroshareNetworkError as exc:
            logger.error("Failed to load capitals: %s", exc)
        except Exception as exc:
            logger.error("Unexpected error fetching capitals: %s", exc)
        return []

    def resolve_capital_id(self, capital_id_str: str) -> Optional[int]:
        """Convert a user's Capital ID string (e.g. '13016500' or '165') into the numeric clientId."""
        clean = capital_id_str.strip()
        if not clean:
            return None

        capitals = self.get_capitals()
        if not capitals:
            logger.warning("No capitals list available to resolve '%s'", capital_id_str)
            return None

        # 1. Try exact numeric id match
        if clean.isdigit():
            c_int = int(clean)
            for cap in capitals:
                if cap.get("id") == c_int:
                    return int(cap["id"])

        # 2. CDSC DP code often starts with 130...
        dp_num = clean[3:] if clean.startswith("130") else clean

        # 3. Try exact code match
        for cap in capitals:
            cap_code = str(cap.get("code", "")).strip()
            if cap_code == clean or cap_code == dp_num:
                return int(cap["id"])

        # 4. Try partial code match
        for cap in capitals:
            cap_code = str(cap.get("code", "")).strip()
            if dp_num and (dp_num in cap_code or cap_code in dp_num):
                return int(cap["id"])

        return None

    def login(self, capital_id_str: str, username: str, password: str) -> Tuple[bool, str, Optional[str]]:
        """
        Authenticate against Meroshare.
        Returns: (success: bool, message: str, token: Optional[str])
        """
        clean_cap = capital_id_str.strip()
        if not clean_cap:
            return False, "Capital ID / DP code is empty or missing in account configuration.", None

        client_id = self.resolve_capital_id(clean_cap)
        if not client_id:
            return False, f"Could not find Capital ID '{clean_cap}' in CDSC DP list", None

        # Clean fresh session for authentication
        self._init_session()

        url = f"{BASE_URL}/meroShare/auth/"
        payload: Dict[str, Any] = {
            "clientId": client_id,
            "username": username.strip(),
            "password": password.strip(),
        }

        try:
            resp = self._request_with_retry("POST", url, json_payload=payload)
            if resp.status_code == 200:
                if "Request Rejected" in resp.text or "The requested URL was rejected" in resp.text:
                    CooldownManager().record_cooldown("CDSC Firewall rejected login request (Temporary IP cooldown)")
                    return False, "CDSC Firewall rejected login request (Temporary IP cooldown)", None

                # Meroshare returns token in header 'Authorization'
                token = resp.headers.get("Authorization") or resp.headers.get("authorization")
                if not token and resp.content:
                    try:
                        data = resp.json()
                        token = data.get("Authorization") or data.get("token")
                    except Exception:
                        pass

                if token:
                    return True, "Login successful", str(token)
                return False, "Login responded with 200 but Authorization token was missing", None

            if resp.status_code == 401:
                return False, "Invalid username or password", None

            if resp.status_code in (403, 429):
                CooldownManager().record_cooldown(f"CDSC rate limit / firewall restriction (HTTP {resp.status_code})")
                return False, "CDSC Firewall rejected login request (Temporary IP cooldown)", None

            # Parse XML/JSON error message
            msg = resp.text
            match = re.search(r"<message>(.*?)</message>", msg)
            if match:
                return False, match.group(1), None

            try:
                data = resp.json()
                if isinstance(data, dict) and data.get("message"):
                    return False, str(data["message"]), None
            except Exception:
                pass

            return False, f"Login failed with status {resp.status_code}", None
        except MeroshareNetworkError as exc:
            return False, f"Network error during login: {exc.message}", None
        except Exception as exc:
            return False, f"Unexpected error during login: {exc}", None

    def get_user_details(self, token: str) -> Optional[Dict[str, Any]]:
        """Fetch own details like DEMAT number, customerId, BOID, etc."""
        url = f"{BASE_URL}/meroShare/ownDetail/"
        headers = {"Authorization": token}
        try:
            resp = self._request_with_retry("GET", url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict):
                    return data
            logger.warning("ownDetail responded with status %d", resp.status_code)
        except Exception as exc:
            logger.warning("Could not fetch user details: %s", exc)
        return None

    def get_applicable_issues(self, token: str) -> List[Dict[str, Any]]:
        """Fetch all currently open IPO / FPO / Right share issues."""
        url = f"{BASE_URL}/meroShare/companyShare/applicableIssue/"
        headers = {"Authorization": token}
        today = datetime.date.today().strftime("%Y-%m-%d")
        payload: Dict[str, Any] = {
            "filterDate": today,
            "filterCompanyWithOptions": True,
            "page": 1,
            "size": 50,
            "searchWord": "",
        }

        try:
            resp = self._request_with_retry("POST", url, headers=headers, json_payload=payload)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict):
                    obj = data.get("object", [])
                    return obj if isinstance(obj, list) else []
                elif isinstance(data, list):
                    return data
            logger.warning("applicableIssue responded with status %d", resp.status_code)
        except Exception as exc:
            logger.error("Error retrieving applicable issues: %s", exc)
            raise MeroshareNetworkError(f"Could not load applicable issues from Meroshare: {exc}") from exc
        return []

    def get_banks(self, token: str) -> List[Dict[str, Any]]:
        """Fetch user's registered CRN bank accounts."""
        url = f"{BASE_URL}/meroShare/bank/"
        headers = {"Authorization": token}
        try:
            resp = self._request_with_retry("GET", url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict) and "object" in data:
                    obj = data["object"]
                    return obj if isinstance(obj, list) else []
            logger.warning("bank endpoint responded with status %d", resp.status_code)
        except Exception as exc:
            logger.error("Error retrieving banks: %s", exc)
            raise MeroshareNetworkError(f"Could not load bank accounts: {exc}") from exc
        return []

    def get_portfolio(self, token: str, demat: str, client_code: str = "") -> Optional[Dict[str, Any]]:
        """
        Fetch user's stock holdings and portfolio valuation from Meroshare.
        Returns dict containing holding rows and aggregate valuation, or None on error.
        """
        url = f"{BASE_URL}/meroShareView/myPortfolio/"
        headers = {"Authorization": token}
        payload: Dict[str, Any] = {
            "sortBy": "script",
            "demat": [str(demat).strip()],
            "clientCode": str(client_code or "").strip(),
            "page": 1,
            "size": 500,
            "sortAsc": True,
        }
        try:
            resp = self._request_with_retry("POST", url, headers=headers, json_payload=payload)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict):
                    return data
            # Fallback to alternate endpoint if any
            alt_url = f"{BASE_URL}/meroShare/portfolio/"
            resp_alt = self._request_with_retry("POST", alt_url, headers=headers, json_payload=payload)
            if resp_alt.status_code == 200:
                data_alt = resp_alt.json()
                if isinstance(data_alt, dict):
                    return data_alt
            logger.warning("Portfolio endpoint responded with status %d", resp.status_code)
        except Exception as exc:
            logger.warning("Could not fetch portfolio for DEMAT %s: %s", demat, exc)
        return None

    def check_application_status(self, token: str, company_share_id: int) -> Optional[Dict[str, Any]]:
        """Check if user has already applied or get application status."""
        url = f"{BASE_URL}/meroShare/applicantForm/active/{company_share_id}"
        headers = {"Authorization": token}
        try:
            resp = self._request_with_retry("GET", url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                return data if isinstance(data, dict) else None
        except Exception as exc:
            logger.warning("Could not check application status for company %s: %s", company_share_id, exc)
        return None

    def get_application_report(self, token: str, company_share_id: int) -> Optional[Dict[str, Any]]:
        """Get official application report and allotment status across applied issues."""
        status = self.check_application_status(token, company_share_id)
        if status:
            return status
        url = f"{BASE_URL}/meroShare/applicantForm/report/"
        headers = {"Authorization": token}
        payload: Dict[str, Any] = {"page": 1, "size": 50, "filterDate": "", "searchWord": ""}
        try:
            resp = self._request_with_retry("POST", url, headers=headers, json_payload=payload)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("object", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
                for item in items:
                    if int(item.get("companyShareId", 0)) == int(company_share_id):
                        return item
        except Exception as exc:
            logger.warning("Could not query application report for company %s: %s", company_share_id, exc)
        return None

    def apply_ipo(
        self,
        token: str,
        user_details: Dict[str, Any],
        bank_info: Dict[str, Any],
        company_share_id: int,
        kitta: int,
        crn: str,
        txn_pin: str,
    ) -> Tuple[bool, str]:
        """
        Submit the IPO application via REST API.
        Returns: (success: bool, status_message: str)
        """
        url = f"{BASE_URL}/meroShare/applicantForm/"
        headers = {"Authorization": token}

        demat = user_details.get("demat") or user_details.get("boid") or ""
        boid = user_details.get("boid") or demat
        customer_id = user_details.get("id") or user_details.get("customerId") or 0

        account_number = bank_info.get("accountNumber") or bank_info.get("accountNo") or ""
        bank_code = bank_info.get("bankCode") or bank_info.get("code") or ""
        account_branch_id = bank_info.get("accountBranchId") or bank_info.get("branchId") or bank_info.get("id")

        payload: Dict[str, Any] = {
            "demat": str(demat),
            "boid": str(boid),
            "accountNumber": str(account_number),
            "customerId": customer_id,
            "appliedKitta": str(kitta),
            "crnNumber": str(crn).strip(),
            "bankCode": str(bank_code),
            "companyShareId": int(company_share_id),
            "accountBranchId": account_branch_id,
            "pin": str(txn_pin).strip(),
        }

        try:
            resp = self._request_with_retry("POST", url, headers=headers, json_payload=payload)

            # Response handling
            if resp.status_code in (200, 201):
                try:
                    data = resp.json()
                    msg = data.get("message", "Share Applied Successfully")
                    return True, str(msg)
                except Exception:
                    return True, "Share Applied Successfully"

            # Parse error
            err_text = resp.text
            match = re.search(r"<message>(.*?)</message>", err_text)
            if match:
                msg = match.group(1)
            else:
                try:
                    err_json = resp.json()
                    msg = err_json.get("message") or err_json.get("error") or str(err_json)
                except Exception:
                    msg = err_text[:150]

            msg_str = str(msg)
            if re.search(r"\balready\b|duplicate|previous|applied", msg_str, re.IGNORECASE):
                return False, f"Already Applied: {msg_str}"
            if re.search(r"balance|insufficient", msg_str, re.IGNORECASE):
                return False, f"Insufficient Balance: {msg_str}"
            if re.search(r"crn", msg_str, re.IGNORECASE):
                return False, f"CRN Error: {msg_str}"
            if re.search(r"pin", msg_str, re.IGNORECASE):
                return False, f"Invalid PIN: {msg_str}"

            return False, f"Application rejected ({resp.status_code}): {msg_str}"
        except MeroshareNetworkError as exc:
            return False, f"Application network error: {exc.message}"
        except Exception as exc:
            return False, f"Application error: {exc}"
