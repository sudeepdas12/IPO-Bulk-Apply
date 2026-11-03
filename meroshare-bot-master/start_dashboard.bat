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

:: 1. Priority 1: Check for pre-bundled standalone portable runtime
if exist "%~dp0portable_runtime\python.exe" (
    set "PYTHON_EXE=%~dp0portable_runtime\python.exe"
    set "PLAYWRIGHT_BROWSERS_PATH=%~dp0portable_runtime\playwright_browsers"
    echo [PORTABLE] Using pre-bundled standalone Python runtime.
    goto :LAUNCH
)

:: 2. Priority 2: Use local virtual environment (.venv)
set "VENV_DIR=%~dp0.venv"
set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"

set "VENV_VALID=0"
if exist "%PYTHON_EXE%" (
    "%PYTHON_EXE%" -c "import sys" >nul 2>&1
    if !ERRORLEVEL! EQU 0 (
        set "VENV_VALID=1"
    ) else (
        echo [NOTICE] Detected virtual environment copied from another PC with different drive/user paths.
        echo [SETUP] Rebuilding clean local environment for this PC...
        rmdir /s /q "%VENV_DIR%" >nul 2>&1
    )
)

:: 3. If no valid .venv exists, create one using system Python
if "!VENV_VALID!"=="0" (
    echo [SETUP] Initializing local virtual environment...
    python -m venv "%VENV_DIR%" >nul 2>&1
    if !ERRORLEVEL! EQU 0 (
        set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"
    ) else (
        echo [NOTICE] System Python is not installed on this PC.
        echo [BOOTSTRAP] Building standalone portable runtime automatically...
        call "%~dp0bundle_portable.bat"
        if exist "%~dp0portable_runtime\python.exe" (
            set "PYTHON_EXE=%~dp0portable_runtime\python.exe"
            set "PLAYWRIGHT_BROWSERS_PATH=%~dp0portable_runtime\playwright_browsers"
            goto :LAUNCH
        ) else (
            echo [ERROR] Could not set up Python environment.
            echo Please install Python 3.10+ from python.org with "Add python.exe to PATH" checked.
            pause
            exit /b 1
        )
    )
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

:LAUNCH
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
