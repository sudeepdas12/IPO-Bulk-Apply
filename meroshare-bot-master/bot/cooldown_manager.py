"""Cooldown Manager for persistent CDSC IP rate limits and firewall lockouts."""

from __future__ import annotations

import datetime
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_COOLDOWN_MINUTES = 15


class CooldownManager:
    """Manages persistent CDSC IP cooldown state across application restarts."""

    def __init__(self, file_path: Optional[Path] = None):
        if file_path is None:
            base_dir = Path(__file__).resolve().parent.parent
            self.file_path = base_dir / "data" / "cdsc_cooldown.json"
        else:
            self.file_path = Path(file_path)

    def load_state(self) -> Dict[str, Any]:
        """Load the persisted cooldown status."""
        if not self.file_path.exists():
            return {"active": False, "reason": "", "triggered_at": "", "expires_at": ""}
        try:
            with self.file_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {"active": False}
        except Exception as exc:
            logger.warning("Could not read cooldown file %s: %s", self.file_path, exc)
            return {"active": False}

    def is_cooldown_active(self) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if CDSC IP cooldown is currently in effect.
        Returns: (is_active: bool, cooldown_info: Dict)
        """
        state = self.load_state()
        if not state.get("active", False):
            return False, state

        expires_str = state.get("expires_at", "")
        if not expires_str:
            return False, state

        try:
            expires_at = datetime.datetime.fromisoformat(expires_str)
            now = datetime.datetime.now()
            if now < expires_at:
                return True, state
            else:
                # Cooldown expired naturally
                self.clear_cooldown()
                return False, {"active": False, "expired": True}
        except Exception:
            return False, state

    def record_cooldown(self, reason: str = "CDSC Firewall IP cooldown", duration_minutes: int = DEFAULT_COOLDOWN_MINUTES) -> Dict[str, Any]:
        """
        Persist a new cooldown lockout.
        """
        now = datetime.datetime.now()
        expires = now + datetime.timedelta(minutes=duration_minutes)

        state = {
            "active": True,
            "reason": reason,
            "triggered_at": now.isoformat(timespec="seconds"),
            "expires_at": expires.isoformat(timespec="seconds"),
            "duration_minutes": duration_minutes,
        }

        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            with self.file_path.open("w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
            logger.warning("CDSC IP Cooldown recorded: expires at %s (reason: %s)", expires, reason)
        except Exception as exc:
            logger.error("Failed to persist cooldown state: %s", exc)

        return state

    def clear_cooldown(self) -> None:
        """Reset and deactivate the cooldown lockout (e.g. after manual override)."""
        state = {"active": False, "reason": "Manually cleared or expired", "cleared_at": datetime.datetime.now().isoformat()}
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            with self.file_path.open("w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
        except Exception as exc:
            logger.warning("Could not clear cooldown file: %s", exc)

    def get_remaining_seconds(self) -> int:
        """Get seconds remaining on active cooldown, or 0 if inactive."""
        active, state = self.is_cooldown_active()
        if not active:
            return 0
        try:
            expires_at = datetime.datetime.fromisoformat(state.get("expires_at", ""))
            delta = (expires_at - datetime.datetime.now()).total_seconds()
            return max(0, int(delta))
        except Exception:
            return 0

    def format_time_remaining(self) -> str:
        """Format remaining time into human readable string e.g. '11m 45s (Expires: 14:45)'."""
        secs = self.get_remaining_seconds()
        if secs <= 0:
            return "Expired"
        state = self.load_state()
        expires_str = state.get("expires_at", "")
        expires_display = ""
        if expires_str:
            try:
                dt = datetime.datetime.fromisoformat(expires_str)
                expires_display = dt.strftime("%H:%M:%S")
            except Exception:
                pass

        mins, rem_secs = divmod(secs, 60)
        time_part = f"{mins}m {rem_secs}s" if mins > 0 else f"{rem_secs}s"
        return f"{time_part} (Next allowed retry: {expires_display})" if expires_display else time_part
