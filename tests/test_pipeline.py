"""End-to-end contracts using generated drawings and seals only."""
from io import BytesIO

import fitz
import numpy as np
import pytest
from PIL import Image, ImageDraw

from examples.make_sample_sheet import build_cover, build_notes
from stamper.config import Settings
from stamper.engineer_box import derive_box, find_engineer_label
from stamper.occupancy import analyze_page
from stamper.pdf_writer import render_stamped_pdf
from stamper.placement import (
    Placement, compute_placements, place_one_page, placement_in_keepout,
    sanitize_placements,
)
from stamper.preview import compose_preview, render_base_page
from stamper.stamp_image import load_stamp_from_bytes


@pytest.fixture
def seal():
    image = Image.new('RGB', (100, 100), 'white')
    ImageDraw.Draw(image).ellipse((5, 5, 94, 94), outline='blue', width=3)
    out = BytesIO()
    image.save(out, format='PNG')
    return load_stamp_from_bytes(out.getvalue())


def test_cover_detects_and_fits_designated_cell_despite_keepout():
    with fitz.open() as doc:
        build_cover(doc)
        settings = Settings(keepout_height_frac=.5)
        p = compute_placements(doc, settings)[0]
        assert p.source == 'engineer_box'
        assert 2020 < p.rect().x0 < p.rect().x1 < 2532
        assert 690 < p.rect().y0 < p.rect().y1 < 1010
        assert p.diameter_pt == pytest.approx(230.4)
        assert p.coverage == 0
        assert placement_in_keepout(p, settings)
        fixed, relocated = sanitize_placements(doc, {0: p}, settings)
        assert not relocated and fixed[0] == p


def test_notes_falls_back_to_whitespace_and_reports_real_ink():
    with fitz.open() as doc:
        build_notes(doc)
        p = compute_placements(doc, Settings())[0]
        assert p.source == 'whitespace'
        assert not placement_in_keepout(p, Settings())
        assert 0 < p.coverage < .01


def test_every_page_is_placed_and_sorted_riskiest_first():
    with fitz.open() as doc:
        doc.new_page(width=400, height=400)
        page = doc.new_page(width=400, height=400)
        page.draw_rect(page.rect, color=None, fill=(0, 0, 0))
        ps = compute_placements(doc, Settings())
        assert [p.page_index for p in ps] == [1, 0]
        assert [p.coverage for p in ps] == [1, 0]


def test_sanitize_relocates_stale_auto_but_preserves_manual():
    with fitz.open() as doc:
        doc.new_page(width=600, height=600)
        doc.new_page(width=600, height=600)
        stale = Placement(0, 550, 50, 100, 'whitespace', 0, 600, 600)
        manual = Placement(1, 550, 50, 100, 'manual', 0, 600, 600)
        fixed, relocated = sanitize_placements(doc, {0: stale, 1: manual}, Settings())
        assert relocated == [0]
        assert not placement_in_keepout(fixed[0], Settings())
        assert fixed[1] == manual


def test_tiny_page_fallback_stays_outside_reserved_corner():
    with fitz.open() as doc:
        page = doc.new_page(width=100, height=100)
        p = place_one_page(page, 0, Settings(keepout_pad_in=0))
        assert page.rect.contains(p.rect())
        assert not placement_in_keepout(p, Settings(keepout_pad_in=0))


def test_fully_reserved_page_refuses_automatic_placement():
    with fitz.open() as doc:
        page = doc.new_page(width=100, height=100)
        with pytest.raises(ValueError, match='reserved'):
            place_one_page(page, 0, Settings())


def test_engineer_box_fallback_respects_analysis_scale():
    # No side rules: a 60pt-wide label falls back to 6pt padding each side.
    with fitz.open() as doc:
        page = doc.new_page(width=300, height=300)
        occ = analyze_page(page, Settings(analysis_dpi=144))
        box = derive_box(occ, (100, 20, 160, 30))
        assert box.box[0] == pytest.approx(97.0)
        assert box.box[2] == pytest.approx(163.0)


