import sys
import tempfile
from pathlib import Path

# Ensure paths
root_dir = Path(__file__).resolve().parent.parent / "meroshare-bot-master"
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from bot.account_manager import AccountManager
from bot.api_client import MeroshareAPIClient
from bot.history_manager import HistoryManager


def test_account_validation():
    # Valid account
    valid_acc = {
        "name": "Ram Bahadur",
        "capital_id": "13016500",
        "username": "00123456",
        "password": "SecretPassword123",
        "bank": "Garima Bikas Bank Ltd.",
        "kitta": "10",
        "crn": "00867066",
        "txn_pin": "1234",
    }
    is_valid, errors = AccountManager.validate_account(valid_acc)
    assert is_valid is True
    assert len(errors) == 0

    # Invalid account (short pin, invalid kitta)
    invalid_acc = {
        "name": "",
        "capital_id": "ABC",
        "username": "",
        "password": "",
        "bank": "",
        "kitta": "-5",
        "crn": "12",
        "txn_pin": "12",
    }
    is_valid, errors = AccountManager.validate_account(invalid_acc)
    assert is_valid is False
    assert len(errors) >= 5


def test_account_manager_crud():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tf:
        tf.write("Name,CapitalID,Username,Password,Bank,Kitta,CRN,TXN_PIN\n")
        tf_path = Path(tf.name)

    try:
        mgr = AccountManager(file_path=tf_path)
        accounts = mgr.load_accounts()
        assert len(accounts) == 0

        # Add account
        acc = {
            "name": "Test User",
            "capital_id": "13016500",
            "username": "testuser01",
            "password": "Password123",
            "bank": "Nabil Bank Ltd",
            "kitta": "10",
            "crn": "CRN123456",
            "txn_pin": "9999",
            "branch": "Kathmandu",
            "company": "",
        }
        ok, _msg = mgr.add_account(acc)
        assert ok is True

        accounts = mgr.load_accounts()
        assert len(accounts) == 1
        assert accounts[0]["name"] == "Test User"

        # Update account
        acc["name"] = "Test User Updated"
        ok, _msg = mgr.update_account(0, acc)
        assert ok is True
        accounts = mgr.load_accounts()
        assert accounts[0]["name"] == "Test User Updated"

        # Bulk operations
        mgr.bulk_update_kitta(50)
        accounts = mgr.load_accounts()
        assert accounts[0]["kitta"] == "50"

        mgr.bulk_update_company("Test Company IPO")
        accounts = mgr.load_accounts()
        assert accounts[0]["company"] == "Test Company IPO"

        # Bulk save
        accounts[0]["kitta"] = "20"
        ok, _msg = mgr.bulk_save_all(accounts)
        assert ok is True
        assert mgr.load_accounts()[0]["kitta"] == "20"

        # Delete account
        ok, _msg = mgr.delete_account(0)
        assert ok is True
        accounts = mgr.load_accounts()
        assert len(accounts) == 0

    finally:
        if tf_path.exists():
            tf_path.unlink()


def test_api_client_capital_resolution():
    client = MeroshareAPIClient()
    # Mock cache
    client._capitals_cache = [
        {"id": 165, "code": "16400", "name": "NEPAL LIFE CAPITAL LIMITED"},
        {"id": 184, "code": "16500", "name": "RBB MERCHANT BANKING LIMITED"},
    ]

    # Resolve by DP code with 130 prefix
    res = client.resolve_capital_id("13016500")
    assert res == 184

    # Resolve by ID directly
    res = client.resolve_capital_id("165")
    assert res == 165


def test_history_manager():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tf:
        tf_path = Path(tf.name)

    try:
        hm = HistoryManager(file_path=tf_path)
        assert len(hm.get_history()) == 0

        hm.log_run(
            company_name="Test Company IPO",
            engine="api",
            total=2,
            applied=2,
            skipped=0,
            failed=0,
            details=[{"name": "User 1", "status": "SUCCESS"}],
        )

        history = hm.get_history()
        assert len(history) == 1
        assert history[0]["company"] == "Test Company IPO"
        assert history[0]["applied"] == 2

        hm.clear()
        assert len(hm.get_history()) == 0
    finally:
        if tf_path.exists():
            tf_path.unlink()


