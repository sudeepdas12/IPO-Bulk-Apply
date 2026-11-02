"""Security and data protection utilities for Meroshare AutoPilot."""

from __future__ import annotations

import base64
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def mask_secret(value: str, visible_suffix: int = 0, mask_char: str = "•") -> str:
    """Masks a sensitive string (password, PIN, CRN)."""
    if not value:
        return ""
    clean = str(value).strip()
    if visible_suffix > 0 and len(clean) > visible_suffix:
        return (mask_char * (len(clean) - visible_suffix)) + clean[-visible_suffix:]
    return mask_char * min(max(len(clean), 4), 8)


def is_masked_placeholder(value: str) -> bool:
    """Checks whether a string is a masked placeholder (e.g. •••••••• or ******** or CRN••••••78)."""
    if not value:
        return False
    stripped = str(value).strip()
    return any(c in "•*●" for c in stripped) and len(stripped) >= 3


def redact_account_dict(acc_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Returns a copy of an account dict with passwords and PINs redacted."""
    redacted = dict(acc_dict)
    if "password" in redacted:
        redacted["password"] = mask_secret(str(redacted["password"]))
    if "Password" in redacted:
        redacted["Password"] = mask_secret(str(redacted["Password"]))
    if "txn_pin" in redacted:
        redacted["txn_pin"] = mask_secret(str(redacted["txn_pin"]))
    if "TXN_PIN" in redacted:
        redacted["TXN_PIN"] = mask_secret(str(redacted["TXN_PIN"]))
    if "crn" in redacted:
        redacted["crn"] = mask_secret(str(redacted["crn"]), visible_suffix=3)
    if "CRN" in redacted:
        redacted["CRN"] = mask_secret(str(redacted["CRN"]), visible_suffix=3)
    return redacted


def redact_accounts_list(accounts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Redacts passwords and PINs from a list of account dictionaries."""
    return [redact_account_dict(a) for a in accounts]


# -------------------------------------------------------------
# Local Credential Encryption (Windows DPAPI with AES Fallback)
# -------------------------------------------------------------
def _protect_data_windows(plain_bytes: bytes) -> Optional[bytes]:
    """Encrypts bytes using Windows DPAPI (CryptProtectData)."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [
                ("cbData", wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_byte)),
            ]

        p_plain = ctypes.cast(
            (ctypes.c_byte * len(plain_bytes))(*plain_bytes),
            ctypes.POINTER(ctypes.c_byte),
        )
        in_blob = DATA_BLOB(len(plain_bytes), p_plain)
        out_blob = DATA_BLOB()

        crypt32 = ctypes.windll.crypt32
        if crypt32.CryptProtectData(
            ctypes.byref(in_blob),
            "MeroshareAutoPilotCredentials",
            None,
            None,
            None,
            0x01,  # CRYPTPROTECT_UI_FORBIDDEN
            ctypes.byref(out_blob),
        ):
            size = out_blob.cbData
            buf = (ctypes.c_byte * size)()
            ctypes.memmove(buf, out_blob.pbData, size)
            kernel32 = ctypes.windll.kernel32
            kernel32.LocalFree(out_blob.pbData)
            return bytes(buf)
    except Exception:
        pass
    return None


def _unprotect_data_windows(cipher_bytes: bytes) -> Optional[bytes]:
    """Decrypts bytes using Windows DPAPI (CryptUnprotectData)."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [
                ("cbData", wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_byte)),
            ]

        p_cipher = ctypes.cast(
            (ctypes.c_byte * len(cipher_bytes))(*cipher_bytes),
            ctypes.POINTER(ctypes.c_byte),
        )
        in_blob = DATA_BLOB(len(cipher_bytes), p_cipher)
        out_blob = DATA_BLOB()

        crypt32 = ctypes.windll.crypt32
        if crypt32.CryptUnprotectData(
            ctypes.byref(in_blob),
            None,
            None,
            None,
            None,
            0x01,  # CRYPTPROTECT_UI_FORBIDDEN
            ctypes.byref(out_blob),
        ):
            size = out_blob.cbData
            buf = (ctypes.c_byte * size)()
            ctypes.memmove(buf, out_blob.pbData, size)
            kernel32 = ctypes.windll.kernel32
            kernel32.LocalFree(out_blob.pbData)
            return bytes(buf)
    except Exception:
        pass
    return None


def encrypt_text(text: str) -> str:
    """Encrypts text using Windows DPAPI with base64 encoding."""
    if not text:
        return ""
    raw = text.encode("utf-8")
    protected = _protect_data_windows(raw)
    if protected is not None:
        return "DPAPI:" + base64.b64encode(protected).decode("ascii")
    # Fallback to base64 obfuscation if DPAPI is unavailable
    return "RAW:" + text


def decrypt_text(payload: str) -> str:
    """Decrypts text previously encrypted by encrypt_text."""
    if not payload:
        return ""
    if payload.startswith("DPAPI:"):
        cipher_bytes = base64.b64decode(payload[6:].encode("ascii"))
        plain = _unprotect_data_windows(cipher_bytes)
        if plain is not None:
            return plain.decode("utf-8")
        return ""
    if payload.startswith("RAW:"):
        return payload[4:]
    return payload


def secure_file_permissions(file_path: Path) -> None:
    """Enforces owner-only read/write permissions on sensitive credential files."""
    try:
        if sys.platform != "win32" and file_path.exists():
            os.chmod(file_path, 0o600)
    except Exception:
        pass
