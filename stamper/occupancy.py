"""Whitespace / occupancy analysis for a single page.

A page is rasterised to grayscale once, turned into a binary "ink" mask, and
summarised with an integral image so we can score any candidate stamp location
in O(1). The search then returns the square seal footprint that covers the
least ink while staying inside the margins and clear of keep-out rectangles.

Everything works in *analysis pixels*; one analysis pixel equals
``72 / analysis_dpi`` points. At the default 72 DPI it is 1 pixel == 1 point.
"""

from __future__ import annotations

from dataclasses import dataclass

import fitz
import numpy as np

from .config import Settings


@dataclass
class PageOccupancy:
    ink: np.ndarray          # bool mask, shape (H, W) in analysis pixels
    integral: np.ndarray     # int64 summed-area table, shape (H+1, W+1)
    scale: float             # analysis pixels per point
    width_pt: float
    height_pt: float

    @property
    def px_per_pt(self) -> float:
        return self.scale


def analyze_page(page: "fitz.Page", settings: Settings) -> PageOccupancy:
    """Rasterise *page* and build its occupancy summary."""
    scale = settings.analysis_dpi / 72.0
    pix = page.get_pixmap(
        matrix=fitz.Matrix(scale, scale),
        colorspace=fitz.csGRAY,
        alpha=False,
    )
    gray = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    ink = gray < settings.ink_threshold
    integral = _integral_image(ink)
    return PageOccupancy(
        ink=ink,
        integral=integral,
        scale=scale,
        width_pt=page.rect.width,
        height_pt=page.rect.height,
    )


def _integral_image(mask: np.ndarray) -> np.ndarray:
    # uint32 is sufficient (the running count maxes out at H*W ink pixels, far
    # below 2**32) and halves the memory of this per-page table versus int64. The
    # summed-area identity a-b-c+e stays correct under unsigned wraparound because
    # every window sum lies in [0, H*W].
    out = np.zeros((mask.shape[0] + 1, mask.shape[1] + 1), dtype=np.uint32)
    out[1:, 1:] = mask.cumsum(axis=0, dtype=np.uint32).cumsum(axis=1, dtype=np.uint32)
    return out


def _window_sums(I: np.ndarray, ys: np.ndarray, xs: np.ndarray, d: int) -> np.ndarray:
    """Vectorised sum of every d x d window whose top-left is (y, x)."""
    a = I[np.ix_(ys + d, xs + d)]
    b = I[np.ix_(ys, xs + d)]
    c = I[np.ix_(ys + d, xs)]
    e = I[np.ix_(ys, xs)]
    return a - b - c + e


