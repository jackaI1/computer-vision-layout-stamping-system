"""DXF/DWG copies, layer controls, and portable, bottom-up xref binding."""
from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory

import ezdxf
from ezdxf import xref
from ezdxf.addons import odafc
from ezdxf.document import Drawing


def configure_oda() -> bool:
    """Use an explicit executable or a standard macOS installation, if present."""
    executable = os.environ.get('ODA_FILE_CONVERTER')
    if executable:
        if not Path(executable).is_file():
            raise ValueError('ODA_FILE_CONVERTER must name an installed executable')
        key = 'win_exec_path' if os.name == 'nt' else 'unix_exec_path'
        ezdxf.options.set('odafc-addon', key, executable)
    elif os.name != 'nt':
        for root in (Path.home() / 'Applications', Path('/Applications')):
            candidate = root / 'ODAFileConverter.app/Contents/MacOS/ODAFileConverter'
            if candidate.is_file():
                ezdxf.options.set('odafc-addon', 'unix_exec_path', str(candidate))
                break
    return odafc.is_installed()


def read_drawing(path: str | Path) -> Drawing:
    path = Path(path).resolve()
    if path.suffix.lower() == '.dxf':
        doc = ezdxf.readfile(path)
    elif path.suffix.lower() == '.dwg':
        if not configure_oda():
            raise ValueError('DWG needs the free ODA File Converter; see docs/cad.md')
        doc = odafc.readfile(path)
    else:
        raise ValueError('Expected a DXF or DWG drawing')
    # ODA reads a temporary DXF. References still belong to the original folder.
    doc.filename = str(path)
    return doc


def save_drawing(doc: Drawing, path: str | Path) -> None:
    """Publish a complete new file; never clobber an existing drawing."""
    path = Path(path).resolve()
    if path.exists():
        raise FileExistsError(f'Output already exists: {path}')
    if path.suffix.lower() not in ('.dxf', '.dwg'):
        raise ValueError('Expected a DXF or DWG output')
    path.parent.mkdir(parents=True, exist_ok=True)
    original = doc.filename
    try:
        with TemporaryDirectory(prefix='.cad-', dir=path.parent) as folder:
            temp = Path(folder) / path.name
            if path.suffix.lower() == '.dwg':
                if not configure_oda():
                    raise ValueError('DWG needs the free ODA File Converter; see docs/cad.md')
                odafc.export_dwg(doc, temp, version='R2018')
            else:
                doc.saveas(temp)
            os.link(temp, path)  # atomic create, including a concurrent writer
    finally:
        doc.filename = original


def layer_states(doc: Drawing) -> list[dict]:
    return [dict(name=layer.dxf.name, color=abs(layer.dxf.color),
                 off=layer.is_off(), frozen=layer.is_frozen(),
                 locked=layer.is_locked(), plot=bool(layer.dxf.plot))
            for layer in doc.layers]


def set_layer(doc: Drawing, name: str, visible: bool) -> None:
    if name not in doc.layers:
        raise ValueError(f'Unknown layer: {name}')
    layer = doc.layers.get(name)
    if visible:
        layer.on()
        layer.thaw()
    else:
        layer.off()


def resolve_xref(raw: str, host: str | Path, search_dirs=()) -> Path:
    """Prefer a host-relative path; explicit folders can relocate a whole project."""
    ref = Path(raw.replace('\\', '/'))
    direct = ref if ref.is_absolute() else Path(host).parent / ref
    if direct.is_file():
        return direct.resolve()
    matches = {p.resolve() for folder in search_dirs
               for p in (Path(folder) / ref, Path(folder) / ref.name) if p.is_file()}
    if len(matches) > 1:
        raise ValueError(f'ambiguous xref: {raw}; narrow --xref-dir')
    if matches:
        return matches.pop()
    raise FileNotFoundError(f'Missing xref: {raw} (host: {Path(host).name})')


def reference_states(doc: Drawing, search_dirs=()) -> list[dict]:
    rows = []
    for block in doc.blocks:
        if not (block.block.is_xref or block.block.is_xref_overlay):
            continue
        raw = block.block.dxf.xref_path
        try:
            resolved = str(resolve_xref(raw, doc.filename, search_dirs))
            error = None
        except (ValueError, FileNotFoundError) as exc:
            resolved, error = None, str(exc)
        rows.append(dict(name=block.name, path=raw, resolved=resolved, error=error,
                         overlay=block.block.is_xref_overlay))
    return rows


