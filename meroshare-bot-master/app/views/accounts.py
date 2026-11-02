"""Secure Account Registry view for Meroshare AutoPilot."""

from __future__ import annotations

import csv
import io
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from bot.account_manager import AccountManager
from bot.security import mask_secret, redact_accounts_list


@st.dialog("Add new Demat account")
def add_account_dialog(acc_mgr: AccountManager) -> None:
    """Secure modal dialog to add a new account without exposing secrets."""
    st.caption("Enter the Meroshare credentials for the new applicant.")

    with st.form("form_add_account"):
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("Applicant full name*", placeholder="e.g. Ram Bahadur Thapa")
            cap_id = st.text_input("Capital ID / DP code*", placeholder="e.g. 13016500")
            username = st.text_input("Meroshare username / Demat*", placeholder="e.g. 00123456")
            password = st.text_input("Password*", type="password")
            bank = st.text_input("Bank name*", placeholder="e.g. Nabil Bank Limited")

        with col2:
            kitta = st.number_input("Default kitta*", min_value=10, max_value=1000, value=10, step=10)
            crn = st.text_input("CRN number*", type="password", placeholder="e.g. 00867066")
            txn_pin = st.text_input("4-digit transaction PIN*", type="password", max_chars=4, placeholder="e.g. 1234")
            branch = st.text_input("Branch name", placeholder="e.g. Kathmandu Main")
            company = st.text_input("Preferred target company (optional)", placeholder="e.g. Upper Tamakoshi")

        submit = st.form_submit_button("Save account", icon=":material/save:", width="stretch")

        if submit:
            new_acc = {
                "name": name.strip(),
                "capital_id": cap_id.strip(),
                "username": username.strip(),
                "password": password.strip(),
                "bank": bank.strip(),
                "kitta": str(kitta),
                "crn": crn.strip(),
                "txn_pin": txn_pin.strip(),
                "branch": branch.strip(),
                "company": company.strip(),
            }
            ok, msg = acc_mgr.add_account(new_acc)
            if ok:
                st.success("Account added successfully.", icon=":material/check_circle:")
                st.rerun()
            else:
                st.error(f"Validation error: {msg}", icon=":material/error:")


@st.dialog("Edit account credentials")
def edit_credentials_dialog(acc_mgr: AccountManager, accounts: List[Dict[str, Any]]) -> None:
    """Secure modal dialog to update credentials without exposing existing passwords."""
    if not accounts:
        st.info("No accounts available to edit.")
        return

    account_labels = [f"{a.get('name', 'Account')} ({a.get('username', '')})" for a in accounts]
    selected_label = st.selectbox("Select account to modify", options=account_labels)
    selected_idx = account_labels.index(selected_label)
    curr_acc = accounts[selected_idx]

    st.info(
        "For security, existing passwords and PINs are never displayed. "
        "Leave credential fields blank if you do not wish to change them.",
        icon=":material/lock:",
    )

    with st.form("form_edit_account"):
        c1, c2 = st.columns(2)
        with c1:
            new_name = st.text_input("Applicant name", value=curr_acc.get("name", ""))
            new_bank = st.text_input("Bank name", value=curr_acc.get("bank", ""))
            new_branch = st.text_input("Branch name", value=curr_acc.get("branch", ""))
            new_kitta = st.number_input(
                "Default kitta",
                min_value=10,
                max_value=1000,
                value=int(curr_acc.get("kitta", 10)) if str(curr_acc.get("kitta", "")).isdigit() else 10,
                step=10,
            )

        with c2:
            new_password = st.text_input("New password (leave blank to keep current)", type="password")
            new_pin = st.text_input("New transaction PIN (leave blank to keep current)", type="password", max_chars=4)
            new_crn = st.text_input("New CRN (leave blank to keep current)", type="password")
            new_company = st.text_input("Target company override", value=curr_acc.get("company", ""))

        submit = st.form_submit_button("Update account", icon=":material/check:", width="stretch")

        if submit:
            updated_dict = {
                "name": new_name.strip() or curr_acc.get("name", ""),
                "capital_id": curr_acc.get("capital_id", ""),
                "username": curr_acc.get("username", ""),
                "password": new_password.strip() if new_password.strip() else curr_acc.get("password", ""),
                "bank": new_bank.strip() or curr_acc.get("bank", ""),
                "kitta": str(new_kitta),
                "crn": new_crn.strip() if new_crn.strip() else curr_acc.get("crn", ""),
                "txn_pin": new_pin.strip() if new_pin.strip() else curr_acc.get("txn_pin", ""),
                "branch": new_branch.strip() or curr_acc.get("branch", ""),
                "company": new_company.strip(),
            }

            ok, msg = acc_mgr.update_account(selected_idx, updated_dict)
            if ok:
                st.success("Account credentials updated safely.", icon=":material/check_circle:")
                st.rerun()
            else:
                st.error(f"Update failed: {msg}", icon=":material/error:")