def _most_open_candidate(integral: np.ndarray, xs: np.ndarray, ys: np.ndarray,
                         d: int, eligible: np.ndarray) -> int | None:
    """Pick the most isolated of the equally-good candidates.

    "Most isolated" is the candidate around which the largest ink-free square
    fits *entirely on the page* -- a square clearance measure. Reusing the
    summed-area table, each square is scored in O(1), so a handful of radii cover
    the whole tie set quickly (and without a heavy distance-transform
    dependency). Because the squares must stay on the page, edges bound them and
    the seal is pulled toward the middle of a void rather than against a margin.

    Parameters mirror the candidate grid in :func:`find_min_ink_spot`: ``xs`` and
    ``ys`` are the per-column/row top-left pixel coordinates and ``eligible`` is
    the 2D ``(len(ys), len(xs))`` mask of candidates tied for least ink. Returns
    the flat index (into that grid) of the winner, or ``None`` if no eligible
    candidate can host even the smallest test square.
    """
    height = integral.shape[0] - 1
    width = integral.shape[1] - 1
    centers_x = xs + d // 2
    centers_y = ys + d // 2
    rows, cols = np.nonzero(eligible)
    cx = centers_x[cols]
    cy = centers_y[rows]

    half = d // 2
    r_max = max(half, min(height, width) // 2)
    radii = np.unique(np.linspace(half, r_max, 16).astype(np.int64))[::-1]
    for r in radii:
        x0, x1 = cx - r, cx + r
        y0, y1 = cy - r, cy + r
        on_page = (x0 >= 0) & (y0 >= 0) & (x1 <= width) & (y1 <= height)
        if not on_page.any():
            continue
        # Clip so masked-out (off-page) candidates can't raise on indexing.
        x0c, x1c = np.clip(x0, 0, width), np.clip(x1, 0, width)
        y0c, y1c = np.clip(y0, 0, height), np.clip(y1, 0, height)
        ink = (integral[y1c, x1c] - integral[y0c, x1c]
               - integral[y1c, x0c] + integral[y0c, x0c])
        clear = on_page & (ink == 0)
        if clear.any():
            j = int(np.argmax(clear))
            return int(rows[j]) * eligible.shape[1] + int(cols[j])
    return None


@dataclass
class Spot:
    center_x_pt: float
    center_y_pt: float
    coverage: float  # fraction of footprint that is ink (0..1)


def find_min_ink_spot(
    occ: PageOccupancy,
    diameter_pt: float,
    settings: Settings,
    keepout_rects_pt: list[tuple[float, float, float, float]] | None = None,
    bounds_pt: tuple[float, float, float, float] | None = None,
) -> Spot | None:
    """Find the seal center with the least underlying ink.

    When several positions tie for least ink (the common "spoiled for choice"
    case on a sparse drawing, where many footprints are completely ink-free),
    the tie is broken by *clearance*: among the equally-best candidates we pick
    the most isolated one -- the centre of the largest ink-free square that still
    fits on the page (see :func:`_most_open_candidate`). Because those squares are
    bounded by the page edges, the seal ends up centred in open space rather than
    hugging a margin. Set ``settings.maximize_clearance`` to ``False`` to fall
    back to plain first-found minimum-ink behaviour.

    Parameters
    ----------
    diameter_pt:
        Seal footprint size (square approximation of the disk).
    keepout_rects_pt:
        Rectangles (x0, y0, x1, y1) that the seal center must avoid.
    bounds_pt:
        Optional sub-region to restrict the search to (used to place inside a
        detected cell). Defaults to the whole page minus the margin.
    """
    s = occ.scale
    d = max(1, int(round(diameter_pt * s)))
    H, W = occ.ink.shape

    if bounds_pt is None:
        # Per-side page padding (display space): keep the seal centre far enough
        # from each edge that the whole footprint stays inside the padded region.
        x0 = settings.margin_left_pt * s
        y0 = settings.margin_top_pt * s
        x1 = W - settings.margin_right_pt * s
        y1 = H - settings.margin_bottom_pt * s
    else:
        bx0, by0, bx1, by1 = (v * s for v in bounds_pt)
        x0, y0, x1, y1 = bx0, by0, bx1, by1

    x_lo, x_hi = int(np.floor(x0)), int(np.ceil(x1)) - d
    y_lo, y_hi = int(np.floor(y0)), int(np.ceil(y1)) - d
    if x_hi < x_lo or y_hi < y_lo:
        return None

    step = max(1, int(round(settings.search_step_pt * s)))
    xs = np.arange(x_lo, x_hi + 1, step)
    ys = np.arange(y_lo, y_hi + 1, step)
    if xs.size == 0 or ys.size == 0:
        return None

    sums = _window_sums(occ.integral, ys, xs, d).astype(np.float64)

    # Disqualify candidates whose footprint touches a keep-out rectangle.
    if keepout_rects_pt:
        cx = (xs + d / 2.0) / s  # center in points, shape (len xs,)
        cy = (ys + d / 2.0) / s
        half = diameter_pt / 2.0
        for (kx0, ky0, kx1, ky1) in keepout_rects_pt:
            overlap_x = (cx + half > kx0) & (cx - half < kx1)   # (len xs,)
            overlap_y = (cy + half > ky0) & (cy - half < ky1)   # (len ys,)
            block = overlap_y[:, None] & overlap_x[None, :]
            sums[block] = np.inf

    if not np.isfinite(sums).any():
        return None

    # Primary criterion: least ink under the footprint. Tie-break: when several
    # candidates share that minimum, prefer the one sitting in the most open
    # space, so a seal that could go anywhere ends up as isolated as possible.
    best = sums.min()
    eligible = sums == best
    flat = None
    if settings.maximize_clearance and int(eligible.sum()) > 1:
        flat = _most_open_candidate(occ.integral, xs, ys, d, eligible)
    if flat is None:
        flat = int(np.argmin(sums))
    iy, ix = np.unravel_index(flat, sums.shape)
    best_x0 = xs[ix]
    best_y0 = ys[iy]
    coverage = float(sums[iy, ix]) / float(d * d)

    center_x_pt = (best_x0 + d / 2.0) / s
    center_y_pt = (best_y0 + d / 2.0) / s
    return Spot(center_x_pt, center_y_pt, coverage)


def disk_coverage(occ: PageOccupancy, center_x_pt: float, center_y_pt: float,
                  diameter_pt: float) -> float:
    """Exact fraction of *ink* under the circular seal footprint."""
    s = occ.scale
    r = (diameter_pt / 2.0) * s
    cx, cy = center_x_pt * s, center_y_pt * s
    H, W = occ.ink.shape
    x0 = max(0, int(np.floor(cx - r)))
    x1 = min(W, int(np.ceil(cx + r)))
    y0 = max(0, int(np.floor(cy - r)))
    y1 = min(H, int(np.ceil(cy + r)))
    if x1 <= x0 or y1 <= y0:
        return 0.0
    sub = occ.ink[y0:y1, x0:x1]
    yy, xx = np.ogrid[y0:y1, x0:x1]
    disk = (xx - cx) ** 2 + (yy - cy) ** 2 <= r * r
    total = int(disk.sum())
    if total == 0:
        return 0.0
    return float((sub & disk).sum()) / total
