#!/usr/bin/env python3
r"""
Simple installer that extracts the bundled `dist/meroshare-bot-<ver>.zip` and
copies it to the target folder (defaults to %ProgramFiles%\Meroshare Bot).

This is intended to be packaged as a one-file EXE (PyInstaller) and distributed
as an alternative installer when NSIS/makensis isn't available.
"""
import argparse
import os
import shutil
import sys
import zipfile
from pathlib import Path


def locate_zip(name_hint="meroshare-bot-0.0.9.zip"):
    # 1) If running from source tree, prefer dist/<zip>
    repo_root = Path(__file__).resolve().parents[1]
    candidate = repo_root / "dist" / name_hint
    if candidate.exists():
        return candidate

    # 2) If bundled by PyInstaller, files are extracted to _MEIPASS
    meipass = getattr(sys, '_MEIPASS', None)
    if meipass:
        candidate = Path(meipass) / name_hint
        if candidate.exists():
            return candidate

    # 3) fallback: current dir
    candidate = Path.cwd() / name_hint
    if candidate.exists():
        return candidate

    return None


def create_shortcut(target, name="Meroshare Bot"):
    # Use PowerShell to create a Windows .lnk shortcut (avoids pywin32 dependency)
    desktop = os.path.join(os.environ.get('PUBLIC') or os.path.join(os.environ['USERPROFILE'], 'Public'), 'Desktop')
    shortcut_path = os.path.join(desktop, f"{name}.lnk")
    ps = (
        "$WshShell = New-Object -ComObject WScript.Shell;"
        f"$s = $WshShell.CreateShortcut('{shortcut_path}');"
        f"$s.TargetPath = '{target}';"
        f"$s.WorkingDirectory = '{os.path.dirname(target)}';"
        "$s.Save();"
    )
    cmd = ["powershell", "-NoProfile", "-Command", ps]
    return os.system(" ".join(cmd)) == 0


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--target", "-t", help="Installation directory (default: ProgramFiles\\Meroshare Bot)")
    p.add_argument("--zip", help="Path to bundled ZIP (used for debugging)")
    args = p.parse_args()

    default_install = os.path.join(os.environ.get('ProgramFiles', 'C:\\Program Files'), 'Meroshare Bot')
    target_dir = Path(args.target or default_install)

    zip_path = Path(args.zip) if args.zip else locate_zip()
    if not zip_path or not zip_path.exists():
        print(f"ERROR: installer ZIP not found (looked for {zip_path})", file=sys.stderr)
        sys.exit(2)

    print(f"Installing from: {zip_path}")
    print(f"Target directory: {target_dir}")

    try:
        if target_dir.exists():
            print(f"Removing existing installation at {target_dir}...")
            shutil.rmtree(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        print("Extracting files...")
        with zipfile.ZipFile(zip_path, 'r') as z:
            z.extractall(target_dir)

        exe = target_dir / 'meroshare-bot.exe'
        if not exe.exists():
            print('ERROR: meroshare-bot.exe not found in package', file=sys.stderr)
            sys.exit(3)

        print('Creating Desktop shortcut...')
        if not create_shortcut(str(exe)):
            print('Warning: could not create shortcut (requires PowerShell/COM access)')

        # Offer to run Playwright installer if present
        playwright_helper = target_dir / '_internal' / 'install_playwright.bat'
        if not playwright_helper.exists():
            playwright_helper = target_dir / 'install_playwright.bat'

        if playwright_helper.exists():
            print('\nPlaywright browser installer helper found.')
            resp = input('Run Playwright installer now? (y/N): ').strip().lower()
            if resp == 'y':
                print(f'Running {playwright_helper} (may require admin)...')
                rc = os.system(f'"{playwright_helper}"')
                print(f'Playwright installer exited with {rc}')

        print('\nInstallation complete.')
        print(f'Run: "{exe}"')
        sys.exit(0)

    except Exception as exc:
        print('Installation failed:', exc, file=sys.stderr)
        sys.exit(4)


if __name__ == '__main__':
    main()
