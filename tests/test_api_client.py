import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

# Ensure paths
root_dir = Path(__file__).resolve().parent.parent / "meroshare-bot-master"
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from bot.api_client import MeroshareAPIClient
from bot.models import MeroshareNetworkError


def test_api_client_get_capitals():
    client = MeroshareAPIClient()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {"id": 130, "code": "13010100", "name": "Global IME Capital Ltd."}
    ]

    with patch.object(client.session, "get", return_value=mock_response):
        capitals = client.get_capitals()
        assert len(capitals) == 1
        assert capitals[0]["id"] == 130
        assert capitals[0]["name"] == "Global IME Capital Ltd."


def test_api_client_login_success():
    client = MeroshareAPIClient()
    mock_capitals = [{"id": 130, "code": "13010100", "name": "Global IME Capital Ltd."}]
    
    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 200
    mock_post_resp.headers = {"Authorization": "Bearer mock-auth-token-12345"}
    mock_post_resp.content = b""

    with patch.object(client, "get_capitals", return_value=mock_capitals), \
         patch.object(client, "_request_with_retry", return_value=mock_post_resp):
        ok, msg, token = client.login("13010100", "12345678", "Password123")
        assert ok is True
        assert "successful" in msg.lower()
        assert token == "Bearer mock-auth-token-12345"


def test_api_client_login_invalid_credentials():
    client = MeroshareAPIClient()
    mock_capitals = [{"id": 130, "code": "13010100", "name": "Global IME Capital Ltd."}]

    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 401
    mock_post_resp.text = '{"message": "Invalid username or password"}'

    with patch.object(client, "get_capitals", return_value=mock_capitals), \
         patch.object(client, "_request_with_retry", return_value=mock_post_resp):
        ok, msg, token = client.login("13010100", "12345678", "WrongPass")
        assert ok is False
        assert "invalid" in msg.lower()
        assert token is None


def test_api_client_login_empty_capital_id():
    client = MeroshareAPIClient()
    ok, msg, token = client.login("", "12345678", "Password123")
    assert ok is False
    assert "empty or missing" in msg
    assert token is None

    ok_ws, msg_ws, _token_ws = client.login("   ", "12345678", "Password123")
    assert ok_ws is False
    assert "empty or missing" in msg_ws


def test_api_client_request_retry_on_timeout():
    """Verify exponential backoff retry on transient RequestException and eventual MeroshareNetworkError."""
    client = MeroshareAPIClient(timeout=1, max_retries=2)

    with patch.object(client.session, "get", side_effect=requests.exceptions.Timeout("Connection timed out")):
        with pytest.raises(MeroshareNetworkError) as exc_info:
            client._request_with_retry("GET", "https://backend.cdsc.com.np/api/dummy")
        assert isinstance(exc_info.value, MeroshareNetworkError)
        assert "failed after 2 attempts" in str(exc_info.value).lower()
        assert client.session.get.call_count == 2


def test_api_client_get_applicable_issues():
    client = MeroshareAPIClient()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "object": [
            {
                "companyShareId": 101,
                "companyName": "Upper Tamakoshi Hydropower",
                "scrip": "UPPER",
                "shareTypeName": "IPO",
                "minUnit": "10",
                "maxUnit": "1000",
            }
        ]
    }

    with patch.object(client, "_request_with_retry", return_value=mock_response):
        issues = client.get_applicable_issues("Bearer test-token")
        assert len(issues) == 1
        assert issues[0]["companyName"] == "Upper Tamakoshi Hydropower"
        assert issues[0]["companyShareId"] == 101


def test_api_client_check_application_status():
    client = MeroshareAPIClient()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "statusName": "APPLIED",
        "appliedKitta": 10,
        "message": "Already applied for this issue",
    }

    with patch.object(client, "_request_with_retry", return_value=mock_response):
        status = client.check_application_status("Bearer test-token", 101)
        assert status is not None
        assert status.get("statusName") == "APPLIED"


def test_api_client_apply_ipo_success():
    client = MeroshareAPIClient()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = '{"message": "Share applied successfully", "status": "SUCCESS"}'
    mock_response.json.return_value = {
        "message": "Share applied successfully",
        "status": "SUCCESS",
    }

    user_details = {
        "demat": "1301010012345678",
        "boid": "1301010012345678",
        "name": "Hari Sharma",
    }
    bank_info = {
        "bankCode": "01",
        "accountBranchId": "001",
        "accountNumber": "0010010001",
        "id": "12345",
    }

    with patch.object(client, "_request_with_retry", return_value=mock_response):
        ok, msg = client.apply_ipo(
            token="Bearer test-token",
            user_details=user_details,
            bank_info=bank_info,
            company_share_id=101,
            kitta=10,
            crn="CRN123456",
            txn_pin="1234",
        )
        assert ok is True
        assert "successfully" in msg.lower()
