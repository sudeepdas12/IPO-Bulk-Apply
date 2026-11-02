# PowerShell script to clean build artifacts
Write-Host "Removing build, dist, and *.egg-info directories..."
$paths = @("build", "dist")
foreach ($p in $paths) {
    if (Test-Path $p) { Remove-Item -Recurse -Force $p -ErrorAction SilentlyContinue }
}
Get-ChildItem -Path . -Filter "*.egg-info" -Directory -ErrorAction SilentlyContinue | ForEach-Object { Remove-Item -Recurse -Force $_.FullName -ErrorAction SilentlyContinue }
Write-Host "Clean complete."