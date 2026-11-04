"""Plot full physical sheets without fit-to-extents or changing the CAD file."""
from __future__ import annotations

import fitz
import re
import xml.etree.ElementTree as ET
from ezdxf.addons.drawing import Frontend, RenderContext, config, layout, svg
from ezdxf.math import BoundingBox2d, Vec3

from stamper.cad_stamp import paper_geometry, paper_layouts


def _inline_styles(drawing: str) -> bytes:
    """MuPDF's SVG reader needs presentation attributes instead of CSS classes.

    This accepts only SVG produced by our pinned ezdxf backend, not user SVG.
    Without inlining, closed CAD outlines become solid black polygons.
    """
    root = ET.fromstring(drawing)
    styles = {}
    for style in root.iter('{http://www.w3.org/2000/svg}style'):
        for name, body in re.findall(r'\.([\w-]+)\s*\{([^}]+)\}', style.text or ''):
            styles[name] = dict(item.strip().split(':', 1) for item in body.split(';') if item.strip())
    for element in root.iter():
        for name in element.attrib.pop('class', '').split():
            for key, value in styles[name].items():
                if key != 'stroke-width' or value.strip() != 'none':
                    element.set(key, value.strip())
    return ET.tostring(root)


def plot_layouts(doc, names) -> bytes:
    sheets = paper_layouts(doc, names)
    if any(b.block.is_xref or b.block.is_xref_overlay for b in doc.blocks):
        raise ValueError('Bind xrefs before plotting; unresolved xrefs would be omitted')
    for sheet in sheets:
        paper_geometry(sheet)
        for vp in sheet.query('VIEWPORT'):
            if vp.dxf.id <= 1 or vp.dxf.status <= 0:
                continue
            if not Vec3(vp.dxf.view_direction_vector).isclose(Vec3(0, 0, 1)) or vp.dxf.flags & 1:
                raise ValueError(f'{sheet.name}: only top-view, parallel viewports can be plotted')
    configuration = config.Configuration(
        background_policy=config.BackgroundPolicy.WHITE,
        color_policy=config.ColorPolicy.BLACK,
    )
    with fitz.open() as result:
        for sheet in sheets:
            region, factor = paper_geometry(sheet)
            width = (region[2] - region[0]) * factor
            height = (region[3] - region[1]) * factor
            backend = svg.SVGBackend()
            context = RenderContext(doc)
            # Non-plot layers, including viewport frames, are excluded explicitly.
            context.set_layer_properties_override(
                lambda layers: [setattr(p, 'is_visible', False) for p in layers
                                if p.layer in doc.layers and not doc.layers.get(p.layer).dxf.plot])
            Frontend(context, backend, config=configuration).draw_layout(sheet)
            drawing = backend.get_string(
                layout.Page(width, height), render_box=BoundingBox2d([region[:2], region[2:]]),
                settings=layout.Settings(fit_page=False, scale=factor, crop_at_margins=True))
            # SVG keeps fractional-point paper dimensions; ezdxf's native PDF
            # backend truncates them. MuPDF converts these vectors to PDF.
            with fitz.open(stream=_inline_styles(drawing), filetype='svg') as image:
                data = image.convert_to_pdf()
            with fitz.open(stream=data, filetype='pdf') as page:
                rotation = int(sheet.dxf_layout.dxf.plot_rotation) * 90
                if rotation:
                    page[0].set_rotation(rotation)
                result.insert_pdf(page)
        return result.tobytes(garbage=4, deflate=True)
