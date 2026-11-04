"""CAD IO contracts against real files, not mocked ezdxf calls."""
from pathlib import Path

import ezdxf
import pytest
from ezdxf import xref

from stamper.cad_io import bind_xrefs, layer_states, read_drawing, resolve_xref, save_drawing, set_layer


def drawing(path, *, reference=None):
    doc = ezdxf.new('R2018')
    doc.layers.new('WALLS', dxfattribs={'color': 3})
    doc.modelspace().add_line((0, 0), (10, 20), dxfattribs={'layer': 'WALLS'})
    if reference:
        xref.attach(doc, block_name='REF', filename=str(reference), insert=(30, 40), scale=2, rotation=90)
    doc.saveas(path)
    return doc


def test_layer_toggle_survives_roundtrip_without_changing_geometry(tmp_path):
    path = tmp_path / 'source.dxf'
    drawing(path)
    before = path.read_bytes()
    doc = read_drawing(path)
    set_layer(doc, 'walls', False)
    dest = tmp_path / 'copy.dxf'
    save_drawing(doc, dest)
    out = read_drawing(dest)
    state = next(x for x in layer_states(out) if x['name'] == 'WALLS')
    assert state['off'] and state['color'] == 3
    assert tuple(out.modelspace().query('LINE')[0].dxf.end) == (10, 20, 0)
    out.layers.get('WALLS').freeze()
    set_layer(out, 'WALLS', True)
    assert not out.layers.get('WALLS').is_off()
    assert not out.layers.get('WALLS').is_frozen()
    assert path.read_bytes() == before
    with pytest.raises(ValueError, match='layer'):
        set_layer(out, 'typo', False)
    with pytest.raises(FileExistsError):
        save_drawing(out, dest)


def test_nested_xrefs_bind_relative_to_each_file_and_preserve_host(tmp_path):
    assets = tmp_path / 'assets'
    assets.mkdir()
    drawing(assets / 'child.dxf')
    drawing(assets / 'parent.dxf', reference='child.dxf')
    source = tmp_path / 'host.dxf'
    drawing(source, reference=r'assets\parent.dxf')
    before = source.read_bytes()
    doc = read_drawing(source)
    bound = bind_xrefs(doc)
    assert len(bound) == 2
    assert not any(b.block.is_xref for b in doc.blocks)
    insert = doc.modelspace().query('INSERT')[0]
    assert tuple(insert.dxf.insert) == (30, 40, 0)
    assert insert.dxf.xscale == 2 and insert.dxf.rotation == 90
    assert len(doc.modelspace().query('LINE')) == 1
    # Host WALLS stays green; imported WALLS receives a reference prefix.
    assert doc.layers.get('WALLS').dxf.color == 3
    assert any('$' in layer.dxf.name for layer in doc.layers)
    output = tmp_path / 'bound.dxf'
    save_drawing(doc, output)
    assert not any(b.block.is_xref for b in read_drawing(output).blocks)
    assert source.read_bytes() == before


def test_reference_search_is_explicit_and_ambiguous_names_fail(tmp_path):
    host = tmp_path / 'host.dxf'
    drawing(host)
    a, b = tmp_path / 'a', tmp_path / 'b'
    a.mkdir()
    b.mkdir()
    drawing(a / 'plan.dxf')
    drawing(b / 'plan.dxf')
    assert resolve_xref(r'C:\old\plan.dxf', host, [a]) == (a / 'plan.dxf').resolve()
    with pytest.raises(ValueError, match='ambiguous'):
        resolve_xref('plan.dxf', host, [a, b])
    with pytest.raises(FileNotFoundError, match='missing.dxf'):
        resolve_xref('missing.dxf', host, [])


def test_missing_and_cyclic_references_fail(tmp_path):
    drawing(tmp_path / 'a.dxf', reference='b.dxf')
    with pytest.raises(FileNotFoundError):
        bind_xrefs(read_drawing(tmp_path / 'a.dxf'))
    drawing(tmp_path / 'b.dxf', reference='a.dxf')
    with pytest.raises(ValueError, match='cycle'):
        bind_xrefs(read_drawing(tmp_path / 'a.dxf'))


def test_nested_overlay_does_not_propagate(tmp_path):
    drawing(tmp_path / 'overlay.dxf')
    parent = drawing(tmp_path / 'parent.dxf')
    xref.attach(parent, block_name='OVERLAY', filename='overlay.dxf', overlay=True)
    parent.save()
    drawing(tmp_path / 'host.dxf', reference='parent.dxf')
    doc = read_drawing(tmp_path / 'host.dxf')
    assert len(bind_xrefs(doc)) == 1
    assert not any(b.block.is_xref for b in doc.blocks)
    assert not any('OVERLAY' in b.name for b in doc.blocks)


@pytest.mark.parametrize('suffix', ['.txt', '.pdf'])
def test_unrelated_file_types_are_rejected(tmp_path, suffix):
    with pytest.raises(ValueError, match='DXF or DWG'):
        read_drawing(tmp_path / ('source' + suffix))


def test_binding_preserves_host_and_viewport_xref_layer_overrides(tmp_path):
    drawing(tmp_path / 'child.dxf')
    drawing(tmp_path / 'parent.dxf', reference='child.dxf')
    host = drawing(tmp_path / 'host.dxf', reference='parent.dxf')
    override = host.layers.new('REF|REF|WALLS', dxfattribs={
        'color': -7, 'flags': 17, 'plot': 0, 'lineweight': 50})
    sheet = host.layouts.get('Layout1')
    sheet.page_setup()
    vp = sheet.add_viewport(center=(50, 50), size=(80, 80), view_center_point=(0, 0), view_height=100)
    vp.frozen_layers = ['REF|REF|WALLS']
    overrides = override.get_vp_overrides()
    overrides.set_color(vp.dxf.handle, 2)
    overrides.commit()
    host.save()
    doc = read_drawing(tmp_path / 'host.dxf')
    bind_xrefs(doc)
    # Find the nested child's actual imported layer via its LINE, not a guessed name.
    layers = [doc.layers.get(e.dxf.layer) for b in doc.blocks for e in b.query('LINE')
              if b.name != 'REF' and e.dxf.layer != 'WALLS']
    target = next(layer for layer in layers if layer.is_off())
    assert target.is_frozen() and target.dxf.plot == 0 and target.dxf.lineweight == 50
    viewport = doc.layouts.get('Layout1').query('VIEWPORT')[1]
    assert target.dxf.name in viewport.frozen_layers
    assert target.get_vp_overrides().get_color(viewport.dxf.handle) == 2
    assert doc.layers.get('WALLS').is_on()
    assert not doc.audit().has_errors


def test_top_level_overlay_is_bound(tmp_path):
    drawing(tmp_path / 'child.dxf')
    host = drawing(tmp_path / 'host.dxf')
    xref.attach(host, block_name='OVERLAY', filename='child.dxf', overlay=True)
    host.save()
    doc = read_drawing(tmp_path / 'host.dxf')
    assert len(bind_xrefs(doc)) == 1
    assert len(doc.blocks.get('OVERLAY').query('LINE')) == 1
    assert not any(b.block.is_xref or b.block.is_xref_overlay for b in doc.blocks)


def test_nondefault_shared_zero_layer_override_fails_without_changing_host(tmp_path):
    drawing(tmp_path / 'child.dxf')
    host = drawing(tmp_path / 'host.dxf', reference='child.dxf')
    host.layers.new('REF|0', dxfattribs={'color': -7, 'flags': 16})
    with pytest.raises(ValueError, match='shared xref layer'):
        bind_xrefs(host)
    assert host.layers.get('0').is_on()