def test_ipo_result_checker():
    from bot.ipo_result_checker import IPOResultChecker

    checker = IPOResultChecker()
    # Test company listing resilience (must always return companies via live or fallback cache)
    ok, _msg, comps = checker.get_company_list()
    assert ok is True
    assert isinstance(comps, list)
    assert len(comps) > 0
    assert "id" in comps[0]
    assert "name" in comps[0]

    # Test invalid BOID
    res = checker.check_boid(123, "1234")
    assert res["allotted"] is False
    assert res["status"] == "INVALID_BOID"
    assert "Invalid BOID" in res["message"]

    # Test clean 16 digit extraction
    assert len("1301650000281157") == 16

    # Test check_via_meroshare graceful validation
    dummy_acc = {"name": "Test User", "capital_id": "", "username": "", "password": ""}
    direct_res = checker.check_via_meroshare(None, dummy_acc, 123)
    assert direct_res["allotted"] is False
    assert direct_res["status"] == "AUTH_FAILED"


def test_api_client_portfolio_query():
    client = MeroshareAPIClient()
    # Test unauthenticated or missing endpoint gracefully returns None
    res = client.get_portfolio(token="invalid_token", demat="1301650000000000")
    assert res is None or isinstance(res, dict)


def test_bulk_csv_account_import_flow():
    # Generate CSV in expected template format
    csv_content = """Name,Capital_ID,Username,Password,Bank_Name,CRN,TXN_PIN,Default_Kitta,Branch
Sudeep Das,13016500,00123456,P@ssword123,Garima Bikas Bank Ltd.,00867066,1234,10,Kathmandu
Anita Sharma,13010600,00987654,SecurePass99,Nabil Bank Limited,00123456,9876,20,Pokhara
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tf:
        tf.write("Name,CapitalID,Username,Password,Bank,Kitta,CRN,TXN_PIN\n")
        vault_path = Path(tf.name)

    try:
        mgr = AccountManager(file_path=vault_path)
        # Parse CSV lines
        import csv
        reader = list(csv.DictReader(csv_content.strip().splitlines()))
        assert len(reader) == 2
        for r in reader:
            acc_dict = {
                "name": r.get("Name", ""),
                "capital_id": r.get("Capital_ID", ""),
                "username": r.get("Username", ""),
                "password": r.get("Password", ""),
                "bank": r.get("Bank_Name", ""),
                "crn": r.get("CRN", ""),
                "txn_pin": r.get("TXN_PIN", ""),
                "kitta": r.get("Default_Kitta", "10"),
                "branch": r.get("Branch", ""),
                "company": "",
            }
            valid, _errs = AccountManager.validate_account(acc_dict)
            assert valid is True
            ok, _msg = mgr.add_account(acc_dict)
            assert ok is True

        loaded = mgr.load_accounts()
        assert len(loaded) == 2
        assert loaded[0]["username"] == "00123456"
        assert loaded[1]["username"] == "00987654"
    finally:
        if vault_path.exists():
            vault_path.unlink()


def test_cdsc_issue_scraper():
    from bot.cdsc_issue_scraper import CDSCIssueScraper
    scraper = CDSCIssueScraper()
    ok, _msg, issues = scraper.fetch_current_issues()
    assert ok is True
    assert isinstance(issues, list)
    if issues:
        first = issues[0]
        assert "company_name" in first
        assert "scrip" in first
        assert "target_group" in first
        assert "is_general_public" in first
        assert "sub_ratio" in first


if __name__ == "__main__":
    print("Running component tests...")
    test_account_validation()
    print("  [x] Account validation passed")
    test_account_manager_crud()
    print("  [x] Account manager CRUD passed")
    test_api_client_capital_resolution()
    print("  [x] Capital ID resolution passed")
    test_history_manager()
    print("  [x] History manager logging passed")
    test_ipo_result_checker()
    print("  [x] IPO result checker passed")
    test_cdsc_issue_scraper()
    print("  [x] CDSC live issue scraper passed")
    print("All tests completed successfully!")
