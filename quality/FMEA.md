# FMEA: seal-stamping design and process risks

| | |
| --- | --- |
| Document | QMS-FMEA-001, revision 6, 2026-11-11 |
| Scope | Local PDF/CAD stamping, carrier inspection, review, export and change control |
| Status | Engineering assessment for a public demonstration; unsigned and not production-approved |
| Register | [Scored failure modes, controls, actions and evidence](FMEA_REGISTER.md) |
| Source | [`fmea.json`](fmea.json); generator/checker: [`fmea_report.py`](fmea_report.py) |

The aim is to prevent a plausible-looking stamped PDF from hiding drawing content,
misstating the intended seal/date, or bypassing required review. The analysis follows
this actual workflow: validate input → prepare seal → rasterize/search → honor a
labelled cell or choose whitespace → review/override → export → independently
check/authorize issue. Design modes concern software behavior; process modes concern
operator decisions, authorization and maintaining evidence.

The register covers every requirement in [`requirements.json`](requirements.json).
Each mode records effects, causes, current prevention/detection controls, S/O/D
ratings with individual rationale, and actions with role owner, status, acceptance
criteria and exact test IDs. Requirement links lead to the generated
[code/test traceability matrix](TRACEABILITY_MATRIX.md); test links lead directly
to source functions, including all parameterized cases of that function.

## Scoring method

RPN = severity × occurrence × detection (1–1000). Higher D means **harder to detect
before issue**, not better detection. These are **current-control ratings**, including
existing software checks and the prescribed human review. They are engineering
judgments based on code, known limitations and synthetic fixtures, not measured
field probabilities. No initial-to-residual improvement is claimed. A passing
regression test supports a defined software control; it does not lower severity,
measure occurrence, or prove that a human review was performed.

The following complete 1–10 scales are specific to this project. They are not an
AIAG/VDA Action Priority table or a certification. The basic S/O/D multiplication
and failure/cause/effect/action structure follow the [ASQ FMEA overview](https://asq.org/quality-resources/fmea).

| Rating | Severity: effect if failure escapes | Occurrence: cause opportunity with current controls | Detection: chance of escape before issue |
| ---: | --- | --- | --- |
| 1 | Cosmetic difference with no effect on use | Cause excluded by the defined input contract | Deterministically blocked before any output |
| 2 | Minor visible appearance defect | Exceptional unsupported input needed | Explicit refusal with a specific reason |
| 3 | Small local correction, source intact | Occasional boundary condition or manual selection | Targeted automated checks plus an obvious error/check |
| 4 | Operator repeats placement on a page | Plausible variation during normal edits/layout changes | Defined geometry/content checks; final visual check still needed |
| 5 | Multiple-page rework before handover | Common input/workflow opportunity with known control gaps | Export-specific tests help, but separate output inspection needed |
| 6 | Review interrupted or output unusable, visibly recoverable | Repeated opportunities across typical sets | Plausible output can escape synthetic checks; layout review essential |
| 7 | Wrong/missing validation evidence could conceal a regression | Cause expected on many supported inputs | Metric/test blind spot; enlarged content/identity review essential |
| 8 | Critical technical content hidden/misplaced or required stamping incomplete | Cause frequent within the intended input family | No software authority check; independent procedural check only |
| 9 | Wrong seal identity, unauthorized issue or disclosure of private seal/drawings | Cause expected on almost every normal run | No routine check likely to expose the failure before handover |
| 10 | Credible direct severe harm without further independent review; none claimed here | Cause unavoidable on every run | No effective detection before external use |

When uncertain, retain the more conservative rating and collect evidence through
PQ or a controlled deviation review. Reassess ratings after controls change;
record the reason and evidence in the change request instead of silently reducing
scores. A stronger test alone does not establish a lower real-world escape rate.

## Review priorities and action closure

- **Review before issue:** S ≥ 8 **or** RPN ≥ 160. A high-severity mode stays visible
  even when occurrence/detection estimates yield a small product.
- **Planned improvement:** remaining RPN ≥ 80.
- **Maintain controls:** remaining RPN < 80; retain tests and review assumptions.

These are project triage triggers, not risk acceptance thresholds. Equal RPNs can
have different effects. The report lists S ≥ 8 first and then sorts by descending
RPN within each severity group. Every issued file still needs all
[SOP-001 acceptance checks](SOP-001-stamp-placement.md#7-acceptance-checks).

`verified_automated` means the bounded software action has executable synthetic
regression evidence in the suite; the [IQ/OQ record](validation/IQ-OQ-EXECUTED.md)
provides the execution results. The generator validates test existence and
relationship, **not execution success**. Some tests characterize a limitation
(faint ink and caption overhang); their acceptance text explicitly preserves that
limitation. `open` means the action needs operator/PQ evidence or a future controlled
change. Its linked tests support only the software part, not human authorization or
completion. Procedural/follow-up actions remain open in this demonstration.
The carrier station mode also requires real camera and PLC adapter commissioning;
the synthetic image checks do not establish hardware readiness.

A responsible role must provide the stated acceptance evidence before closing an
open action. Keep real seal files, client drawings, approvals and issue records in
the organization's private records. If software changes are required, use
[SOP-002](SOP-002-change-control.md), add a regression test, rerun the full suite and
update this analysis. Do not convert a procedural action to `verified_automated`
merely because a related software test passes. Production acceptance needs the
engineer of record and representative PQ; neither is asserted by this repository.

## Reproduce and maintain

From the repository root with the documented development environment installed:

```sh
python quality/fmea_report.py          # validate source and generate linked register
python quality/fmea_report.py --check  # read-only CI check; fail for invalid/stale evidence
python quality/trace_matrix.py --check
python -m pytest -q
python quality/oq_report.py --check
```

After changing the register, requirements, test names or test source line numbers,
regenerate the FMEA and traceability, then execute `python quality/oq_report.py`
to renew the fingerprint and actual test results. CI checks all three records.
S/O/D accept integers 1–10 only; RPN is computed, never hand-entered. The checker
rejects missing rationales/actions/owners/acceptance criteria, duplicate mode/action
IDs, unknown requirements, missing exact tests, unrelated evidence and stale reports.

Revisit the analysis for any deviation, unfamiliar drawing family, seal-processing
change, coordinate/search/export change, changed defaults or dependency upgrade.
The principal remaining gaps are faint-content sensitivity, caption clearance,
manual overrides, external authorization, confidential-file handling and unexecuted
real-drawing PQ. See the register's open actions for their owners and closure criteria.
