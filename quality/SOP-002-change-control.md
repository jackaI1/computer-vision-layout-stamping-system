# SOP-002 Change Control for the Engineering Stamp Placer

| | |
| --- | --- |
| Document | QMS-SOP-002 |
| Version | 1.0 (draft, 2026-11-03) |
| Author | Jack Lai |
| Status | **Demonstration document.** Not adopted or approved by any organisation. |
| Related | [SOP-001](SOP-001-stamp-placement.md), [Change log](CHANGE_LOG.md), [VP-001](validation/VP-001-validation-protocol.md) |

## 1. Purpose

To make sure that any change to the tool is proposed, assessed, tested, approved and
recorded before it is used on issued drawings, so the tool stays in a validated state.

## 2. Scope

Changes to: `stamper/`, `app.py`, `desktop_app.py`, default settings in `stamper/config.py`,
dependency pins (`requirements*.txt`), the tests, `quality/requirements.json`, and the
seal conventions in `ASSUMPTIONS.md`. The FMEA source, method, generated register and quality scripts are also controlled and fingerprinted. Documentation-only changes outside the validated file set follow section 8.

## 3. Responsibilities

| Role | Responsibility |
| --- | --- |
| Requester | Describes the change and why. |
| Tool owner | Assesses impact, implements or assigns, keeps records, executes revalidation. |
| Reviewer | A person other than the implementer who reviews the pull request and evidence. |
| Approver | Engineer or manager who accepts the risk of releasing the change for production use. |

## 4. Change classes

| Class | Examples | Revalidation needed |
| --- | --- | --- |
| Documentation only | README, SOP wording, comments | None. Log it. |
| Minor | Wording of a message, UI layout, a bug fix that does not change placement or output | Full automated suite; regenerate traceability and IQ/OQ. |
| Major | Placement algorithm, default settings, PDF writing, seal preparation, new dependency or version bump, new requirement | Minor items, plus new or updated tests for each affected requirement, risk review, and PQ on representative drawings. |
| Emergency | Tool is producing wrong output now | Stop use (SOP-001 section 8). Fix on a branch, run the same checks as above, record the change afterwards within 2 working days. |

When unsure, treat the change as Major.

## 5. Procedure

1. **Request.** Open a GitHub issue or write the request with a number `CR-nnn`: what, why, urgency.
2. **Impact assessment.** List the requirements affected (use [`requirements.json`](requirements.json) and the
   [traceability matrix](TRACEABILITY_MATRIX.md) to find code and tests), the risk (High/Medium/Low as listed),
   and the class from section 4. Review the affected failure modes and open actions in [the FMEA](FMEA_REGISTER.md); reassess ratings when controls or intended inputs change. If placement output can change, note that `PLACEMENT_LOGIC_VERSION` in
   `stamper/placement.py` must be increased so cached placements are not reused.
3. **Approval to proceed.** The Approver agrees the class and plan (a comment on the issue is enough).
4. **Implement** on a new branch, never directly on `main`.
5. **Test.** Add or update tests for every affected requirement. New tests must be linked to a requirement
   in `requirements.json`; a new requirement needs at least one test.
6. **Regenerate the records:**
   - `python quality/fmea_report.py` validates scoring and action evidence and rewrites the FMEA register;
   - `python quality/trace_matrix.py` rewrites the traceability matrix;
   - `python quality/oq_report.py` runs the installation checks and the full test suite and rewrites
     [`validation/IQ-OQ-EXECUTED.md`](validation/IQ-OQ-EXECUTED.md).
7. **Review.** Open a pull request. The description states the CR number, class, requirements affected, and
   the OQ result. The Reviewer checks the diff, the new tests and the regenerated records.
8. **Automatic gate (CI).** The pull request must pass: the full test suite, `trace_matrix.py --check`
   (no requirement without a test, no orphan test, matrix current), `fmea_report.py --check` (scores, owned actions, exact related test evidence and register current), and `oq_report.py --check` (record matches
   the files). A change to a validated file without re-executing the record fails CI.
9. **Release approval.** For Major changes, run PQ (VP-001 section 8) and attach the result. The Approver approves.
10. **Merge and log.** Merge the pull request (squash). Add the entry to [`CHANGE_LOG.md`](CHANGE_LOG.md) with the
    commit, class, requirements affected and validation evidence. This can be part of the same pull request.
11. **Effective.** The merged commit is the new validated state. Tell users; SOP-001 section 5 step 1 enforces it.

## 6. Rollback

Revert the merge commit with `git revert`, then regenerate the records and log the reversal as a new change.
Do not rewrite history on `main`.

## 7. Dependencies and environment

A dependency version bump is a Major change. Update both `requirements.txt` and `requirements-lock.txt`,
and run the whole procedure. Installation Qualification compares installed packages against the lock file
and fails on any mismatch.

## 8. Documentation-only changes

Edit on a branch, open a pull request, merge, and add a one-line change-log entry. The IQ/OQ record is
unaffected only for documents outside the validated file set. FMEA method/register changes require regeneration and re-execution under section 5.

## 9. Records

Change requests (issues), pull requests, the change log, the regenerated matrix and the IQ/OQ record together
form the change record. Git history is the immutable store for the code and documents.

## Approval

| Role | Name | Signature | Date |
| --- | --- | --- | --- |
| Author | Jack Lai | _not signed_ | |
| Reviewer / Approver | _none (demonstration)_ | | |
