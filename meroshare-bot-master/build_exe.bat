@echo off
REM Build a distributable folder using PyInstaller (Windows)
REM Requires: .venv\Scripts\python.exe and PyInstaller installed in that env.

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: .venv\Scripts\python.exe not found.
    echo Create the virtual environment first, then install requirements.
    exit /b 1
)

:: Create build directory
if not exist build mkdir build

:: One-dir build (recommended for Playwright)
:: allow passing extra arguments (e.g. --distpath dist\meroshare-bot-0.0.5)
".venv\Scripts\python.exe" -m PyInstaller --noconfirm meroshare-bot.spec %*

if %ERRORLEVEL% neq 0 (
    echo Build failed
    exit /b %ERRORLEVEL%
)

:: flatten nested output if present (handles versioned dist paths)
:: locate any subfolder named "meroshare-bot" under the dist tree and
:: move its exe and _internal contents up one level
for /f "usebackq delims=" %%d in (`dir /b /s /ad dist 2^>nul ^| findstr /i "\\meroshare-bot$"`) do (
    if exist "%%d\meroshare-bot.exe" (
        echo Flattening nested directory %%d...
        :: move exe up one level (to parent folder) and copy _internal there
        if exist "%%d\..\meroshare-bot.exe" del /f /q "%%d\..\meroshare-bot.exe" >nul 2>&1
        move "%%d\meroshare-bot.exe" "%%d\..\" >nul 2>&1
        if exist "%%d\_internal" (
            xcopy "%%d\_internal\*" "%%d\..\_internal\" /e /i /q >nul 2>&1
        )
        :: copy any remaining files/directories (configs, txts, scripts, datas)
        xcopy "%%d\*" "%%d\..\" /e /i /q >nul 2>&1
        rd /s /q "%%d" >nul 2>&1
    )
)

echo Build complete. Deliver the folder in dist\
echo NOTE: If Chromium is not bundled, run "python -m playwright install chromium" on target machine.