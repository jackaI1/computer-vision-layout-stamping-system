# Packaging the Engineering Stamp Placer for Windows

This folder builds a **self-contained Windows application** that runs on a
machine with **no Python and no dependencies installed**. The app is bundled
with [PyInstaller](https://pyinstaller.org/); an optional
[Inno Setup](https://jrsoftware.org/isinfo.php) step wraps it in a single
`Setup.exe`.

## What gets produced

| Artifact | What it is | How the recipient uses it |
|---|---|---|
| `dist\EngineeringStampPlacer\` | A folder containing `EngineeringStampPlacer.exe` and every dependency. | Copy the whole folder over, double-click the `.exe`. |
| `dist\EngineeringStampPlacer-Setup.exe` *(optional)* | A single per-user installer (needs Inno Setup to build). | Double-click; it installs the app and adds Start Menu / desktop shortcuts. |

Either way the app needs nothing pre-installed on the target machine.

## Build it (on a Windows machine with Python 3.10+)

From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
```

That installs the dependencies plus PyInstaller and runs the build. When it
finishes you'll have `dist\EngineeringStampPlacer\EngineeringStampPlacer.exe`.

### Also build the single-file installer (optional)

Install Inno Setup once, then pass `-Installer`:

```powershell
winget install JRSoftware.InnoSetup
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1 -Installer
```

This produces `dist\EngineeringStampPlacer-Setup.exe`.

## Updating machines that already have the app

Feature changes that touch only `app.py` / `stamper/` plus the bundled default seals (no
new dependencies) don't need a full reinstall — the packaged app stores that source as plain
files under `_internal/` and reads its built-in seals from `_internal\stamps`.
Build a single self-contained updater:

```powershell
python packaging\make_updater.py
```

This writes `dist\Update-EngineeringStampPlacer.bat`. Its size tracks what's embedded: it
carries the new `app.py` + `stamper/` **and every PNG in `stamps/`**, so with the three
default seals it is roughly **1.5–1.7 MB** (not the tens of KB of a source-only patch). Send
that one file to each machine; the engineer double-clicks it and it:

1. finds the existing install (next to itself, or the per-user / Program Files install path),
2. backs up the current source + seals to a fresh `_internal\_backup_before_update\<run-id>\`
   folder (a new sub-folder each run, so re-running never clobbers an earlier rollback point),
3. swaps in the new `app.py` + `stamper/` and refreshes the bundled seals in `_internal\stamps`.

> ⚠️ The `.bat` embeds the P.Eng. seal PNGs — a legal signature. Distribute it **only** to
> people authorised to apply those seals, exactly as you would the built app or installer.

No reinstall, no admin rights. (If a machine's antivirus blocks the `.bat`, or you'd rather
not patch in place, just rebuild `Setup.exe` with the version bumped in `installer.iss` and
re-run it — the fixed `AppId` makes it upgrade the existing install. Or send the whole new
`dist\EngineeringStampPlacer\` folder and have them replace the old one.)

## How it works

- `desktop_app.py` is the entry point. It starts the Streamlit server on a free
  local port, waits for it to come up, and opens the default browser — so the
  user just sees the app, not a terminal command.
- `EngineeringStampPlacer.spec` tells PyInstaller to bundle Streamlit (including
  its compiled front-end), the `streamlit-image-coordinates` component, PyMuPDF,
  NumPy, Pillow, the project's own `app.py` + `stamper/` package, and the seal
  PNGs in `stamps/` as built-in defaults (unpacked to `_internal\stamps`).
- The app runs entirely on the local machine; nothing is uploaded anywhere.

## Using the app on the target machine

1. Launch it (double-click the `.exe`, the Start Menu entry, or the desktop
   shortcut). A small status window opens and the app appears in the browser.
2. In the sidebar, **pick a seal** from the built-in defaults, or choose
   *Upload a seal…* to use your own PNG. (You can also drop extra seal files into
   the `stamps` folder next to the executable and restart — they appear in the
   dropdown alongside the bundled defaults, and a same-named file overrides one.)
3. Upload one or more drawing PDFs, review the placements, and download the
   stamped files.
4. Close the status window to quit.

> The seal is a legal signature: distribute the built app only to people who are
> authorised to apply that seal.

## Notes & troubleshooting

- **First launch is slower** while Windows scans the new executable; subsequent
  launches are quick.
- **SmartScreen / antivirus:** unsigned PyInstaller executables can trigger a
  one-time "Windows protected your PC" prompt (choose *More info → Run anyway*)
  or an antivirus scan. Code-sign the executable to avoid this in a production
  rollout.
- **Rebuild after changing the app:** re-run the build script; PyInstaller picks
  up the current `app.py` and `stamper/` automatically.
