"""Tunable settings and constants.

All geometry is expressed in PDF *points* (1 pt = 1/72 inch) in the page's
unrotated coordinate system with the origin at the top-left and ``y`` growing
downward. That convention matches PyMuPDF's text/search coordinates and the
analysis raster, which keeps the whole pipeline in a single coordinate space.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

PT_PER_INCH = 72.0


# --- Stamp seal geometry (fractions of the seal image's bounding box) ---------
# The seal is a circle with two inner horizontal band lines. The upper "top
# hole" (the empty semicircle above the name band) is where the date goes.
# Measured from the supplied sample seal:
#   - top inner band line  ~0.37 of height
#   - bottom inner band line ~0.62 of height
# The date reads best centred horizontally and a little above the top band line.
DATE_REL_X = 0.50
DATE_REL_Y = 0.30

# --- Caption under the seal ---------------------------------------------------
# A short caption printed beneath the circle (e.g. "FOR STRUCTURAL ITEMS ONLY").
# Its font size is chosen so the caption is exactly as wide as the seal, so the
# text never extends past the seal's left/right edges. The gap is the vertical
# space between the seal's bottom and the caption, as a fraction of the diameter.
BOTTOM_TEXT_DEFAULT = "FOR STRUCTURAL ITEMS ONLY"
BOTTOM_TEXT_GAP_FRAC = 0.06
# Fraction of the diameter the caption may use (a hair under 1.0 so it always
# fits inside the seal's width without clipping).
BOTTOM_TEXT_WIDTH_FRAC = 0.98
# Upper bound on the caption's font height, as a fraction of the diameter. The
# font is normally sized to span the seal's width, but a *short* caption would
# otherwise need a huge font to be that wide; this caps the height so a short
# caption simply renders narrower than the seal instead of overflowing the page.
BOTTOM_TEXT_MAX_HEIGHT_FRAC = 0.12


@dataclass(frozen=True)
class Settings:
    """User-facing knobs. Immutable so it can be a cache key."""

    # --- Stamp sizing -------------------------------------------------------
    stamp_diameter_in: float = 1.9
    """Default seal diameter used for free-whitespace placements (inches)."""

    fit_stamp_to_engineer_box: bool = True
    """When an 'ENGINEER STAMP' cell is found, size the seal to fill it."""

    min_stamp_diameter_in: float = 1.4
    max_stamp_diameter_in: float = 3.2

    # --- Date text ----------------------------------------------------------
    date_font_pt: float = 9.0
    date_color: tuple[float, float, float] = (0.0, 0.0, 0.0)

    # --- Caption under the seal --------------------------------------------
    bottom_text: str = BOTTOM_TEXT_DEFAULT
    """Caption printed under the circle. Empty string disables it. Auto-sized so
    its width matches the seal diameter (see ``BOTTOM_TEXT_WIDTH_FRAC``)."""
    bottom_text_color: tuple[float, float, float] = (0.0, 0.0, 0.0)

    # --- Output flattening --------------------------------------------------
    flatten_output: bool = False
    """When True, rasterise every page to an image at ``flatten_dpi`` so the seal
    is permanently baked in (nothing selectable/removable). Off keeps the
    original vector/text content and adds the seal as an overlay (full quality)."""
    flatten_dpi: int = 150
    """Raster resolution used when ``flatten_output`` is on."""

    # --- Whitespace analysis ------------------------------------------------
    analysis_dpi: int = 72
    """Raster DPI for occupancy analysis. 72 => 1 pixel per point."""

    ink_threshold: int = 180
    """Grayscale value below which a pixel counts as 'ink' (content)."""

    search_step_pt: float = 6.0
    """Candidate-center grid spacing for the whitespace search."""

    maximize_clearance: bool = True
    """When several whitespace spots tie for least ink, prefer the one farthest
    from any drawing (and the page edges) so the seal sits in the most open
    space. Disable to take the first least-ink spot found."""

    # --- Page padding (per side) -------------------------------------------
    # Keep the seal at least this far inside each page edge, in inches. The UI
    # exposes one "overall minimum" slider that raises the floor of all four.
    margin_top_in: float = 0.4
    margin_bottom_in: float = 0.4
    margin_left_in: float = 0.4
    margin_right_in: float = 0.4

    # --- Preview rendering (does not affect placement) ---------------------
    preview_dpi: int = 72
    """Resolution the page is rasterised at once, then cached, for fast
    in-memory preview compositing."""

    preview_zoom: float = 1.0
    """Preview zoom. 1.0 = the whole page is shown; larger values zoom *in*
    toward the seal (the shown window is the page scaled down by this factor and
    centred on the seal)."""

    preview_target_px: int = 1100
    """Target longest-edge of a preview image, in pixels. Larger so a full-page
    view (the default) is still legible."""

    # --- Reserved top-right keep-out ---------------------------------------
    # The reserved municipal/approval whitespace lives in the top-right corner
    # of the sheet. We never auto-place there. Expressed as fractions of the
    # page's width/height, anchored to the *visual* top-right corner (adjusted
    # for landscape-flipped pages).
    keepout_width_frac: float = 0.20
    keepout_height_frac: float = 0.32
    keepout_pad_in: float = 1.5
    """Extra 'inch or two' breathing room enforced around the keep-out."""

    def with_overrides(self, **kwargs) -> "Settings":
        return replace(self, **kwargs)

    # --- Convenience conversions -------------------------------------------
    @property
    def stamp_diameter_pt(self) -> float:
        return self.stamp_diameter_in * PT_PER_INCH

    @property
    def min_stamp_diameter_pt(self) -> float:
        return self.min_stamp_diameter_in * PT_PER_INCH

    @property
    def max_stamp_diameter_pt(self) -> float:
        return self.max_stamp_diameter_in * PT_PER_INCH

    @property
    def margin_top_pt(self) -> float:
        return self.margin_top_in * PT_PER_INCH

    @property
    def margin_bottom_pt(self) -> float:
        return self.margin_bottom_in * PT_PER_INCH

    @property
    def margin_left_pt(self) -> float:
        return self.margin_left_in * PT_PER_INCH

    @property
    def margin_right_pt(self) -> float:
        return self.margin_right_in * PT_PER_INCH

    @property
    def keepout_pad_pt(self) -> float:
        return self.keepout_pad_in * PT_PER_INCH

    def cache_key(self) -> tuple:
        """Hashable snapshot of the **placement-affecting** settings, used to
        memoize the whitespace analysis/placement. Output-only settings (date,
        caption, fonts) are deliberately excluded so editing them does not
        recompute placements — see :meth:`render_key`."""
        return (
            round(self.stamp_diameter_in, 3),
            self.fit_stamp_to_engineer_box,
            round(self.min_stamp_diameter_in, 3),
            round(self.max_stamp_diameter_in, 3),
            self.analysis_dpi,
            self.ink_threshold,
            round(self.search_step_pt, 2),
            self.maximize_clearance,
            round(self.margin_top_in, 3),
            round(self.margin_bottom_in, 3),
            round(self.margin_left_in, 3),
            round(self.margin_right_in, 3),
            round(self.keepout_width_frac, 3),
            round(self.keepout_height_frac, 3),
            round(self.keepout_pad_in, 3),
        )

    def render_key(self) -> tuple:
        """Hashable snapshot of the settings that change the **rendered overlay**
        (seal + date + caption) for a fixed placement. Used to key the stamped-PDF
        and preview caches so editing the date font or the caption refreshes the
        output without recomputing placements."""
        return (
            round(self.stamp_diameter_in, 3),
            self.fit_stamp_to_engineer_box,
            round(self.min_stamp_diameter_in, 3),
            round(self.max_stamp_diameter_in, 3),
            round(self.date_font_pt, 3),
            self.date_color,
            self.bottom_text,
            self.bottom_text_color,
            self.flatten_output,
            self.flatten_dpi,
        )


DEFAULT_SETTINGS = Settings()
