# bale-adapter bootstrap — idempotent (Windows).
# Installs uv + Python, creates venv, syncs deps, activates, runs login.
#
# Usage (dot-source so venv stays active):
#   . .\scripts\bootstrap.ps1
#
# Skip login on re-run:
#   . .\scripts\bootstrap.ps1 -SkipLogin

param(
    [switch]$SkipLogin,
    [string]$PythonVersion = "3.12"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$Uv = . (Join-Path $Root "scripts\ensure-uv.ps1")
$Venv = Join-Path $Root "venv"
$Python = Join-Path $Venv "Scripts\python.exe"

Write-Host "[bootstrap] installing Python $PythonVersion via uv"
& $Uv python install $PythonVersion

$env:UV_PROJECT_ENVIRONMENT = "venv"

if (-not (Test-Path $Python)) {
    Write-Host "[bootstrap] creating venv at $Venv"
    & $Uv venv $Venv --python $PythonVersion
}

Write-Host "[bootstrap] syncing dependencies via uv"
& $Uv sync --python $Python --directory $Root --group dev

foreach ($dir in @(".session", "data", "logs", "kb")) {
    New-Item -ItemType Directory -Force -Path (Join-Path $Root $dir) | Out-Null
}

. (Join-Path $Root "scripts\activate.ps1")

$session = $env:BALE_SESSION_PATH
$needsLogin = -not (Test-Path $session) -or ((Get-Item $session -ErrorAction SilentlyContinue).Length -eq 0)

if (-not $SkipLogin -and $needsLogin) {
    Write-Host "[bootstrap] no session - starting interactive login"
    & $Python (Join-Path $Root "scripts\login.py")
} elseif ($needsLogin) {
    Write-Host "[bootstrap] no session - run: python scripts\login.py"
} else {
    Write-Host "[bootstrap] session exists at $session - skipping login"
}

Write-Host "[bootstrap] ok - python=$Python uv=$Uv"

if ($MyInvocation.InvocationName -ne '.') {
    Write-Host ""
    Write-Host "Tip: dot-source to keep the venv active in this shell:"
    Write-Host "  . .\scripts\bootstrap.ps1"
    Write-Host "Or activate later:"
    Write-Host "  . .\scripts\activate.ps1"
}
