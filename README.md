# Computer Vision Layout Stamping System

A local PDF tool that places seal images in designated cells or low-ink regions, lets an operator review each placement, and exports stamped PDFs.

https://github.com/user-attachments/assets/b15a6e9c-6d9e-455d-9c16-bb4cde0c89b9

## Overview

Placing a seal across a drawing set requires checking title-block conventions,
reserved corners and underlying linework on every sheet. Repeating a fixed
coordinate can cover content when layouts differ.

The tool searches for a designated engineer-stamp cell first. Otherwise it scores
a grid over the page, excluding margins and a reserved corner. It orders results
by ink coverage so the operator can inspect difficult placements first, move or
remove individual seals, then download the PDFs.

Built during an engineering co-op, the public repository uses synthetic sheets
and a generated demonstration seal. It contains no real professional seal or
project drawings. Applying an image does not perform engineering approval.

## How it works

1. **Prepare the seal.** [`stamper/stamp_image.py`](stamper/stamp_image.py)
   loads the PNG and converts near-white pixels to transparency. Placement size
   is expressed in PDF points; the default whitespace diameter is 136.8 pt
   (1.9 inches). Settings live in [`stamper/config.py`](stamper/config.py).
2. **Build occupancy.** [`stamper/occupancy.py`](stamper/occupancy.py)
   rasterises a page to greyscale at 72 DPI by default and marks pixels darker
   than 180/255 as ink. `_integral_image` builds a zero-bordered, `uint32`
   summed-area table in O(N) time and memory for N analysis pixels.
3. **Find a designated cell.**
   [`stamper/engineer_box.py`](stamper/engineer_box.py) searches real PDF text
   for engineer-stamp labels, transforms coordinates into displayed orientation,
   then estimates the surrounding cell from ruling lines. A fitting cell takes
   precedence over whitespace search.
4. **Search the eligible grid.** `find_min_ink_spot` in
   [`stamper/occupancy.py`](stamper/occupancy.py) scores square seal footprints
   at 6 pt steps by default. Four summed-area lookups give each window's ink in
   O(1), rather than scanning its d × d pixels. Scoring K candidates therefore
   costs O(K) after the O(N) build, versus O(Kd²) brute force. The code rejects
   footprints outside margins or intersecting the reserved top-right rectangle.
5. **Resolve ties and measure coverage.** Among minimum-ink candidates, an
   integer binary search finds the largest ink-free square clearance bounded by
   the page. For T tied candidates and maximum padding P, this costs O(T log P).
   `disk_coverage` then measures ink within the actual circular footprint.
   That disk ratio is the reported coverage, not the square search score.
6. **Review placements.** [`stamper/placement.py`](stamper/placement.py)
   sorts pages by descending disk coverage and sanitises stale automatic
   placements before output. [`app.py`](app.py) exposes click-to-place, sliders,
   size/date/caption settings, per-page removal and multi-file downloads.
   [`stamper/preview.py`](stamper/preview.py) renders review images.
7. **Write overlays.** [`stamper/pdf_writer.py`](stamper/pdf_writer.py)
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

See [`ASSUMPTIONS.md`](ASSUMPTIONS.md) for the seal layout, caption and
keep-out assumptions, and [`packaging/README.md`](packaging/README.md) for the
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
[`tests/test_pipeline.py`](tests/test_pipeline.py) checks both placement paths,
all pages in a ten-sheet set, and preserved image/vector/text content.
[`tests/test_occupancy.py`](tests/test_occupancy.py) compares the entire eligible
grid minimum and clearance result against brute-force references. No general
speed or accuracy guarantee is inferred from these fixtures.

## Getting started

Use CPython 3.12; the fresh-copy check used 3.12.14 on macOS arm64.
The image-coordinate component requires Python 3.10 or later; Python 3.12 is the
verified environment for the pinned dependency set.
Run these commands from the repository root:

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python examples/make_sample_sheet.py
```

The command writes `examples/sample_seal.png`, `sample_cover.pdf`,
`sample_notes.pdf` and the two `_stamped.pdf` outputs in `examples/`. Its console
output reports the placement sources and coverage values in the table above.
All of these inputs are synthetic.

For interactive review:

```sh
python -m streamlit run app.py --server.address=127.0.0.1 --server.port=8501 --server.headless=true --browser.gatherUsageStats=false
```

Open `http://127.0.0.1:8501`, choose the generated seal and upload the generated
sheet PDFs. Review the ordered pages, move a seal or remove it if needed, then
use the per-file download. Output filenames end in `_stamped.pdf`. Stop the
server with Ctrl-C. No accounts, API keys or OCR executable are required.

