@echo off
setlocal
:: Ensure PyInstaller build exists
:: allow packaging of versioned dist folders (e.g. dist\meroshare-bot-0.0.9)
:: use the versioned dist folder produced earlier
set "EXPECTED=dist\meroshare-bot-0.0.9"
if not exist "%EXPECTED%" (
  echo ERROR: PyInstaller output folder '%EXPECTED%' not found.
  echo Run "build_exe.bat --distpath dist\meroshare-bot-0.0.9" first.
  exit /b 1
)

:: Check for NSIS (makensis)
where makensis >nul 2>&1
if errorlevel 1 (
  echo ERROR: 'makensis' not found in PATH. Install NSIS (https://nsis.sourceforge.io/Download) and re-run this script.
  exit /b 1
)

:: Build the installer
:: pass the located dist folder to NSIS as a macro
set "ABS_EXPECTED=%CD%\%EXPECTED%"
makensis /DAPP_DIST="%ABS_EXPECTED%" meroshare-bot-installer.nsi
if errorlevel 1 (
  echo NSIS build failed.
  exit /b %errorlevel%
)
echo Installer created: dist\meroshare-bot-0.0.9-setup.exe
endlocal
