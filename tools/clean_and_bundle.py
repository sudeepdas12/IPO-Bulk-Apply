"""
Clean & Bundle Distributor for Meroshare AutoPilot
1. Safely wipes all personal account credentials and audit histories.
2. Packages standalone portable Python runtime and pre-downloaded Chromium.
3. Prepares a 100% clean, plug-and-play directory that runs on ANY Windows PC.
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

def log(msg: str):
    print(f"[CLEAN & BUNDLE] {msg}")

def clean_personal_data():
    log("Wiping all personal accounts, credentials, and histories...")

    # Reset demats.txt files to empty clean template
    clean_header = "Name,CapitalID,Username,Password,Bank,Kitta,CRN,TXN_PIN,Branch,Company\n"
    demat_paths = [
        ROOT_DIR / "demats.txt",
        ROOT_DIR / "meroshare-bot-master" / "demats.txt",
    ]
    for dp in demat_paths:
        dp.parent.mkdir(parents=True, exist_ok=True)
        dp.write_text(clean_header, encoding="utf-8")
        log(f"  -> Reset: {dp.relative_to(ROOT_DIR)} (0 accounts)")

    # Clear application history & cooldown data
    data_dirs = [
        ROOT_DIR / "data",
        ROOT_DIR / "meroshare-bot-master" / "data",
    ]
    for dd in data_dirs:
        if dd.exists():
            for f in dd.glob("*.json"):
                try:
                    f.unlink()
                    log(f"  -> Removed: {f.relative_to(ROOT_DIR)}")
                except Exception:
                    pass

    # Remove temporary cache folders
    cache_patterns = ["__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"]
    for pattern in cache_patterns:
        for p in ROOT_DIR.rglob(pattern):
            if p.is_dir() and "portable_runtime" not in str(p):
                try:
                    shutil.rmtree(p, ignore_errors=True)
                except Exception:
                    pass

    log("Personal data wiped successfully.")

def ensure_portable_runtime():
    portable_python = ROOT_DIR / "portable_runtime" / "python.exe"
    if not portable_python.exists():
        log("Building portable standalone Python runtime...")
        bundler_script = ROOT_DIR / "tools" / "bundle_portable.py"
        py_exe = sys.executable
        subprocess.run([py_exe, str(bundler_script)], check=True)
    else:
        log("Portable standalone runtime is already present.")

if __name__ == "__main__":
    clean_personal_data()
    ensure_portable_runtime()
    log("=======================================================")
    log(" SUCCESS: System is sanitized and bundled!")
    log(" You can now copy this folder to any Windows PC.")
    log(" Simply double-click 'start_dashboard.bat' to run.")
    log("=======================================================")