@pytest.mark.parametrize('label', ['ENGINEER STAMP', 'Engineering Stamp', "ENGINEER'S STAMP"])
def test_detects_common_stamp_box_labels(label):
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((50, 50), label)
        assert find_engineer_label(page) is not None


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
def test_pdf_overlay_preserves_content_and_upright_geometry(rotation, seal):
    with fitz.open() as doc:
        page = doc.new_page(width=400, height=500)
        page.insert_text((30, 30), 'SYNTHETIC SOURCE')
        page.draw_line((30, 60), (370, 60))
        page.set_rotation(rotation)
        source = doc.tobytes()
        original_streams = [doc.xref_stream(x) for x in page.get_contents()]
        pw, ph = page.rect.width, page.rect.height
        p = Placement(0, pw / 2, ph / 2, 100, 'manual', 0, pw, ph)
        stamped = render_stamped_pdf(source, [p], seal, '2026-10-19', Settings())
    with fitz.open(stream=stamped, filetype='pdf') as out:
        page = out[0]
        assert 'SYNTHETIC SOURCE' in page.get_text()
        assert '2026-10-19' in page.get_text()
        assert 'FOR STRUCTURAL ITEMS ONLY' in page.get_text()
        streams = [out.xref_stream(x) for x in page.get_contents()]
        assert all(s in streams for s in original_streams)
        assert len(page.get_drawings()) == 1
        image = page.get_image_info()[0]
        rect = fitz.Rect(image['bbox']) * page.rotation_matrix
        assert tuple(rect) == pytest.approx(tuple(p.rect()), abs=.01)
        assert image['width'] == seal.width
        assert image['height'] == seal.height


def test_small_seal_date_is_not_silently_dropped(seal):
    with fitz.open() as doc:
        doc.new_page(width=300, height=300)
        source = doc.tobytes()
    p = Placement(0, 150, 150, 57.6, 'manual', 0, 300, 300)
    data = render_stamped_pdf(source, [p], seal, '2026-10-19', Settings(date_font_pt=14))
    with fitz.open(stream=data, filetype='pdf') as out:
        assert '2026-10-19' in out[0].get_text()


def test_removal_leaves_page_unstamped_and_flatten_is_optional(seal):
    with fitz.open() as doc:
        for _ in range(2):
            page = doc.new_page(width=300, height=300)
            page.insert_text((20, 30), 'SYNTHETIC SOURCE')
        source = doc.tobytes()
    p = Placement(0, 150, 150, 100, 'manual', 0, 300, 300)
    data = render_stamped_pdf(source, [p], seal, '2026-10-19', Settings())
    with fitz.open(stream=data, filetype='pdf') as out:
        assert len(out) == 2
        assert len(out[0].get_images()) == 1
        assert not out[1].get_images()
        assert '2026-10-19' not in out[1].get_text()
    flat = render_stamped_pdf(source, [p], seal, '2026-10-19', Settings(flatten_output=True))
    with fitz.open(stream=flat, filetype='pdf') as out:
        assert len(out) == 2
        assert all(not page.get_text() and len(page.get_images()) == 1 for page in out)


def test_preview_maps_clicks_and_removal_restores_source(seal):
    with fitz.open() as doc:
        page = doc.new_page(width=400, height=300)
        base, scale = render_base_page(page, 72)
    p = Placement(0, 200, 150, 100, 'manual', 0, 400, 300)
    s = Settings(preview_target_px=400)
    clean = compose_preview(base, scale, p, seal, '', s, draw_seal=False)
    preview = compose_preview(base, scale, p, seal, '', s)
    assert clean.pixel_to_point(200, 150) == (200, 150)
    assert clean.png_bytes != preview.png_bytes
    assert np.asarray(Image.open(BytesIO(clean.png_bytes))).min() == 255
    zoomed = compose_preview(base, scale, p, seal, '', s.with_overrides(preview_zoom=2))
    assert zoomed.pixel_to_point(200, 150) == (200, 150)


