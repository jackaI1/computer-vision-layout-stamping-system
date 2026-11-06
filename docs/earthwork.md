# Earthwork take-off

Use a DXF in model space with contour polylines on `CONTOURS` and exactly one
closed proposed pad or road boundary on `PAD`. Change these names with
`--contour-layer` and `--pad-layer`. Each contour vertex needs its surveyed
height: use the elevation property of a 2D polyline or the Z coordinate of a
3D polyline. Give the pad boundary vertices their proposed heights in the same
way. Use a consistent horizontal and vertical unit, such as metres; areas are
then square metres and volumes cubic metres. The DXF unit setting does not
convert coordinates. Linearize curves before exporting, and remove unrelated
entities from these layers.

```sh
python -m pip install -r requirements-earthwork.txt
python -m stamper.earthwork site.dxf --output output/site --spacing 0.5
```

The program triangulates the survey vertices and pad vertices separately and
linearly interpolates elevation within each triangle. It clips a regular grid to
the pad, samples each clipped cell at an interior point and multiplies height
difference by the clipped area. It sums positive differences as fill and
negative differences as cut. Areas are horizontal plan areas. The PDF colours
sample points by elevation difference. The table includes total area, separate
cut/fill areas and volumes, and grid spacing. A zero difference contributes to
neither cut nor fill area.

This is an estimate, not a finished engineering design. Compare results at
successively smaller grid spacings, especially across a cut/fill boundary.
The method uses unconstrained Delaunay triangles, so it does not enforce contour
segments, breaklines, holes, retaining walls, or road cross sections; pad
interior heights are interpolated from boundary vertices only. It assumes the
survey's convex hull is valid coverage and cannot detect gaps inside it. Review
that assumption and all input elevations before using the result. It rejects
pads outside the survey hull, curved polylines, conflicting elevations and
invalid boundaries. It does not calculate shrink/swell, stripping, or haul.
Existing output files in the chosen directory are replaced.
