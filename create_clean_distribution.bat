@echo off
setlocal
title Meroshare AutoPilot - Clean Distribution Bundler

echo ========================================================
echo        CLEAN PORTABLE DISTRIBUTION BUILDER
echo ========================================================
echo.
echo This tool prepares a 100%% clean, portable package:
echo   1. Wipes all saved accounts from demats.txt (0 accounts)
echo   2. Clears previous application histories and cooldown logs
echo   3. Pre-bundles portable Python and Chromium browser
echo.
echo The resulting folder can be copied to ANY Windows PC and
echo will work automatically by double-clicking start_dashboard.bat!
echo.
echo --------------------------------------------------------
set /p CONFIRM="Are you sure you want to sanitize and bundle? (Y/N): "
if /i not "%CONFIRM%"=="Y" (
    echo [ABORTED] Distribution build cancelled.
    pause
    exit /b 0
)

cd /d "%~dp0"

set "BUILD_PY="
if exist "%~dp0.venv\Scripts\python.exe" (
    set "BUILD_PY=%~dp0.venv\Scripts\python.exe"
) else (
    set "BUILD_PY=python"
)

echo.
echo Running Clean Bundler...
"%BUILD_PY%" tools\clean_and_bundle.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Clean bundle process failed with code %ERRORLEVEL%.
    pause
    exit /b %ERRORLEVEL%
)

echo.
pause
