"""Tests for the whitespace/occupancy search.

Every fixture here is a synthetic ink mask built in-process. ``PageOccupancy`` is
a plain dataclass, so the whole search can be exercised without rasterising a
PDF -- which keeps these tests fast and free of any drawing data.
"""

import numpy as np
import pytest

from stamper import occupancy
from stamper.config import Settings


def make_occ(ink: np.ndarray, scale: float = 1.0) -> occupancy.PageOccupancy:
    """Build a PageOccupancy directly from a boolean ink mask."""
    ink = np.asarray(ink, dtype=bool)
    h, w = ink.shape
    return occupancy.PageOccupancy(
        ink=ink,
        integral=occupancy._integral_image(ink),
        scale=scale,
        width_pt=w / scale,
        height_pt=h / scale,
    )


def loose_settings(**overrides) -> Settings:
    """Settings with no page margins, so a small synthetic page is searchable."""
    base = Settings().with_overrides(
        margin_top_in=0.0,
        margin_bottom_in=0.0,
        margin_left_in=0.0,
        margin_right_in=0.0,
        search_step_pt=1.0,
    )
    return base.with_overrides(**overrides) if overrides else base


# --------------------------------------------------------------------------
# _integral_image
# --------------------------------------------------------------------------

def test_integral_image_shape_and_zero_border():
    mask = np.ones((4, 6), dtype=bool)
    I = occupancy._integral_image(mask)
    assert I.shape == (5, 7)
    assert np.all(I[0, :] == 0)
    assert np.all(I[:, 0] == 0)


def test_integral_image_matches_brute_force_cumulative_sum():
    rng = np.random.default_rng(20260813)
    mask = rng.random((9, 11)) < 0.4
    I = occupancy._integral_image(mask)
    for y in range(mask.shape[0] + 1):
        for x in range(mask.shape[1] + 1):
            assert I[y, x] == mask[:y, :x].sum()


def test_integral_image_of_empty_mask_is_all_zero():
    I = occupancy._integral_image(np.zeros((5, 5), dtype=bool))
    assert I.sum() == 0


# --------------------------------------------------------------------------
# _window_sums
# --------------------------------------------------------------------------

def test_window_sums_matches_brute_force():
    rng = np.random.default_rng(7)
    mask = rng.random((12, 12)) < 0.5
    I = occupancy._integral_image(mask)
    d = 4
    ys = np.arange(0, mask.shape[0] - d + 1, 3)
    xs = np.arange(0, mask.shape[1] - d + 1, 3)

    got = occupancy._window_sums(I, ys, xs, d)

    assert got.shape == (len(ys), len(xs))
    for i, y in enumerate(ys):
        for j, x in enumerate(xs):
            assert got[i, j] == mask[y:y + d, x:x + d].sum()


def test_window_sums_on_solid_mask_equals_window_area():
    mask = np.ones((10, 10), dtype=bool)
    I = occupancy._integral_image(mask)
    d = 3
    got = occupancy._window_sums(I, np.array([0, 5]), np.array([0, 5]), d)
    assert np.all(got == d * d)


# --------------------------------------------------------------------------
# find_min_ink_spot
# --------------------------------------------------------------------------

def test_finds_the_blank_half_of_a_half_inked_page():
    ink = np.zeros((100, 100), dtype=bool)
    ink[:, :50] = True                      # left half solid ink
    spot = occupancy.find_min_ink_spot(make_occ(ink), 10.0, loose_settings())

    assert spot is not None
    assert spot.center_x_pt > 50.0          # landed in the blank right half
    assert spot.coverage == pytest.approx(0.0)


def test_reports_nonzero_coverage_when_every_position_has_ink():
    ink = np.ones((40, 40), dtype=bool)
    spot = occupancy.find_min_ink_spot(make_occ(ink), 8.0, loose_settings())

    assert spot is not None
    assert spot.coverage == pytest.approx(1.0)


def test_returns_none_when_the_seal_cannot_fit():
    ink = np.zeros((10, 10), dtype=bool)
    spot = occupancy.find_min_ink_spot(make_occ(ink), 50.0, loose_settings())
    assert spot is None


