import sys
import tempfile
from pathlib import Path

# Ensure paths
root_dir = Path(__file__).resolve().parent.parent / "meroshare-bot-master"
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from bot.account_manager import AccountManager
from bot.history_manager import HistoryManager
from bot.models import Account, ResultState
from bot.security import (
    decrypt_text,
    encrypt_text,
    is_masked_placeholder,
    mask_secret,
    redact_accounts_list,
)


def test_account_model_validation():
    acc = Account(
        name="Hari Sharma",
        capital_id="13010100",
        username="12345678",
        password="MySecretPassword#1",
        bank="NIC ASIA BANK LTD",
        kitta="20",
        crn="CRN998877",
        txn_pin="4321",
    )
    is_valid, errors = acc.validate()
    assert is_valid is True
    assert len(errors) == 0

    masked = acc.to_dict(mask_secrets=True)
    assert masked["password"] == "••••••••"
    assert masked["txn_pin"] == "••••"
    assert "•" in masked["crn"]
    assert masked["name"] == "Hari Sharma"


def test_account_model_invalid():
    acc = Account(
        name="",
        capital_id="",
        username="",
        password="",
        bank="",
        kitta="invalid",
        crn="1",
        txn_pin="9",
    )
    is_valid, errors = acc.validate()
    assert is_valid is False
    assert len(errors) >= 5


def test_mask_secret_helper():
    assert mask_secret("password123") == "••••••••"
    assert mask_secret("1234") == "••••"
    assert mask_secret("CRN12345678", visible_suffix=2) == "•••••••••78"
    assert mask_secret("") == ""


def test_is_masked_placeholder():
    assert is_masked_placeholder("••••••••") is True
    assert is_masked_placeholder("CRN••••••78") is True
    assert is_masked_placeholder("RealPassword123") is False
    assert is_masked_placeholder("") is False


def test_redact_accounts_list():
    raw_list = [
        {
            "name": "User One",
            "password": "SecretOne",
            "crn": "CRN001122",
            "txn_pin": "1234",
        }
    ]
    redacted = redact_accounts_list(raw_list)
    assert redacted[0]["password"] == "••••••••"
    assert redacted[0]["txn_pin"] == "••••"
    assert "•" in redacted[0]["crn"]


def test_encryption_decryption_roundtrip():
    plain = "SuperSecretMasterKey123!@#"
    cipher = encrypt_text(plain)
    assert cipher.startswith(("DPAPI:", "RAW:"))
    assert cipher != plain
    decrypted = decrypt_text(cipher)
    assert decrypted == plain


def test_account_manager_preserves_masked_secrets():
    """Ensure that editing an account with masked placeholder retains original credentials."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tf:
        tf.write("Name,CapitalID,Username,Password,Bank,Kitta,CRN,TXN_PIN,Branch,Company\n")
        tf.write("Original Name,13010100,origuser,TruePassword123,Nabil Bank Ltd,10,CRN123456,9876,Kathmandu,\n")
        tf_path = Path(tf.name)

    try:
        mgr = AccountManager(file_path=tf_path)
        accounts = mgr.load_accounts()
        assert len(accounts) == 1
        assert accounts[0]["password"] == "TruePassword123"

        # Simulating dashboard table edit where password was masked
        edited_accounts = [
            {
                "name": "Updated Name",
                "capital_id": "13010100",
                "username": "origuser",
                "password": "••••••••",  # Masked!
                "bank": "Nabil Bank Ltd",
                "kitta": "20",
                "crn": "CRN••••••56",  # Masked!
                "txn_pin": "••••",  # Masked!
                "branch": "Kathmandu",
                "company": "",
            }
        ]

        ok = mgr.save_accounts(edited_accounts)
        assert ok is True

        reloaded = mgr.load_accounts()
        assert len(reloaded) == 1
        assert reloaded[0]["name"] == "Updated Name"
        assert reloaded[0]["kitta"] == "20"
        # Real credentials must be retained!
        assert reloaded[0]["password"] == "TruePassword123"
        assert reloaded[0]["crn"] == "CRN123456"
        assert reloaded[0]["txn_pin"] == "9876"

        # Test encrypt_vault and decrypt_vault
        assert mgr.is_vault_encrypted() is False
        ok_enc = mgr.encrypt_vault()
        assert ok_enc is True
        assert mgr.is_vault_encrypted() is True

        # Ensure raw file content is encrypted
        raw_text = tf_path.read_text(encoding="utf-8")
        assert "TruePassword123" not in raw_text
        assert "DPAPI:" in raw_text

        # Ensure loaded credentials remain decrypted in memory
        loaded_enc = mgr.load_accounts()
        assert loaded_enc[0]["password"] == "TruePassword123"
        assert loaded_enc[0]["crn"] == "CRN123456"
        assert loaded_enc[0]["txn_pin"] == "9876"

        # Decrypt vault back to plaintext
        ok_dec = mgr.decrypt_vault()
        assert ok_dec is True
        assert mgr.is_vault_encrypted() is False
        assert "TruePassword123" in tf_path.read_text(encoding="utf-8")
    finally:
        if tf_path.exists():
            tf_path.unlink()


def test_history_manager_atomic_write():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        tf_path = Path(tf.name)

    try:
        hm = HistoryManager(file_path=tf_path)
        record = hm.log_run(
            company_name="Mega Hydro Limited",
            engine="API",
            total=1,
            applied=1,
            skipped=0,
            failed=0,
            details=[{
                "account": "Hari Sharma",
                "status": ResultState.SUCCESS.value,
                "message": "IPO Application successfully placed via API",
            }],
        )
        assert record["applied"] == 1
        assert record["company"] == "Mega Hydro Limited"

        # Verify atomic persistence
        history = hm.get_history()
        assert len(history) == 1
        assert history[0]["company"] == "Mega Hydro Limited"
        assert history[0]["applied"] == 1
        assert history[0]["engine"] == "API"
    finally:
        if tf_path.exists():
            tf_path.unlink()
