"""Manages IPO application run history logs with atomic file replacement."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class HistoryManager:
    """Stores and retrieves IPO application history logs safely with atomic persistence."""

    def __init__(self, file_path: Optional[Path] = None):
        if file_path is None:
            self.file_path = Path(__file__).resolve().parent.parent / "data" / "history.json"
        else:
            self.file_path = Path(file_path)

        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.file_path.exists():
            self._save([])

    def _load(self) -> List[Dict[str, Any]]:
        """Safely loads history records from JSON."""
        if not self.file_path.exists():
            return []
        try:
            with self.file_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save(self, records: List[Dict[str, Any]]) -> None:
        """Atomically saves records to prevent corruption on crash or mid-write failure."""
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        temp_fd, temp_path_str = tempfile.mkstemp(
            dir=str(self.file_path.parent),
            prefix="history_tmp_",
            suffix=".json",
            text=True,
        )
        temp_path = Path(temp_path_str)
        try:
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                json.dump(records, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())

            temp_path.replace(self.file_path)
        except Exception:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass
            raise

    def log_run(
        self,
        company_name: str,
        engine: str,
        total: int,
        applied: int,
        skipped: int,
        failed: int,
        details: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Append a completed run record atomically."""
        now = datetime.now()
        record: Dict[str, Any] = {
            "id": now.strftime("%Y%m%d%H%M%S%f"),
            "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
            "company": company_name,
            "engine": engine,
            "total": total,
            "applied": applied,
            "skipped": skipped,
            "failed": failed,
            "details": details,
        }
        records = self._load()
        records.insert(0, record)  # most recent first
        # Retain last 200 runs
        self._save(records[:200])
        return record

    def get_history(self) -> List[Dict[str, Any]]:
        """Returns the full history list."""
        return self._load()

    def clear(self) -> None:
        """Clears all historical records."""
        self._save([])
