@echo off
setlocal
title Meroshare AutoPilot - Portable Bundle Builder

echo ========================================================
echo        MEROSHARE AUTOPILOT PORTABLE BUNDLER
echo  Builds a 100%% offline, zero-dependency portable folder
echo ========================================================
echo.

cd /d "%~dp0"

set "BUILD_PY="
if exist "%~dp0.venv\Scripts\python.exe" (
    set "BUILD_PY=%~dp0.venv\Scripts\python.exe"
) else (
    set "BUILD_PY=python"
)

echo Using Python builder: %BUILD_PY%
"%BUILD_PY%" tools\bundle_portable.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Portable bundle creation failed with code %ERRORLEVEL%.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo ========================================================
echo  SUCCESS! Portable runtime created in:
echo  %~dp0portable_runtime
echo.
echo  You can now copy this entire project folder to any USB
echo  drive or Windows PC. It will run without any Python
echo  or Git installation required!
echo ========================================================
echo.
pause
