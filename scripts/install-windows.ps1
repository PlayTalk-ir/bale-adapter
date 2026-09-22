# PlayTalk bale-adapter — one-shot Windows installer.
#
# Installs Git (if missing), clones the repo, runs bootstrap (uv + Python + login).
#
# One-liner (paste in PowerShell):
#   irm https://raw.githubusercontent.com/PlayTalk-ir/bale-adapter/master/scripts/install-windows.ps1 | iex
#
# Custom install folder:
#   & ([scriptblock]::Create((irm https://raw.githubusercontent.com/PlayTalk-ir/bale-adapter/master/scripts/install-windows.ps1))) -InstallDir "D:\PlayTalk\bale-adapter"

param(
    [string]$RepoUrl = "https://github.com/PlayTalk-ir/bale-adapter.git",
    [string]$InstallDir = "",
    [switch]$SkipLogin
)

$ErrorActionPreference = "Stop"

function Refresh-Path {
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [System.Environment]::GetEnvironmentVariable("Path", "User")
}

function Ensure-Git {
    Refresh-Path
    if (Get-Command git -ErrorAction SilentlyContinue) {
        Write-Host "[install] git already installed: $(git --version)"
        return
    }

    Write-Host "[install] Git not found — installing..."

    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install --id Git.Git -e `
            --accept-package-agreements `
            --accept-source-agreements `
            --scope user
        Refresh-Path
    }

    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        foreach ($p in @(
            "$env:ProgramFiles\Git\cmd",
            "$env:ProgramFiles (x86)\Git\cmd",
            "$env:LocalAppData\Programs\Git\cmd"
        )) {
            if (Test-Path $p) {
                $env:Path = "$p;$env:Path"
                break
            }
        }
    }

    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        throw @"
Git installation failed.
Install manually from https://git-scm.com/download/win then re-run this script.
"@
    }

    Write-Host "[install] git installed: $(git --version)"
}

function Ensure-Repo {
    param([string]$Dir, [string]$Url)

    if (-not $Dir) {
        $Dir = Join-Path $env:USERPROFILE "bale-adapter"
    }
    $Dir = [System.IO.Path]::GetFullPath($Dir)

    if (Test-Path (Join-Path $Dir ".git")) {
        Write-Host "[install] repo exists at $Dir — pulling latest"
        Set-Location $Dir
        git pull --ff-only origin master 2>$null
        if ($LASTEXITCODE -ne 0) {
            git pull --ff-only origin main 2>$null
        }
    } elseif (Test-Path $Dir) {
        throw "Path exists but is not a git repo: $Dir — choose another -InstallDir"
    } else {
        Write-Host "[install] cloning $Url -> $Dir"
        $parent = Split-Path -Parent $Dir
        if ($parent -and -not (Test-Path $parent)) {
            New-Item -ItemType Directory -Force -Path $parent | Out-Null
        }
        git clone $Url $Dir
        Set-Location $Dir
    }

    return $Dir
}

Write-Host "========================================"
Write-Host " PlayTalk bale-adapter — Windows install"
Write-Host "========================================"
Write-Host ""

Ensure-Git
$Root = Ensure-Repo -Dir $InstallDir -Url $RepoUrl
Set-Location $Root

Write-Host ""
Write-Host "[install] running bootstrap in $Root"
Write-Host ""

$bootstrapArgs = @{}
if ($SkipLogin) { $bootstrapArgs.SkipLogin = $true }

. (Join-Path $Root "scripts\bootstrap.ps1") @bootstrapArgs

Write-Host ""
Write-Host "========================================"
Write-Host " Done. Project: $Root"
Write-Host ""
Write-Host " Next time, open PowerShell and run:"
Write-Host "   cd `"$Root`""
Write-Host "   . .\scripts\activate.ps1"
Write-Host "   python scripts\support_cli.py inbox --unread"
Write-Host "========================================"
