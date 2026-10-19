"""Detect a designated 'ENGINEER STAMP' cell and derive its usable box.

Many title blocks include a labelled cell ("ENGINEER STAMP") with empty space
below it that is reserved for exactly this seal. When present we honour it. The
label is found with PyMuPDF text search; the surrounding cell is then derived
from the page's ink mask by walking outward from just below the label until we
hit the bounding rules (long horizontal/vertical lines) of the title block.
"""

from __future__ import annotations

from dataclasses import dataclass

import fitz
import numpy as np

from .occupancy import PageOccupancy

# Search terms in priority order (PyMuPDF search ignores ASCII case).
_LABELS = ["ENGINEER STAMP", "ENGINEERING STAMP", "ENGINEERS STAMP", "ENGINEER'S STAMP"]

# A raster row/column is considered a ruling line of the title block when this
# fraction of it (over the relevant span) is ink.
_LINE_INK_FRAC = 0.55


@dataclass
class EngineerBox:
    label_rect: tuple[float, float, float, float]  # pt
    box: tuple[float, float, float, float]         # pt (x0, y0, x1, y1) usable area


def find_engineer_label(page: "fitz.Page") -> tuple[float, float, float, float] | None:
    """Return the label rect in *display* space (matching the analysis raster).

    ``search_for`` reports coordinates in the page's unrotated space; map them
    through the rotation matrix so they line up with the display-space ink mask.
    """
    for term in _LABELS:
        hits = page.search_for(term)
        if hits:
            r = (hits[0] * page.rotation_matrix).normalize()
            return (r.x0, r.y0, r.x1, r.y1)
    return None


def _ink_frac_rows(ink: np.ndarray, c0: int, c1: int) -> np.ndarray:
    span = ink[:, c0:c1]
    if span.shape[1] == 0:
        return np.zeros(ink.shape[0])
    return span.mean(axis=1)


def _ink_frac_cols(ink: np.ndarray, r0: int, r1: int) -> np.ndarray:
    span = ink[r0:r1, :]
    if span.shape[0] == 0:
        return np.zeros(ink.shape[1])
    return span.mean(axis=0)


def derive_box(
    occ: PageOccupancy,
    label_rect: tuple[float, float, float, float],
) -> EngineerBox | None:
    """Compute the empty rectangle below the label, bounded by the cell rules."""
    s = occ.scale
    H, W = occ.ink.shape
    lx0, ly0, lx1, ly1 = label_rect
    lcx = 0.5 * (lx0 + lx1)
    label_cx_px = int(round(lcx * s))
    label_bottom_px = int(round(ly1 * s))

    # The cell is at least as wide as the label; probe a tall window starting
    # just below the label to find the left/right vertical rules.
    probe_top = label_bottom_px + int(round(6 * s))
    probe_bot = min(H, probe_top + int(round(180 * s)))
    if probe_bot <= probe_top:
        return None
    col_frac = _ink_frac_cols(occ.ink, probe_top, probe_bot)

    left = _scan_for_line(col_frac, start=label_cx_px, step=-1)
    right = _scan_for_line(col_frac, start=label_cx_px, step=+1)
    if left is None:
        left = max(0, int(round((lx0 - 6) * s)))
    if right is None:
        right = min(W - 1, int(round((lx1 + 6) * s)))

    inner_l = left + max(2, int(round(3 * s)))
    inner_r = right - max(2, int(round(3 * s)))
    if inner_r - inner_l < int(round(40 * s)):
        return None

    # Find the bottom rule: first strong horizontal line below the label.
    row_frac = _ink_frac_rows(occ.ink, inner_l, inner_r)
    box_top = label_bottom_px + max(2, int(round(8 * s)))
    bottom = None
    y = box_top + int(round(20 * s))  # skip immediate neighbourhood of label
    while y < H:
        if row_frac[y] > _LINE_INK_FRAC:
            bottom = y
            break
        y += 1
    if bottom is None:
        bottom = min(H, box_top + int(round(260 * s)))
    inner_b = bottom - max(2, int(round(3 * s)))
    if inner_b - box_top < int(round(40 * s)):
        return None

    box_pt = (inner_l / s, box_top / s, inner_r / s, inner_b / s)
    return EngineerBox(label_rect=label_rect, box=box_pt)


def _scan_for_line(frac: np.ndarray, start: int, step: int) -> int | None:
    """Walk from *start* in *step* direction until a vertical ruling line."""
    n = len(frac)
    i = start
    while 0 <= i < n:
        if frac[i] > _LINE_INK_FRAC:
            return i
        i += step
    return None


def detect_engineer_box(page: "fitz.Page", occ: PageOccupancy) -> EngineerBox | None:
    label = find_engineer_label(page)
    if label is None:
        return None
    return derive_box(occ, label)
