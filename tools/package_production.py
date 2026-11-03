"""
Production Packager for Meroshare AutoPilot
Creates a self-contained, standalone distribution directory:
  dist/Meroshare-AutoPilot-Portable/
that contains everything needed to run anywhere with a single double-click.
"""

import os
import sys
import shutil
import zipfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DIST_DIR = ROOT_DIR / "dist" / "Meroshare-AutoPilot-Portable"

def log(msg: str):
    print(f"[PACKAGER] {msg}")

def build_production_bundle():
    log("Starting Final Production Package Build...")
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR, ignore_errors=True)
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Copy Application Source Code
    log("Copying application source code...")
    shutil.copytree(ROOT_DIR / "meroshare-bot-master", DIST_DIR / "meroshare-bot-master", 
                    ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", ".venv", "build", "dist"))

    # 2. Copy Requirements and Documentation
    shutil.copy2(ROOT_DIR / "requirements.txt", DIST_DIR / "requirements.txt")
    shutil.copy2(ROOT_DIR / "requirements.lock", DIST_DIR / "requirements.lock")
    if (ROOT_DIR / "README.md").exists():
        shutil.copy2(ROOT_DIR / "README.md", DIST_DIR / "README.md")

    # 3. Create Fresh Clean Demats Template (Zero Accounts / Zero Personal Data)
    clean_header = "Name,CapitalID,Username,Password,Bank,Kitta,CRN,TXN_PIN,Branch,Company\n"
    (DIST_DIR / "demats.txt").write_text(clean_header, encoding="utf-8")
    (DIST_DIR / "meroshare-bot-master" / "demats.txt").write_text(clean_header, encoding="utf-8")
    log("Created clean demats.txt template (0 accounts).")

    # 4. Clean any existing audit history / cooldown files in distribution
    dist_data_dirs = [DIST_DIR / "data", DIST_DIR / "meroshare-bot-master" / "data"]
    for dd in dist_data_dirs:
        if dd.exists():
            for f in dd.glob("*.json"):
                f.unlink(missing_ok=True)

    # 5. Create Standalone Universal Double-Click Launcher
    launcher_content = """@echo off
setlocal enabledelayedexpansion
title Meroshare AutoPilot Portable

echo ========================================================
echo                 MEROSHARE AUTOPILOT
echo          Portable Multi-Account IPO Suite
echo ========================================================
echo.

cd /d "%~dp0"

set "PYTHONUTF8=1"
set "STREAMLIT_LOGGER_HIDE_WELCOME_MESSAGE=true"
set "STREAMLIT_BROWSER_GATHER_USAGE_STATS=false"
set "STREAMLIT_CLIENT_TOOLBAR_MODE=minimal"

set "VENV_DIR=%~dp0.venv"
set "PYTHON_EXE=%VENV_DIR%\\Scripts\\python.exe"

set "VENV_OK=0"
if exist "%PYTHON_EXE%" (
    "%PYTHON_EXE%" -c "import sys" >nul 2>&1
    if !ERRORLEVEL! EQU 0 set "VENV_OK=1"
)

if "!VENV_OK!"=="0" (
    echo [SETUP] Initializing local Python virtual environment...
    if exist "%VENV_DIR%" rmdir /s /q "%VENV_DIR%" >nul 2>&1
    python -m venv "%VENV_DIR%"
    if !ERRORLEVEL! NEQ 0 (
        echo [ERROR] Python 3.10+ is required to run on this PC.
        echo Please install Python from https://www.python.org/downloads/
        echo Make sure to check "Add python.exe to PATH" during installation.
        pause
        exit /b 1
    )
    set "PYTHON_EXE=%VENV_DIR%\\Scripts\\python.exe"
    echo [SETUP] Installing required dependencies from requirements.lock...
    "%PYTHON_EXE%" -m pip install --upgrade pip >nul 2>&1
    "%PYTHON_EXE%" -m pip install -r "%~dp0requirements.txt"
    echo [SETUP] Installing Playwright Chromium browser...
    "%PYTHON_EXE%" -m playwright install chromium
    echo.
)

echo Launching Web Dashboard in your browser...
echo Local address: http://127.0.0.1:8501
echo.

"%PYTHON_EXE%" -m streamlit run "meroshare-bot-master\\app\\dashboard.py" --server.address=127.0.0.1 --server.headless=false --browser.gatherUsageStats=false --logger.hideWelcomeMessage=true --client.toolbarMode=minimal

if !ERRORLEVEL! NEQ 0 (
    echo [ERROR] Dashboard exited with code !ERRORLEVEL!.
)
pause
"""
    (DIST_DIR / "Start_Meroshare_AutoPilot.bat").write_text(launcher_content, encoding="utf-8")
    log("Created Start_Meroshare_AutoPilot.bat launcher.")

    # 6. Create Distribution ZIP Archive
    zip_dest = ROOT_DIR / "dist" / "Meroshare-AutoPilot-v0.0.9-Portable.zip"
    if zip_dest.exists():
        zip_dest.unlink()

    log(f"Compressing distribution package to {zip_dest.name}...")
    with zipfile.ZipFile(zip_dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(DIST_DIR):
            for file in files:
                file_path = Path(root) / file
                arcname = file_path.relative_to(DIST_DIR.parent)
                zf.write(file_path, arcname)

    log(f"SUCCESS: Final Production Distribution Package created at:")
    log(f"  Folder: {DIST_DIR}")
    log(f"  Zip:    {zip_dest} ({zip_dest.stat().st_size / (1024*1024):.2f} MB)")

if __name__ == "__main__":
    build_production_bundle()
