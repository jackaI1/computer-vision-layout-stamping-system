"""Generate public-only CAD fixtures. No client drawing or professional seal."""
from __future__ import annotations

import argparse
from pathlib import Path

import ezdxf
from ezdxf import units, xref
from ezdxf.enums import TextEntityAlignment


def rectangle(space, x, y, width, height, layer):
    space.add_lwpolyline([(x, y), (x + width, y), (x + width, y + height), (x, y + height)],
                         close=True, dxfattribs={'layer': layer})


def make_sample(folder: Path):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    furniture = ezdxf.new('R2018', units=units.MM)
    furniture.layers.new('DESKS', dxfattribs={'color': 4})
    for x, y in ((1200, 1200), (1200, 5500), (7000, 5500), (8500, 1500)):
        rectangle(furniture.modelspace(), x, y, 1600, 800, 'DESKS')
        furniture.modelspace().add_circle((x + 800, y - 400), 300, dxfattribs={'layer': 'DESKS'})
    furniture.saveas(folder / 'furniture.dxf')

    doc = ezdxf.new('R2018', units=units.MM)
    for name, color in (('WALLS', 7), ('DOORS', 2), ('NOTES', 3), ('FURNITURE', 4), ('SHEET', 7)):
        doc.layers.new(name, dxfattribs={'color': color})
    doc.layers.new('VIEWPORTS', dxfattribs={'plot': 0})
    model = doc.modelspace()
    rectangle(model, 0, 0, 12000, 8000, 'WALLS')
    rectangle(model, 200, 200, 11600, 7600, 'WALLS')
    for start, end in (((6000, 200), (6000, 3200)), ((6000, 4200), (6000, 7800)),
                       ((200, 4000), (2400, 4000)), ((3400, 4000), (11800, 4000))):
        model.add_line(start, end, dxfattribs={'layer': 'WALLS'})
    model.add_arc((6000, 3200), 1000, 0, 90, dxfattribs={'layer': 'DOORS'})
    model.add_line((6000, 3200), (7000, 3200), dxfattribs={'layer': 'DOORS'})
    model.add_arc((2400, 4000), 1000, 0, 90, dxfattribs={'layer': 'DOORS'})
    for text, point in (('MEETING', (2400, 2000)), ('WORKSHOP', (8500, 2000)),
                         ('OFFICE', (2400, 6500)), ('STUDIO', (8500, 6500))):
        model.add_text(text, dxfattribs={'height': 250, 'layer': 'NOTES'}).set_placement(
            point, align=TextEntityAlignment.MIDDLE_CENTER)
    attached = xref.attach(doc, block_name='FURNITURE_REF', filename='furniture.dxf')
    attached.dxf.layer = 'FURNITURE'
    for name, title, view_center, view_height in (
        ('A101', 'FLOOR PLAN 1:50', (6000, 4000), 8000),
        ('A102', 'OFFICE DETAIL 1:30', (3000, 6000), 4800),
    ):
        sheet = doc.layouts.new(name)
        sheet.page_setup(size=(420, 297), margins=(0, 0, 0, 0), units='mm')
        rectangle(sheet, 10, 10, 400, 277, 'SHEET')
        rectangle(sheet, 290, 10, 120, 277, 'SHEET')
        rectangle(sheet, 315, 145, 70, 70, 'SHEET')
        sheet.add_viewport(center=(150, 170), size=(240, 160), view_center_point=view_center,
                           view_height=view_height, dxfattribs={'layer': 'VIEWPORTS'})
        for text, point, height in ((name, (300, 260), 8), (title, (300, 245), 4),
                                    ('SYNTHETIC EXAMPLE', (300, 230), 3),
                                    ('SEAL REVIEW AREA', (320, 220), 3),
                                    ('NOT FOR CONSTRUCTION', (300, 40), 3),
                                    ('All dimensions in millimetres', (30, 45), 4)):
            sheet.add_text(text, dxfattribs={'height': height, 'layer': 'SHEET'}).set_placement(point)
    doc.layouts.delete('Layout1')
    doc.saveas(folder / 'floor_plan.dxf')

    seal = ezdxf.new('R2018', units=units.MM)
    space = seal.modelspace()
    space.add_circle((0, 0), 20)
    space.add_circle((0, 0), 18)
    for y in (-4, 4):
        space.add_line((-17, y), (17, y))
    for text, y, height in (('DEMO', 0, 4), ('NOT VALID', -10, 2.6)):
        space.add_text(text, dxfattribs={'height': height}).set_placement(
            (0, y), align=TextEntityAlignment.MIDDLE_CENTER)
    seal.saveas(folder / 'demo_seal.dxf')
    return doc


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=Path('examples/cad'))
    args = parser.parse_args()
    make_sample(args.output_dir)
    print(f'Generated floor_plan.dxf, furniture.dxf and demo_seal.dxf in {args.output_dir}')
