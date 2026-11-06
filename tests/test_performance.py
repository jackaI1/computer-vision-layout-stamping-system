"""Correctness, cache ownership and a generous large-drawing time budget."""
from contextlib import ExitStack
from statistics import median
from time import perf_counter

import fitz
import numpy as np
import pytest

from benchmarks import reference
from benchmarks.drawings import make_drawings, make_seal
from stamper import occupancy
from stamper.config import Settings
from stamper.placement import compute_placements
from stamper.pdf_writer import render_stamped_pdf


@pytest.mark.parametrize("shape", [(0, 0), (0, 7), (7, 0), (1, 1), (83, 97)])
def test_integral_exactly_matches_reference(shape):
    mask = np.random.default_rng(47).random(shape) < .7
    np.testing.assert_array_equal(occupancy._integral_image(mask), reference.integral_image(mask))
    np.testing.assert_array_equal(occupancy._integral_image(mask.T), reference.integral_image(mask.T))


def test_integral_large_counts_and_strided_input():
    mask = np.ones((900, 1200), dtype=bool)[:, ::2]
    result = occupancy._integral_image(mask)
    assert result.dtype == np.uint32
    assert result[-1, -1] == 540000
    np.testing.assert_array_equal(result, reference.integral_image(mask))


def test_cache_reuses_analysis_only_when_raster_inputs_match(monkeypatch):
    calls = []
    original = occupancy.analyze_page
    def analyze(page, settings):
        calls.append((page.number, settings.analysis_dpi, settings.ink_threshold))
        return original(page, settings)
    monkeypatch.setattr(occupancy, 'analyze_page', analyze)
    with fitz.open() as doc:
        doc.new_page(width=320, height=300)
        doc.new_page(width=320, height=300)
        cache = occupancy.PageAnalysisCache(doc)
        settings = Settings()
        first = cache.get(0, settings)
        assert cache.get(0, settings.with_overrides(stamp_diameter_in=2.1, margin_left_in=.8, preview_dpi=144)) is first
        assert not first.ink.flags.writeable and not first.integral.flags.writeable
        cache.get(1, settings)
        cache.get(0, settings.with_overrides(ink_threshold=90))
        cache.get(0, settings.with_overrides(analysis_dpi=144))
        assert len(calls) == 4
        cache.clear()
        assert cache.retained_bytes == 0
        assert cache.get(0, settings) is not first


def test_cache_lru_eviction_oversize_and_document_ownership():
    with fitz.open() as doc, fitz.open() as other:
        for _ in range(3):
            doc.new_page(width=100, height=100)
        other.new_page(width=100, height=100)
        size = 10000 + 101 * 101 * 4
        cache = occupancy.PageAnalysisCache(doc, max_bytes=2 * size)
        first = cache.get(0, Settings())
        second = cache.get(1, Settings())
        assert cache.get(0, Settings()) is first  # page 1 becomes oldest
        cache.get(2, Settings())
        assert cache.retained_bytes == 2 * size
        assert cache.get(1, Settings()) is not second
        assert cache.retained_bytes <= cache.max_bytes
        tiny = occupancy.PageAnalysisCache(doc, max_bytes=1)
        assert tiny.get(0, Settings()) is not tiny.get(0, Settings())
        assert tiny.retained_bytes == 0
        with pytest.raises(ValueError, match='different document'):
            compute_placements(other, Settings(), analysis_cache=cache)
        with pytest.raises(ValueError, match='nonnegative'):
            occupancy.PageAnalysisCache(doc, max_bytes=-1)
        cache.clear()
    with pytest.raises(ValueError, match='closed'):
        cache.get(0, Settings())


def test_cache_clear_after_document_edit():
    with fitz.open() as doc:
        page = doc.new_page(width=100, height=100)
        cache = occupancy.PageAnalysisCache(doc)
        before = cache.get(0, Settings())
        page.draw_rect(page.rect, color=(0, 0, 0), fill=(0, 0, 0))
        cache.clear()  # immutable-upload contract: an editor invalidates explicitly
        after = cache.get(0, Settings())
        assert not before.ink.any()
        assert after.ink.all()


def test_large_drawing_pipeline_matches_reference_and_time_budget(tmp_path):
    paths = make_drawings(tmp_path)
    stamp = make_seal()
    settings = Settings()
    with ExitStack() as stack:
        docs = [stack.enter_context(fitz.open(path)) for path in paths]
        caches = [occupancy.PageAnalysisCache(doc) for doc in docs]
        elapsed = []
        for repeat in range(3):
            # Measure a cold pass, not just a cache lookup, including PDF output.
            for cache in caches:
                cache.clear()
            start = perf_counter()
            results = [compute_placements(doc, settings, analysis_cache=cache) for doc, cache in zip(docs, caches)]
            outputs = [render_stamped_pdf(path.read_bytes(), placements, stamp, '2026-11-05', settings)
                       for path, placements in zip(paths, results)]
            elapsed.append(perf_counter() - start)
        assert median(elapsed) < 5.0, f'Four large sheets exceeded the 5s cold placement/export budget: {elapsed}'
        for doc, cache, result, data in zip(docs, caches, results, outputs):
            expected = reference.compute_placements(doc, settings)
            assert result == expected
            assert compute_placements(doc, settings, analysis_cache=cache) == expected
            with fitz.open(stream=data, filetype='pdf') as output:
                assert len(output) == len(doc)
                for page in output:
                    assert '2026-11-05' in page.get_text()
                    assert page.get_image_info()
            cache.clear()


def test_ui_automatic_and_manual_review_share_analysis(monkeypatch):
    import app
    app._analysis_cache.clear()
    app._auto_placements.clear()
    calls = []
    original = occupancy.analyze_page
    def analyze(page, settings):
        calls.append(page.number)
        return original(page, settings)
    monkeypatch.setattr(occupancy, 'analyze_page', analyze)
    with fitz.open() as doc:
        doc.new_page(width=400, height=400)
        data = doc.tobytes()
    fid = app._file_id(data)
    try:
        settings = Settings()
        app._auto_placements(fid, settings.cache_key(), 7, data, settings)
        app._occupancy(fid, 0, settings.cache_key(), data, settings)
        changed = settings.with_overrides(stamp_diameter_in=2.0)
        app._auto_placements(fid, changed.cache_key(), 7, data, changed)
        assert calls == [0]
    finally:
        app._analysis_cache(fid, data).clear()
        app._analysis_cache.clear()
        app._auto_placements.clear()
        app._open_doc(fid, data).close()
        app._open_doc.clear()
