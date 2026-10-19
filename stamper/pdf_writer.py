"""Write seals onto a PDF without flattening it.

``page.insert_image`` adds the seal as an overlay image XObject and
``page.insert_text`` adds the date as real, selectable text. Neither touches
the existing page content streams, so the original vector/drawing data is
preserved at full quality. Saving with garbage collection + lossless deflate
only de-duplicates and compresses object streams; it never rasterises the page.
"""

from __future__ import annotations

from io import BytesIO

import fitz

from .config import (
    Settings,
    DATE_REL_X,
    DATE_REL_Y,
    BOTTOM_TEXT_GAP_FRAC,
    BOTTOM_TEXT_WIDTH_FRAC,
    BOTTOM_TEXT_MAX_HEIGHT_FRAC,
)
from .placement import Placement
from .stamp_image import StampAsset

_CAPTION_FONT = "helv"

# Ceiling on a flattened page's raster size (pixels). ~40 MP ≈ 120 MB RGB, a safe
# cap on a typical office PC; only very large sheets at high DPI are downscaled.
_FLATTEN_MAX_PIXELS = 40_000_000


def _derotation_with_origin(page: "fitz.Page") -> "fitz.Matrix":
    """Derotation matrix that also compensates a non-zero page (MediaBox) origin.

    Placements are in *display* space (the origin-normalised ``page.rect``).
    PyMuPDF's ``insert_image``/``insert_text`` already compensate for a non-zero
    MediaBox origin when the page is *unrotated*, but **not** on rotated pages —
    there the seal, date and caption would be shifted by the origin (verified:
    e.g. a 270°-rotated sheet with origin (100,200) misplaces the seal by ~200 pt,
    landing it off the sheet or on the drawing, while the preview still looks
    correct). Pre-translate display coordinates per rotation so every case lands
    where the preview shows it. This is a no-op when the origin is (0,0), so
    ordinary pages are unchanged.
    """
    ox, oy = page.mediabox.x0, page.mediabox.y0
    corr = {0: (0.0, 0.0), 90: (oy, ox), 180: (-ox, oy), 270: (-oy, -ox)}
    cdx, cdy = corr.get(page.rotation, (0.0, 0.0))
    return fitz.Matrix(1, 0, 0, 1, cdx, cdy) * page.derotation_matrix


def _insert_one(page: "fitz.Page", placement: Placement, stamp: StampAsset,
                date_str: str, settings: Settings) -> None:
    # Placements live in *display* space (the visually-upright page, matching
    # the analysis raster and previews). Insertion APIs use the page's
    # *unrotated* coordinate space, so map every rectangle through the page's
    # derotation matrix and rotate the content back to upright with ``rotate``.
    #
    # Two matrices: ``insert_image`` does NOT compensate a non-zero MediaBox
    # origin on rotated pages (so it needs the origin-corrected matrix), but
    # ``insert_text``/``insert_textbox`` already do for every rotation — feeding
    # them the corrected matrix would double-count the origin and fling the date
    # and caption off the seal. So the seal uses ``derot_img`` and the text uses
    # the plain ``derot``. Both reduce to the same thing at origin (0,0).
    rot = page.rotation
    derot = page.derotation_matrix
    derot_img = _derotation_with_origin(page)
    disp_rect = placement.rect()

    page.insert_image(
        disp_rect * derot_img,
        stream=stamp.png_bytes,
        keep_proportion=True,
        rotate=rot,
        overlay=True,
    )

    d = placement.diameter_pt

    # Caption under the circle (e.g. "FOR STRUCTURAL ITEMS ONLY"), sized so its
    # width matches the seal diameter. Drawn with insert_text (point/baseline) --
    # not insert_textbox -- because a textbox sized snugly to the text can
    # silently overflow and draw nothing; insert_text always draws.
    if settings.bottom_text:
        text = settings.bottom_text
        unit = fitz.get_text_length(text, fontname=_CAPTION_FONT, fontsize=1.0)
        if unit > 0:
            # Size to span the seal width, but cap the height so a short caption
            # doesn't blow up to a giant font (it just ends up narrower instead).
            fs_cap = min((d * BOTTOM_TEXT_WIDTH_FRAC) / unit,
                         d * BOTTOM_TEXT_MAX_HEIGHT_FRAC)
            text_w = unit * fs_cap
            cap_x = disp_rect.x0 + (d - text_w) / 2.0          # centre under seal
            cap_y = disp_rect.y1 + d * BOTTOM_TEXT_GAP_FRAC + fs_cap  # baseline
            page.insert_text(
                fitz.Point(cap_x, cap_y) * derot,
                text,
                fontsize=fs_cap,
                fontname=_CAPTION_FONT,
                color=settings.bottom_text_color,
                rotate=rot,
                overlay=True,
            )

    if not date_str:
        return

    # Date sits in the seal's top hole, centred horizontally. A generously
    # sized textbox (so it never silently overflows) is rotated to match.
    unit = fitz.get_text_length(date_str, fontname="helv", fontsize=1.0)
    fs = min(settings.date_font_pt, d * 0.88 / max(unit, 1.0), d * 0.2)
    cx = disp_rect.x0 + DATE_REL_X * d
    cy = disp_rect.y0 + DATE_REL_Y * d
    half_w = d * 0.45
    box = fitz.Rect(cx - half_w, cy - fs * 0.75, cx + half_w, cy + fs * 1.25)
    page.insert_textbox(
        box * derot,
        date_str,
        fontsize=fs,
        fontname="helv",
        color=settings.date_color,
        align=fitz.TEXT_ALIGN_CENTER,
        rotate=rot,
        overlay=True,
    )


