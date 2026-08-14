"""Load a seal image and prepare it for compositing.

The supplied seals are opaque RGB PNGs on a white background. Pasting that
white box on a drawing would needlessly hide content, so we knock out the
near-white background to transparency. The result is cached as PNG bytes ready
to hand to ``page.insert_image(stream=...)``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image

# Pixels at or above this luminance are treated as background and made
# transparent. High enough to keep anti-aliased gray edges of the ink.
_WHITE_CUTOFF = 240


@dataclass(frozen=True)
class StampAsset:
    """A seal ready to be placed.

    Attributes
    ----------
    png_bytes:
        RGBA PNG (white knocked out) suitable for ``insert_image``.
    width, height:
        Pixel dimensions of the trimmed seal.
    digest:
        Stable hash of the source bytes (used as a cache key).
    """

    png_bytes: bytes
    width: int
    height: int
    digest: str


def _make_white_transparent(img: Image.Image) -> Image.Image:
    rgba = np.asarray(img.convert("RGBA")).copy()
    rgb = rgba[:, :, :3].astype(np.int16)
    # Background = all channels bright (near white).
    is_bg = np.all(rgb >= _WHITE_CUTOFF, axis=2)
    rgba[is_bg, 3] = 0
    return Image.fromarray(rgba, "RGBA")


def _strip_border_lines(img: Image.Image, *, threshold: float = 0.85,
                        max_depth: int = 8) -> Image.Image:
    """Peel off spurious solid lines that run along the very edge of a scan/crop.

    A correctly-cropped circular seal only touches each image edge along a short
    tangent arc, so after the white knockout an outer row/column is almost
    entirely transparent. A crop artifact (a 1–2 px line straight down an edge —
    e.g. one seal arrived with a black line on its right and bottom) instead
    leaves that whole row/column opaque. We remove any outer row/column that is
    nearly all opaque, up to ``max_depth`` px per edge, stopping at the first
    clean line so the seal itself is never cut.
    """
    alpha = np.asarray(img.convert("RGBA"))[:, :, 3] > 0
    h, w = alpha.shape
    top, bottom, left, right = 0, h, 0, w
    for _ in range(max_depth):
        if bottom - top <= 1 or right - left <= 1:
            break
        if alpha[top, left:right].mean() > threshold:
            top += 1
        elif alpha[bottom - 1, left:right].mean() > threshold:
            bottom -= 1
        elif alpha[top:bottom, left].mean() > threshold:
            left += 1
        elif alpha[top:bottom, right - 1].mean() > threshold:
            right -= 1
        else:
            break
    if (top, left, bottom, right) == (0, 0, h, w):
        return img
    return img.crop((left, top, right, bottom))


def _trim_transparent(img: Image.Image) -> Image.Image:
    """Crop to the non-transparent bounding box so the disk fills the frame."""
    alpha = np.asarray(img)[:, :, 3]
    ys, xs = np.where(alpha > 0)
    if len(xs) == 0:
        return img
    return img.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))


def load_stamp_from_bytes(raw: bytes) -> StampAsset:
    digest = hashlib.sha256(raw).hexdigest()
    return _build_asset(raw, digest)


@lru_cache(maxsize=16)
def _build_asset(raw: bytes, digest: str) -> StampAsset:
    img = Image.open(BytesIO(raw))
    img = _make_white_transparent(img)
    img = _strip_border_lines(img)
    img = _trim_transparent(img)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return StampAsset(buf.getvalue(), img.width, img.height, digest)


def load_stamp(path: str | Path) -> StampAsset:
    raw = Path(path).read_bytes()
    return load_stamp_from_bytes(raw)


@lru_cache(maxsize=8)
def _pil_for_digest(digest: str, png_bytes: bytes) -> Image.Image:
    return Image.open(BytesIO(png_bytes)).convert("RGBA")


def stamp_pil(asset: StampAsset) -> Image.Image:
    """Return the prepared (white-knocked-out) seal as an RGBA PIL image.

    Used for fast in-memory preview compositing; cached by content digest.
    """
    return _pil_for_digest(asset.digest, asset.png_bytes)
