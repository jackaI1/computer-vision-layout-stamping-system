# CAD Stamping Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline, with a fresh whole-branch review.

**Goal:** Stamp editable CAD sheet copies and plot them to PDF.

**Architecture:** Keep the PDF pipeline intact. Separate CAD file/reference IO,
seal placement, plotting and CLI orchestration; use real generated DXFs in tests.

**Tech Stack:** Python 3.12, ezdxf 1.4.5, existing PyMuPDF, optional ODA converter.

**Spec:** docs/superpowers/specs/2026-11-04-cad-stamping-design.md

## Global constraints

No private data, preserve PDF behavior, explicit paper units, reject overwrite,
public PR only, all CI green on main, independent verifier PASS.

## Review focus

Missing/nested/cyclic references must fail or bind completely; layer collisions
must preserve host behavior; inch sheets and shifted origins must plot at physical
size; repeat stamping must preserve unrelated blocks; invalid CLI operations must
leave source and existing output intact.

## Tasks

- [x] 1. Write and run failing `tests/test_cad_io.py`; implement `cad_io.py` with
  read/write, layer states and recursive reference binding. Verify real roundtrips.
- [x] 2. Write and run failing `tests/test_cad_stamp.py` and `test_cad_plot.py`;
  implement normalized vector block import, owned seal replacement, paper bounds,
  fixed-size plots and visibility checks. Verify PDF geometry and viewport ink.
- [x] 3. Write and run failing `tests/test_cad_cli.py`; implement `python -m stamper.cad`
  inspect/edit/stamp/plot commands and `examples/make_sample_cad.py`, committing
  generated, public-only DXFs. Verify README commands and DWG roundtrip with ODA.
- [x] 4. Update README and `docs/cad.md`, dependency notices and pins, CI and quality
  traceability records. Run the complete suite and existing quality checks.
- [ ] 5. Fresh branch review, fix findings with regression tests, push PR, watch CI,
  squash merge, check main CI and invoke the required independent Sol verifier.

## Execution record

Baseline: 115 tests passed. Existing worktree is isolated on the requested branch,
equal to origin/main. Repository visibility is PUBLIC. No servers or browsers used.

Tasks 1-4 complete: tests were written and observed failing before the CAD
modules, then implemented against real files. Final full run: 145 passed, with
5 pre-existing PyMuPDF SWIG deprecation warnings. ODA 27.10 roundtrip passed on
macOS arm64. Dependency compatibility and all quality checks pass.

Fresh review found host xref overrides lost during binding and wide annotations
escaping paper bounds. Both have reproduced RED-to-GREEN regression cases,
including nested viewport layer properties. The reported partial-output parent
path issue is also fixed and tested. No deferred review findings remain.

Implementation decision: use ezdxf SVG with inlined styles and MuPDF conversion
because the native PDF backend truncates fractional-point paper dimensions.
Non-default shared xref layer 0/Defpoints overrides fail explicitly rather than
changing unrelated host content. Details and alternatives are in docs/cad.md.