Dependencies are pinned in [`requirements.txt`](requirements.txt) with
[`requirements-lock.txt`](requirements-lock.txt) constraining the transitive
resolution. The Streamlit/Starlette pins include a media-response compatibility
fix covered by [`tests/test_runtime_compat.py`](tests/test_runtime_compat.py).

## Testing

```sh
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

The current suite has 78 passing tests, grouped as follows:

- [`tests/test_occupancy.py`](tests/test_occupancy.py): integral sums versus brute
  force, full-grid minima, exact tie clearance, margins, keep-out and disk scores.
- [`tests/test_pipeline.py`](tests/test_pipeline.py): designated cells, fallback
  search, ten-page output, small-page failures, stale placement correction,
  removals, overlay preservation, all four right-angle rotations and non-zero origins.
- [`tests/test_ui.py`](tests/test_ui.py): settings, mixed sheet sizes, manual
  edits/removal reaching actual download bytes, seal-cache invalidation and bulk
  download behaviour through Streamlit AppTest.
- [`tests/test_runtime_compat.py`](tests/test_runtime_compat.py): media responses
  with identity and gzip encoding.
- [`tests/test_stamp_image.py`](tests/test_stamp_image.py): seal background
  knock-out, edge-artefact removal, trimming and content hash.
- [`tests/test_controls.py`](tests/test_controls.py): unreadable and
  password-protected PDFs are rejected with a reason; the `stamper` package
  imports no network modules.
- [`tests/test_quality_tools.py`](tests/test_quality_tools.py): the traceability
  and IQ/OQ scripts in [`quality/`](quality/).

Fixtures are generated locally. PyMuPDF may emit upstream SWIG deprecation
warnings. Windows executable packaging is outside these tests.

## Project structure

```text
stamper/                     occupancy, cell detection, placement and PDF overlays
app.py                       Streamlit interface
desktop_app.py              optional desktop entry point
examples/make_sample_sheet.py  synthetic sheets and demonstration seal
tests/                      numerical, PDF and UI regressions
packaging/                   Windows build scripts and installer specification
ASSUMPTIONS.md               adjustable drawing and seal conventions
quality/                     SOPs, change control, traceability, IQ/OQ/PQ validation
.github/workflows/ci.yml     tests plus traceability and validation-record checks
```

## Quality system (GMP-style documentation)

[`quality/`](quality/) documents the tool as if it were regulated production
software, using GAMP 5 and 21 CFR Part 11 ideas explained in plain words. It is
a demonstration for an internal engineering tool: the documents are unsigned,
not adopted by any organisation, and PQ on real drawings is defined but not
executed. [`quality/GAMP5-PART11-NOTES.md`](quality/GAMP5-PART11-NOTES.md) lists
what the tool does not provide (no audit trail, no log-in, no electronic signatures).

```sh
python quality/trace_matrix.py   # regenerate requirement -> code -> test matrix
python quality/oq_report.py      # run IQ checks and the full suite, write the OQ record
```

## Skills demonstrated

| Skill | What it does in this project | Where |
| --- | --- | --- |
| GMP-style SOP writing | Controlled procedure for applying seals: scope, roles, steps, acceptance checks, deviations, record templates | [`quality/SOP-001-stamp-placement.md`](quality/SOP-001-stamp-placement.md) |
| Change control | Change classes, impact assessment, revalidation rules and a change log | [`quality/SOP-002-change-control.md`](quality/SOP-002-change-control.md), [`quality/CHANGE_LOG.md`](quality/CHANGE_LOG.md) |
| Requirements traceability | 19 requirements linked to code and tests; a script regenerates the matrix from test names and CI fails on gaps | [`quality/requirements.json`](quality/requirements.json), [`quality/trace_matrix.py`](quality/trace_matrix.py), [`quality/TRACEABILITY_MATRIX.md`](quality/TRACEABILITY_MATRIX.md) |
| IQ/OQ/PQ validation | Protocol plus an executed IQ/OQ record generated from the real test run, tied to the tested files by SHA-256 | [`quality/validation/`](quality/validation/), [`quality/oq_report.py`](quality/oq_report.py) |
| Continuous integration | Runs the suite and both quality checks on every pull request | [`.github/workflows/ci.yml`](.github/workflows/ci.yml) |

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

## License

Developed at D.L. Engineering Inc. and published with the firm's written
permission. Client drawings, firm documents, internal identifiers and
proprietary data are excluded.

Original project source is MIT; see [`LICENSE`](LICENSE). PyMuPDF 1.26.7 is
AGPL-3.0: combined distributions require applicable corresponding-source and
licence compliance, and network deployments may require source access. MIT does
not waive those terms. Other dependencies and optional Windows build-tool
exceptions are documented in [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).
