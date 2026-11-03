@echo off
setlocal enabledelayedexpansion
title Meroshare AutoPilot

echo ========================================================
echo                 MEROSHARE AUTOPILOT
echo        Multi-Account IPO Automation Suite
echo ========================================================
echo.

cd /d "%~dp0"

:: Set environment variables to silence all prompts, telemetry, and ensure UTF-8
set "PYTHONUTF8=1"
set "STREAMLIT_LOGGER_HIDE_WELCOME_MESSAGE=true"
set "STREAMLIT_BROWSER_GATHER_USAGE_STATS=false"
set "STREAMLIT_CLIENT_TOOLBAR_MODE=minimal"

:: 1. Determine base Python candidate
set "VENV_DIR=%~dp0.venv"
set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"

:: 2. Test if existing .venv works on this machine (detects broken paths from copying between PCs)
set "VENV_VALID=0"
if exist "%PYTHON_EXE%" (
    "%PYTHON_EXE%" -c "import sys" >nul 2>&1
    if !ERRORLEVEL! EQU 0 (
        set "VENV_VALID=1"
    ) else (
        echo [NOTICE] Found a virtual environment copied from another PC with mismatched paths.
        echo [SETUP] Rebuilding clean local environment for this PC...
        rmdir /s /q "%VENV_DIR%" >nul 2>&1
    )
)

:: 3. If no valid .venv exists, create one using system Python
if "!VENV_VALID!"=="0" (
    echo [SETUP] Initializing local virtual environment...
    python -m venv "%VENV_DIR%"
    if !ERRORLEVEL! NEQ 0 (
        echo [ERROR] System Python not found. Please install Python 3.10 or 3.11 from python.org
        echo         and ensure "Add python.exe to PATH" is checked.
        pause
        exit /b 1
    )
    set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"
)

echo Using Python: %PYTHON_EXE%

:: 4. Verify all core dependencies (Streamlit, Playwright, Pandas, Cryptography)
"%PYTHON_EXE%" -c "import streamlit, playwright, pandas, cryptography" >nul 2>&1
if !ERRORLEVEL! NEQ 0 (
    echo.
    echo [SETUP] Installing required dependencies from requirements.txt...
    "%PYTHON_EXE%" -m pip install --upgrade pip
    if exist "%~dp0requirements.txt" (
        "%PYTHON_EXE%" -m pip install -r "%~dp0requirements.txt"
    ) else if exist "%~dp0meroshare-bot-master\requirements.txt" (
        "%PYTHON_EXE%" -m pip install -r "%~dp0meroshare-bot-master\requirements.txt"
    )
    echo [SETUP] Installing Playwright Chromium browser engine...
    "%PYTHON_EXE%" -m playwright install chromium
    echo.
)

:: 5. Launch the Web Dashboard bound strictly to 127.0.0.1
echo Launching Web Dashboard in your browser...
echo Local address: http://127.0.0.1:8501
echo.

set "APP_ENTRY="
if exist "%~dp0meroshare-bot-master\app\dashboard.py" (
    set "APP_ENTRY=%~dp0meroshare-bot-master\app\dashboard.py"
) else if exist "%~dp0app\dashboard.py" (
    set "APP_ENTRY=%~dp0app\dashboard.py"
) else (
    echo [ERROR] dashboard.py not found in project directory.
    pause
    exit /b 1
)

"%PYTHON_EXE%" -m streamlit run "%APP_ENTRY%" --server.address=127.0.0.1 --server.headless=false --browser.gatherUsageStats=false --logger.hideWelcomeMessage=true --client.toolbarMode=minimal

if !ERRORLEVEL! NEQ 0 (
    echo.
    echo [ERROR] Streamlit dashboard terminated with error code !ERRORLEVEL!.
    echo.
)

pause
