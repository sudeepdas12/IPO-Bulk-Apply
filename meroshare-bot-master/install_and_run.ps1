<#
PowerShell helper: set up virtualenv, install dependencies, install Playwright browsers,
and run meroshare-bot. Intended for a fresh Windows machine.
Usage (PowerShell as Admin if required):
  .\install_and_run.ps1 [-Company "Ridge Line"]

python -m playwright install chromium

if ($Company -ne "") {
    Write-Host "Running bot for company: $Company"
    python main.py --company "$Company"
} else {
    Write-Host "Running bot for all accounts"
    python main.py
}
#>
param(
    [string]$Company = ""
)

$ErrorActionPreference = 'Stop'

function Invoke-Step {
    param(
        [string]$Command,
        [string]$Label
    )
    Write-Host $Label
    Invoke-Expression $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Step failed: $Label (exit code $LASTEXITCODE)"
    }
}

Write-Host "Creating virtual environment (.venv) if missing..."
if (-not (Test-Path -Path .venv)) {
    python -m venv .venv
}

Write-Host "Activating virtual environment..."
.\.venv\Scripts\Activate.ps1

Invoke-Step "python -m pip install --upgrade pip" "Installing/Upgrading pip..."
Invoke-Step "python -m pip install -r requirements.txt" "Installing Python dependencies (requirements.txt)..."
Invoke-Step "python -m playwright install chromium" "Installing Playwright browsers (chromium)..."

if ($Company -ne "") {
    Invoke-Step "python main.py --company \"$Company\"" "Running bot for company: $Company"
} else {
    Invoke-Step "python main.py" "Running bot for all accounts"
}