"""Domain models, result enums, and typed exceptions for Meroshare AutoPilot."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class ResultState(str, Enum):
    """Normalized execution and check outcome states."""
    SUCCESS = "SUCCESS"
    ALREADY_APPLIED = "ALREADY_APPLIED"
    NO_ISSUE = "NO_ISSUE"
    SKIPPED = "SKIPPED"
    AUTH_FAILED = "AUTH_FAILED"
    IP_COOLDOWN = "IP_COOLDOWN"
    DEFERRED_IP_COOLDOWN = "DEFERRED_IP_COOLDOWN"
    NETWORK_ERROR = "NETWORK_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    RATE_LIMITED = "RATE_LIMITED"
    FAILED = "FAILED"

    @property
    def is_terminal_failure(self) -> bool:
        return self in (ResultState.AUTH_FAILED, ResultState.FAILED, ResultState.VALIDATION_ERROR, ResultState.IP_COOLDOWN)

    @property
    def is_success_or_skipped(self) -> bool:
        return self in (ResultState.SUCCESS, ResultState.ALREADY_APPLIED, ResultState.SKIPPED, ResultState.NO_ISSUE, ResultState.DEFERRED_IP_COOLDOWN)


# Typed Exceptions Hierarchy
class MeroshareError(Exception):
    """Base exception for all Meroshare bot errors."""
    def __init__(self, message: str, state: ResultState = ResultState.FAILED):
        super().__init__(message)
        self.message = message
        self.state = state


class MeroshareAuthError(MeroshareError):
    """Raised when authentication fails (invalid credentials, expired session)."""
    def __init__(self, message: str = "Invalid credentials or unauthorized"):
        super().__init__(message, state=ResultState.AUTH_FAILED)


class MeroshareIpCooldownError(MeroshareError):
    """Raised when CDSC/Meroshare firewall imposes an IP cooldown."""
    def __init__(self, message: str = "CDSC Firewall rejected login request (Temporary IP cooldown)"):
        super().__init__(message, state=ResultState.IP_COOLDOWN)


class MeroshareNetworkError(MeroshareError):
    """Raised on connection drop, DNS failure, or API gateway timeout."""
    def __init__(self, message: str = "Network or gateway communication error"):
        super().__init__(message, state=ResultState.NETWORK_ERROR)


class MeroshareRateLimitError(MeroshareError):
    """Raised when CDSC/Meroshare throttles requests."""
    def __init__(self, message: str = "Rate limit encountered; throttling requests"):
        super().__init__(message, state=ResultState.RATE_LIMITED)


class MeroshareIssueNotFoundError(MeroshareError):
    """Raised when the specified target IPO company is not currently open for application."""
    def __init__(self, message: str = "Target IPO issue is not currently open"):
        super().__init__(message, state=ResultState.NO_ISSUE)


class MeroshareValidationError(MeroshareError):
    """Raised when account or form parameters fail validation."""
    def __init__(self, message: str):
        super().__init__(message, state=ResultState.VALIDATION_ERROR)


class SkippableIpoStateError(MeroshareError):
    """Raised when an application is already submitted or in non-applicable state."""
    def __init__(self, message: str = "IPO Already Applied"):
        super().__init__(message, state=ResultState.ALREADY_APPLIED)


@dataclass
class Account:
    """Represents a Meroshare Demat applicant account with validation and redaction."""
    name: str
    capital_id: str
    username: str
    password: str
    bank: str
    kitta: str = "10"
    crn: str = ""
    txn_pin: str = ""
    branch: str = ""
    company: str = ""
    id: Optional[int] = None

    def clean(self) -> "Account":
        """Returns a sanitized account with trimmed fields."""
        return Account(
            name=self.name.strip(),
            capital_id=self.capital_id.strip(),
            username=self.username.strip(),
            password=self.password.strip(),
            bank=self.bank.strip(),
            kitta=str(self.kitta).strip() or "10",
            crn=self.crn.strip(),
            txn_pin=self.txn_pin.strip(),
            branch=self.branch.strip(),
            company=self.company.strip(),
            id=self.id,
        )

    @property
    def boid(self) -> str:
        """Constructs 16-digit BOID from capital_id and username if standard format."""
        return f"{self.capital_id.strip()}{self.username.strip()}"

    def masked_password(self) -> str:
        """Returns a masked representation of the password."""
        return "••••••••" if self.password else ""

    def masked_pin(self) -> str:
        """Returns a masked representation of the transaction PIN."""
        return "••••" if self.txn_pin else ""

    def masked_crn(self) -> str:
        """Returns partially masked CRN keeping last 3 chars visible if long enough."""
        clean = self.crn.strip()
        if len(clean) > 4:
            return "•" * (len(clean) - 3) + clean[-3:]
        return "••••" if clean else ""

    def to_dict(self, mask_secrets: bool = False) -> Dict[str, Any]:
        """Serializes account to dictionary with optional secret masking."""
        return {
            "id": self.id,
            "name": self.name,
            "capital_id": self.capital_id,
            "username": self.username,
            "password": self.masked_password() if mask_secrets else self.password,
            "bank": self.bank,
            "kitta": self.kitta,
            "crn": self.masked_crn() if mask_secrets else self.crn,
            "txn_pin": self.masked_pin() if mask_secrets else self.txn_pin,
            "branch": self.branch,
            "company": self.company,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Account":
        """Instantiates an Account from a dictionary."""
        return cls(
            name=str(data.get("name", "")).strip(),
            capital_id=str(data.get("capital_id", "") or data.get("CapitalID", "")).strip(),
            username=str(data.get("username", "") or data.get("Username", "")).strip(),
            password=str(data.get("password", "") or data.get("Password", "")).strip(),
            bank=str(data.get("bank", "") or data.get("Bank", "")).strip(),
            kitta=str(data.get("kitta", "10") or data.get("Kitta", "10")).strip() or "10",
            crn=str(data.get("crn", "") or data.get("CRN", "")).strip(),
            txn_pin=str(data.get("txn_pin", "") or data.get("TXN_PIN", "")).strip(),
            branch=str(data.get("branch", "") or data.get("Branch", "")).strip(),
            company=str(data.get("company", "") or data.get("Company", "")).strip(),
            id=data.get("id") if isinstance(data.get("id"), int) else None,
        )

    def validate(self) -> Tuple[bool, List[str]]:
        """
        Validates account fields against Meroshare and banking constraints.
        Returns: (is_valid, list_of_error_strings)
        """
        errors: List[str] = []

        if not self.name.strip():
            errors.append("Account name cannot be empty")

        clean_cap = self.capital_id.strip()
        if not (clean_cap.isdigit() and len(clean_cap) in (3, 4, 8)):
            errors.append(f"Capital ID '{self.capital_id}' must be 3, 4 or 8 digits (e.g. 13016500)")

        if not self.username.strip():
            errors.append("Username cannot be empty")

        if not self.password.strip():
            errors.append("Password cannot be empty")

        if not self.bank.strip() or not re.search(r"[A-Za-z]", self.bank):
            errors.append(f"Invalid bank name '{self.bank}'")

        kitta_str = str(self.kitta).strip()
        if not kitta_str.isdigit() or int(kitta_str) < 10 or int(kitta_str) % 10 != 0:
            errors.append(f"Kitta '{self.kitta}' must be a multiple of 10 and >= 10")

        crn_str = self.crn.strip()
        if not crn_str or not re.fullmatch(r"[A-Za-z0-9_-]{4,30}", crn_str):
            errors.append(f"CRN '{self.crn}' must be alphanumeric between 4 and 30 characters")

        pin_str = self.txn_pin.strip()
        if not pin_str or not re.fullmatch(r"\d{4}", pin_str):
            errors.append(f"Transaction PIN '{self.txn_pin}' must be exactly 4 digits")

        return len(errors) == 0, errors


@dataclass
class AccountResult:
    """Standardized result for an individual account execution."""
    account_name: str
    username: str
    status: ResultState
    message: str
    kitta: int = 10
    company: str = ""
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "account": self.account_name,
            "username": self.username,
            "status": self.status.value,
            "message": self.message,
            "kitta": self.kitta,
            "company": self.company,
            "timestamp": self.timestamp,
        }
