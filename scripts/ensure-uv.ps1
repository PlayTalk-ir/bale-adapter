# Ensure uv is on PATH and return the uv executable path.
# Usage (dot-source):  $Uv = . .\scripts\ensure-uv.ps1

function Find-UvExe {
    $cmd = Get-Command uv -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($p in @(
        (Join-Path $env:USERPROFILE ".local\bin\uv.exe"),
        (Join-Path $env:USERPROFILE ".cargo\bin\uv.exe")
    )) {
        if (Test-Path $p) { return $p }
    }
    return $null
}

$Uv = Find-UvExe
if (-not $Uv) {
    Write-Host "[bootstrap] installing uv (https://astral.sh/uv)"
    try {
        irm https://astral.sh/uv/install.ps1 | iex
    } catch {
        throw "failed to install uv: $_"
    }
    $env:Path = @(
        (Join-Path $env:USERPROFILE ".local\bin"),
        (Join-Path $env:USERPROFILE ".cargo\bin"),
        $env:Path
    ) -join ";"
    $Uv = Find-UvExe
}

if (-not $Uv) {
    throw "uv not found after install - open a new terminal and re-run bootstrap"
}

return $Uv
