# Computer Vision Layout Stamping System

I built a drawing-stamping tool because placing the same seal on every sheet by hand took time, and a fixed position could cover notes or linework.

## Overview

I give it a seal image and a set of drawings. It looks for a box marked for the
seal, then searches for an open area if there isn't a suitable box. It shows me
the placements covering the most drawing content first, so I can check those
before exporting. I can move or remove any seal and download the finished PDFs.

I can also stamp an editable CAD drawing, the drawing file used by AutoCAD.
This lets me keep its layers, which group items such as walls and furniture,
and its sheet layouts instead of exporting to PDF first. The CAD commands below
make a stamped drawing copy and a PDF I can review.

I built the original during an engineering co-op. This public version uses
generated sheets and a demonstration seal, with no client drawings or real
professional seal. To try it, run the sample below and review the suggested
positions in the browser. Applying an image does not approve a drawing.

I also use a [station check](docs/station.md) to check that a drawing or seal
carrier is loaded in a fixed position and that its two labels match the expected
drawing and revision. It reports PASS or FAIL from an image. To try that example
after the Python setup below, run `python -m stamper.station_demo`; it creates
the images and a lighting-test report in `output/station/`.

## Try it

Use Python 3.12. From the repository root:

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python examples/make_sample_sheet.py
python -m streamlit run app.py --server.address=127.0.0.1 --server.port=8501 --server.headless=true --browser.gatherUsageStats=false
```

Open <http://127.0.0.1:8501>. Choose `examples/sample_seal.png` and upload
`examples/sample_cover.pdf` and `examples/sample_notes.pdf`. Check each placement,
move or remove it if needed, then download the PDFs. Output names end in
`_stamped.pdf`. Stop the app with Ctrl-C. No account or API key is needed.

The sample generator also writes stamped examples without opening the app.
For the optional Windows package, see the [packaging guide](packaging/README.md).

## Stamp editable drawings

I use the command line for CAD drawings. DXF is an exchange format AutoCAD can
open; it works with the same Python setup above, without an AutoCAD installation.
The example includes a generated floor plan, two sheets and a seal marked
"DEMO / NOT VALID".

```sh
python -m stamper.cad inspect examples/cad/floor_plan.dxf
python -m stamper.cad edit examples/cad/floor_plan.dxf --off FURNITURE --bind-xrefs -o output/cad/plan.dxf
python -m stamper.cad stamp output/cad/plan.dxf --seal examples/cad/demo_seal.dxf --layout A101 --layout A102 --center 350 180 --diameter 40 --date 2026-11-04 --caption "DEMONSTRATION ONLY" -o output/cad/plan_stamped.dxf --pdf output/cad/plan_stamped.pdf
```

I open `output/cad/plan_stamped.pdf` to review the two sheets, and open the DXF
in a CAD editor to keep editing. The commands create new files and refuse to
overwrite existing output. To repeat the example, choose new output names.

The first command lists layers, sheets and xrefs, which are links to other
drawing files. The second hides furniture and binds those links, meaning it
copies their drawing content into the output so the copy can travel on its own.
`--on FURNITURE` shows furniture again. The last command places a reusable seal
block, a group of drawing objects, on the `STAMPER_SEAL` layer in the selected
sheet layouts. I can hide that layer to hide the seal, date and caption together.

For this sample, the centre is 350 mm right and 180 mm up from the sheet origin,
and the seal diameter is 40 mm. I choose and review the CAD position explicitly;
the automatic open-space search belongs to the PDF workflow. My own vector seal
can be supplied as a DXF with the seal geometry in model space, the drawing's
main working area. DWG, AutoCAD's native format, also works with the separately
installed free ODA converter. [The CAD guide](docs/cad.md) covers that setup,
reference folders, plotting existing drawings, and limitations.

## Review before exporting

I change the seal size, date and caption in the sidebar. By default, export
adds the seal while keeping the original PDF content. Flattening, which turns
each sheet into a single image, is a separate option.
A crowded sheet can still get a placement over some linework. Faint lines may
be treated as empty space, and the caption below a seal is outside the area
checked for collisions. Review the actual exported PDF before using it.

[Placement details](docs/placement.md) explain the search, coordinate handling,
synthetic results and limitations. [ASSUMPTIONS.md](ASSUMPTIONS.md) records the
seal layout and reserved areas. The reported reduction from twenty minutes to
under one minute came from real use, not the public sample sheets.

## Before offering it to another firm

I keep a [commercialization assessment](docs/commercialization.md) to decide
what evidence I need before a wider release. It rates the public PDF prototype
on a nine-level readiness scale, compares nearby patent publications and maps
possible Canadian research support. It also explains the licence and the real
drawing checks I still need. I can check its citations without an account:

```sh
python scripts/check_commercialization.py
```

Add `--online` to recheck patent publication numbers and titles against their
source pages. The assessment distinguishes reported workplace use from tests
that anyone can reproduce here.

## How the placement works

The browser interface is built with Streamlit, a Python tool for interactive
pages. The placement code renders each sheet as a grayscale image and counts
dark pixels to find areas with less drawing content. It checks marked stamp
boxes first and otherwise avoids a reserved corner. A separate PDF writer adds
the chosen image, date and caption to the original document.

I keep the search and export details in [the placement guide](docs/placement.md),
including rotated pages and cases where an apparently empty area is unsafe.

## Check a labelled part

The station command compares a camera image with an empty fixture image. It
checks a fixed area for the part and reads a barcode and a square QR label from
their own areas. I use the expected drawing number and revision to reject a
loaded carrier with the wrong labels. A missing part, unreadable code or poor
image produces FAIL.

```sh
python -m stamper.station_demo --output-dir output/station
python -m stamper.station --image output/station/present.png --empty output/station/empty.png --recipe output/station/recipe.json
```

The second command prints a JSON record with `status`, reasons, measured part
area and the decoded labels. `plc_pass` is 1 only when every check passes, and
0 on failure. A PLC is a machine controller; this value is for an output adapter,
not an electrical signal. The example runs locally without a camera or account.
The [station guide](docs/station.md) explains camera calibration, the low-output
fault behavior and how to inspect my own images.

## Repeatable checks

I keep a [placement procedure](quality/SOP-001-stamp-placement.md) so the input,
review and export checks are written down. I use a failure mode and effects
analysis, a structured review of what can go wrong, to maintain the
[risk register](quality/FMEA_REGISTER.md). It records current checks and work
still left open.
The [register notes](docs/risk-register.md) explain how its links are checked. The
[change procedure](quality/SOP-002-change-control.md) helps decide what to retest
when the tool changes.

The [quality notes](quality/README.md) link requirements to code and tests.
The generated installation qualification and operational qualification record,
or IQ/OQ record, captures installation checks and executed software tests. These are
unsigned practice documents. They have not been adopted by an organisation;
checks on real drawings remain unperformed. The
[scope notes](quality/GAMP5-PART11-NOTES.md) explain the missing controls, including
an audit trail, sign-in and electronic signatures.

```sh
python -m pip install -r requirements-dev.txt
python -m pytest -q
python quality/fmea_report.py --check
python quality/trace_matrix.py --check
python quality/oq_report.py --check
```

To regenerate a report, omit `--check`. The last command then runs the full test
suite and writes a new installation/software-check record. Tests use generated
sheets and cover placement, PDF output, interface controls and the quality scripts.
The station adds 85 tests and a 44-image lighting and contrast sweep, including
low light and glare. The sweep measured 44/44 expected decisions with zero false
passes and zero false rejects on generated images. This is not a real-station
accuracy claim. CI saves the images and report for inspection.
Continuous integration (CI), the checks GitHub runs for each change, also rejects
stale risk registers, requirement links and saved test records.

## Demo

https://github.com/user-attachments/assets/b15a6e9c-6d9e-455d-9c16-bb4cde0c89b9

## License

Developed at D.L. Engineering Inc. and published with the firm's written
permission. Client drawings, firm documents, internal identifiers and proprietary
data are excluded.

Original source is MIT; see [LICENSE](LICENSE). PyMuPDF is AGPL-3.0, with source
and licence obligations for combined distributions and some network deployments.
Other dependency and build-tool terms are in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
