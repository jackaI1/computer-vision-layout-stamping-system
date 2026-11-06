"""Estimate earthwork between surveyed contours and a proposed DXF boundary."""
import argparse
import csv
import math
from pathlib import Path

import ezdxf
import numpy as np
from scipy.interpolate import LinearNDInterpolator
from scipy.spatial import ConvexHull, QhullError
from shapely.geometry import Polygon, box
from openpyxl import Workbook


def _vertices(entity):
    if entity.dxftype() == 'LWPOLYLINE':
        if any(abs(p[4]) > 1e-12 for p in entity.get_points('xyseb')):
            raise ValueError('Curved polyline segments are not supported; linearize them first')
        z = float(entity.dxf.elevation)
        return [(float(p[0]), float(p[1]), z) for p in entity.get_points()]
    if entity.dxftype() == 'POLYLINE':
        if not (entity.is_2d_polyline or entity.is_3d_polyline):
            raise ValueError('Only 2D and 3D polylines are supported')
        points = []
        for v in entity.vertices:
            if abs(v.dxf.get('bulge', 0)) > 1e-12:
                raise ValueError('Curved polyline segments are not supported; linearize them first')
            p = v.dxf.location
            z = p.z if entity.is_3d_polyline else entity.dxf.elevation.z
            points.append((float(p.x), float(p.y), float(z)))
        return points
    raise ValueError('Only polylines are supported on input layers')


def _surface(points):
    unique = {}
    for x, y, z in points:
        if not all(math.isfinite(v) for v in (x, y, z)):
            raise ValueError('Coordinates must be finite')
        if (x, y) in unique and not math.isclose(unique[x, y], z, abs_tol=1e-9):
            raise ValueError('Conflicting elevations at the same coordinate')
        unique[x, y] = z
    a = np.array([(x, y, z) for (x, y), z in unique.items()])
    if len(a) < 3:
        raise ValueError('Each surface needs at least three distinct points')
    try:
        hull = ConvexHull(a[:, :2])
        return LinearNDInterpolator(a[:, :2], a[:, 2]), Polygon(a[hull.vertices, :2])
    except QhullError as exc:
        raise ValueError('Surface points must not be collinear') from exc


def calculate(path, spacing=1.0, contour_layer='CONTOURS', pad_layer='PAD', _cells=None):
    if not math.isfinite(spacing) or spacing <= 0:
        raise ValueError('Grid spacing must be positive and finite')
    doc = ezdxf.readfile(path)
    entities = list(doc.modelspace())
    contours = [e for e in entities if e.dxf.layer.casefold() == contour_layer.casefold()]
    pads = [e for e in entities if e.dxf.layer.casefold() == pad_layer.casefold()]
    if not contours or len(pads) != 1:
        raise ValueError('Expected contours and exactly one closed pad polyline')
    pad = pads[0]
    if pad.dxftype() not in ('LWPOLYLINE', 'POLYLINE') or not pad.is_closed:
        raise ValueError('Pad must be a closed polyline')
    boundary = _vertices(pad)
    polygon = Polygon([(x, y) for x, y, _ in boundary])
    if not polygon.is_valid or polygon.area <= 0:
        raise ValueError('Pad boundary must be a valid polygon')
    ground, coverage = _surface([p for e in contours for p in _vertices(e)])
    proposed, _ = _surface(boundary)
    if not coverage.buffer(1e-8).covers(polygon):
        raise ValueError('Survey coverage does not contain the entire pad')
    minx, miny, maxx, maxy = polygon.bounds
    nx, ny = math.ceil((maxx-minx)/spacing), math.ceil((maxy-miny)/spacing)
    if nx * ny > 1_000_000:
        raise ValueError('Grid exceeds one million cells; increase spacing')
    cut = fill = cut_area = fill_area = 0.0
    for i in range(nx):
        for j in range(ny):
            part = polygon.intersection(box(minx+i*spacing, miny+j*spacing, minx+(i+1)*spacing, miny+(j+1)*spacing))
            if part.is_empty or part.area == 0:
                continue
            # A representative point remains inside even for concave clipped cells.
            point = part.representative_point()
            delta = float(proposed(point.x, point.y)) - float(ground(point.x, point.y))
            if not math.isfinite(delta):
                raise ValueError('Surface interpolation failed inside the pad')
            if delta > 0:
                fill += delta * part.area
                fill_area += part.area
            elif delta < 0:
                cut -= delta * part.area
                cut_area += part.area
            if _cells is not None:
                _cells.append((point.x, point.y, delta, part.area))
    return dict(area=polygon.area, cut_area=cut_area, fill_area=fill_area, cut_volume=cut, fill_volume=fill, grid_spacing=spacing)


def run(path, output_dir, spacing=1.0, contour_layer='CONTOURS', pad_layer='PAD'):
    cells = []
    result = calculate(path, spacing, contour_layer, pad_layer, cells)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    with (output / 'quantities.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(result))
        writer.writeheader()
        writer.writerow(result)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Quantities'
    sheet.append(list(result))
    sheet.append(list(result.values()))
    workbook.save(output / 'quantities.xlsx')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(11.7, 8.3))
    x, y, d, area = zip(*cells)
    plot = ax.scatter(x, y, c=d, cmap='coolwarm', marker='s', s=20)
    fig.colorbar(plot, ax=ax, label='Proposed minus existing elevation')
    doc = ezdxf.readfile(path)
    for e in doc.modelspace():
        if e.dxf.layer.casefold() in (contour_layer.casefold(), pad_layer.casefold()):
            pts = _vertices(e)
            if e.is_closed:
                pts = pts + pts[:1]
            ax.plot([p[0] for p in pts], [p[1] for p in pts], color='black', linewidth=0.8)
    ax.set_aspect('equal')
    ax.set_title(f'Earthwork layout | Cut {result["cut_volume"]:.2f} | Fill {result["fill_volume"]:.2f}')
    ax.set_xlabel('X'); ax.set_ylabel('Y')
    fig.tight_layout()
    fig.savefig(output / 'layout.pdf')
    plt.close(fig)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dxf')
    parser.add_argument('--output', required=True)
    parser.add_argument('--spacing', type=float, default=1.0)
    parser.add_argument('--contour-layer', default='CONTOURS')
    parser.add_argument('--pad-layer', default='PAD')
    args = parser.parse_args()
    try:
        print(run(args.dxf, args.output, args.spacing, args.contour_layer, args.pad_layer))
    except (ValueError, OSError, ezdxf.DXFError) as exc:
        parser.exit(2, f'Error: {exc}\n')


if __name__ == '__main__':
    main()