@st.dialog("Delete account confirmation")
def delete_account_dialog(acc_mgr: AccountManager, accounts: List[Dict[str, Any]]) -> None:
    """Destructive confirmation modal for account removal."""
    if not accounts:
        st.info("No accounts to remove.")
        return

    account_labels = [f"{a.get('name', 'Account')} ({a.get('username', '')})" for a in accounts]
    selected_label = st.selectbox("Select account to permanently remove", options=account_labels)
    selected_idx = account_labels.index(selected_label)
    curr_acc = accounts[selected_idx]

    st.warning(
        f"Are you sure you want to remove **{curr_acc.get('name')}** (`{curr_acc.get('username')}`)? "
        "This action cannot be undone.",
        icon=":material/warning:",
    )

    confirm_box = st.checkbox("I understand this account will be permanently removed.")

    if st.button("Permanently delete account", icon=":material/delete_forever:", disabled=not confirm_box, width="stretch"):
        ok, msg = acc_mgr.delete_account(selected_idx)
        if ok:
            st.success("Account deleted successfully.", icon=":material/check_circle:")
            st.rerun()
        else:
            st.error(f"Deletion failed: {msg}")


def render_accounts_registry(acc_mgr: AccountManager) -> None:
    """Render the main account registry view with read-only masking and dialogs."""
    st.title("Account registry")
    st.caption("Secure management of applicant Demat accounts with masked secrets and protected storage.")

    accounts = acc_mgr.load_accounts()

    # Action Toolbar
    act_col1, act_col2, act_col3, act_col4 = st.columns([1.5, 1.5, 1.5, 1.5], vertical_alignment="center")
    with act_col1:
        if st.button("Add account", icon=":material/person_add:", width="stretch"):
            add_account_dialog(acc_mgr)
    with act_col2:
        if st.button("Edit credentials", icon=":material/key:", disabled=len(accounts) == 0, width="stretch"):
            edit_credentials_dialog(acc_mgr, accounts)
    with act_col3:
        if st.button("Delete account", icon=":material/delete:", disabled=len(accounts) == 0, width="stretch"):
            delete_account_dialog(acc_mgr, accounts)
    with act_col4:
        # Export Redacted CSV
        redacted_accounts = redact_accounts_list(accounts)
        export_df = pd.DataFrame(redacted_accounts)
        csv_data = export_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Export redacted CSV",
            data=csv_data,
            file_name="demat_accounts_backup_redacted.csv",
            mime="text/csv",
            icon=":material/download:",
            width="stretch",
            help="Exports registered accounts with passwords and PINs securely masked.",
        )

    st.write("")

    # Read-Only Registry Table
    if accounts:
        display_rows = []
        for a in accounts:
            raw_pwd = a.get("password", "")
            raw_pin = a.get("txn_pin", "")
            raw_crn = a.get("crn", "")

            # Mask sensitive values strictly
            masked_pwd = "••••••••" if raw_pwd else "Missing"
            masked_pin = "••••" if raw_pin else "Missing"
            masked_crn = mask_secret(raw_crn, visible_suffix=3) if raw_crn else "Missing"

            display_rows.append({
                "Applicant Name": a.get("name", ""),
                "Capital ID": a.get("capital_id", ""),
                "Username": a.get("username", ""),
                "Password": masked_pwd,
                "Bank": a.get("bank", ""),
                "Default Kitta": a.get("kitta", "10"),
                "CRN": masked_crn,
                "PIN": masked_pin,
                "Branch": a.get("branch", ""),
                "Target Company": a.get("company", ""),
            })

        df = pd.DataFrame(display_rows)
        st.dataframe(df, width="stretch", hide_index=True)
    else:
        with st.container(border=True):
            st.info("No Demat accounts currently registered. Click 'Add account' to register your first applicant.", icon=":material/info:")

    st.write("")

    # Bulk Account Operations Container
    with st.container(border=True):
        st.markdown("### Bulk operations")
        st.caption("Apply bulk parameters across all registered applicant accounts.")

        b_col1, b_col2 = st.columns(2)
        with b_col1:
            bulk_kitta_val = st.number_input("Bulk update kitta", min_value=10, max_value=1000, value=10, step=10)
            if st.button("Apply kitta to all accounts", icon=":material/done_all:", disabled=len(accounts) == 0, width="stretch"):
                updated_count = acc_mgr.bulk_update_kitta(bulk_kitta_val)
                st.success(f"Updated default kitta to {bulk_kitta_val} across all {updated_count} accounts.", icon=":material/check_circle:")
                st.rerun()

        with b_col2:
            bulk_comp_val = st.text_input("Bulk update target company", placeholder="e.g. Upper Tamakoshi Hydropower")
            if st.button("Apply company to all accounts", icon=":material/edit_note:", disabled=len(accounts) == 0, width="stretch"):
                updated_count = acc_mgr.bulk_update_company(bulk_comp_val)
                st.success(f"Updated target company to '{bulk_comp_val}' across all {updated_count} accounts.", icon=":material/check_circle:")
                st.rerun()

    # Import Accounts Accordion with Template & Validation Preview
    with st.expander("Import accounts in bulk (CSV upload)", expanded=False):
        st.caption("Upload a structured CSV file with columns: Name, Capital_ID, Username, Password, Bank, Kitta, CRN, TXN_PIN, Branch, Target_Company")

        # Download sample template
        sample_csv = (
            "Name,Capital_ID,Username,Password,Bank,Default_Kitta,CRN,TXN_PIN,Branch,Target_Company\n"
            "Ram Bahadur Thapa,13016500,00123456,MySecret@123,Nabil Bank,10,00867066,1234,Kathmandu Main,\n"
            "Sita Kumari Sharma,13010100,00234567,SitaPass#2026,Global IME Bank,10,00998877,4321,Pokhara Branch,\n"
        ).encode("utf-8")

        c_tmpl, _ = st.columns([1.5, 3.5])
        with c_tmpl:
            st.download_button(
                "Download sample CSV template",
                data=sample_csv,
                file_name="demat_accounts_template.csv",
                mime="text/csv",
                icon=":material/download:",
                width="stretch",
            )

        uploaded_file = st.file_uploader("Upload accounts CSV", type=["csv", "txt"], key="bulk_acc_csv_uploader")
        if uploaded_file is not None:
            try:
                content = uploaded_file.getvalue().decode("utf-8-sig")
                reader = csv.reader(io.StringIO(content))
                rows = list(reader)

                existing_keys = {
                    (str(a.get("capital_id", "")).strip(), str(a.get("username", "")).strip())
                    for a in accounts
                }

                parsed_accounts: List[Dict[str, Any]] = []
                preview_rows: List[Dict[str, Any]] = []

                for r in rows:
                    if not r or len(r) < 8:
                        continue
                    # Skip header
                    first_cell = r[0].strip().lower()
                    if first_cell in ("name", "applicant", "applicant name", "fullname"):
                        continue

                    name_val = r[0].strip()
                    cap_val = r[1].strip()
                    user_val = r[2].strip()
                    pwd_val = r[3].strip()
                    bank_val = r[4].strip()
                    kitta_val = r[5].strip() if len(r) > 5 and r[5].strip().isdigit() else "10"
                    crn_val = r[6].strip() if len(r) > 6 else ""
                    pin_val = r[7].strip() if len(r) > 7 else ""
                    branch_val = r[8].strip() if len(r) > 8 else ""
                    comp_val = r[9].strip() if len(r) > 9 else ""

                    is_dup = (cap_val, user_val) in existing_keys
                    is_valid = bool(name_val and cap_val and user_val and pwd_val and crn_val and len(pin_val) == 4)

                    acc_item = {
                        "name": name_val,
                        "capital_id": cap_val,
                        "username": user_val,
                        "password": pwd_val,
                        "bank": bank_val,
                        "kitta": kitta_val,
                        "crn": crn_val,
                        "txn_pin": pin_val,
                        "branch": branch_val,
                        "company": comp_val,
                    }

                    if not is_dup and is_valid:
                        parsed_accounts.append(acc_item)

                    preview_rows.append({
                        "Applicant Name": name_val,
                        "DP Code": cap_val,
                        "Username": user_val,
                        "Bank": bank_val,
                        "Kitta": kitta_val,
                        "PIN": "••••" if pin_val else "Missing",
                        "Status": "🟢 Ready" if (not is_dup and is_valid) else ("🟡 Duplicate" if is_dup else "🔴 Incomplete"),
                    })

                if preview_rows:
                    st.write("")
                    st.markdown(f"**Found {len(preview_rows)} row(s):** {len(parsed_accounts)} ready to import, {len(preview_rows) - len(parsed_accounts)} skipped/duplicate.")
                    preview_df = pd.DataFrame(preview_rows)
                    st.dataframe(preview_df, width="stretch", hide_index=True)

                    if len(parsed_accounts) > 0:
                        if st.button(f"Import {len(parsed_accounts)} valid account(s)", type="primary", icon=":material/upload:", width="stretch"):
                            imported_count = 0
                            for item in parsed_accounts:
                                ok, _ = acc_mgr.add_account(item)
                                if ok:
                                    imported_count += 1
                            st.success(f"Successfully imported {imported_count} new account(s) into Demat vault.", icon=":material/check_circle:")
                            st.rerun()
                    else:
                        st.warning("No new valid accounts found to import (all rows are duplicates or missing required fields).", icon=":material/warning:")
                else:
                    st.info("No data rows found in uploaded file. Check headers and formatting.", icon=":material/info:")

            except Exception as exc:
                st.error(f"Error reading accounts CSV file: {exc}", icon=":material/error:")
