"""Compute one seal placement per page and score how much it covers.

Priority for each page:
1. A detected 'ENGINEER STAMP' cell -> centre the seal in it, sized to fit.
2. Otherwise the least-ink free spot, avoiding the reserved top-right keep-out.

Placements are returned sorted by *coverage* descending, so the riskiest ones
(the seals sitting on the most ink) surface first for the operator to review.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

import fitz

from .config import Settings
from .engineer_box import detect_engineer_box
from .occupancy import analyze_page, disk_coverage, find_min_ink_spot, PageOccupancy

# Bump this whenever placement logic changes. It is folded into the app's cache
# keys so that a plain Streamlit "Rerun" (which keeps cached/session data alive)
# can never serve placements produced by older, buggy logic.
PLACEMENT_LOGIC_VERSION = 7


@dataclass
class Placement:
    page_index: int
    center_x_pt: float
    center_y_pt: float
    diameter_pt: float
    source: str          # "engineer_box" | "whitespace" | "manual"
    coverage: float      # 0..1 fraction of ink under the seal disk
    page_width_pt: float
    page_height_pt: float

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Placement":
        return cls(**d)

    def rect(self) -> "fitz.Rect":
        r = self.diameter_pt / 2.0
        return fitz.Rect(
            self.center_x_pt - r,
            self.center_y_pt - r,
            self.center_x_pt + r,
            self.center_y_pt + r,
        )


def keepout_rects(page_w: float, page_h: float,
                  settings: Settings) -> list[tuple[float, float, float, float]]:
    """Reserved whitespace rectangle at the visual top-right corner.

    Everything in the pipeline works in *display* space (the visually-upright
    page), so the reserved corner is always (x=max, y=min) regardless of the
    page's underlying ``/Rotate`` value. Padded by an extra inch-or-two.
    """
    w = settings.keepout_width_frac * page_w + settings.keepout_pad_pt
    h = settings.keepout_height_frac * page_h + settings.keepout_pad_pt
    return [(page_w - w, 0.0, page_w, h)]


def _fit_diameter_to_box(box, settings: Settings) -> float:
    x0, y0, x1, y1 = box
    d = min(x1 - x0, y1 - y0) * 0.86
    d = max(settings.min_stamp_diameter_pt, min(d, settings.max_stamp_diameter_pt))
    return d


def _safe_corner_placement(page_index: int, pw: float, ph: float, d: float,
                           settings: Settings, occ: PageOccupancy | None = None,
                           source: str = "whitespace") -> Placement:
    """A guaranteed on-sheet placement at the bottom-left (opposite the top-right
    keep-out). The diameter is shrunk to fit pages smaller than the seal and the
    centre is clamped so the whole disk stays on the page."""
    # A small sheet may not fit the nominal seal or padding. Shrink to the
    # largest bottom-left square that avoids the top-right reserved rectangle.
    kos = keepout_rects(pw, ph, settings)
    kx0, _, _, ky1 = kos[0]
    available = max(min(max(0.0, kx0), ph), min(pw, max(0.0, ph - ky1)))
    if available <= 0:
        raise ValueError("The reserved corner covers the whole page; reduce its fractions or padding.")
    d = min(d, pw, ph, available)
    half = d / 2.0
    cx = min(max(settings.margin_left_pt + half, half), pw - half)
    cy = min(max(ph - settings.margin_bottom_pt - half, half), ph - half)
    if intersects_keepout(cx, cy, d, kos):
        cx, cy = half, ph - half
    cov = disk_coverage(occ, cx, cy, d) if occ is not None else 0.0
    return Placement(page_index, cx, cy, d, source, cov, pw, ph)


def place_one_page(page: "fitz.Page", page_index: int, settings: Settings,
                   occ: PageOccupancy | None = None) -> Placement:
    if occ is None:
        occ = analyze_page(page, settings)
    pw, ph = page.rect.width, page.rect.height

    # 1) Honour a designated engineer-stamp cell -- but only if the seal actually
    #    fits inside it. A tiny detected cell would otherwise be overfilled by the
    #    min-diameter clamp and spill over the title-block rules, so fall through
    #    to whitespace placement in that case.
    if settings.fit_stamp_to_engineer_box:
        ebox = detect_engineer_box(page, occ)
        if ebox is not None:
            x0, y0, x1, y1 = ebox.box
            d = _fit_diameter_to_box(ebox.box, settings)
            if d <= min(x1 - x0, y1 - y0):
                cx = 0.5 * (x0 + x1)
                cy = 0.5 * (y0 + y1)
                cov = disk_coverage(occ, cx, cy, d)
                return Placement(page_index, cx, cy, d, "engineer_box", cov, pw, ph)

    # 2) Fall back to the emptiest spot, avoiding the reserved corner.
    d = settings.stamp_diameter_pt
    kos = keepout_rects(pw, ph, settings)
    spot = find_min_ink_spot(occ, d, settings, keepout_rects_pt=kos)
    if spot is None:
        # Degenerate page (smaller than margins+seal, or fully blocked): place a
        # clamped, shrunk-to-fit seal at the bottom-left so it never runs off.
        return _safe_corner_placement(page_index, pw, ph, d, settings, occ)

    cov = disk_coverage(occ, spot.center_x_pt, spot.center_y_pt, d)
    return Placement(page_index, spot.center_x_pt, spot.center_y_pt, d,
                     "whitespace", cov, pw, ph)


def compute_placements(doc: "fitz.Document", settings: Settings) -> list[Placement]:
    """Compute placements for every page, sorted by coverage descending.

    Fail explicitly when a page cannot be analysed or has no legal placement.
    A guessed corner with zero coverage would misrepresent an unreadable page.
    """
    placements: list[Placement] = []
    for i in range(doc.page_count):
        try:
            placements.append(place_one_page(doc[i], i, settings))
        except Exception as exc:
            raise ValueError(f"Could not place a stamp on page {i + 1}: {exc}") from exc
    placements.sort(key=lambda p: p.coverage, reverse=True)
    return placements


# --------------------------------------------------------------------------- #
# Keep-out enforcement (defense in depth)
# --------------------------------------------------------------------------- #
def intersects_keepout(center_x_pt: float, center_y_pt: float, diameter_pt: float,
                       keepouts: list[tuple[float, float, float, float]]) -> bool:
    """True if a seal of this size/center overlaps any reserved rectangle."""
    half = diameter_pt / 2.0
    for (x0, y0, x1, y1) in keepouts:
        if (center_x_pt + half > x0 and center_x_pt - half < x1
                and center_y_pt + half > y0 and center_y_pt - half < y1):
            return True
    return False


def placement_in_keepout(p: Placement, settings: Settings) -> bool:
    kos = keepout_rects(p.page_width_pt, p.page_height_pt, settings)
    return intersects_keepout(p.center_x_pt, p.center_y_pt, p.diameter_pt, kos)


def sanitize_placements(doc: "fitz.Document", placements: dict[int, Placement],
                        settings: Settings) -> tuple[dict[int, Placement], list[int]]:
    """Guarantee no *automatic* placement sits in the reserved keep-out.

    Runs on every render/download (uncached), so even a stale cached or
    session-stored placement produced by older logic is corrected before it can
    reach the output. Designated engineer-stamp boxes are exempt (an explicit
    "stamp here" overrides the keep-out, and such a box may legitimately abut the
    reserved corner). Manual placements are the operator's deliberate choice and
    are left untouched (the UI warns separately if one is in the corner).

    Returns the corrected mapping and the page indices that were relocated.
    """
    fixed: dict[int, Placement] = dict(placements)
    relocated: list[int] = []
    for idx, p in placements.items():
        if p.source != "whitespace":
            continue
        if placement_in_keepout(p, settings):
            newp = place_one_page(doc[idx], idx, settings)
            if newp.source == "whitespace" and placement_in_keepout(newp, settings):
                # Re-placement still landed in the corner (degenerate page where
                # the search returns the same blocked spot). Force a guaranteed
                # bottom-left, on-sheet position so the documented guarantee holds.
                newp = _safe_corner_placement(
                    idx, p.page_width_pt, p.page_height_pt,
                    settings.stamp_diameter_pt, settings)
            fixed[idx] = newp
            relocated.append(idx)
    return fixed, relocated
