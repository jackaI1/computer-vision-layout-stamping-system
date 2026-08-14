"""Build a single self-contained update file for the packaged Windows app.

The packaged app stores ``app.py`` and ``stamper/`` as plain source inside
``_internal/``, and feature updates that add no new dependencies only need those
files swapped. This script bundles the current source into one double-clickable
``Update-EngineeringStampPlacer.bat`` that locates an existing install, backs up
the current source, and copies the new source in. No rebuild or reinstall needed
on the target machine.

Usage (from the repo root):
    python packaging/make_updater.py [output.bat]

Default output: dist/Update-EngineeringStampPlacer.bat
"""

from __future__ import annotations

import base64
import io
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAYLOAD_FILES = ["app.py"]
PAYLOAD_DIRS = ["stamper"]
# Seal PNGs shipped as built-in defaults. The frozen app reads bundled seals from
# ``_internal/stamps`` (BUNDLED_STAMPS_DIR), which is exactly the update target
# (%DEST%), so the updater drops them straight into ``%DEST%\stamps``.
PAYLOAD_STAMP_DIR = "stamps"
MARKER = ":::PAYLOAD:::"

# Batch + a minimal PowerShell decode/extract step. Plain file copy for install.
BAT_TEMPLATE = r"""@echo off
setlocal EnableExtensions
title Engineering Stamp Placer - Update
echo(
echo   Engineering Stamp Placer - reliability update
echo   Fixes blank previews when adding/removing multiple files, corrects seal
echo   placement on rotated sheets, and skips unreadable/locked PDFs cleanly
echo   instead of crashing. Includes all earlier features.
echo(

set "SELF=%~f0"
set "SELFDIR=%~dp0"

REM --- locate the installed _internal folder -----------------------------------
set "DEST="
for %%P in (
  "%SELFDIR%_internal"
  "%SELFDIR%EngineeringStampPlacer\_internal"
  "%LOCALAPPDATA%\Programs\EngineeringStampPlacer\_internal"
  "%ProgramFiles%\EngineeringStampPlacer\_internal"
  "%ProgramFiles(x86)%\EngineeringStampPlacer\_internal"
) do if not defined DEST if exist "%%~P\app.py" set "DEST=%%~P"

if not defined DEST (
  echo   Could not find Engineering Stamp Placer on this PC.
  echo   Put this file in the same folder as EngineeringStampPlacer.exe
  echo   ^(or its "EngineeringStampPlacer" folder^) and double-click it again.
  echo(
  pause
  exit /b 1
)
echo   Updating: %DEST%
echo(

REM --- close the app if it is open (avoid file locks) --------------------------
taskkill /im EngineeringStampPlacer.exe /f >nul 2>&1
REM give the process a moment to release its file handles before copying
ping -n 2 127.0.0.1 >nul 2>&1

REM --- decode + extract the embedded payload -----------------------------------
set "WORK=%TEMP%\esp_update_%RANDOM%%RANDOM%"
mkdir "%WORK%" >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ls=Get-Content -LiteralPath $env:SELF; $i=[Array]::LastIndexOf($ls,'%MARKER%'); if($i -lt 0){exit 3}; $b=($ls[($i+1)..($ls.Length-1)]) -join ''; $zip=Join-Path $env:WORK 'p.zip'; [IO.File]::WriteAllBytes($zip,[Convert]::FromBase64String($b)); Expand-Archive -LiteralPath $zip -DestinationPath $env:WORK -Force"
if errorlevel 1 (
  echo   Could not unpack the update.
  echo(
  pause
  exit /b 1
)

REM --- verify the extracted payload before touching the install ----------------
if not exist "%WORK%\app.py" goto :badpayload
if not exist "%WORK%\stamper\__init__.py" goto :badpayload

REM --- back up the current source ----------------------------------------------
REM Use a fresh, uniquely-named folder for every run so re-running the updater can
REM never overwrite an earlier backup with already-updated source (which would
REM make rollback impossible). Verify the backup is complete before overwriting
REM anything, so a failed backup can't leave the install unrecoverable.
set "BK=%DEST%\_backup_before_update\%RANDOM%%RANDOM%"
mkdir "%BK%" >nul 2>&1
copy /y "%DEST%\app.py" "%BK%\app.py" >nul 2>&1
xcopy /e /i /y "%DEST%\stamper" "%BK%\stamper\" >nul 2>&1
if exist "%DEST%\stamps" xcopy /e /i /y "%DEST%\stamps" "%BK%\stamps\" >nul 2>&1
if not exist "%BK%\app.py" goto :nobackup
if not exist "%BK%\stamper\__init__.py" goto :nobackup

REM --- install the new source --------------------------------------------------
copy /y "%WORK%\app.py" "%DEST%\app.py" >nul
if errorlevel 1 goto :failed
REM Mirror stamper (remove the old folder first) so a module deleted/renamed in a
REM new version can't linger and keep being imported.
if exist "%DEST%\stamper" rmdir /s /q "%DEST%\stamper" >nul 2>&1
xcopy /e /i /y "%WORK%\stamper" "%DEST%\stamper\" >nul
if errorlevel 1 goto :failed
REM bundled default seals -> _internal\stamps (BUNDLED_STAMPS_DIR)
if exist "%WORK%\stamps" xcopy /e /i /y "%WORK%\stamps" "%DEST%\stamps\" >nul
if exist "%DEST%\stamper\__pycache__" rmdir /s /q "%DEST%\stamper\__pycache__" >nul 2>&1
if exist "%DEST%\__pycache__" del /q "%DEST%\__pycache__\app.*" >nul 2>&1

REM --- verify the install actually landed --------------------------------------
if not exist "%DEST%\app.py" goto :failed
if not exist "%DEST%\stamper\__init__.py" goto :failed

rmdir /s /q "%WORK%" >nul 2>&1
echo   Update installed successfully.
echo   A backup of the previous version is in:
echo     %BK%
echo(
echo   Launch Engineering Stamp Placer as usual to use the new options.
echo(
pause
exit /b 0

:badpayload
echo   The update package did not unpack correctly. Nothing was changed.
rmdir /s /q "%WORK%" >nul 2>&1
echo(
pause
exit /b 1

:nobackup
echo   Could not create a complete backup of the current version.
echo   Nothing was changed - your existing install is intact.
rmdir /s /q "%WORK%" >nul 2>&1
echo(
pause
exit /b 1

:failed
echo   ******************************************************************
echo   The update FAILED partway through ^(a file may have been locked^).
echo   Restore the previous version by copying everything from:
echo     %BK%
echo   back into:
echo     %DEST%
echo   ******************************************************************
rmdir /s /q "%WORK%" >nul 2>&1
echo(
pause
exit /b 1

@@MARKERLINE@@
@@PAYLOAD@@
"""


def build_payload_b64() -> str:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in PAYLOAD_FILES:
            zf.write(ROOT / name, name)
        for d in PAYLOAD_DIRS:
            for p in sorted((ROOT / d).rglob("*.py")):
                if "__pycache__" in p.parts:
                    continue
                zf.write(p, str(p.relative_to(ROOT)).replace("\\", "/"))
        # Bundled default seals (PNG only). These are legal signatures — the .bat
        # therefore carries them, so only distribute it to authorised engineers.
        stamps = ROOT / PAYLOAD_STAMP_DIR
        if stamps.is_dir():
            for p in sorted(stamps.glob("*.png")):
                zf.write(p, f"{PAYLOAD_STAMP_DIR}/{p.name}")
    return base64.encodebytes(buf.getvalue()).decode("ascii")


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "dist" / "Update-EngineeringStampPlacer.bat"
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = build_payload_b64()
    body = (BAT_TEMPLATE
            .replace("%MARKER%", MARKER)
            .replace("@@MARKERLINE@@", MARKER)
            .replace("@@PAYLOAD@@", payload))
    # Batch files want CRLF line endings.
    out.write_bytes(body.replace("\n", "\r\n").encode("ascii"))
    print(f"wrote {out} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
