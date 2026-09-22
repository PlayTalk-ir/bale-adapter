# Activate bale-adapter venv + local env vars (PowerShell).
# Usage:  . .\scripts\activate.ps1

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Activate = Join-Path $Root "venv\Scripts\Activate.ps1"

if (-not (Test-Path $Activate)) {
    throw "venv not found - run .\scripts\bootstrap.ps1 first"
}

. $Activate

$env:PYTHONIOENCODING = "utf-8"
$env:BALE_SESSION_PATH = Join-Path $Root ".session\session.bale"
$env:BALE_KB_DIR = Join-Path $Root "kb"
$env:BALE_LOG_FILE = Join-Path $Root "logs\userbot.log"
$env:BALE_STORE_PATH = Join-Path $Root "data\support_inbox.sqlite"
$env:PYTHONPATH = $Root

Write-Host "bale-adapter venv active ($Root)"
