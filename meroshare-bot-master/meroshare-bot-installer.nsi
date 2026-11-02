!include "MUI2.nsh"

; Meroshare Bot NSIS installer
; Builds a single .exe installer that installs the PyInstaller "dist/meroshare-bot" folder

!define PRODUCT_NAME "Meroshare Bot"
!define PRODUCT_VERSION "0.0.9"

Name "${PRODUCT_NAME} ${PRODUCT_VERSION}"
OutFile "dist\\meroshare-bot-${PRODUCT_VERSION}-setup.exe"
InstallDir "$PROGRAMFILES\\Meroshare Bot"
ShowInstDetails show
RequestExecutionLevel admin
SetCompressor /SOLID lzma

; Pages
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_LANGUAGE "English"

;------------------------------------------------
Section "Install"
  SetOutPath "$INSTDIR"

  ; Copy the entire single-folder distribution created by PyInstaller
  ; (must exist at "dist\\meroshare-bot" when building the installer)
  File /r "dist\\meroshare-bot\\*"

  ; Create Start Menu folder & shortcuts
  CreateDirectory "$SMPROGRAMS\\${PRODUCT_NAME}"
  CreateShortCut "$SMPROGRAMS\\${PRODUCT_NAME}\\${PRODUCT_NAME}.lnk" "$INSTDIR\\meroshare-bot.exe"
  CreateShortCut "$DESKTOP\\${PRODUCT_NAME}.lnk" "$INSTDIR\\meroshare-bot.exe"

  ; Uninstaller
  WriteUninstaller "$INSTDIR\\Uninstall.exe"

  ; Register in Add/Remove Programs
  WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${PRODUCT_NAME}" "DisplayName" "${PRODUCT_NAME}"
  WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${PRODUCT_NAME}" "UninstallString" "$INSTDIR\\Uninstall.exe"
  WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${PRODUCT_NAME}" "DisplayVersion" "${PRODUCT_VERSION}"
  WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${PRODUCT_NAME}" "InstallLocation" "$INSTDIR"
SectionEnd

; Prompt to run Playwright browser installer after successful install
Function .onInstSuccess
  MessageBox MB_YESNO "Run Playwright browser installer now? (recommended)" IDYES run_playwright
  Return

  run_playwright:
    ; run the bundled helper (bundled under the PyInstaller _internal directory)
    ExecWait '"$SYSDIR\\cmd.exe" /C "$INSTDIR\\_internal\\install_playwright.bat"'
FunctionEnd

; Uninstall section
Section "Uninstall"
  Delete "$SMPROGRAMS\\${PRODUCT_NAME}\\${PRODUCT_NAME}.lnk"
  Delete "$DESKTOP\\${PRODUCT_NAME}.lnk"
  Delete "$INSTDIR\\Uninstall.exe"
  RMDir /r "$INSTDIR"
  DeleteRegKey HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${PRODUCT_NAME}"
SectionEnd
