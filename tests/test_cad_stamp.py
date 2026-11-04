"""Seal inserts remain editable, contained, and independently hideable."""
import ezdxf
import pytest
from ezdxf import bbox

from stamper.cad_stamp import SEAL_LAYER, stamp_layouts


def seal_drawing():
    doc = ezdxf.new('R2018')
    doc.modelspace().add_circle((100, 200), 20)
    doc.modelspace().add_line((80, 200), (120, 200))
    return doc


def sheet_drawing(units='mm'):
    doc = ezdxf.new('R2018')
    for name in ('A101', 'A102'):
        doc.layouts.new(name).page_setup(size=(420, 297) if units == 'mm' else (17, 11), units=units)
    doc.modelspace().add_line((0, 0), (500, 400))
    return doc


def test_imports_normalized_seal_in_selected_paperspace_and_replaces_only_owned():
    doc = sheet_drawing()
    sheet = doc.layouts.get('A101')
    other = doc.blocks.new('USER_BLOCK')
    other.add_circle((0, 0), 2)
    sheet.add_blockref('USER_BLOCK', (10, 10), dxfattribs={'layer': '0'})
    stamp_layouts(doc, seal_drawing(), ['A101'], center=(350, 180), diameter=40,
                  date='2026-11-04', caption='DEMONSTRATION')
    inserted = list(sheet.query(f'INSERT[layer=="{SEAL_LAYER}"]'))
    assert len(inserted) == 1
    bounds = bbox.extents(inserted, fast=False)
    assert bounds.extmin.x == pytest.approx(330)
    assert bounds.extmax.x == pytest.approx(370)
    assert bounds.extmax.y == pytest.approx(200)
    assert bounds.extmin.y >= 148
    assert len(doc.modelspace().query('LINE')) == 1
    assert not doc.layouts.get('A102').query('INSERT')
    assert doc.layers.get(SEAL_LAYER).dxf.plot == 1
    stamp_layouts(doc, seal_drawing(), ['A101'], center=(300, 180), diameter=40,
                  date='2026-11-05', caption='DEMONSTRATION')
    assert len(sheet.query(f'INSERT[layer=="{SEAL_LAYER}"]')) == 1
    assert len(sheet.query('INSERT[name=="USER_BLOCK"]')) == 1
    assert len(sheet.query('INSERT')) == 2


@pytest.mark.parametrize('center,diameter', [((2, 2), 40), ((410, 290), 40), ((50, 50), -1), ((float('nan'), 60), 10)])
def test_invalid_geometry_is_rejected_before_any_sheet_changes(center, diameter):
    doc = sheet_drawing()
    with pytest.raises(ValueError):
        stamp_layouts(doc, seal_drawing(), ['A101', 'A102'], center=center, diameter=diameter)
    assert not doc.layouts.get('A101').query('INSERT')
    assert SEAL_LAYER not in doc.layers


def test_modelspace_unknown_sheet_empty_seal_and_multiline_text_fail():
    for names, seal, caption in [(['Model'], seal_drawing(), ''),
                                 (['typo'], seal_drawing(), ''),
                                 (['A101'], ezdxf.new('R2018'), ''),
                                 (['A101'], seal_drawing(), 'line\nbreak')]:
        with pytest.raises(ValueError):
            stamp_layouts(sheet_drawing(), seal, names, center=(200, 180), diameter=40, caption=caption)


def test_inch_sheet_uses_paper_units_and_reopens_with_seal(tmp_path):
    doc = sheet_drawing('inch')
    stamp_layouts(doc, seal_drawing(), ['A101', 'A102'], center=(14, 7), diameter=2)
    path = tmp_path / 'stamped.dxf'
    doc.saveas(path)
    out = ezdxf.readfile(path)
    assert not out.audit().has_errors
    for name in ('A101', 'A102'):
        insert = out.layouts.get(name).query('INSERT')[0]
        assert tuple(insert.dxf.insert) == (14, 7, 0)
        assert insert.dxf.xscale == 2


@pytest.mark.parametrize('field', ['date', 'caption'])
def test_wide_annotation_text_fits_the_seal_width(field):
    doc = sheet_drawing()
    doc.layouts.get('A101').page_setup(size=(100, 100))
    stamp_layouts(doc, seal_drawing(), ['A101'], center=(5, 50), diameter=10,
                  **{field: 'W' * 80})
    bounds = bbox.extents(doc.layouts.get('A101').query('INSERT'), fast=False)
    assert bounds.extmin.x >= 0
    assert bounds.extmax.x <= 10
