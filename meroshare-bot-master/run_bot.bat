@echo off
REM Simple launcher for meroshare-bot (Windows)
REM Usage: double-click or run from Task Scheduler

:: activate virtualenv if present
if exist ".venv\Scripts\Activate.ps1" (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "& '.\.venv\Scripts\Activate.ps1'"
) else (
    REM use system python
)

:: run default (no company filter). Change or add --company "Name" as needed.
.\.venv\Scripts\python.exe main.py %*

pause