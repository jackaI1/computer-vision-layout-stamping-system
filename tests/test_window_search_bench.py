"""The benchmark gate: a slow timing fails, an accurate run passes, and the report is checked."""
import json

import numpy as np
import pytest

from benchmarks import window_search_bench as wb
from stamper import window_search as ws
from stamper.config import Settings
from stamper.occupancy import PageOccupancy, _integral_image


def _report(rows):
    return {"results": [{"backend": b, "batch": n, "median_ms": ms, "pages_per_second": 1.0}
                        for b, n, ms in rows]}


THRESHOLDS = {"max_median_ms": {"numpy": {"1": 10, "4": 40}, "torch": {"1": 20}}}


def test_check_passes_when_every_timing_is_under_its_threshold():
    assert wb.check(_report([("numpy", 1, 9.9), ("numpy", 4, 40.0), ("torch", 1, 3.0)]), THRESHOLDS) == []


def test_check_fails_each_timing_above_its_threshold():
    problems = wb.check(_report([("numpy", 1, 10.5), ("torch", 1, 25.0), ("numpy", 4, 39.0)]), THRESHOLDS)
    assert len(problems) == 2
    assert "numpy batch 1" in problems[0] and "torch batch 1" in problems[1]


def test_backends_or_batches_without_a_threshold_are_not_gated():
    assert wb.check(_report([("triton", 16, 9999.0), ("numpy", 16, 9999.0)]), THRESHOLDS) == []


def test_committed_thresholds_cover_every_backend_and_batch_size():
    data = json.loads(wb.Path("benchmarks/window_search_thresholds.json").read_text())["max_median_ms"]
    for backend in ("numpy", "torch", "triton"):
        assert sorted(int(n) for n in data[backend]) == sorted(wb.BATCH_SIZES)


def test_benchmark_run_checks_equivalence_on_small_pages(tmp_path):
    rng = np.random.default_rng(1)
    pages = []
    for density in (0.0, 0.05, 0.4):
        ink = rng.random((400, 420)) < density
        pages.append(PageOccupancy(ink=ink, integral=_integral_image(ink), scale=1.0,
                                   width_pt=420, height_pt=400))
    report = wb.run(pages, repeats=1, batch_sizes=(1, 3))
    assert {row["batch"] for row in report["results"]} == {1, 3}
    assert all(row["median_ms"] >= 0 for row in report["results"])
    assert "numpy" in {row["backend"] for row in report["results"]}


def test_run_fails_loudly_when_a_backend_disagrees(monkeypatch):
    rng = np.random.default_rng(2)
    ink = rng.random((400, 400)) < 0.1
    pages = [PageOccupancy(ink=ink, integral=_integral_image(ink), scale=1.0,
                           width_pt=400, height_pt=400)]
    assert wb.ws.find_min_ink_spots(pages, 100.0, Settings())[0] is not None
    real = ws.find_min_ink_spots

    def wrong(occs, *args, **kwargs):
        spots = real(occs, *args, **kwargs)
        return [None for _ in spots] if kwargs.get("backend") == "numpy" else spots

    monkeypatch.setattr(wb, "available_backends", lambda: ["numpy"])
    monkeypatch.setattr(wb.ws, "find_min_ink_spots", wrong)
    with pytest.raises(AssertionError, match="disagrees"):
        wb.run(pages, repeats=1, batch_sizes=(1,))
