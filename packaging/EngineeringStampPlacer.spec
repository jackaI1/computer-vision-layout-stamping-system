# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build specification for the Engineering Stamp Placer.

Produces a self-contained Windows distribution (no Python or pip required on the
target machine). Build from the repository root with:

    python -m PyInstaller packaging/EngineeringStampPlacer.spec --noconfirm --clean

The result is ``dist/EngineeringStampPlacer/`` containing the executable and all
of its dependencies.
"""

import os

from PyInstaller.utils.hooks import collect_all, copy_metadata

# ``SPECPATH`` is the directory holding this spec (…/packaging); the project root
# is its parent. Using absolute paths keeps the build independent of the current
# working directory.
ROOT = os.path.dirname(SPECPATH)

datas = []
binaries = []
hiddenimports = []

# Packages whose code, data files (e.g. Streamlit's compiled front-end and the
# streamlit-image-coordinates component), and native libraries must be bundled.
_bundle = [
    "streamlit",
    "streamlit_image_coordinates",
    "fitz",            # PyMuPDF import package
    "pymupdf",         # PyMuPDF distribution package (native library)
    "numpy",
    "PIL",
    "altair",          # Streamlit charting dependency
    "pyarrow",         # Streamlit data dependency
    "tornado",
    "uvicorn",         # Streamlit 1.57+ serves over an ASGI/uvicorn stack
    "h11",
    "websockets",
    "wsproto",
]
for _pkg in _bundle:
    try:
        _d, _b, _h = collect_all(_pkg)
        datas += _d
        binaries += _b
        hiddenimports += _h
    except Exception:
        # A package that isn't installed is simply skipped; the build then fails
        # loudly later if it was actually required.
        pass

# Streamlit and several dependencies read their own version via
# importlib.metadata, which needs the distribution metadata bundled too.
datas += copy_metadata("streamlit", recursive=True)

# app.py is executed by Streamlit at runtime (not imported by the launcher) and
# the headless library lives alongside it, so bundle both as data.
datas += [(os.path.join(ROOT, "app.py"), "."),
          (os.path.join(ROOT, "stamper"), "stamper")]

# Retain project and third-party licensing alongside every packaged build.
datas += [(os.path.join(ROOT, name), ".")
          for name in ("LICENSE", "README.md", "THIRD_PARTY_NOTICES.md")]
datas += [(os.path.join(ROOT, "THIRD_PARTY_LICENSES"), "THIRD_PARTY_LICENSES")]

# Bundle the seal PNGs from stamps/ as built-in defaults so a fresh install ships
# with the standard seals already in the dropdown (app reads these from
# ``sys._MEIPASS/stamps`` — see BUNDLED_STAMPS_DIR in app.py). Recipients can
# still drop additional/override PNGs into the writable ``stamps`` folder next to
# the executable. The seals are a legal signature: only distribute the build to
# people authorised to apply them.
_stamps_dir = os.path.join(ROOT, "stamps")
if os.path.isdir(_stamps_dir):
    for _f in sorted(os.listdir(_stamps_dir)):
        if _f.lower().endswith(".png"):
            datas += [(os.path.join(_stamps_dir, _f), "stamps")]

a = Analysis(
    [os.path.join(ROOT, "desktop_app.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["scipy", "tkinter", "matplotlib", "pytest", "IPython"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="EngineeringStampPlacer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,  # shows startup status; closing the window quits the app
    disable_windowed_traceback=False,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="EngineeringStampPlacer",
)
