@echo off
setlocal
title Meroshare AutoPilot

echo ========================================================
echo                 MEROSHARE AUTOPILOT
echo        Multi-Account IPO Automation Suite
echo ========================================================
echo.

cd /d "%~dp0"

:: Set environment variables to silence all prompts, nudges, and telemetry
set "PYTHONUTF8=1"
set "STREAMLIT_LOGGER_HIDE_WELCOME_MESSAGE=true"
set "STREAMLIT_BROWSER_GATHER_USAGE_STATS=false"
set "STREAMLIT_CLIENT_TOOLBAR_MODE=minimal"

set "PYTHON_EXE="
if exist "%~dp0..\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0..\.venv\Scripts\python.exe"
) else if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo Using Python: %PYTHON_EXE%
echo Launching Web Dashboard in your browser...
echo.

"%PYTHON_EXE%" -m streamlit run "app\dashboard.py" --server.headless=false --browser.gatherUsageStats=false --logger.hideWelcomeMessage=true --client.toolbarMode=minimal

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Streamlit dashboard terminated with error code %ERRORLEVEL%.
    echo.
)

pause
