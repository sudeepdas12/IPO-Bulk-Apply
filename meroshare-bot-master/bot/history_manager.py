"""Manages IPO application run history logs with atomic file replacement and write-ahead batch checkpointing."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from filelock import FileLock
    HAS_FILELOCK = True
except ImportError:
    HAS_FILELOCK = False


class HistoryManager:
    """Stores and retrieves IPO application history logs safely with atomic persistence and WAL checkpointing."""

    def __init__(self, file_path: Optional[Path] = None):
        if file_path is None:
            self.file_path = Path(__file__).resolve().parent.parent / "data" / "history.json"
        else:
            self.file_path = Path(file_path)

        self.wal_path = self.file_path.parent / "run_state.json"
        self.lock_path = self.file_path.parent / "history.lock"

        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.file_path.exists():
            self._save([])

    def _get_lock(self) -> Any:
        if HAS_FILELOCK:
            return FileLock(str(self.lock_path), timeout=10)
        return None

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
        """Atomically saves records with cross-process file locking."""
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        lock = self._get_lock()
        
        def _write() -> None:
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

        if lock:
            with lock:
                _write()
        else:
            _write()

    # -------------------------------------------------------------
    # Write-Ahead Log (WAL) Checkpoint API for Resumable Batches
    # -------------------------------------------------------------
    def start_checkpoint(self, company_name: str, engine: str, total: int, accounts: List[Dict[str, Any]]) -> None:
        """Initializes a new batch execution checkpoint state."""
        checkpoint_data = {
            "status": "RUNNING",
            "start_time": datetime.now().isoformat(),
            "company": company_name,
            "engine": engine,
            "total": total,
            "accounts": accounts,
            "processed": [],
        }
        self.wal_path.parent.mkdir(parents=True, exist_ok=True)
        self.wal_path.write_text(json.dumps(checkpoint_data, indent=2), encoding="utf-8")

    def update_checkpoint(self, result_entry: Dict[str, Any]) -> None:
        """Atomically records progress for an individual processed account."""
        if not self.wal_path.exists():
            return
        try:
            data = json.loads(self.wal_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "processed" in data:
                data["processed"].append(result_entry)
                self.wal_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def get_interrupted_checkpoint(self) -> Optional[Dict[str, Any]]:
        """Returns active checkpoint if an incomplete interrupted batch exists."""
        if not self.wal_path.exists():
            return None
        try:
            data = json.loads(self.wal_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("status") == "RUNNING":
                processed_len = len(data.get("processed", []))
                total = data.get("total", 0)
                if processed_len < total:
                    return data
        except Exception:
            pass
        return None

    def clear_checkpoint(self) -> None:
        """Deletes checkpoint on clean batch completion."""
        try:
            if self.wal_path.exists():
                self.wal_path.unlink()
        except Exception:
            pass

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
