# VP-001 Validation Protocol: Engineering Stamp Placer (IQ / OQ / PQ)

| | |
| --- | --- |
| Document | QMS-VP-001 |
| Version | 1.0 (draft, 2026-11-03) |
| Author | Jack Lai |
| Status | **Demonstration document.** IQ and OQ are executed automatically; PQ is defined but not executed. |
| Related | [Requirements](../requirements.json), [Traceability matrix](../TRACEABILITY_MATRIX.md), [IQ/OQ record](IQ-OQ-EXECUTED.md), [SOP-001](../SOP-001-stamp-placement.md) |

## 1. Purpose

To show, with evidence, that the tool is installed correctly (IQ), meets its written
requirements (OQ), and works for real drawings in real use (PQ).

## 2. Scope and intended use

Intended use: place an authorised seal image, date and caption on PDF drawings on one operator's
computer, with a human reviewing every page. In scope: `stamper/`, `app.py`, `desktop_app.py`
and the pinned dependencies. Out of scope: the Windows installer, engineering judgement, seal custody.

## 3. Approach (risk-based)

Requirements carry a risk rating (High/Medium/Low). Every requirement must have at least one
automated test; High-risk requirements are checked against independent references (for example
brute-force searches) or all rotations. Traceability is checked by `quality/trace_matrix.py`.

## 4. Responsibilities

Executor runs the stages; Tool owner reviews results and raises deviations; Approver accepts the
validated state. For IQ/OQ the executor is the script, and in this demonstration there is no
human reviewer or approver.

## 5. Acceptance rule

A stage passes only if every listed check passes. Any failure is a deviation (SOP-001 section 8)
and the tool is not in a validated state until it is resolved and the stage is re-run.

## 6. Installation Qualification (IQ)

| Step | Check | Acceptance |
| --- | --- | --- |
| IQ-1 | Python version | 3.10 or later (3.12 is the verified version). |
| IQ-2 | Every package in `requirements-lock.txt` is installed at exactly the pinned version | No mismatch and none missing. |
| IQ-3 | `import stamper` works | No exception. |

Executed by `python quality/oq_report.py`; results in the first table of the [record](IQ-OQ-EXECUTED.md).
Setup: `python3.12 -m venv .venv && source .venv/bin/activate && python -m pip install -r requirements-dev.txt`.

## 7. Operational Qualification (OQ)

| Step | Check | Acceptance |
| --- | --- | --- |
| OQ-1 | Traceability: every requirement has a test, every test a requirement, every code reference exists | `trace_matrix.py` reports no errors. |
| OQ-2 | Run the full suite with `python -m pytest -q` | No failed, errored or skipped test. |
| OQ-3 | Each requirement's linked tests all pass | Every requirement row in the record reads PASS. |
| OQ-4 | The record names the exact files tested | Combined SHA-256 fingerprint is present; `oq_report.py --check` passes on the same tree. |

The OQ results are never typed in: `oq_report.py` runs pytest, reads its JUnit XML and writes the record.
OQ uses only generated PDFs and a drawn seal. See the [matrix](../TRACEABILITY_MATRIX.md) for which test
verifies which requirement.

## 8. Performance Qualification (PQ): protocol, not executed

PQ needs representative drawings and a trained operator, so it cannot be run by script or from this
public repository. To execute: follow SOP-001 on a representative real set (for example 10 or more sheets
with at least one sheet with a designated cell, one without, one rotated, one with dense linework), then record:

| Step | Check | Acceptance |
| --- | --- | --- |
| PQ-1 | Run SOP-001 end to end by a trained Operator | Procedure can be followed without workarounds. |
| PQ-2 | Checks A1 to A7 on every output file | All pass. |
| PQ-3 | Independent checker repeats A2 to A5 on a sample (all sheets for issued sets) | No disagreement with the Operator. |
| PQ-4 | Time and corrections recorded | Operator records time taken and the number of manual moves; no pass limit is set here. |
| PQ-5 | Any deviation | Raised and closed per SOP-001 section 8. |

Reference smoke check (reproducible, synthetic): `python examples/make_sample_sheet.py` should report the cover sheet
placed by `engineer_box` at 230.4 pt with 0.00% ink, and the notes sheet by `whitespace` at 136.8 pt with 0.16% ink.
This was run when this protocol was written and matched. It is a smoke check, not PQ.

**PQ status: NOT EXECUTED.** No claim of performance qualification is made.

## 9. Revalidation triggers

Any change to a validated file (the `oq_report.py --check` fingerprint changes), a dependency bump, a move to
a different Python version or operating system, or a repeated deviation. See SOP-002.

## 10. Reporting

The IQ/OQ record is the report for those stages. A PQ report, if executed, is filed beside it with the
Operator's and Approver's signatures.

## Approval

| Role | Name | Signature | Date |
| --- | --- | --- | --- |
| Author | Jack Lai | _not signed_ | |
| Approver | _none (demonstration)_ | | |
