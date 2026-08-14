"""Engineering-stamp placement toolkit.

This package finds the best place to drop a circular engineer's seal on each
page of a multi-page drawing set, writes the date into the seal's top hole, and
produces a high-quality, *non-flattened* stamped PDF.

Public API is intentionally small; the Streamlit app (``app.py``) wires the
pieces together, but everything here is usable headless (see the
"Use the library without the UI" example in the README).
"""

from .config import Settings, DEFAULT_SETTINGS
from .stamp_image import StampAsset, load_stamp
from .placement import (
    Placement,
    compute_placements,
    sanitize_placements,
    placement_in_keepout,
    PLACEMENT_LOGIC_VERSION,
)
from .pdf_writer import render_stamped_pdf
from . import preview

__all__ = [
    "Settings",
    "DEFAULT_SETTINGS",
    "StampAsset",
    "load_stamp",
    "Placement",
    "compute_placements",
    "sanitize_placements",
    "placement_in_keepout",
    "PLACEMENT_LOGIC_VERSION",
    "render_stamped_pdf",
    "preview",
]
