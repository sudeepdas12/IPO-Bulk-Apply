import csv
import re
import sys
from pathlib import Path

EXPECTED_HEADERS = [
    ["name", "capitalid", "username", "password", "bank", "kitta", "crn", "txn_pin"],
    ["name", "capitalid", "username", "password", "bank", "kitta", "crn", "txn_pin", "branch"],
    ["name", "capitalid", "username", "password", "bank", "kitta", "crn", "txn_pin", "branch", "company"],
]

BANK_ALIASES = {
    "NIC ASIA BANK LTD": "NIC ASIA BANK LTD",
    "NABIL BANK LTD": "NABIL BANK LTD",
    "NABIL BANK LIMITED": "NABIL BANK LTD",
    "CIVIL BANK LTD": "CIVIL BANK LTD",
    "NEPAL INVESTMENT BANK LTD": "NEPAL INVESTMENT BANK LTD",
    "GARIMA BIKAS BANK LTD": "GARIMA BIKAS BANK LTD",
    "MAHALAXMI BIKAS BANK LTD": "MAHALAXMI BIKAS BANK LTD",
    "NMB BANK LTD": "NMB BANK LTD",
    "NEPAL SBI BANK LTD": "NEPAL SBI BANK LTD",
    "LUMBINI BIKAS BANK LTD": "LUMBINI BIKAS BANK LTD",
}


def normalize_bank(bank_name):
    normalized = re.sub(r"\s+", " ", bank_name.strip().upper().rstrip("."))
    return BANK_ALIASES.get(normalized, normalized)


def is_header_row(row):
    return [item.strip().lower() for item in row] in EXPECTED_HEADERS


def validate_row(line_no, row):
    issues = []
    if len(row) not in (8, 9, 10):
        issues.append((line_no, "wrong_field_count", f"expected 8, 9 or 10, got {len(row)}"))
        return issues, None

    if len(row) == 8:
        name, capitalid, username, password, bank, kitta, crn, txn_pin = [x.strip() for x in row]
        branch = ""
        company = ""
    elif len(row) == 9:
        name, capitalid, username, password, bank, kitta, crn, txn_pin, branch = [x.strip() for x in row]
        company = ""
    else:
        name, capitalid, username, password, bank, kitta, crn, txn_pin, branch, company = [x.strip() for x in row]

    if not name:
        issues.append((line_no, "name_empty", name))

    if not re.fullmatch(r"\d{8}", capitalid):
        issues.append((line_no, "capitalid_invalid", capitalid))
    elif not capitalid.startswith("130"):
        issues.append((line_no, "capitalid_prefix_unexpected", capitalid))

    if not username:
        issues.append((line_no, "username_empty", username))

    if not password:
        issues.append((line_no, "password_empty", password))

    if not re.fullmatch(r"\d+", kitta) or int(kitta) <= 0:
        issues.append((line_no, "kitta_invalid", kitta))

    if not re.fullmatch(r"[A-Za-z0-9]{6,20}", crn):
        issues.append((line_no, "crn_invalid", crn))

    if not re.fullmatch(r"\d{4}", txn_pin):
        issues.append((line_no, "txn_pin_invalid", txn_pin))

    normalized_bank = normalize_bank(bank)
    if normalized_bank not in BANK_ALIASES.values():
        issues.append((line_no, "bank_unknown", bank))

    parsed = {
        "name": name,
        "capitalid": capitalid,
        "username": username,
        "password": password,
        "bank": normalized_bank,
        "kitta": kitta,
        "crn": crn,
        "txn_pin": txn_pin,
        "branch": branch,
        "company": company,
    }
    return issues, parsed


def main():
    demat_path = Path(__file__).resolve().parents[1] / "demats.txt"
    print(f"Validating {demat_path}...")

    if not demat_path.exists():
        print("\nFound issues:")
        print(f" - ('global', 'file_missing', '{demat_path}')")
        sys.exit(1)

    issues = []
    accounts = []

    with demat_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.reader(file)
        for line_no, row in enumerate(reader, start=1):
            if not row or all(not cell.strip() for cell in row):
                continue

            if line_no == 1 and is_header_row(row):
                continue

            row_issues, account = validate_row(line_no, row)
            issues.extend(row_issues)
            if account:
                accounts.append(account)

    # Treat duplicate CapitalID as a valid scenario (clients from same capital).
    # Report it as a warning but do not fail validation because of it.
    warnings = []

    capital_ids = [account["capitalid"] for account in accounts]
    duplicate_capital_ids = sorted({item for item in capital_ids if capital_ids.count(item) > 1})
    if duplicate_capital_ids:
        warnings.append(("global", "duplicate_capitalid", ",".join(duplicate_capital_ids)))

    usernames = [account["username"] for account in accounts]
    duplicate_usernames = sorted({item for item in usernames if usernames.count(item) > 1})
    if duplicate_usernames:
        issues.append(("global", "duplicate_username", ",".join(duplicate_usernames)))

    print("\nFound issues:")
    if not issues:
        print(" - No format issues detected.")
    else:
        for issue in issues:
            print(" -", issue)

    if warnings:
        print("\nWarnings:")
        for w in warnings:
            print(" -", w)

    print("\nDetected accounts:")
    for account in accounts:
        display = [
            account["name"],
            account["capitalid"],
            account["username"],
            "***",
            account["bank"],
            account["kitta"],
            account["crn"],
            "****",
        ]
        if account.get("company"):
            display.append(account["company"])
        print(" -", display)

    # Exit only when true errors were found (warnings like duplicate CapitalID won't fail validation)
    if issues:
        sys.exit(1)


if __name__ == "__main__":
    main()
