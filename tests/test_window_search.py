"""Batch page search matches the reference search on every backend, including edge cases.

The Triton kernel runs here only when ``TRITON_INTERPRET=1`` is set (the Python
interpreter for Triton, no GPU needed). CI sets that variable and also sets
``WINDOW_SEARCH_REQUIRE_TRITON=1``, so a missing Triton install fails the job
instead of skipping the kernel tests.
"""
import os

import fitz
import numpy as np
import pytest

from stamper import window_search as ws
from stamper.config import Settings
from stamper.occupancy import PageOccupancy, _integral_image, analyze_page, find_min_ink_spot

REQUIRE_TRITON = os.environ.get("WINDOW_SEARCH_REQUIRE_TRITON") == "1"
HAS_TORCH = ws._torch() is not None
TRITON_READY = ws.triton_available()
if REQUIRE_TRITON:
    assert TRITON_READY, "WINDOW_SEARCH_REQUIRE_TRITON=1 but Triton cannot run"

BACKENDS = [
    "numpy",
    pytest.param("torch", marks=pytest.mark.skipif(not HAS_TORCH, reason="torch not installed")),
    pytest.param("triton", marks=pytest.mark.skipif(not TRITON_READY, reason="Triton not runnable")),
]


def make_occ(ink, scale=1.0):
    ink = np.asarray(ink, dtype=bool)
    h, w = ink.shape
    return PageOccupancy(ink=ink, integral=_integral_image(ink), scale=scale,
                         width_pt=w / scale, height_pt=h / scale)


def random_pages(seed, count, shape, densities):
    rng = np.random.default_rng(seed)
    return [make_occ(rng.random(shape) < densities[i % len(densities)]) for i in range(count)]


def fine_settings(**kw):
    return Settings(search_step_pt=kw.pop("search_step_pt", 4.0), **kw)


def reference(occs, diameter_pt, settings, keepouts=None, bounds=None):
    keepouts = keepouts or [None] * len(occs)
    return [find_min_ink_spot(o, diameter_pt, settings, keepouts[i], bounds)
            for i, o in enumerate(occs)]


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize("maximize_clearance", [True, False])
def test_random_pages_match_reference(backend, maximize_clearance):
    settings = fine_settings(maximize_clearance=maximize_clearance)
    occs = random_pages(7, 9, (120, 160), densities=[0.0, 0.01, 0.05, 0.3, 0.7])
    keepouts = [None, [(10, 10, 60, 60)], [(0, 0, 200, 200)], None, [(40, 20, 90, 110), (5, 90, 30, 140)],
                None, None, [(70, 30, 150, 80)], None]
    expected = reference(occs, 30.0, settings, keepouts)
    got = ws.find_min_ink_spots(occs, 30.0, settings, keepouts, backend=backend)
    assert got == expected


@pytest.mark.parametrize("backend", BACKENDS)
def test_blank_page_matches_reference_and_uses_open_space(backend):
    settings = fine_settings()
    blank = make_occ(np.zeros((100, 140), dtype=bool))
    expected = reference([blank], 24.0, settings)
    got = ws.find_min_ink_spots([blank], 24.0, settings, backend=backend)
    assert got == expected
    assert got[0].coverage == 0.0


@pytest.mark.parametrize("backend", BACKENDS)
def test_full_ink_page_matches_reference_and_reports_full_coverage(backend):
    settings = fine_settings()
    full = make_occ(np.ones((90, 90), dtype=bool))
    expected = reference([full], 20.0, settings)
    got = ws.find_min_ink_spots([full], 20.0, settings, backend=backend)
    assert got == expected
    assert got[0].coverage == 1.0


@pytest.mark.parametrize("backend", BACKENDS)
def test_page_too_small_or_fully_blocked_returns_none(backend):
    settings = fine_settings()
    small = make_occ(np.zeros((10, 10), dtype=bool))
    roomy = make_occ(np.zeros((100, 100), dtype=bool))
    got = ws.find_min_ink_spots([small, roomy], 50.0, settings,
                                keepouts=[None, [(0, 0, 100, 100)]], backend=backend)
    assert got == [None, None]
    assert got == reference([small, roomy], 50.0, settings,
                            keepouts=[None, [(0, 0, 100, 100)]])


