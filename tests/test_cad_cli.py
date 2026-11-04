"""Run the documented workflow as a user would, including output protection."""
import json
import os
from pathlib import Path
import subprocess
import sys

import ezdxf
import fitz
import pytest

from examples.make_sample_cad import make_sample

ROOT = Path(__file__).resolve().parents[1]


def cli(*args):
    return subprocess.run([sys.executable, '-m', 'stamper.cad', *map(str, args)],
                          cwd=ROOT, capture_output=True, text=True, timeout=45)


def test_documented_inspect_edit_stamp_plot_workflow(tmp_path):
    make_sample(tmp_path)
    source = tmp_path / 'floor_plan.dxf'
    before = source.read_bytes()
    result = cli('inspect', source)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert {'A101', 'A102'} <= {x['name'] for x in report['layouts']}
    assert report['xrefs'][0]['resolved'].endswith('furniture.dxf')
    edited = tmp_path / 'edited.dxf'
    result = cli('edit', source, '-o', edited, '--off', 'FURNITURE', '--bind-xrefs')
    assert result.returncode == 0, result.stderr
    assert ezdxf.readfile(edited).layers.get('FURNITURE').is_off()
    stamped, pdf = tmp_path / 'stamped.dxf', tmp_path / 'stamped.pdf'
    result = cli('stamp', edited, '--seal', tmp_path / 'demo_seal.dxf', '--layout', 'A101',
                 '--layout', 'A102', '--center', 350, 180, '--diameter', 40,
                 '--date', '2026-11-04', '--caption', 'DEMONSTRATION ONLY', '-o', stamped, '--pdf', pdf)
    assert result.returncode == 0, result.stderr
    out = ezdxf.readfile(stamped)
    assert not out.audit().has_errors
    for name in ('A101', 'A102'):
        assert len(out.layouts.get(name).query('INSERT[layer=="STAMPER_SEAL"]')) == 1
    assert not any(b.block.is_xref or b.block.is_xref_overlay for b in out.blocks)
    with fitz.open(pdf) as document:
        assert len(document) == 2 and len(document[0].get_drawings()) > 20
    plot = tmp_path / 'plotted.pdf'
    result = cli('plot', stamped, '--layout', 'A101', '-o', plot)
    assert result.returncode == 0, result.stderr
    with fitz.open(plot) as document:
        assert len(document) == 1
    assert source.read_bytes() == before


def test_output_exists_and_bad_sheet_do_not_write_or_clobber(tmp_path):
    make_sample(tmp_path)
    source = tmp_path / 'floor_plan.dxf'
    original = source.read_bytes()
    result = cli('edit', source, '-o', source, '--off', 'WALLS')
    assert result.returncode != 0 and 'exists' in result.stderr
    assert source.read_bytes() == original
    dest = tmp_path / 'bad.dxf'
    result = cli('stamp', source, '--seal', tmp_path / 'demo_seal.dxf', '--layout', 'typo',
                 '--center', 350, 180, '--diameter', 40, '-o', dest)
    assert result.returncode != 0 and not dest.exists()
    assert 'Traceback' not in result.stderr


def test_edit_relocates_unbound_reference_paths(tmp_path):
    make_sample(tmp_path)
    target = tmp_path / 'new_folder' / 'copy.dxf'
    result = cli('edit', tmp_path / 'floor_plan.dxf', '-o', target, '--off', 'NOTES')
    assert result.returncode == 0, result.stderr
    report = json.loads(cli('inspect', target).stdout)
    assert report['xrefs'][0]['resolved'] == str((tmp_path / 'furniture.dxf').resolve())


def test_invalid_pdf_parent_does_not_leave_a_partial_drawing(tmp_path):
    make_sample(tmp_path)
    parent = tmp_path / 'regular-file'
    parent.write_text('preserve')
    output = tmp_path / 'copy.dxf'
    result = cli('stamp', tmp_path / 'floor_plan.dxf', '--seal', tmp_path / 'demo_seal.dxf',
                 '--layout', 'A101', '--center', 350, 180, '--diameter', 40,
                 '-o', output, '--pdf', parent / 'copy.pdf')
    assert result.returncode != 0
    assert not output.exists() and parent.read_text() == 'preserve'


@pytest.mark.skipif(not os.environ.get('TEST_ODA'), reason='Set TEST_ODA=1 with ODA installed for real DWG conversion')
def test_real_oda_dwg_roundtrip_and_stamp(tmp_path):
    from stamper.cad_io import read_drawing, save_drawing
    make_sample(tmp_path)
    # Bind before initial DWG creation, so AutoCAD has no DXF xref dependency.
    bound = tmp_path / 'bound.dxf'
    assert cli('edit', tmp_path / 'floor_plan.dxf', '--bind-xrefs', '-o', bound).returncode == 0
    dwg = tmp_path / 'source.dwg'
    save_drawing(read_drawing(bound), dwg)
    assert dwg.read_bytes().startswith(b'AC1032')
    output = tmp_path / 'stamped.dwg'
    result = cli('stamp', dwg, '--seal', tmp_path / 'demo_seal.dxf', '--layout', 'A101',
                 '--center', 350, 180, '--diameter', 40, '-o', output)
    assert result.returncode == 0, result.stderr
    out = read_drawing(output)
    assert len(out.layouts.get('A101').query('INSERT[layer=="STAMPER_SEAL"]')) == 1
    assert not out.audit().has_errors
