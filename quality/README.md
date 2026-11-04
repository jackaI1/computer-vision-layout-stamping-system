# Quality system (GMP-style documentation for an internal tool)

This folder treats the stamp placer like regulated production software, as a demonstration.
It is truthful about scope: the tool is an internal engineering tool, and the documents are not
adopted by any organisation or signed off. Read [`GAMP5-PART11-NOTES.md`](GAMP5-PART11-NOTES.md) first
for the plain-words explanation and the honest list of gaps.

| Document | What it is |
| --- | --- |
| [`SOP-001-stamp-placement.md`](SOP-001-stamp-placement.md) | Controlled procedure for using the tool: purpose, scope, roles, steps, acceptance checks, deviations, record templates. |
| [`SOP-002-change-control.md`](SOP-002-change-control.md) | How changes are requested, assessed, tested, reviewed and released. |
| [`CHANGE_LOG.md`](CHANGE_LOG.md) | Record of changes to the validated tool. |
| [`FMEA.md`](FMEA.md), [`FMEA_REGISTER.md`](FMEA_REGISTER.md) | Design/process risk analysis: 14 scored modes, controls, owned actions and exact requirement/test links. Register generated from [`fmea.json`](fmea.json). |
| [`requirements.json`](requirements.json) | The 20 requirements: the one hand-maintained input to traceability. |
| [`TRACEABILITY_MATRIX.md`](TRACEABILITY_MATRIX.md) | Requirement to code to test, **generated**. |
| [`validation/VP-001-validation-protocol.md`](validation/VP-001-validation-protocol.md) | IQ/OQ/PQ protocol. |
| [`validation/IQ-OQ-EXECUTED.md`](validation/IQ-OQ-EXECUTED.md) | Executed IQ and OQ results, **generated** from the real test run. |

## Commands (from the repository root, virtual environment active)

```sh
python quality/fmea_report.py           # validate and generate the scored FMEA register
python quality/fmea_report.py --check    # reject invalid scores/evidence or a stale register
python quality/trace_matrix.py          # rewrite the traceability matrix from test names
python quality/trace_matrix.py --check  # fail if it is stale or traceability is broken
python quality/oq_report.py             # run IQ checks + full test suite, rewrite the IQ/OQ record
python quality/oq_report.py --check     # fail if validated files changed since the record
```

The matrix is built by reading the test files with `ast` and matching the name patterns in
`requirements.json`. It fails on a requirement with no test, a pattern that matches nothing, a code
reference that does not exist, or a test linked to no requirement. CI runs all three `--check` commands. FMEA source, method, register and quality scripts are included in the IQ/OQ fingerprint.

PQ (performance qualification on real drawings) is defined but not executed; no claim is made that it was.
