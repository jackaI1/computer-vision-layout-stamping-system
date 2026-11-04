# Placement reference

How the tool chooses a seal position, writes PDFs and checks its results.

## How it works

1. **Prepare the seal.** [`stamper/stamp_image.py`](../stamper/stamp_image.py)
   loads the PNG and converts near-white pixels to transparency. Placement size
   is expressed in PDF points; the default whitespace diameter is 136.8 pt
   (1.9 inches). Settings live in [`stamper/config.py`](../stamper/config.py).
2. **Build occupancy.** [`stamper/occupancy.py`](../stamper/occupancy.py)
   rasterises a page to greyscale at 72 DPI by default and marks pixels darker
   than 180/255 as ink. `_integral_image` builds a zero-bordered, `uint32`
   summed-area table in O(N) time and memory for N analysis pixels.
3. **Find a designated cell.**
   [`stamper/engineer_box.py`](../stamper/engineer_box.py) searches real PDF text
   for engineer-stamp labels, transforms coordinates into displayed orientation,
   then estimates the surrounding cell from ruling lines. A fitting cell takes
   precedence over whitespace search.
4. **Search the eligible grid.** `find_min_ink_spot` in
   [`stamper/occupancy.py`](../stamper/occupancy.py) scores square seal footprints
   at 6 pt steps by default. Four summed-area lookups give each window's ink in
   O(1), rather than scanning its d × d pixels. Scoring K candidates therefore
   costs O(K) after the O(N) build, versus O(Kd²) brute force. The code rejects
   footprints outside margins or intersecting the reserved top-right rectangle.
5. **Resolve ties and measure coverage.** Among minimum-ink candidates, an
   integer binary search finds the largest ink-free square clearance bounded by
   the page. For T tied candidates and maximum padding P, this costs O(T log P).
   `disk_coverage` then measures ink within the actual circular footprint.
   That disk ratio is the reported coverage, not the square search score.
6. **Review placements.** [`stamper/placement.py`](../stamper/placement.py)
   sorts pages by descending disk coverage and sanitises stale automatic
   placements before output. [`app.py`](../app.py) exposes click-to-place, sliders,
   size/date/caption settings, per-page removal and multi-file downloads.
   [`stamper/preview.py`](../stamper/preview.py) renders review images.
7. **Write overlays.** [`stamper/pdf_writer.py`](../stamper/pdf_writer.py)
   inserts the PNG as an image object and date/caption as selectable text.
   Rotation and non-zero page origins have separate coordinate transforms.
   Default output preserves existing page content without rasterising it;
   optional flattening is a separate export choice.
## Design decisions and trade-offs

- A square approximates the circular footprint during search. It is conservative
  about nearby ink but does not optimise the exact disk ratio continuously.
- Clearance breaks ties only; extra open space never outweighs a lower ink score.
- A designated stamp cell overrides the automatic corner exclusion. Manual moves
  also remain possible, with a warning for corner overlap.
- Analysis, previews and placement use displayed page coordinates. Insertion maps
  them back to PDF coordinates, adding transformation complexity but supporting
  rotated sheets consistently.
- Preview images are cached raster composites. The exported PDF is the reference
  for typography and final appearance.
- Files share one set of sidebar settings. Bulk download produces individual PDFs;
  browsers may require permission for multiple downloads.

See [`ASSUMPTIONS.md`](../ASSUMPTIONS.md) for the seal layout, caption and
keep-out assumptions, and [`packaging/README.md`](../packaging/README.md) for the
optional Windows distribution workflow.
## Results and evaluation

Reported real-world use: stamping a drawing set went from 20 minutes to under
1 minute on the job. The demo video's “Minimum linework covered” figures, 4.5%
for hand placement and 0.3% for automatic placement, also come from real use. Neither comparison is a benchmark reproducible from these synthetic
fixtures. The repository's coverage metric is ink pixels divided by pixels in
the seal disk; it is not the fraction of all sheet linework obscured.

Reproducible here: `python examples/make_sample_sheet.py` generates both test
sheets and runs the actual placement/export path with default settings.

| Synthetic sheet | Placement source | Diameter | Disk ink coverage |
| --- | --- | ---: | ---: |
| Cover | `engineer_box` | 230.4 pt | 0.00% |
| Notes | `whitespace` | 136.8 pt | 0.16% |

These values come from the generated PDFs, not from the real-use comparison.
[`tests/test_pipeline.py`](../tests/test_pipeline.py) checks both placement paths,
all pages in a ten-sheet set, and preserved image/vector/text content.
[`tests/test_occupancy.py`](../tests/test_occupancy.py) compares the entire eligible
grid minimum and clearance result against brute-force references. No general
speed or accuracy guarantee is inferred from these fixtures.
## Limitations and known issues

- Designated-cell detection requires extractable text and recognisable ruling
  lines. Scans fall back to occupancy search; unfamiliar title blocks need review.
- Faint content above the configured greyscale threshold counts as whitespace.
  Results depend on analysis DPI, threshold and grid step.
- The caption beneath the seal is outside the footprint collision search. It may
  overhang a tight cell; shorten it, clear it or reduce the seal diameter.
- A crowded sheet can still receive a placement with non-zero coverage. Small
  sheets can shrink the seal; a completely reserved sheet fails explicitly.
- Placement is independent per page. There is no constraint that related sheets
  use a common coordinate, nor any assessment of engineering content.
- The current fresh-copy checks cover macOS source execution. The Windows
  executable and installer were not built or certified in this pass.
