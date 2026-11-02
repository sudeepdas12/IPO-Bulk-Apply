import re
import time
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

CDSC_IPOLIST_URL = "https://cdsc.com.np/ipolist"

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}


class CDSCIssueScraper:
    """
    Scrapes and analyzes live issue listings from CDSC Nepal (https://cdsc.com.np/ipolist).
    Provides instant, zero-credential discovery of open/upcoming IPOs, debentures,
    target audience classification (General Public vs Migrant vs Locals), and live subscription metrics.
    """

    def __init__(self, timeout: int = 10, cache_ttl_seconds: int = 60):
        self.timeout = timeout
        self.cache_ttl = cache_ttl_seconds
        self._cached_issues: Optional[List[Dict[str, Any]]] = None
        self._last_fetch_time: float = 0.0

    def fetch_current_issues(self, force_refresh: bool = False) -> Tuple[bool, str, List[Dict[str, Any]]]:
        """
        Fetch and parse the current issues table from CDSC official portal.
        Returns: (success: bool, message: str, issues: List[Dict])
        """
        now = time.time()
        if not force_refresh and self._cached_issues is not None and (now - self._last_fetch_time < self.cache_ttl):
            return True, "Loaded from cache", self._cached_issues

        try:
            resp = requests.get(CDSC_IPOLIST_URL, headers=DEFAULT_HEADERS, timeout=self.timeout)
            if resp.status_code != 200:
                return False, f"HTTP {resp.status_code} received from cdsc.com.np", []

            soup = BeautifulSoup(resp.text, "html.parser")
            table = soup.find("table")
            if not table:
                return False, "Issue table not found on cdsc.com.np/ipolist", []

            rows = table.find_all("tr")[1:]  # Skip header
            issues: List[Dict[str, Any]] = []

            for row in rows:
                cols = [td.get_text(strip=True) for td in row.find_all("td")]
                if len(cols) < 9:
                    continue

                raw_name = cols[1]
                issue_manager = cols[2]
                issued_unit_str = re.sub(r"\D", "", cols[3]) or "0"
                num_applicants_str = re.sub(r"\D", "", cols[4]) or "0"
                applied_unit_str = re.sub(r"\D", "", cols[5]) or "0"
                amount_str = re.sub(r"\D", "", cols[6]) or "0"
                open_date = cols[7].strip()
                close_date = cols[8].strip()
                last_update = cols[9].strip() if len(cols) > 9 else ""

                issued_units = int(issued_unit_str)
                applied_units = int(applied_unit_str)
                applicants = int(num_applicants_str)
                total_amount = int(amount_str)

                # Parse audience / eligibility from parenthesized text
                aud_match = re.search(r"\((.*?)\)", raw_name)
                audience_raw = aud_match.group(1).strip() if aud_match else "General Public"

                # Parse Scrip code (e.g. " - RBBLD89 (")
                scrip_match = re.search(r"-\s*([A-Za-z0-9]+)\s*\(", raw_name)
                scrip = scrip_match.group(1).strip() if scrip_match else ""

                # Clean company name
                clean_name = re.sub(r"-\s*[A-Za-z0-9]+\s*\(.*?\)", "", raw_name)
                clean_name = re.sub(r"\(.*?\)", "", clean_name).strip()
                if not clean_name:
                    clean_name = raw_name

                # Target audience classification
                aud_lower = audience_raw.lower()
                if any(k in aud_lower for k in ["foreign", "migrant", "baideshik"]):
                    target_group = "Foreign Migrant Workers"
                    is_general_public = False
                elif any(k in aud_lower for k in ["local", "project", "affected", "sthanik"]):
                    target_group = "Project Affected Locals"
                    is_general_public = False
                elif any(k in aud_lower for k in ["mutual", "fund"]):
                    target_group = "Mutual Funds"
                    is_general_public = False
                elif any(k in aud_lower for k in ["employee"]):
                    target_group = "Company Employees"
                    is_general_public = False
                else:
                    target_group = "General Public"
                    is_general_public = True

                # Issue type classification
                raw_lower = raw_name.lower()
                if "debenture" in raw_lower:
                    issue_type = "Debenture"
                elif "right" in raw_lower:
                    issue_type = "Right Share"
                elif "fpo" in raw_lower:
                    issue_type = "FPO"
                else:
                    issue_type = "IPO"

                # Subscription ratio
                sub_ratio = round(applied_units / issued_units, 2) if issued_units > 0 else 0.0
                is_oversubscribed = sub_ratio >= 1.0

                # Date & Status calculation
                status = "Open"
                days_left = 0
                try:
                    c_date = datetime.strptime(close_date, "%Y-%m-%d").date()
                    o_date = datetime.strptime(open_date, "%Y-%m-%d").date()
                    t_date = date.today()

                    if t_date < o_date:
                        status = "Upcoming"
                        days_left = (o_date - t_date).days
                    elif t_date > c_date:
                        status = "Closed"
                        days_left = 0
                    else:
                        status = "Open"
                        days_left = (c_date - t_date).days
                except Exception:
                    status = "Open"

                issues.append({
                    "raw_name": raw_name,
                    "company_name": clean_name,
                    "scrip": scrip,
                    "target_group": target_group,
                    "is_general_public": is_general_public,
                    "issue_type": issue_type,
                    "issue_manager": issue_manager,
                    "issued_units": issued_units,
                    "applied_units": applied_units,
                    "applicants": applicants,
                    "amount": total_amount,
                    "open_date": open_date,
                    "close_date": close_date,
                    "last_update": last_update,
                    "sub_ratio": sub_ratio,
                    "is_oversubscribed": is_oversubscribed,
                    "status": status,
                    "days_left": days_left,
                })

            self._cached_issues = issues
            self._last_fetch_time = now
            return True, f"Retrieved {len(issues)} current issue(s) from CDSC", issues

        except Exception as e:
            return False, f"Failed to connect to cdsc.com.np: {str(e)}", []

    def get_general_public_issues(self) -> List[Dict[str, Any]]:
        """Return only issues that standard General Public demats can apply for."""
        ok, _, issues = self.fetch_current_issues()
        if not ok:
            return []
        return [i for i in issues if i["is_general_public"]]
