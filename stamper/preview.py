"""Fast, in-memory previews of a placement.

The expensive part of a preview is rasterising the (often very heavy) drawing
page. So we do that **once per page** and cache the result; moving a seal then
only re-composites the cached image with PIL, which is effectively instant and
makes click/slider adjustments feel real-time.

A preview shows the whole page by default (``preview_zoom`` = 1.0) and can zoom
in toward the seal (larger ``preview_zoom``). It also returns the mapping needed
to convert a click on the preview back into page points.

All coordinates are in *display* space (the visually-upright page), matching the
analysis raster and the placement model. The seal image is already upright, so
no rotation is needed for the preview itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

import fitz
from PIL import Image, ImageDraw, ImageFont

from .config import (
    Settings,
    DATE_REL_X,
    DATE_REL_Y,
    BOTTOM_TEXT_GAP_FRAC,
    BOTTOM_TEXT_WIDTH_FRAC,
    BOTTOM_TEXT_MAX_HEIGHT_FRAC,
)
from .placement import Placement
from .stamp_image import StampAsset, stamp_pil


@dataclass
class PreviewResult:
    png_bytes: bytes
    # Mapping from preview pixel -> page point: page = origin + pixel / zoom.
    origin_x_pt: float
    origin_y_pt: float
    zoom: float          # preview pixels per point
    width_px: int
    height_px: int

    def pixel_to_point(self, px: float, py: float) -> tuple[float, float]:
        return (self.origin_x_pt + px / self.zoom,
                self.origin_y_pt + py / self.zoom)


def render_base_page(page: "fitz.Page", dpi: int) -> tuple[Image.Image, float]:
    """Rasterise the whole (upright) page once. Returns (image, px_per_pt).

    Pure function -- the app layer caches it by (pdf, page, dpi).
    """
    scale = dpi / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    # Keep the cached base image as RGB; only the small cropped preview is
    # promoted to RGBA (for alpha-compositing the seal), which avoids holding a
    # full-page 4-channel raster in the cache.
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    return img, scale


def _load_font(size_px: float) -> ImageFont.FreeTypeFont:
    # Use the true (zoom-scaled) size with only a 1px floor. A larger floor stops
    # the text shrinking once it reaches that size, so at high zoom-out the date
    # renders oversized relative to the seal.
    size_px = max(1, int(round(size_px)))
    try:
        return ImageFont.load_default(size=size_px)  # scalable in Pillow >= 10.1
    except TypeError:  # pragma: no cover - very old Pillow
        return ImageFont.load_default()


def compose_preview(base_img: Image.Image, base_scale: float,
                    placement: Placement, stamp: StampAsset, date_str: str,
                    settings: Settings, draw_seal: bool = True) -> PreviewResult:
    """Crop the cached page image around the seal and paste seal + date.

    When ``draw_seal`` is False the surrounding page is shown *without* the seal
    -- used to preview a page whose stamp has been removed, so the operator can
    confirm it will go out clean.
    """
    target = settings.preview_target_px
    d = placement.diameter_pt
    cx, cy = placement.center_x_pt, placement.center_y_pt
    pw, ph = placement.page_width_pt, placement.page_height_pt

    # Zoom: 1.0 shows the whole page; larger zooms in toward the seal. The shown
    # window is the page scaled down by the zoom factor, centred on the seal and
    # clamped to the page so it never runs off an edge.
    z = max(1.0, settings.preview_zoom)
    win_w = pw / z
    win_h = ph / z
    x0 = min(max(cx - win_w / 2.0, 0.0), pw - win_w)
    y0 = min(max(cy - win_h / 2.0, 0.0), ph - win_h)
    x1 = x0 + win_w
    y1 = y0 + win_h

    # Crop the cached base image (base pixels).
    bx0, by0 = int(round(x0 * base_scale)), int(round(y0 * base_scale))
    bx1, by1 = int(round(x1 * base_scale)), int(round(y1 * base_scale))
    bx1, by1 = max(bx1, bx0 + 1), max(by1, by0 + 1)
    crop = base_img.crop((bx0, by0, bx1, by1))

    longest = max(crop.width, crop.height) or 1
    out_scale = target / longest
    crop = crop.resize(
        (max(1, round(crop.width * out_scale)), max(1, round(crop.height * out_scale))),
        Image.LANCZOS,
    ).convert("RGBA")

    zoom = base_scale * out_scale          # preview pixels per point
    origin_x_pt = bx0 / base_scale
    origin_y_pt = by0 / base_scale

    if not draw_seal:
        buf = BytesIO()
        crop.save(buf, format="PNG")
        return PreviewResult(
            png_bytes=buf.getvalue(),
            origin_x_pt=origin_x_pt,
            origin_y_pt=origin_y_pt,
            zoom=zoom,
            width_px=crop.width,
            height_px=crop.height,
        )

    # Paste the seal.
    seal_px = max(1, round(d * zoom))
    seal_img = stamp_pil(stamp).resize((seal_px, seal_px), Image.LANCZOS)
    seal_left = round((cx - d / 2 - origin_x_pt) * zoom)
    seal_top = round((cy - d / 2 - origin_y_pt) * zoom)
    crop.alpha_composite(seal_img, (seal_left, seal_top))
    draw = ImageDraw.Draw(crop)

    # Draw the date in the seal's top hole (approximation of the PDF text).
    # Mirror pdf_writer's anchor exactly so the preview tracks DATE_REL_X/Y if
    # they are changed in config.
    if date_str:
        font = _load_font(settings.date_font_pt * zoom)
        date_cx = (cx - d / 2 + DATE_REL_X * d - origin_x_pt) * zoom
        date_cy = (cy - d / 2 + DATE_REL_Y * d - origin_y_pt) * zoom
        color = tuple(int(c * 255) for c in settings.date_color)
        draw.text((date_cx, date_cy), date_str, font=font, fill=color, anchor="mm")

    # Caption under the seal, sized to span the seal width but height-capped so a
    # short caption stays small (mirrors pdf_writer).
    if settings.bottom_text:
        seal_px = d * zoom
        target_w = seal_px * BOTTOM_TEXT_WIDTH_FRAC
        ref = _load_font(20)
        ref_w = draw.textlength(settings.bottom_text, font=ref) or 1.0
        fs_cap_px = min(20 * target_w / ref_w, seal_px * BOTTOM_TEXT_MAX_HEIGHT_FRAC)
        cap_font = _load_font(max(6, round(fs_cap_px)))
        cap_cx = (cx - origin_x_pt) * zoom                                  # seal centre x
        cap_top = (cy + d / 2 + d * BOTTOM_TEXT_GAP_FRAC - origin_y_pt) * zoom
        color = tuple(int(c * 255) for c in settings.bottom_text_color)
        draw.text((cap_cx, cap_top), settings.bottom_text, font=cap_font,
                  fill=color, anchor="ma")

    buf = BytesIO()
    crop.save(buf, format="PNG")
    return PreviewResult(
        png_bytes=buf.getvalue(),
        origin_x_pt=origin_x_pt,
        origin_y_pt=origin_y_pt,
        zoom=zoom,
        width_px=crop.width,
        height_px=crop.height,
    )
