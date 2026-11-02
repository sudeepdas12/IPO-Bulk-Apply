<#
Publish `dist/meroshare-bot-0.0.9.zip` to a GitHub Release.

Usage (preferred):
  $env:GITHUB_TOKEN = '<PAT-with-repo-scope>'
  .\scripts\publish_release.ps1 -Repo 'owner/repo' -Tag 'v0.0.1'

If $env:GITHUB_TOKEN is not set the script will prompt for a PAT.
#>
param(
    [string]$Repo = $(if ($env:GITHUB_REPO) { $env:GITHUB_REPO } else { 'sudeepdas12/IPO-Bulk-Apply' }),
    [string]$Tag = 'v0.0.9',
    [string]$Zip = 'dist\meroshare-bot-0.0.9.zip',
    [switch]$Draft
)

if (-not (Test-Path $Zip)) {
    Write-Error "Release asset not found: $Zip"
    exit 1
}

$token = $env:GITHUB_TOKEN
if (-not $token) {
    Write-Host "GITHUB_TOKEN env var not set. Paste a GitHub Personal Access Token (repo scope)" -ForegroundColor Yellow
    $secure = Read-Host -AsSecureString "Token (input is hidden)"
    $token = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
}

$headers = @{ Authorization = "token $token"; "User-Agent" = "meroshare-bot-publisher"; Accept = 'application/vnd.github.v3+json' }

$body = @{
    tag_name = $Tag
    name     = $Tag
    body     = "Release built from local workspace — includes Windows single-folder bundle (meroshare-bot.exe)."
    draft    = $Draft.IsPresent
    prerelease = $false
} | ConvertTo-Json

try {
    Write-Host "Creating release $Tag in repo $Repo ..."
    $release = Invoke-RestMethod -Method Post -Uri "https://api.github.com/repos/$Repo/releases" -Headers $headers -Body $body -ContentType 'application/json'
} catch {
    Write-Error "Failed to create release: $($_.Exception.Message)"
    exit 1
}

$uploadUrl = $release.upload_url -replace '\{.*$',''
$fileName = [IO.Path]::GetFileName($Zip)
$uploadEndpoint = "$uploadUrl?name=$fileName"

try {
    Write-Host "Uploading asset $fileName ..."
    Invoke-RestMethod -Method Post -Uri $uploadEndpoint -Headers $headers -InFile $Zip -ContentType 'application/zip'
    Write-Host "Upload complete. Release URL: $($release.html_url)" -ForegroundColor Green
} catch {
    Write-Error "Asset upload failed: $($_.Exception.Message)"
    exit 1
}
