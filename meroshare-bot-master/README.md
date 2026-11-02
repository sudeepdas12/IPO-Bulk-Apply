<div align="center">

# MEROSHARE BOT

[![Playwright](https://img.shields.io/pypi/v/playwright.svg)](https://pypi.python.org/pypi/playwright)
[![License Badge](https://img.shields.io/github/license/tprototype/meroshare-bot?color=2b9348)](https://github.com/tprototype/meroshare-bot/blob/master/README.md)
[![Releases](https://img.shields.io/badge/version-0.0.9-blue)](https://github.com/tprototype/meroshare-bot/releases)

</div>


**This is meroshare bot, which will auto apply IPO of different company which are open.**

## Get Started

To get started, you need to download this project or can clone this repo on your machine.
And you can simply run the main.py file. But before that you need to setup the environment.

When running the bot you may optionally supply `--fast` to remove most of the built‑in
sleep delays (useful if the portal is responsive and you want a quicker run). Example:

```bash
python main.py --company "Ridge Line" --fast
```

### 1. Install the dependencies (automatic on pip install)

You can install the package with pip — this will automatically install all Python dependencies listed in `requirements.txt`:

```
pip install .
# or (developer / editable)
pip install -e .
```

If you prefer installing from the requirements file directly you can still do:

```
pip install -r requirements.txt
# or
python3 -m pip install -r requirements.txt
```

> Note: Playwright's browser binaries are not installed via pip. After installing the package run:
>
> ```
> python -m playwright install chromium
> ```

### 2. Run following code in the terminal

```
playwright install chromium
```

### 3. Edit demats.txt file to setup your information in the serial order as given

```
Name,CapitalID,Username,Password,Bank,Kitta,CRN,TXN_PIN

Optional extended format (recommended):
Name,CapitalID,Username,Password,Bank,Kitta,CRN,TXN_PIN,Branch[,Company]

For example:
Ram,13010400,00810257,password123,NABIL BANK LTD.,10,08410017501210,1234
Ram,13010400,00810257,password123,NABIL BANK LTD.,10,08410017501210,1234,Kathmandu Main Branch
Ram,13010400,00810257,password123,NABIL BANK LTD.,10,08410017501210,1234,Kathmandu Main Branch,Ridge Line Energy

"Ram" here is just a placeholder to denote the account, it can be anything you like

Branch and Company are optional. If `Company` is present for a row, that account will only be used to apply for the named IPO (case-insensitive, partial match). Company precedence: `--company` CLI flag (highest) → per-account `Company` in `demats.txt` → `config.ini` default.
```

### 4. Run the bot

```
python main.py
# or
python3 main.py
```

### 5. Apply for one specific IPO company (production mode)

You can specify the target company in two ways:

- Per-run using the CLI flag (overrides config):

```bash
python main.py --company "Ridge Line Energy"
```

- Persistent default using `config.ini` (the bot will use this when `--company` is not provided):

Create or edit `config.ini` next to `main.py` or next to the EXE and set:

```ini
[general]
company = Ridge Line Energy
```

The `--company` filter (or `config.ini` value) is case-insensitive and supports partial matches.

## Distribution / deployment

Two easy ways to distribute the bot to another Windows machine:

1) Lightweight (recommended): copy the repo, create a virtualenv and run `install_and_run.ps1`.
   - Example (PowerShell):
     - `powershell -ExecutionPolicy Bypass -File .\install_and_run.ps1 -Company "Ridge Line"`
   - Pros: easy to update, small footprint.

2) Single-folder EXE (for non-Python users): build with PyInstaller.
   - Use provided `build_exe.bat` on the developer machine to produce `dist\meroshare-bot`.
   - Copy the `dist\meroshare-bot` folder to the target PC and run `meroshare-bot.exe`.
   - Reminder: run `python -m playwright install chromium` on the target machine once.

3) Windows installer (recommended for end users): create a single .exe installer using NSIS.
   - Build steps on the developer machine:
     1. Build the PyInstaller bundle: `build_exe.bat` (produces `dist\meroshare-bot`).
     2. Run `build_installer.bat` (requires `makensis` in PATH).
     3. Installer produced at `dist\meroshare-bot-0.0.9-setup.exe` — run on target machine.
   - The installer:
     - installs the app to `Program Files` and creates Start Menu/Desktop shortcuts,
     - registers an Uninstall entry,
     - includes Playwright runtime data; after install the installer can optionally run the bundled `install_playwright.bat` helper to install Chromium.


### CI / Publishing (GitHub Actions)

A GitHub Actions workflow has been added to automatically build and publish when you create a GitHub Release (published).

- Files created: `.github/workflows/publish.yml`
- What it does: builds `sdist` + `wheel`, uploads the `dist/` artifact and — if you add a `PYPI_API_TOKEN` secret — publishes to PyPI.

To enable publishing on your repo:
1. Create a PyPI API token at https://pypi.org/manage/account/token/ and add it to the repository secrets as `PYPI_API_TOKEN`.
2. Create a Git tag (e.g. `v0.0.9`) and create/publish a GitHub Release for that tag — the workflow runs on the `release.published` event.

> The workflow will only publish to PyPI if `PYPI_API_TOKEN` is present in the repo secrets.

Publish release locally

- I added helper scripts so you can create a GitHub Release and upload the `dist/meroshare-bot-0.0.9.zip` artifact from your machine:
  - `scripts/publish_release.ps1` (PowerShell, prompts for PAT if needed)
  - `scripts/publish_release.sh` (bash / curl)

PowerShell example:

  $env:GITHUB_TOKEN = '<YOUR_TOKEN>'
  .\scripts\publish_release.ps1 -Repo 'owner/repo' -Tag 'v0.0.9'

Or run the script and paste your token when prompted.


### Quick launcher & scheduling

- `run_bot.bat` — a simple launcher included in the repo (double-click or call from Task Scheduler).
- `task_scheduler_example.bat` — example that creates a daily Task Scheduler entry.

## Runtime behavior

- `IPO Applied Successfully`: form submitted successfully.
- `IPO skipped ...`: usually already applied or not eligible for that account.  
  (the bot now inspects portal messages after submitting and will report "already applied" rather than success when appropriate)

## Changelog

### 0.0.4

* Detect "already applied" messages on submission and report as skipped instead of success
* Allow alphanumeric CRN values
* Added clean scripts and other packaging improvements

### 0.0.5

* Improved IPO selector to recognise 'edit'/'modify' links so missing Apply button is treated as already applied
* Additional heuristics after clicking Apply to catch portal "already applied" messages

### 0.0.6

* tightened Apply-button lookup to match whole word and avoid clicking unrelated links (e.g. "application")
* added a brief post-click wait loop to catch delayed portal messages

### 0.0.7

* standardized skip output text to "IPO Already Applied for the selected company"

### 0.0.8

### 0.0.9

* added `--fast` command‑line flag and FAST_MODE option to reduce internal sleep delays (speedup)


### 0.0.9

* added documentation and runtime support for `--fast` / FAST_MODE to speed up
  operations by reducing sleep delays


* flattened EXE distribution layout so `meroshare-bot.exe` appears at top level of the
  `dist` folder (no more nested `meroshare-bot` subdirectory)
* added `--fast` command‑line flag and `FAST_MODE` option to reduce internal
  sleep delays/timeouts (useful for speedy runs on reliable connections)

- `Login Error ...`: credentials or account access issue.
- `IPO Application Error ...`: actionable failure that should be investigated.

At the end of each run, the bot prints a summary:

- Total Accounts
- Applied
- Skipped
- Login Failed
- No Open Issue
- Errors

Exit code is non-zero only when `Errors > 0`.

### Please :star: Star us on GitHub — it motivates us a lot!

### You can raise issues or send message to ask if there is any problem you faced in any step
### And suggestion are welcome :)

