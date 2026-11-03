"""Account manager for Meroshare Demat accounts."""

from __future__ import annotations

import csv
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from bot.models import Account
from bot.security import decrypt_text, encrypt_text, is_masked_placeholder, secure_file_permissions

EXPECTED_HEADERS = [
    ["name", "capitalid", "username", "password", "bank", "kitta", "crn", "txn_pin"],
    ["name", "capitalid", "username", "password", "bank", "kitta", "crn", "txn_pin", "branch"],
    ["name", "capitalid", "username", "password", "bank", "kitta", "crn", "txn_pin", "branch", "company"],
]


class AccountManager:
    """Manages Meroshare accounts, validation, persistence, and safe sync."""

    def __init__(self, file_path: Optional[Path] = None):
        if file_path is None:
            curr_dir = Path(__file__).resolve().parent
            candidates = [
                curr_dir.parent / "demats.txt",
                curr_dir / "demats.txt",
                Path.cwd() / "demats.txt",
                Path.cwd() / "meroshare-bot-master" / "demats.txt",
            ]
            self.file_path = next((p for p in candidates if p.exists()), candidates[0])
        else:
            self.file_path = Path(file_path)

    def load_account_objects(self) -> List[Account]:
        """Loads accounts as domain Account objects."""
        raw_list = self.load_accounts()
        return [Account.from_dict(d) for d in raw_list]

    def load_accounts(self) -> List[Dict[str, Any]]:
        """Load accounts from demats.txt into structured dictionaries."""
        accounts: List[Dict[str, Any]] = []
        if not self.file_path.exists():
            return accounts

        with self.file_path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = list(csv.reader(f))

        for line_no, row in enumerate(reader, start=1):
            if not row or all(not cell.strip() for cell in row):
                continue

            normalized = [x.strip().lower() for x in row]
            if line_no == 1 and normalized in EXPECTED_HEADERS:
                continue

            if len(row) not in (8, 9, 10):
                continue

            name = row[0].strip()
            capital_id = row[1].strip()
            username = row[2].strip()
            password = decrypt_text(row[3].strip())
            bank = row[4].strip()
            kitta = row[5].strip()
            crn = decrypt_text(row[6].strip())
            txn_pin = decrypt_text(row[7].strip())
            branch = row[8].strip() if len(row) >= 9 else ""
            company = row[9].strip() if len(row) >= 10 else ""

            acc = Account(
                name=name,
                capital_id=capital_id,
                username=username,
                password=password,
                bank=bank,
                kitta=kitta if kitta else "10",
                crn=crn,
                txn_pin=txn_pin,
                branch=branch,
                company=company,
                id=line_no,
            )
            accounts.append(acc.to_dict(mask_secrets=False))

        return accounts

    def is_vault_encrypted(self) -> bool:
        """Checks if stored vault credentials contain encrypted (DPAPI) secrets."""
        if not self.file_path.exists():
            return False
        try:
            with self.file_path.open("r", encoding="utf-8-sig", newline="") as f:
                content = f.read()
                return "DPAPI:" in content
        except Exception:
            return False

    def encrypt_vault(self) -> bool:
        """Encrypts all account passwords, PINs, and CRNs at rest using Windows DPAPI."""
        accs = self.load_accounts()
        if not accs:
            return True
        return self.save_accounts(accs, encrypt_secrets=True)

    def decrypt_vault(self) -> bool:
        """Converts vault credentials back to plaintext."""
        accs = self.load_accounts()
        if not accs:
            return True
        return self.save_accounts(accs, encrypt_secrets=False)

    def save_accounts(self, accounts: List[Dict[str, Any]], encrypt_secrets: Optional[bool] = None) -> bool:
        """
        Atomically save accounts list back to demats.txt.
        If any password or PIN contains a masked placeholder, preserves existing secret.
        Supports encryption at rest via Windows DPAPI.
        """
        existing_lookup: Dict[str, Dict[str, Any]] = {}
        if self.file_path.exists():
            for old in self.load_accounts():
                key = f"{old.get('capital_id')}_{old.get('username')}".lower()
                existing_lookup[key] = old

        header = ["Name", "CapitalID", "Username", "Password", "Bank", "Kitta", "CRN", "TXN_PIN", "Branch", "Company"]
        rows = [header]

        should_encrypt = self.is_vault_encrypted() if encrypt_secrets is None else encrypt_secrets

        for acc in accounts:
            cap_id = str(acc.get("capital_id", "")).strip()
            uname = str(acc.get("username", "")).strip()
            key = f"{cap_id}_{uname}".lower()
            old_data = existing_lookup.get(key, {})

            pwd = str(acc.get("password", "")).strip()
            if is_masked_placeholder(pwd) and old_data.get("password"):
                pwd = str(old_data["password"]).strip()

            pin = str(acc.get("txn_pin", "")).strip()
            if is_masked_placeholder(pin) and old_data.get("txn_pin"):
                pin = str(old_data["txn_pin"]).strip()

            crn_val = str(acc.get("crn", "")).strip()
            if is_masked_placeholder(crn_val) and old_data.get("crn"):
                crn_val = str(old_data["crn"]).strip()

            if should_encrypt:
                pwd_to_save = encrypt_text(pwd) if not pwd.startswith("DPAPI:") else pwd
                pin_to_save = encrypt_text(pin) if not pin.startswith("DPAPI:") else pin
                crn_to_save = encrypt_text(crn_val) if not crn_val.startswith("DPAPI:") else crn_val
            else:
                pwd_to_save = pwd
                pin_to_save = pin
                crn_to_save = crn_val

            rows.append([
                str(acc.get("name", "")).strip(),
                cap_id,
                uname,
                pwd_to_save,
                str(acc.get("bank", "")).strip(),
                str(acc.get("kitta", "10")).strip() or "10",
                crn_to_save,
                pin_to_save,
                str(acc.get("branch", "")).strip(),
                str(acc.get("company", "")).strip(),
            ])

        # Atomic write to temporary file in same directory, then rename
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        temp_fd, temp_path_str = tempfile.mkstemp(
            dir=str(self.file_path.parent),
            prefix="demats_tmp_",
            suffix=".txt",
            text=True,
        )
        temp_path = Path(temp_path_str)
        try:
            with os.fdopen(temp_fd, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerows(rows)
                f.flush()
                os.fsync(f.fileno())

            secure_file_permissions(temp_path)
            temp_path.replace(self.file_path)
            secure_file_permissions(self.file_path)
            return True
        except Exception:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass
            raise

    @staticmethod
    def validate_account(acc: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Validate an account dictionary using the domain Account model."""
        account_obj = Account.from_dict(acc)
        return account_obj.validate()

    def add_account(self, acc: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate and add an account."""
        is_valid, errors = self.validate_account(acc)
        if not is_valid:
            return False, "; ".join(errors)

        accounts = self.load_accounts()
        cap_id = str(acc.get("capital_id", "")).strip()
        uname = str(acc.get("username", "")).strip().lower()

        for existing in accounts:
            if existing.get("username", "").strip().lower() == uname and str(existing.get("capital_id", "")).strip() == cap_id:
                return False, f"Account with username '{uname}' and Capital ID '{cap_id}' already exists."

        accounts.append(acc)
        self.save_accounts(accounts)
        return True, "Account added successfully."

    def update_account(self, index: int, updated: Dict[str, Any]) -> Tuple[bool, str]:
        """Update an existing account by its list index."""
        # Check if secrets were left masked; restore them before validation if needed
        accounts = self.load_accounts()
        if index < 0 or index >= len(accounts):
            return False, "Account index out of range."

        old_acc = accounts[index]
        validated_dict = dict(updated)
        if is_masked_placeholder(str(validated_dict.get("password", ""))) and old_acc.get("password"):
            validated_dict["password"] = old_acc["password"]
        if is_masked_placeholder(str(validated_dict.get("txn_pin", ""))) and old_acc.get("txn_pin"):
            validated_dict["txn_pin"] = old_acc["txn_pin"]
        if is_masked_placeholder(str(validated_dict.get("crn", ""))) and old_acc.get("crn"):
            validated_dict["crn"] = old_acc["crn"]

        is_valid, errors = self.validate_account(validated_dict)
        if not is_valid:
            return False, "; ".join(errors)

        accounts[index] = validated_dict
        self.save_accounts(accounts)
        return True, "Account updated successfully."

    def delete_account(self, index: int) -> Tuple[bool, str]:
        """Delete an account by its list index."""
        accounts = self.load_accounts()
        if index < 0 or index >= len(accounts):
            return False, "Account index out of range."

        removed = accounts.pop(index)
        self.save_accounts(accounts)
        return True, f"Account '{removed.get('name')}' deleted successfully."

    def bulk_update_kitta(self, kitta: int) -> int:
        """Update default kitta across all accounts."""
        accounts = self.load_accounts()
        for a in accounts:
            a["kitta"] = str(kitta)
        self.save_accounts(accounts)
        return len(accounts)

    def bulk_update_company(self, company: str) -> int:
        """Update target company across all accounts."""
        accounts = self.load_accounts()
        for a in accounts:
            a["company"] = company.strip()
        self.save_accounts(accounts)
        return len(accounts)

    def bulk_save_all(self, accounts: List[Dict[str, Any]]) -> Tuple[bool, str]:
        """Save a modified list of accounts after validation."""
        existing = self.load_accounts()
        for idx, a in enumerate(accounts, start=1):
            check_dict = dict(a)
            if idx - 1 < len(existing):
                old = existing[idx - 1]
                if is_masked_placeholder(str(check_dict.get("password", ""))) and old.get("password"):
                    check_dict["password"] = old["password"]
                if is_masked_placeholder(str(check_dict.get("txn_pin", ""))) and old.get("txn_pin"):
                    check_dict["txn_pin"] = old["txn_pin"]
                if is_masked_placeholder(str(check_dict.get("crn", ""))) and old.get("crn"):
                    check_dict["crn"] = old["crn"]

            is_valid, errors = self.validate_account(check_dict)
            if not is_valid:
                return False, f"Row #{idx} ({a.get('name', 'Unknown')}): {'; '.join(errors)}"

        self.save_accounts(accounts)
        return True, f"Successfully saved and validated {len(accounts)} accounts."
