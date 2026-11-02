@echo off
setlocal

echo Installing Playwright Chromium browser...
python -m playwright install chromium
if %ERRORLEVEL% neq 0 (
    echo.
    echo Failed to install Chromium. Ensure Python is installed and on PATH.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo Chromium installed successfully.
echo You can now run meroshare-bot.exe
pause
