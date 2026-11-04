"""Editable CAD workflow: python -m stamper.cad --help."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

import ezdxf
from ezdxf.addons import odafc

from stamper.cad_io import (bind_xrefs, layer_states, read_drawing, reference_states,
                           resolve_xref, save_drawing, set_layer)
from stamper.cad_plot import plot_layouts
from stamper.cad_stamp import paper_geometry, stamp_layouts


def parser():
    root = argparse.ArgumentParser(description='Inspect, edit, stamp and plot CAD sheet copies.')
    commands = root.add_subparsers(dest='command', required=True)
    for command in ('inspect', 'edit', 'stamp', 'plot'):
        p = commands.add_parser(command)
        p.add_argument('drawing', type=Path)
        p.add_argument('--xref-dir', action='append', type=Path, default=[], help='Extra reference folder; repeat as needed')
        if command != 'inspect':
            p.add_argument('-o', '--output', required=True, type=Path, help='New file; existing files are never overwritten')
        if command in ('edit', 'stamp', 'plot'):
            p.add_argument('--off', action='append', default=[], metavar='LAYER')
            p.add_argument('--on', action='append', default=[], metavar='LAYER')
        if command == 'edit':
            p.add_argument('--bind-xrefs', action='store_true')
        if command in ('stamp', 'plot'):
            p.add_argument('--layout', action='append', required=True, help='Paper-space sheet name; repeat for a sheet set')
        if command == 'stamp':
            p.add_argument('--seal', required=True, type=Path, help='DXF/DWG containing the vector seal in model space')
            p.add_argument('--center', nargs=2, required=True, type=float, metavar=('X', 'Y'), help='Sheet coordinates, origin at lower left of printable area plus plot offset')
            p.add_argument('--diameter', required=True, type=float, help='Diameter in sheet units, mm or inches')
            p.add_argument('--date', default='')
            p.add_argument('--caption', default='')
            p.add_argument('--pdf', type=Path, help='Also write the selected sheets to a new PDF')
    return root


def main(argv=None):
    root = parser()
    args = root.parse_args(argv)
    try:
        outputs = [p.resolve() for p in (getattr(args, 'output', None), getattr(args, 'pdf', None)) if p]
        if len(set(outputs)) != len(outputs):
            raise ValueError('Drawing and PDF outputs must be different paths')
        for path in outputs:
            if path.exists():
                raise FileExistsError(f'Output already exists: {path}')
            if any(parent.exists() and not parent.is_dir() for parent in path.parents):
                raise ValueError(f'Output parent is not a directory: {path}')
        doc = read_drawing(args.drawing)
        if args.command == 'inspect':
            sheets = []
            for sheet in doc.layouts:
                if sheet.name.casefold() == 'model':
                    continue
                try:
                    region, factor = paper_geometry(sheet)
                    sheets.append(dict(name=sheet.name, units='inch' if factor == 25.4 else 'mm',
                                       paper_bounds=region))
                except ValueError as exc:
                    sheets.append(dict(name=sheet.name, error=str(exc)))
            print(json.dumps(dict(layers=layer_states(doc), layouts=sheets,
                                  xrefs=reference_states(doc, args.xref_dir)), indent=2))
            return 0
        overlap = {s.casefold() for s in args.on} & {s.casefold() for s in args.off}
        if overlap:
            raise ValueError('A layer cannot be both --on and --off')
        # Bind before layer changes so reference-prefixed layers can be addressed.
        if args.command != 'edit' or args.bind_xrefs:
            bind_xrefs(doc, args.xref_dir)
        else:
            # Keep references valid when the edited copy lives in another folder.
            for block in doc.blocks:
                if block.block.is_xref or block.block.is_xref_overlay:
                    resolved = resolve_xref(block.block.dxf.xref_path, doc.filename, args.xref_dir)
                    block.block.dxf.xref_path = os.path.relpath(resolved, args.output.resolve().parent)
        for name in args.off:
            set_layer(doc, name, False)
        for name in args.on:
            set_layer(doc, name, True)
        pdf = None
        if args.command == 'stamp':
            seal = read_drawing(args.seal)
            bind_xrefs(seal, args.xref_dir)
            stamp_layouts(doc, seal, args.layout, center=args.center, diameter=args.diameter,
                          date=args.date, caption=args.caption)
            if args.pdf:
                pdf = plot_layouts(doc, args.layout)
        if args.command == 'plot':
            if args.output.suffix.lower() != '.pdf':
                raise ValueError('Plot output must end in .pdf')
            pdf = plot_layouts(doc, args.layout)
        else:
            if args.command == 'stamp' and args.pdf and args.pdf.suffix.lower() != '.pdf':
                raise ValueError('--pdf output must end in .pdf')
            save_drawing(doc, args.output)
        if pdf is not None:
            destination = args.output if args.command == 'plot' else args.pdf
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open('xb') as stream:
                stream.write(pdf)
        print(json.dumps(dict(output=str(args.output), pdf=str(args.pdf) if getattr(args, 'pdf', None) else None)))
        return 0
    except (OSError, ValueError, ezdxf.DXFError, odafc.ODAFCError) as exc:
        print(f'CAD error: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