def _preserve_layer_overrides(doc, aliases):
    """Carry host dependent-layer properties onto the bound local layer names."""
    viewports = [vp for sheet in doc.layouts for vp in sheet.query('VIEWPORT')]
    for old, new in aliases.items():
        if old not in doc.layers or new not in doc.layers:
            continue
        source, target = doc.layers.get(old), doc.layers.get(new)
        source_overrides = source.get_vp_overrides()
        if new.casefold() in ('0', 'defpoints'):
            # These are shared host layers, so changing them would change host
            # geometry too. Refuse non-default overrides rather than reveal ink.
            different = any(source.dxf.get_default(a) != target.dxf.get_default(a)
                            for a in ('color', 'true_color', 'linetype', 'lineweight', 'plot'))
            if (different or source.transparency != target.transparency or
                    source.dxf.flags & 7 != target.dxf.flags & 7 or
                    source_overrides.has_overrides() or
                    any(old.casefold() in {n.casefold() for n in v.frozen_layers} for v in viewports)):
                raise ValueError(f'Cannot bind an override of shared xref layer {old}; use a named source layer')
            continue
        for attr in ('color', 'linetype', 'lineweight', 'plot'):
            target.dxf.set(attr, source.dxf.get_default(attr))
        if source.dxf.hasattr('true_color'):
            target.dxf.true_color = source.dxf.true_color
        else:
            target.dxf.discard('true_color')
        target.dxf.flags = source.dxf.flags & 7  # drop external dependency bits
        target.transparency = source.transparency
        target_overrides = target.get_vp_overrides()
        for vp in viewports:
            vp.rename_frozen_layer(old, new)
            handle = vp.dxf.handle
            if source_overrides.has_overrides(handle):
                for prop in ('color', 'rgb', 'transparency', 'linetype', 'lineweight'):
                    value = getattr(source_overrides, f'get_{prop}')(handle)
                    getattr(target_overrides, f'set_{prop}')(handle, value)
        target_overrides.commit()


def bind_xrefs(doc: Drawing, search_dirs=(), *, _stack=(), _nested=False, _aliases=None) -> list[str]:
    """Embed all attached drawings; reject cycles and never flatten INSERT transforms.

    Nested overlays are removed as CAD overlay semantics require. Top-level
    overlays are included because they are visible in the current host.
    """
    host = Path(doc.filename).resolve()
    if host in _stack:
        raise ValueError('xref cycle: ' + ' -> '.join(p.name for p in (*_stack, host)))
    if len(_stack) >= 32:
        raise ValueError('xref nesting exceeds 32 drawings')
    bound = []
    aliases = {} if _aliases is None else _aliases
    for block in list(doc.blocks):
        if not (block.block.is_xref or block.block.is_xref_overlay):
            continue
        if _nested and block.block.is_xref_overlay:
            for layout in doc.layouts_and_blocks():
                for insert in list(layout.query('INSERT')):
                    if insert.dxf.name.casefold() == block.name.casefold():
                        layout.delete_entity(insert)
            doc.blocks.delete_block(block.name, safe=False)
            continue
        path = resolve_xref(block.block.dxf.xref_path, host, search_dirs)
        child = read_drawing(path)
        child_aliases = {}
        bound.extend(bind_xrefs(child, search_dirs, _stack=(*_stack, host), _nested=True,
                                _aliases=child_aliases))
        # The pinned XREF_PREFIX policy always uses this unique name algorithm.
        # Record it before importing, including collisions such as REF$0$WALLS.
        imported_names = {layer.dxf.name: (layer.dxf.name if layer.dxf.name.casefold() in ('0', 'defpoints')
                          else xref.get_unique_table_name(layer.dxf.name, block.name, doc.layers))
                          for layer in child.layers}
        block.block.dxf.xref_path = str(path)
        # embed() requires the attachment bit even for a top-level overlay.
        block.block.set_flag_state(block.block.XREF, state=True)
        xref.embed(block, load_fn=lambda _: child)
        block.block.set_flag_state(block.block.XREF_OVERLAY, state=False)
        block.block.dxf.discard('xref_path')
        for original, imported in imported_names.items():
            aliases[f'{block.name}|{original}'] = imported
        for original, local in child_aliases.items():
            if local in imported_names:
                aliases[f'{block.name}|{original}'] = imported_names[local]
        _preserve_layer_overrides(doc, aliases)
        bound.append(str(path))
    return bound
