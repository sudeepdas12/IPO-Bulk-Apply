import sys
from pathlib import Path
from unittest.mock import patch

# Ensure paths
root_dir = Path(__file__).resolve().parent.parent / "meroshare-bot-master"
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from bot.executor import IPOExecutor
from bot.models import ResultState
import pytest


@pytest.fixture(autouse=True)
def reset_cooldown():
    """Ensure any live cooldown from environment does not bleed into unit tests."""
    from bot.cooldown_manager import CooldownManager
    cm = CooldownManager()
    cm.clear_cooldown()
    yield
    cm.clear_cooldown()


def test_executor_dry_run_mode():
    """Verify that dry_run mode performs validation without placing live application calls."""
    executor = IPOExecutor(mode="api", delay=0)

    accounts = [
        {
            "name": "Test Account",
            "capital_id": "13010100",
            "username": "12345678",
            "password": "ValidPassword123",
            "bank": "NIC ASIA BANK LTD",
            "kitta": "10",
            "crn": "CRN123456",
            "txn_pin": "1234",
        }
    ]

    with patch.object(executor.api_client, "login", return_value=(True, "Login successful", "Bearer mock-tok")), \
         patch.object(executor.api_client, "get_user_details", return_value={"demat": "1301010012345678"}), \
         patch.object(executor.api_client, "get_applicable_issues", return_value=[
             {"companyShareId": 888, "companyName": "Test Hydro Limited", "scrip": "THL"}
         ]), \
         patch.object(executor.api_client, "check_application_status", return_value={"actionStatus": "apply"}), \
         patch.object(executor.api_client, "get_banks", return_value=[{"bankName": "NIC ASIA BANK LTD", "id": 1}]), \
         patch.object(executor.api_client, "apply_ipo") as mock_apply:

        summary = executor.run(accounts=accounts, company_name="Test Hydro Limited", dry_run=True)

        # In dry run, apply_ipo must NEVER be called
        mock_apply.assert_not_called()
        assert len(summary["details"]) == 1
        assert summary["details"][0]["status"] == "DRY_RUN"
        assert "[Preview]" in summary["details"][0]["message"]
        assert len(summary["skipped"]) == 1


def test_executor_missing_company_classification():
    """Verify missing company returns NO_ISSUE / SKIPPED and not FAILED."""
    executor = IPOExecutor(mode="api", delay=0)

    accounts = [
        {
            "name": "Test Account",
            "capital_id": "13010100",
            "username": "12345678",
            "password": "ValidPassword123",
            "bank": "NIC ASIA BANK LTD",
            "kitta": "10",
            "crn": "CRN123456",
            "txn_pin": "1234",
        }
    ]

    with patch.object(executor.api_client, "login", return_value=(True, "Login successful", "Bearer mock-tok")), \
         patch.object(executor.api_client, "get_user_details", return_value={"demat": "1301010012345678"}), \
         patch.object(executor.api_client, "get_applicable_issues", return_value=[
             {"companyShareId": 999, "companyName": "Some Other Company", "scrip": "SOC"}
         ]):

        summary = executor.run(accounts=accounts, company_name="NonExistent Company", dry_run=False)

        # Should be classified as NO_ISSUE in skipped, NOT failed
        assert len(summary["details"]) == 1
        assert summary["details"][0]["status"] == ResultState.NO_ISSUE.value
        assert "not open" in summary["details"][0]["message"].lower()
        assert len(summary["failed"]) == 0
        assert len(summary["skipped"]) == 1


def test_executor_already_applied_classification():
    """Verify already-applied issue is flagged as ALREADY_APPLIED and placed in skipped list."""
    executor = IPOExecutor(mode="api", delay=0)

    accounts = [
        {
            "name": "Test Account",
            "capital_id": "13010100",
            "username": "12345678",
            "password": "ValidPassword123",
            "bank": "NIC ASIA BANK LTD",
            "kitta": "10",
            "crn": "CRN123456",
            "txn_pin": "1234",
        }
    ]

    with patch.object(executor.api_client, "login", return_value=(True, "Login successful", "Bearer mock-tok")), \
         patch.object(executor.api_client, "get_user_details", return_value={"demat": "1301010012345678"}), \
         patch.object(executor.api_client, "get_applicable_issues", return_value=[
             {"companyShareId": 777, "companyName": "Everest Energy Ltd", "scrip": "EEL"}
         ]), \
         patch.object(executor.api_client, "check_application_status", return_value={
             "actionStatus": "view",
             "statusName": "VERIFIED",
         }):

        summary = executor.run(accounts=accounts, company_name="Everest Energy Ltd", dry_run=False)

        assert len(summary["details"]) == 1
        assert summary["details"][0]["status"] == ResultState.ALREADY_APPLIED.value
        assert "already applied" in summary["details"][0]["message"].lower()
        assert len(summary["skipped"]) == 1
        assert len(summary["failed"]) == 0