def test_analysis_failure_is_reported_instead_of_zero_coverage(monkeypatch):
    import stamper.placement as placement
    def unreadable_page(*args):
        raise RuntimeError('synthetic renderer failure')
    monkeypatch.setattr(placement, 'analyze_page', unreadable_page)
    with fitz.open() as doc:
        doc.new_page()
        with pytest.raises(ValueError, match='page 1.*synthetic renderer failure'):
            compute_placements(doc, Settings())


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
def test_nonzero_page_origin_keeps_overlay_at_display_position(rotation, seal):
    with fitz.open() as doc:
        page = doc.new_page(width=400, height=500)
        page.set_mediabox(fitz.Rect(100, 200, 500, 700))
        page.set_rotation(rotation)
        pw, ph = page.rect.width, page.rect.height
        p = Placement(0, pw / 2, ph / 2, 100, 'manual', 0, pw, ph)
        data = render_stamped_pdf(doc.tobytes(), [p], seal, '2026-10-19', Settings())
    with fitz.open(stream=data, filetype='pdf') as doc:
        page = doc[0]
        bbox = fitz.Rect(page.get_image_info()[0]['bbox']) * page.rotation_matrix
        assert tuple(bbox) == pytest.approx(tuple(p.rect()), abs=.01)
        assert '2026-10-19' in page.get_text()


def test_date_font_colour_and_caption_reach_pdf(seal):
    with fitz.open() as doc:
        doc.new_page(width=400, height=400)
        source = doc.tobytes()
    p = Placement(0, 200, 200, 160, 'manual', 0, 400, 400)
    settings = Settings(date_font_pt=12, date_color=(1, 0, 0), bottom_text='SYNTHETIC')
    data = render_stamped_pdf(source, [p], seal, '2026-10-19', settings)
    with fitz.open(stream=data, filetype='pdf') as doc:
        spans = [s for b in doc[0].get_text('dict')['blocks'] if 'lines' in b
                 for line in b['lines'] for s in line['spans']]
        date = next(s for s in spans if s['text'] == '2026-10-19')
        assert date['size'] == pytest.approx(12)
        assert date['color'] == 0xff0000
        assert any(s['text'] == 'SYNTHETIC' for s in spans)
    data = render_stamped_pdf(source, [p], seal, '', Settings(bottom_text=''))
    with fitz.open(stream=data, filetype='pdf') as doc:
        assert doc[0].get_text() == ''


def test_ten_sheet_set_is_stamped_on_every_page(seal):
    with fitz.open() as doc:
        for i in range(10):
            page = doc.new_page(width=400 + i * 5, height=300)
            page.insert_text((20, 30), f'SYNTHETIC SHEET {i + 1}')
            page.draw_line((20, 60), (380, 60))
        settings = Settings()
        placements = compute_placements(doc, settings)
        data = render_stamped_pdf(doc.tobytes(), placements, seal, '2026-10-19', settings)
    with fitz.open(stream=data, filetype='pdf') as out:
        assert len(out) == 10
        assert all(len(page.get_image_info()) == 1 and '2026-10-19' in page.get_text()
                   for page in out)


def test_original_raster_image_bytes_are_preserved(seal):
    image = Image.new('RGB', (31, 27), 'white')
    ImageDraw.Draw(image).line((0, 0, 30, 26), fill='red', width=2)
    raw = BytesIO()
    image.save(raw, format='JPEG')
    with fitz.open() as doc:
        page = doc.new_page(width=400, height=400)
        xref = page.insert_image(fitz.Rect(10, 10, 100, 100), stream=raw.getvalue())
        original = doc.extract_image(xref)['image']
        source = doc.tobytes()
    p = Placement(0, 250, 250, 100, 'manual', 0, 400, 400)
    data = render_stamped_pdf(source, [p], seal, '2026-10-19', Settings())
    with fitz.open(stream=data, filetype='pdf') as doc:
        original_xref = next(i[0] for i in doc[0].get_images() if i[2:4] == (31, 27))
        assert doc.extract_image(original_xref)['image'] == original


def test_sanitize_keeps_a_newly_detected_box_exempt_from_keepout():
    with fitz.open() as doc:
        build_cover(doc)
        settings = Settings(keepout_height_frac=.5)
        stale = Placement(0, 2400, 100, 136.8, 'whitespace', 0, 2592, 1728)
        fixed, relocated = sanitize_placements(doc, {0: stale}, settings)
        assert relocated == [0]
        assert fixed[0].source == 'engineer_box'
        assert fixed[0].center_x_pt == pytest.approx(2273.5)
