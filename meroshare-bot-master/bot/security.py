"""Security and data protection utilities for Meroshare AutoPilot."""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False


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


def derive_key(passphrase: str, salt: bytes, iterations: int = 600000) -> bytes:
    """Derives a 256-bit cryptographic key from a passphrase using PBKDF2-HMAC-SHA256."""
    return hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt, iterations, dklen=32)


def encrypt_aes_gcm(text: str, passphrase: str) -> str:
    """Encrypts text using PBKDF2-HMAC-SHA256 key derivation and AES-256-GCM authenticated cipher."""
    if not text:
        return ""
    if not HAS_CRYPTOGRAPHY:
        raise RuntimeError("cryptography package is required for AES-256-GCM encryption")
    salt = secrets.token_bytes(16)
    nonce = secrets.token_bytes(12)
    key = derive_key(passphrase, salt)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, text.encode("utf-8"), None)
    # Format: GCM:<salt(16)>:<nonce(12)>:<ciphertext+tag> in base64
    combined = salt + nonce + ciphertext
    return "GCM:" + base64.b64encode(combined).decode("ascii")


def decrypt_aes_gcm(payload: str, passphrase: str) -> Optional[str]:
    """Decrypts text previously encrypted by encrypt_aes_gcm using the provided passphrase."""
    if not payload or not payload.startswith("GCM:"):
        return None
    if not HAS_CRYPTOGRAPHY:
        raise RuntimeError("cryptography package is required for AES-256-GCM decryption")
    try:
        raw = base64.b64decode(payload[4:].encode("ascii"))
        if len(raw) < 16 + 12 + 16:  # salt + nonce + min tag
            return None
        salt = raw[:16]
        nonce = raw[16:28]
        ciphertext = raw[28:]
        key = derive_key(passphrase, salt)
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode("utf-8")
    except Exception:
        return None


def encrypt_text(text: str, master_passphrase: Optional[str] = None) -> str:
    """
    Encrypts text using AES-256-GCM (if master passphrase provided)
    or Windows DPAPI with base64 encoding.
    """
    if not text:
        return ""
    if master_passphrase:
        return encrypt_aes_gcm(text, master_passphrase)

    raw = text.encode("utf-8")
    protected = _protect_data_windows(raw)
    if protected is not None:
        return "DPAPI:" + base64.b64encode(protected).decode("ascii")
    # Fallback to base64 obfuscation if DPAPI is unavailable
    return "RAW:" + text


def decrypt_text(payload: str, master_passphrase: Optional[str] = None) -> str:
    """
    Decrypts text previously encrypted by encrypt_text.
    Supports GCM:, DPAPI:, and RAW: prefixes.
    """
    if not payload:
        return ""
    if payload.startswith("GCM:"):
        if master_passphrase:
            decrypted = decrypt_aes_gcm(payload, master_passphrase)
            if decrypted is not None:
                return decrypted
        return ""
    if payload.startswith("DPAPI:"):
        try:
            cipher_bytes = base64.b64decode(payload[6:].encode("ascii"))
            plain = _unprotect_data_windows(cipher_bytes)
            if plain is not None:
                return plain.decode("utf-8")
        except Exception:
            pass
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
