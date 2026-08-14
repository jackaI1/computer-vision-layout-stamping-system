<#
.SYNOPSIS
    Build the standalone Windows distribution of the Engineering Stamp Placer.

.DESCRIPTION
    Installs the build/runtime dependencies and runs PyInstaller against
    packaging\EngineeringStampPlacer.spec. The result is a self-contained folder
    (dist\EngineeringStampPlacer\) that runs on a machine with no Python.

    If Inno Setup is installed, optionally pass -Installer to also produce a
    single Setup.exe (dist\EngineeringStampPlacer-Setup.exe).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
    powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1 -Installer
#>
param(
    [switch]$Installer
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "==> Installing dependencies" -ForegroundColor Cyan
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install "pyinstaller==6.20.0"

Write-Host "==> Building with PyInstaller" -ForegroundColor Cyan
python -m PyInstaller packaging\EngineeringStampPlacer.spec --noconfirm --clean

$exe = Join-Path $root "dist\EngineeringStampPlacer\EngineeringStampPlacer.exe"
if (-not (Test-Path $exe)) {
    throw "Build failed: $exe was not produced."
}
Write-Host "==> Build complete: $exe" -ForegroundColor Green

if ($Installer) {
    $iscc = Get-Command iscc -ErrorAction SilentlyContinue
    if (-not $iscc) {
        Write-Warning "Inno Setup (iscc) not found. Install it (winget install JRSoftware.InnoSetup) and re-run with -Installer."
    } else {
        Write-Host "==> Building installer with Inno Setup" -ForegroundColor Cyan
        & $iscc.Source "packaging\installer.iss"
        Write-Host "==> Installer complete: dist\EngineeringStampPlacer-Setup.exe" -ForegroundColor Green
    }
}
