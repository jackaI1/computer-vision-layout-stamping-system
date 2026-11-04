"""Physical PDF page size, sheet origin, viewport content and layer visibility."""
import ezdxf
import fitz
import numpy as np
import pytest
from ezdxf import xref

from stamper.cad_plot import plot_layouts
from stamper.cad_stamp import stamp_layouts
from tests.test_cad_stamp import seal_drawing, sheet_drawing


def ink(page, rect):
    pix = page.get_pixmap(clip=rect, colorspace=fitz.csGRAY)
    return np.count_nonzero(np.frombuffer(pix.samples, dtype=np.uint8) < 150)


@pytest.mark.parametrize('units,size,center,diameter', [('mm', (420, 297), (350, 180), 40), ('inch', (17, 11), (14, 7), 2)])
def test_pdf_preserves_paper_size_and_absolute_seal_position(units, size, center, diameter):
    doc = sheet_drawing(units)
    stamp_layouts(doc, seal_drawing(), ['A101', 'A102'], center=center, diameter=diameter)
    data = plot_layouts(doc, ['A101', 'A102'])
    factor = 72 / 25.4 if units == 'mm' else 72
    with fitz.open(stream=data, filetype='pdf') as pdf:
        assert len(pdf) == 2
        page = pdf[0]
        assert tuple(page.rect)[2:] == pytest.approx((size[0] * factor, size[1] * factor), abs=.01)
        expected = fitz.Rect((center[0] - diameter / 2) * factor,
                             (size[1] - center[1] - diameter / 2) * factor,
                             (center[0] + diameter / 2) * factor,
                             (size[1] - center[1] + diameter / 2) * factor)
        assert ink(page, expected) > 100
        # No fit-to-extents scaling or centering of sparse sheet content.
        assert ink(page, fitz.Rect(0, 0, page.rect.width / 10, page.rect.height / 10)) == 0
        paths = page.get_drawings()
        assert len(paths) >= 2


def test_viewport_geometry_is_plotted_and_hidden_layers_disappear():
    doc = sheet_drawing()
    sheet = doc.layouts.get('A101')
    doc.layers.new('DETAIL')
    doc.modelspace().delete_all_entities()
    doc.modelspace().add_circle((0, 0), 20, dxfattribs={'layer': 'DETAIL'})
    sheet.add_viewport(center=(100, 150), size=(80, 80), view_center_point=(0, 0), view_height=80)
    with fitz.open(stream=plot_layouts(doc, ['A101']), filetype='pdf') as pdf:
        assert ink(pdf[0], pdf[0].rect) > 100
    doc.layers.get('DETAIL').off()
    with fitz.open(stream=plot_layouts(doc, ['A101']), filetype='pdf') as pdf:
        assert ink(pdf[0], pdf[0].rect) == 0


def test_shifted_origin_is_preserved():
    doc = sheet_drawing()
    sheet = doc.layouts.get('A101')
    sheet.page_setup(size=(420, 297), margins=(5, 5, 5, 5), offset=(10, 15))
    lo, hi = sheet.get_paper_limits()
    sheet.add_line((lo.x + 20, lo.y + 20), (lo.x + 40, lo.y + 20))
    with fitz.open(stream=plot_layouts(doc, ['A101']), filetype='pdf') as pdf:
        rect = next(p['rect'] for p in pdf[0].get_drawings() if p['type'] == 's')
        assert rect.x0 == pytest.approx(20 * 72 / 25.4, abs=.1)
        assert rect.y0 == pytest.approx((297 - 20) * 72 / 25.4, abs=.1)


def test_unresolved_xrefs_and_unsupported_viewports_refuse_plot():
    doc = sheet_drawing()
    xref.attach(doc, block_name='MISSING', filename='missing.dxf')
    with pytest.raises(ValueError, match='xref'):
        plot_layouts(doc, ['A101'])
    doc = sheet_drawing()
    vp = doc.layouts.get('A101').add_viewport(center=(100, 100), size=(80, 80), view_center_point=(0, 0), view_height=80)
    vp.dxf.view_direction_vector = (1, 1, 1)
    with pytest.raises(ValueError, match='viewport'):
        plot_layouts(doc, ['A101'])


def test_closed_polylines_plot_as_outlines_without_solid_fill():
    doc = sheet_drawing()
    doc.layouts.get('A101').add_lwpolyline([(10, 10), (400, 10), (400, 280), (10, 280)], close=True)
    with fitz.open(stream=plot_layouts(doc, ['A101']), filetype='pdf') as pdf:
        page = pdf[0]
        assert ink(page, fitz.Rect(100, 100, 900, 700)) == 0
        assert 100 < ink(page, page.rect) < 15000
