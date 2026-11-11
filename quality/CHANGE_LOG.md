# Change Log

Controlled by [SOP-002](SOP-002-change-control.md). Newest first. Class is Documentation, Minor or Major.

| CR | Date | Commit | Class | Change | Requirements affected | Validation evidence |
| --- | --- | --- | --- | --- | --- | --- |
| CR-005 | 2026-11-11 | this change's squash commit | Minor (new quality tooling and a batch search path; the single-page placement is unchanged) | Added `quality/rtm.py`: CSV and ReqIF import with stable IDs, export, baselines, a coverage matrix, baseline gap report and a DXL-style check that fails CI when a requirement has no design element or test. Added a batch least-ink page search (`stamper/window_search.py`) with a Triton kernel, PyTorch and NumPy backends, a benchmark with an equivalence check and a stored-threshold gate, and a profile script. Added REQ-28 to REQ-30 and FM-19 to FM-21. | REQ-27, REQ-28, REQ-29, REQ-30; FM-19 to FM-21 | Suite 253 to passing count in the regenerated IQ/OQ record; the Triton kernel runs under TRITON_INTERPRET in the new GPU-search workflow. No GPU timing or Nsight trace exists yet. |
| CR-004 | 2026-11-05 | this change's squash commit | Minor (separate station command) | Added calibrated carrier presence and 1D/2D identity checks, fail-low JSON, a 44-case lighting sweep and 85 station tests. Added station risk review and real-camera/PLC commissioning follow-up. | REQ-26 | 239 passed locally with the real ODA converter enabled; CI also executes the real ODA roundtrip separately. See the regenerated IQ/OQ record. |
| CR-003 | 2026-11-03 | this change's squash commit | Minor (quality tooling and test additions; application behavior unchanged) | Added 14-mode design/process FMEA with S/O/D rationale, calculated RPN, 28 owned actions and exact requirement/test evidence; CI checks integrity and report freshness. Added REQ-20, two synthetic characterizations of faint-ink/caption limits and 35 FMEA cases. Extended IQ/OQ fingerprints to FMEA artifacts and quality scripts. | REQ-01, REQ-04, REQ-13, REQ-19, REQ-20; risk review covers all 20 requirements | Suite 78 to 115 passing; all three quality checks current; [executed IQ/OQ](validation/IQ-OQ-EXECUTED.md). Human/PQ follow-ups remain open; no production approval claimed. |
| CR-002 | 2026-11-03 | this change's squash commit | Documentation + test additions (no change to application code) | Introduced the `quality/` system: SOP-001, SOP-002, requirements, generated traceability matrix, VP-001 (IQ/OQ/PQ), IQ/OQ execution record, CI gate. Added 16 tests (`test_stamp_image.py`, `test_controls.py`, `test_quality_tools.py`) to close verification gaps found while building the matrix: seal preparation (REQ-14), bad-input messages (REQ-16), no network imports (REQ-17), quality scripts (REQ-19). | REQ-14, REQ-16, REQ-17, REQ-19 (new or newly verified) | Suite 62 to 78 passing; traceability complete; IQ/OQ executed ([record](validation/IQ-OQ-EXECUTED.md)). |
| CR-001 | 2026-11-03 | n/a | Baseline | Retrospective baseline. History before CR-002 was not individually change-controlled; it is listed below from Git for completeness. The 62 tests existing at that point are the baseline. | all | 62 passing before CR-002 |

## Pre-QMS history (reconstructed from Git, not individually controlled)

| Date | Commit | Subject |
| --- | --- | --- |
| 2026-10-28 | `5e37d7b` | README: update demo video |
| 2026-10-23 | `ce370ee` | Docs: replace em dashes |
| 2026-10-22 | `25b5f9e` | README: restore firm publication permission note |
| 2026-10-19 | `b4de610` | Update demo video end screen |
| 2026-10-19 | `fb36632` | Rewrite README as technical documentation |
| 2026-10-19 | `6cc55df` | Add licence notices and pin dependencies |
| 2026-10-19 | `67909cb` | Make the code match the demo video and prepare for public release |
| 2026-10-19 | `b122c02` | Replace demo GIF with demo video |
| 2026-08-13 | `663cc20` | Initial commit |