def apply_placements(doc: "fitz.Document", placements: list[Placement],
                     stamp: StampAsset, date_str: str,
                     settings: Settings) -> None:
    """Mutate *doc* in place, stamping every placement."""
    for p in placements:
        page = doc[p.page_index]
        _insert_one(page, p, stamp, date_str, settings)


def _flatten_doc(doc: "fitz.Document", dpi: int) -> "fitz.Document":
    """Return a new document where every page is a single rasterised image.

    Each page (with the seal/date/caption already applied) is rendered to a
    pixmap at *dpi* in display space and placed on a fresh, unrotated page of the
    same visible size. The result has no selectable text or movable overlays —
    the stamp is permanently baked in.
    """
    out = fitz.open()
    for page in doc:
        scale = dpi / 72.0
        w_pt, h_pt = page.rect.width, page.rect.height
        # Cap resolution on very large sheets (E-size 36x48 in at 300 DPI is a
        # ~150 MP / ~450 MB pixmap) so flattening can't exhaust memory. Lower the
        # effective DPI just enough to stay under the ceiling; normal sheets are
        # unaffected.
        pixels = (w_pt * scale) * (h_pt * scale)
        if pixels > _FLATTEN_MAX_PIXELS:
            scale *= (_FLATTEN_MAX_PIXELS / pixels) ** 0.5
        mat = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        new_page = out.new_page(width=w_pt, height=h_pt)
        new_page.insert_image(new_page.rect, pixmap=pix)
    return out


def render_stamped_pdf(source_pdf: bytes, placements: list[Placement],
                       stamp: StampAsset, date_str: str,
                       settings: Settings) -> bytes:
    """Return a stamped copy of *source_pdf* (original is untouched).

    Default: the seal is an overlay image and the date/caption real text, with
    the original vector/raster content untouched (full quality). If
    ``settings.flatten_output`` is set, every page is instead rasterised at
    ``settings.flatten_dpi`` so the stamp is permanently baked in.
    """
    doc = fitz.open(stream=source_pdf, filetype="pdf")
    try:
        apply_placements(doc, placements, stamp, date_str, settings)
        if settings.flatten_output:
            flat = _flatten_doc(doc, settings.flatten_dpi)
            try:
                out = BytesIO()
                flat.save(out, garbage=3, deflate=True)
                return out.getvalue()
            finally:
                flat.close()
        out = BytesIO()
        # garbage=3 de-duplicates objects (so the seal image is stored once and
        # shared across pages); deflate compresses losslessly. We deliberately do
        # *not* pass clean=True: it rewrites every existing content stream, which
        # is both far slower (seconds per heavy sheet) and contrary to leaving the
        # original vector/raster content untouched.
        doc.save(out, garbage=3, deflate=True)
        return out.getvalue()
    finally:
        doc.close()
