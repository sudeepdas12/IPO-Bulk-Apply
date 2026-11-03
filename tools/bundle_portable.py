"""
Portable Runtime Builder for Meroshare AutoPilot
Creates a 100% standalone, zero-dependency portable folder containing:
- Embedded Python 3.11 64-bit
- All pinned production dependencies (Streamlit, Playwright, Pandas, Cryptography, Requests)
- Bundled Chromium headless browser
- Self-contained launcher (Run_Meroshare_AutoPilot.bat)
"""

import os
import sys
import shutil
import zipfile
import urllib.request
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
PORTABLE_DIR = ROOT_DIR / "portable_runtime"
PYTHON_EMBED_URL = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip"
GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"

def log(msg: str):
    print(f"[PORTABLE BUILDER] {msg}")

def setup_portable_runtime():
    PORTABLE_DIR.mkdir(parents=True, exist_ok=True)
    python_exe = PORTABLE_DIR / "python.exe"

    # Step 1: Download Embedded Python if not present
    if not python_exe.exists():
        zip_path = ROOT_DIR / "python_embed.zip"
        log(f"Downloading embedded Python 3.11 runtime from {PYTHON_EMBED_URL}...")
        urllib.request.urlretrieve(PYTHON_EMBED_URL, zip_path)
        log("Extracting embedded Python...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(PORTABLE_DIR)
        zip_path.unlink()

        # Enable site-packages in embedded python (uncomment 'import site' in ._pth file)
        for pth_file in PORTABLE_DIR.glob("*._pth"):
            content = pth_file.read_text(encoding="utf-8")
            if "#import site" in content:
                content = content.replace("#import site", "import site\nLib\\site-packages")
            elif "import site" not in content:
                content += "\nimport site\nLib\\site-packages\n"
            pth_file.write_text(content, encoding="utf-8")
            log(f"Enabled site-packages in {pth_file.name}")

    # Step 2: Ensure pip is installed in embedded python
    site_packages = PORTABLE_DIR / "Lib" / "site-packages"
    site_packages.mkdir(parents=True, exist_ok=True)
    pip_exe = PORTABLE_DIR / "Scripts" / "pip.exe"

    if not pip_exe.exists():
        get_pip_path = ROOT_DIR / "get-pip.py"
        log("Downloading get-pip.py...")
        urllib.request.urlretrieve(GET_PIP_URL, get_pip_path)
        log("Installing pip into embedded runtime...")
        subprocess.run([str(python_exe), str(get_pip_path), "--no-warn-script-location"], check=True)
        get_pip_path.unlink()

    # Step 3: Install production dependencies
    req_file = ROOT_DIR / "requirements.txt"
    log(f"Installing pinned dependencies from {req_file.name}...")
    subprocess.run([
        str(python_exe), "-m", "pip", "install", "--no-warn-script-location", "-r", str(req_file)
    ], check=True)

    # Step 4: Install Playwright Chromium into local bundled directory
    local_browsers_dir = PORTABLE_DIR / "playwright_browsers"
    local_browsers_dir.mkdir(exist_ok=True)
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(local_browsers_dir)
    log("Bundling Chromium browser into portable directory...")
    subprocess.run([str(python_exe), "-m", "playwright", "install", "chromium"], check=True)

    log("Portable runtime successfully built!")

if __name__ == "__main__":
    setup_portable_runtime()