def test_executor_company_name_robust_matching():
    """Verify that company matching works with parenthesized suffixes and scrips."""
    executor = IPOExecutor(mode="api", delay=0)

    account = {
        "name": "Test Account",
        "capital_id": "13010100",
        "username": "12345678",
        "password": "ValidPassword123",
        "bank": "NIC ASIA BANK LTD",
        "kitta": "10",
        "crn": "CRN123456",
        "txn_pin": "1234",
    }

    with patch.object(executor.api_client, "login", return_value=(True, "Login successful", "Bearer mock-tok")), \
         patch.object(executor.api_client, "get_user_details", return_value={"demat": "1301010012345678"}), \
         patch.object(executor.api_client, "get_applicable_issues", return_value=[
             {"companyShareId": 398, "companyName": "Him Parbat Hydropower Limited - (General Public)", "scrip": "HPHL"}
         ]), \
         patch.object(executor.api_client, "check_application_status", return_value={"actionStatus": "apply"}), \
         patch.object(executor.api_client, "get_banks", return_value=[{"bankName": "NIC ASIA BANK LTD", "id": 1}]):

        # Matching by clean company query with HPHL suffix
        status, msg = executor._apply_via_api(account, "Him Parbat Hydropower Limited (HPHL)", 10, dry_run=True)
        assert status == "DRY_RUN"
        assert "Him Parbat" in msg

        # Matching by scrip only
        status, msg = executor._apply_via_api(account, "HPHL", 10, dry_run=True)
        assert status == "DRY_RUN"
        assert "HPHL" in msg or "Him Parbat" in msg


def test_executor_circuit_breaker_on_ip_cooldown(tmp_path):
    """Verify that circuit breaker stops remaining accounts upon first IP cooldown."""
    from bot.cooldown_manager import CooldownManager

    cool_file = tmp_path / "test_cooldown.json"
    cooldown_mgr = CooldownManager(file_path=cool_file)
    executor = IPOExecutor(mode="api", delay=0, stop_on_ip_cooldown=True, cooldown_mgr=cooldown_mgr)

    accounts = [
        {"name": "Acc 1", "capital_id": "13010100", "username": "111", "password": "p1"},
        {"name": "Acc 2", "capital_id": "13010100", "username": "222", "password": "p2"},
        {"name": "Acc 3", "capital_id": "13010100", "username": "333", "password": "p3"},
    ]

    with patch.object(
        executor.api_client,
        "login",
        side_effect=[
            (False, "CDSC Firewall rejected login request (Temporary IP cooldown)", None),
            (True, "Should never be called", "mock-token"),
        ],
    ) as mock_login:
        summary = executor.run(accounts=accounts, company_name="Test Corp", dry_run=False)

        # Login must only have been attempted ONCE for Acc 1
        assert mock_login.call_count == 1

        details = summary["details"]
        assert len(details) == 3

        # Account 1 got IP_COOLDOWN
        assert details[0]["name"] == "Acc 1"
        assert details[0]["status"] == ResultState.IP_COOLDOWN.value

        # Remaining accounts got DEFERRED_IP_COOLDOWN without being attempted
        assert details[1]["name"] == "Acc 2"
        assert details[1]["status"] == ResultState.DEFERRED_IP_COOLDOWN.value
        assert "remaining accounts were not attempted" in details[1]["message"].lower()

        assert details[2]["name"] == "Acc 3"
        assert details[2]["status"] == ResultState.DEFERRED_IP_COOLDOWN.value

        # Cooldown must be recorded
        active, _ = cooldown_mgr.is_cooldown_active()
        assert active is True


def test_executor_blocks_execution_during_active_cooldown(tmp_path):
    """Verify that an active cooldown blocks execution upfront before attempting any accounts."""
    from bot.cooldown_manager import CooldownManager

    cool_file = tmp_path / "test_cooldown.json"
    cooldown_mgr = CooldownManager(file_path=cool_file)
    cooldown_mgr.record_cooldown(reason="Prior IP block", duration_minutes=15)

    executor = IPOExecutor(mode="api", delay=0, cooldown_mgr=cooldown_mgr)
    accounts = [
        {"name": "Acc 1", "capital_id": "13010100", "username": "111", "password": "p1"},
        {"name": "Acc 2", "capital_id": "13010100", "username": "222", "password": "p2"},
    ]

    with patch.object(executor.api_client, "login") as mock_login:
        summary = executor.run(accounts=accounts, company_name="Test Corp", dry_run=False)

        # Must not have called login at all
        mock_login.assert_not_called()
        assert summary.get("blocked_by_cooldown") is True
        for d in summary["details"]:
            assert d["status"] == ResultState.DEFERRED_IP_COOLDOWN.value
            assert "cooldown active" in d["message"].lower()


def test_cooldown_manager_persistence(tmp_path):
    """Verify CooldownManager records, persists, formats, and clears cooldown lockouts."""
    from bot.cooldown_manager import CooldownManager

    cool_file = tmp_path / "cooldown_test.json"
    cm = CooldownManager(file_path=cool_file)

    assert cm.is_cooldown_active()[0] is False
    assert cm.get_remaining_seconds() == 0

    # Record cooldown
    cm.record_cooldown(reason="F5 ASM throttle", duration_minutes=10)
    active, info = cm.is_cooldown_active()
    assert active is True
    assert info["reason"] == "F5 ASM throttle"
    assert cm.get_remaining_seconds() > 500
    assert "m" in cm.format_time_remaining()

    # Clear cooldown
    cm.clear_cooldown()
    assert cm.is_cooldown_active()[0] is False
