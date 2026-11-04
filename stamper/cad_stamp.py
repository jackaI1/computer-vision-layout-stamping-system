"""Normalize a vector seal drawing and place editable blocks on sheet copies."""
from __future__ import annotations

import math
from uuid import uuid4

from ezdxf import bbox, xref
from ezdxf.enums import TextEntityAlignment
from ezdxf.tools.text_size import text_size

SEAL_LAYER = 'STAMPER_SEAL'
OWNER_APP = 'STAMPER_CAD'


def paper_layouts(doc, names):
    names = list(dict.fromkeys(names))
    if not names:
        raise ValueError('Select at least one paper-space layout')
    sheets = []
    for name in names:
        if name not in doc.layouts or name.casefold() == 'model':
            raise ValueError(f'Unknown paper-space layout: {name}')
        sheets.append(doc.layouts.get(name))
    return sheets


def paper_geometry(sheet):
    """Physical full-paper region in sheet coordinates, including plot origin."""
    dxf = sheet.dxf_layout.dxf
    if dxf.plot_paper_units not in (0, 1):
        raise ValueError(f'{sheet.name}: paper units must be mm or inches')
    if not math.isclose(dxf.scale_numerator, dxf.scale_denominator):
        raise ValueError(f'{sheet.name}: paper plot scale must be 1:1')
    factor = 25.4 if dxf.plot_paper_units == 0 else 1.0
    width, height = dxf.paper_width, dxf.paper_height
    if not all(math.isfinite(v) and v > 0 for v in (width, height)):
        raise ValueError(f'{sheet.name}: set a physical paper size first')
    x = -(dxf.left_margin + dxf.plot_origin_x_offset) / factor
    y = -(dxf.bottom_margin + dxf.plot_origin_y_offset) / factor
    return (x, y, x + width / factor, y + height / factor), factor


def stamp_layouts(doc, seal_doc, names, *, center, diameter, date='', caption=''):
    sheets = paper_layouts(doc, names)
    if not all(math.isfinite(v) for v in (*center, diameter)) or diameter <= 0:
        raise ValueError('Seal coordinates must be finite and diameter positive')
    for text in (date, caption):
        if len(text) > 80 or any(ord(c) < 32 for c in text):
            raise ValueError('Date and caption must be single lines of at most 80 characters')
    if any(b.block.is_xref or b.block.is_xref_overlay for b in seal_doc.blocks):
        raise ValueError('Bind seal xrefs before importing')
    bounds = bbox.extents(seal_doc.modelspace(), fast=False)
    if not bounds.has_data or max(bounds.size.x, bounds.size.y) <= 0:
        raise ValueError('Seal drawing needs visible model-space geometry')
    for sheet in sheets:
        (x0, y0, x1, y1), _ = paper_geometry(sheet)
        # Caption is part of the block and included in the containment check.
        low = .72 if caption else .5
        x, y = center
        if x - diameter / 2 < x0 or x + diameter / 2 > x1 or y - low * diameter < y0 or y + diameter / 2 > y1:
            raise ValueError(f'Seal and caption extend outside paper: {sheet.name}')

    if SEAL_LAYER not in doc.layers:
        doc.layers.new(SEAL_LAYER, dxfattribs={'color': 5, 'plot': 1})
    layer = doc.layers.get(SEAL_LAYER)
    layer.on()
    layer.thaw()
    layer.unlock()
    layer.dxf.plot = 1
    if OWNER_APP not in doc.appids:
        doc.appids.new(OWNER_APP)

    token = uuid4().hex[:12]
    raw = doc.blocks.new(f'STAMPER_GEOMETRY_{token}', base_point=bounds.center)
    loader = xref.Loader(seal_doc, doc, conflict_policy=xref.ConflictPolicy.NUM_PREFIX)
    loader.load_modelspace(raw)
    loader.execute()
    block = doc.blocks.new(f'STAMPER_SEAL_{token}')
    extent = max(bounds.size.x, bounds.size.y)
    block.add_blockref(raw.name, (0, 0), dxfattribs={'xscale': 1 / extent, 'yscale': 1 / extent, 'zscale': 1 / extent})
    for text, y, height in ((date, .13, .065), (caption, -.62, .075)):
        if text:
            annotation = block.add_text(text, dxfattribs={'height': height})
            measured = text_size(annotation).width
            if measured > .9:
                annotation.dxf.height *= .9 / measured
            annotation.set_placement((0, y), align=TextEntityAlignment.MIDDLE_CENTER)
    for sheet in sheets:
        for old in list(sheet.query('INSERT')):
            if old.has_xdata(OWNER_APP):
                sheet.delete_entity(old)
        insert = sheet.add_blockref(block.name, center, dxfattribs={
            'layer': SEAL_LAYER, 'xscale': diameter, 'yscale': diameter, 'zscale': diameter})
        insert.set_xdata(OWNER_APP, [(1000, 'seal-v1')])
    return [sheet.name for sheet in sheets]
