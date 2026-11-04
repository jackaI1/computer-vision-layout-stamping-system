# Computer Vision Layout Stamping System

A local tool for placing seal images on PDF drawing sheets and reviewing them before export.

## Overview

Putting a seal on every sheet is repetitive, but using the same position each
time can cover notes or linework. This tool looks for a designated stamp cell
first, then for an open area if there isn't one. It puts the crowded placements
first so I can check them, move or remove a seal, and download the finished PDFs.

I built this during an engineering co-op. The public project uses generated
sheets and a demonstration seal, with no client drawings or real professional
seal. Start with the sample below; applying an image does not approve a drawing.

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

## Checking placements

I can change the seal size, date and caption in the sidebar. The tool preserves
the original PDF content by default; flattening is a separate export option.
A crowded sheet can still get a placement over some linework. Faint lines may
be treated as empty space, and the caption below a seal is outside the area
checked for collisions. Review the actual exported PDF before using it.

[Placement details](docs/placement.md) explain the search, coordinate handling,
synthetic results and limitations. [ASSUMPTIONS.md](ASSUMPTIONS.md) records the
seal layout and reserved areas. The reported reduction from twenty minutes to
under one minute came from real use, not the public sample sheets.

## Repeatable checks

I keep a [placement procedure](quality/SOP-001-stamp-placement.md) so the input,
review and export checks are written down. The [risk register](quality/FMEA_REGISTER.md)
records what could go wrong, the current checks and work still left open.
The [register notes](docs/risk-register.md) explain how its links are checked. The
[change procedure](quality/SOP-002-change-control.md) helps decide what to retest
when the tool changes.

The [quality notes](quality/README.md) link requirements to code and tests, and
include a generated record of installation and software checks. These are
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

## Demo

https://github.com/user-attachments/assets/b15a6e9c-6d9e-455d-9c16-bb4cde0c89b9

## License

Developed at D.L. Engineering Inc. and published with the firm's written
permission. Client drawings, firm documents, internal identifiers and proprietary
data are excluded.

Original source is MIT; see [LICENSE](LICENSE). PyMuPDF is AGPL-3.0, with source
and licence obligations for combined distributions and some network deployments.
Other dependency and build-tool terms are in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
