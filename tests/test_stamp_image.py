"""Seal preparation: the applied stamp must cover only its own ink."""
from io import BytesIO

import numpy as np
from PIL import Image, ImageDraw

from stamper.stamp_image import load_stamp_from_bytes


def _png(image: Image.Image) -> bytes:
    out = BytesIO()
    image.save(out, format='PNG')
    return out.getvalue()


def _ring(size=120, margin=10):
    image = Image.new('RGB', (size, size), 'white')
    ImageDraw.Draw(image).ellipse((margin, margin, size - margin, size - margin),
                                  outline='blue', width=4)
    return image


def _alpha(asset):
    return np.asarray(Image.open(BytesIO(asset.png_bytes)).convert('RGBA'))[:, :, 3]


def test_white_background_becomes_transparent_and_ink_is_kept():
    asset = load_stamp_from_bytes(_png(_ring()))
    alpha = _alpha(asset)
    assert alpha.max() == 255          # the ring survives
    assert alpha[alpha.shape[0] // 2, alpha.shape[1] // 2] == 0   # inside is clear
    assert alpha[0, 0] == 0            # corner background is clear


def test_transparent_margin_is_trimmed_so_the_ring_fills_the_frame():
    asset = load_stamp_from_bytes(_png(_ring(size=120, margin=30)))
    assert asset.width < 120 and asset.height < 120
    alpha = _alpha(asset)
    assert alpha[0].any() and alpha[-1].any()
    assert alpha[:, 0].any() and alpha[:, -1].any()


def test_edge_crop_artifact_lines_are_removed_but_the_seal_is_not_cut():
    clean = _ring()
    dirty = clean.copy()
    draw = ImageDraw.Draw(dirty)
    draw.line((119, 0, 119, 119), fill='black', width=2)   # scan artefact, right edge
    draw.line((0, 119, 119, 119), fill='black', width=2)   # scan artefact, bottom edge
    clean_asset = load_stamp_from_bytes(_png(clean))
    dirty_asset = load_stamp_from_bytes(_png(dirty))
    assert (dirty_asset.width, dirty_asset.height) == (clean_asset.width, clean_asset.height)


def test_digest_identifies_the_source_bytes():
    a = load_stamp_from_bytes(_png(_ring()))
    b = load_stamp_from_bytes(_png(_ring(margin=20)))
    assert a.digest != b.digest
    assert a.digest == load_stamp_from_bytes(_png(_ring())).digest