@pytest.mark.parametrize("backend", BACKENDS)
def test_bounds_restrict_every_page(backend):
    settings = fine_settings()
    occs = random_pages(3, 4, (110, 130), densities=[0.02, 0.4])
    bounds = (20.0, 30.0, 80.0, 90.0)
    expected = reference(occs, 18.0, settings, bounds=bounds)
    got = ws.find_min_ink_spots(occs, 18.0, settings, bounds_pt=bounds, backend=backend)
    assert got == expected
    for spot in got:
        assert spot is None or (20 <= spot.center_x_pt <= 80 and 30 <= spot.center_y_pt <= 90)


@pytest.mark.parametrize("backend", BACKENDS)
def test_mixed_page_sizes_are_grouped_and_keep_input_order(backend):
    settings = fine_settings()
    a = random_pages(11, 3, (80, 100), densities=[0.1])
    b = random_pages(12, 3, (60, 150), densities=[0.1])
    occs = [a[0], b[0], a[1], b[1], a[2], b[2]]
    expected = reference(occs, 16.0, settings)
    assert ws.find_min_ink_spots(occs, 16.0, settings, backend=backend) == expected


@pytest.mark.parametrize("backend", BACKENDS)
def test_scale_is_honoured(backend):
    # Pages rendered at 2x: the grid, footprint and centres must all scale together.
    settings = fine_settings()
    rng = np.random.default_rng(5)
    occs = [make_occ(rng.random((160, 200)) < 0.05, scale=2.0) for _ in range(3)]
    assert ws.find_min_ink_spots(occs, 25.0, settings, backend=backend) == reference(occs, 25.0, settings)


def test_empty_batch_and_bad_inputs():
    settings = fine_settings()
    assert ws.find_min_ink_spots([], 20.0, settings, backend="numpy") == []
    with pytest.raises(ValueError, match="unknown backend"):
        ws.find_min_ink_spots([], 20.0, settings, backend="cuda-please")
    with pytest.raises(ValueError, match="one entry per page"):
        ws.find_min_ink_spots(random_pages(1, 2, (50, 50), [0.1]), 10.0, settings, keepouts=[None])


def test_auto_uses_reference_when_torch_is_missing(monkeypatch):
    monkeypatch.setattr(ws, "_torch", lambda: None)
    assert ws.resolve_backend("auto") == "numpy"
    settings = fine_settings()
    occs = random_pages(2, 3, (70, 90), [0.05])
    assert ws.find_min_ink_spots(occs, 14.0, settings) == reference(occs, 14.0, settings)


def test_resolve_backend_auto_is_never_the_interpreter_or_torch_on_cpu(monkeypatch):
    # Without CUDA the interpreter is far too slow, and the NumPy reference is faster
    # than the PyTorch CPU path, so auto must choose NumPy.
    monkeypatch.setattr(ws, "cuda_available", lambda: False)
    monkeypatch.setenv("TRITON_INTERPRET", "1")
    assert ws.resolve_backend("auto") == "numpy"
    monkeypatch.setattr(ws, "cuda_available", lambda: True)
    monkeypatch.setattr(ws, "triton_available", lambda: True)
    assert ws.resolve_backend("auto") == "triton"


def test_real_rendered_page_matches_reference(tmp_path):
    path = tmp_path / "page.pdf"
    with fitz.open() as doc:
        page = doc.new_page(width=612, height=792)
        for y in range(80, 700, 40):
            page.draw_line((60, y), (520, y + 6), color=(0, 0, 0), width=1.2)
        page.draw_rect(fitz.Rect(380, 620, 560, 740), color=(0, 0, 0), width=2)
        doc.save(path)
    settings = Settings()
    with fitz.open(path) as doc:
        occ = analyze_page(doc[0], settings)
    diameter = settings.stamp_diameter_in * 72
    expected = find_min_ink_spot(occ, diameter, settings)
    for backend in ("numpy", "torch", "triton"):
        if (backend == "torch" and not HAS_TORCH) or (backend == "triton" and not TRITON_READY):
            continue
        assert ws.find_min_ink_spots([occ], diameter, settings, backend=backend) == [expected]
