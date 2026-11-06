import csv

import ezdxf
import pytest
from openpyxl import load_workbook

from stamper.earthwork import calculate, run


def drawing(path, design_z=2):
    doc = ezdxf.new()
    m = doc.modelspace()
    for y in (0, 10):
        m.add_lwpolyline([(0, y), (10, y)], dxfattribs={'layer': 'CONTOURS', 'elevation': 0})
    m.add_polyline3d([(0, 0, design_z), (10, 0, design_z), (10, 10, design_z), (0, 10, design_z)], close=True, dxfattribs={'layer': 'PAD'})
    doc.saveas(path)


def test_flat_fill_and_outputs(tmp_path):
    source = tmp_path / 'site.dxf'
    drawing(source)
    result = run(source, tmp_path / 'out', spacing=3)
    assert result['fill_volume'] == pytest.approx  (200)
    assert result['cut_volume'] == pytest.approx(0)
    assert result['area'] == pytest.approx(100)
    with (tmp_path / 'out' / 'quantities.csv').open() as f:
        assert list(csv.DictReader(f))[0]['fill_volume'] == '200.0'
    assert load_workbook(tmp_path / 'out' / 'quantities.xlsx').active.max_row == 2
    assert (tmp_path / 'out' / 'layout.pdf').stat().st_size > 1000


def test_flat_cut(tmp_path):
    source = tmp_path / 'site.dxf'
    drawing(source, -1)
    result = calculate(source, spacing=2)
    assert result['cut_volume'] == pytest.approx(100)
    assert result['fill_volume'] == 0


def test_reject_pad_outside_survey(tmp_path):
    source = tmp_path / 'site.dxf'
    drawing(source)
    doc = ezdxf.readfile(source)
    pad = doc.modelspace().query('POLYLINE[layer=="PAD"]')[0]
    pad.vertices[1].dxf.location = (11, 0, 2)
    doc.saveas(source)
    with pytest.raises(ValueError, match='coverage'):
        calculate(source, spacing=1)


def test_sloping_ground_has_both_cut_and_fill(tmp_path):
    source = tmp_path / 'slope.dxf'
    doc = ezdxf.new()
    m = doc.modelspace()
    for y, z in ((0, 0), (10, 2)):
        m.add_lwpolyline([(0, y), (10, y)], dxfattribs={'layer': 'CONTOURS', 'elevation': z})
    m.add_lwpolyline([(0, 0), (10, 0), (10, 10), (0, 10)], close=True, dxfattribs={'layer': 'PAD', 'elevation': 1})
    doc.saveas(source)
    result = calculate(source, spacing=1)
    assert result['cut_volume'] == pytest.approx(25)
    assert result['fill_volume'] == pytest.approx(25)
    assert result['cut_area'] == pytest.approx(50)
    assert result['fill_area'] == pytest.approx(50)