def test_keepout_rectangle_is_avoided():
    ink = np.zeros((100, 100), dtype=bool)
    # Force the "interesting" region to be inside the keep-out by inking
    # everything else, then confirm the search still refuses to go there.
    keepout = (60.0, 0.0, 100.0, 40.0)
    spot = occupancy.find_min_ink_spot(
        make_occ(ink), 10.0, loose_settings(), keepout_rects_pt=[keepout]
    )

    assert spot is not None
    kx0, ky0, kx1, ky1 = keepout
    half = 5.0
    overlaps = (spot.center_x_pt + half > kx0 and spot.center_x_pt - half < kx1
                and spot.center_y_pt + half > ky0 and spot.center_y_pt - half < ky1)
    assert not overlaps


def test_returns_none_when_keepout_covers_every_candidate():
    ink = np.zeros((30, 30), dtype=bool)
    spot = occupancy.find_min_ink_spot(
        make_occ(ink), 5.0, loose_settings(),
        keepout_rects_pt=[(-100.0, -100.0, 200.0, 200.0)],
    )
    assert spot is None


def test_bounds_restrict_the_search_region():
    ink = np.zeros((100, 100), dtype=bool)
    spot = occupancy.find_min_ink_spot(
        make_occ(ink), 6.0, loose_settings(), bounds_pt=(10.0, 10.0, 30.0, 30.0)
    )

    assert spot is not None
    assert 10.0 <= spot.center_x_pt <= 30.0
    assert 10.0 <= spot.center_y_pt <= 30.0


def test_clearance_tiebreak_pulls_the_seal_off_the_page_edge():
    """On a blank page every position ties at zero ink. With the tie-break on,
    the seal should sit away from the margin rather than at the first candidate."""
    ink = np.zeros((100, 100), dtype=bool)
    occ = make_occ(ink)

    centred = occupancy.find_min_ink_spot(
        occ, 10.0, loose_settings(maximize_clearance=True))
    first_found = occupancy.find_min_ink_spot(
        occ, 10.0, loose_settings(maximize_clearance=False))

    assert centred is not None and first_found is not None
    # The no-tie-break path takes argmin, i.e. the top-left-most candidate.
    assert first_found.center_x_pt == pytest.approx(5.0)
    assert first_found.center_y_pt == pytest.approx(5.0)
    # The clearance path must not hug that corner.
    assert centred.center_x_pt > first_found.center_x_pt
    assert centred.center_y_pt > first_found.center_y_pt


def test_scale_is_honoured_when_converting_pixels_to_points():
    ink = np.zeros((200, 200), dtype=bool)
    occ = make_occ(ink, scale=2.0)          # 2 analysis px per point
    spot = occupancy.find_min_ink_spot(occ, 10.0, loose_settings())

    assert spot is not None
    # The page is 100 x 100 pt at this scale, so the centre must stay inside it.
    assert 0.0 <= spot.center_x_pt <= 100.0
    assert 0.0 <= spot.center_y_pt <= 100.0


# --------------------------------------------------------------------------
# disk_coverage
# --------------------------------------------------------------------------

def test_disk_coverage_is_one_on_solid_ink():
    occ = make_occ(np.ones((60, 60), dtype=bool))
    assert occupancy.disk_coverage(occ, 30.0, 30.0, 20.0) == pytest.approx(1.0)


def test_disk_coverage_is_zero_on_a_blank_page():
    occ = make_occ(np.zeros((60, 60), dtype=bool))
    assert occupancy.disk_coverage(occ, 30.0, 30.0, 20.0) == pytest.approx(0.0)


def test_disk_coverage_is_zero_when_the_disk_falls_off_the_page():
    occ = make_occ(np.ones((60, 60), dtype=bool))
    assert occupancy.disk_coverage(occ, -100.0, -100.0, 10.0) == pytest.approx(0.0)


def test_disk_coverage_is_about_half_when_ink_covers_half_the_disk():
    ink = np.zeros((60, 60), dtype=bool)
    ink[:30, :] = True                      # top half inked
    occ = make_occ(ink)
    got = occupancy.disk_coverage(occ, 30.0, 30.0, 20.0)
    assert got == pytest.approx(0.5, abs=0.05)


def test_disk_coverage_is_stricter_than_the_square_search_estimate():
    """The search scores a square footprint; the report uses the exact circle.
    Ink parked in the square's corners must not count toward disk coverage."""
    ink = np.zeros((60, 60), dtype=bool)
    ink[20:23, 20:23] = True                # corner of the 20pt square at (30,30)
    occ = make_occ(ink)
    assert occupancy.disk_coverage(occ, 30.0, 30.0, 20.0) == pytest.approx(0.0)
