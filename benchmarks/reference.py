"""Analysis from main at 1ccaffa, retained only for repeatable comparisons.

The placement/search/output logic is shared with production. Only the old
render-buffer copy and integral-image construction are reproduced here.
"""
import fitz
import numpy as np

from stamper.occupancy import PageOccupancy
from stamper.placement import place_one_page


def integral_image(mask):
    out = np.zeros((mask.shape[0] + 1, mask.shape[1] + 1), dtype=np.uint32)
    out[1:, 1:] = mask.cumsum(axis=0, dtype=np.uint32).cumsum(axis=1, dtype=np.uint32)
    return out


def analyze_page(page, settings):
    scale = settings.analysis_dpi / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), colorspace=fitz.csGRAY, alpha=False)
    gray = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    ink = gray < settings.ink_threshold
    integral = integral_image(ink)
    return PageOccupancy(ink, integral, scale, page.rect.width, page.rect.height)


def compute_placements(doc, settings):
    placements = [place_one_page(page, i, settings, occ=analyze_page(page, settings))
                  for i, page in enumerate(doc)]
    placements.sort(key=lambda p: p.coverage, reverse=True)
    return placements
