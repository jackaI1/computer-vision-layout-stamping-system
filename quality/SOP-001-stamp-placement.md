# SOP-001 Applying Engineer Seals to PDF Drawings with the Engineering Stamp Placer

| | |
| --- | --- |
| Document | QMS-SOP-001 |
| Version | 1.0 (draft, 2026-11-03) |
| Author | Jack Lai |
| Status | **Demonstration document.** Not adopted or approved by D.L. Engineering Inc. or any other organisation. Approval lines below are intentionally blank. |
| Related | [SOP-002 Change Control](SOP-002-change-control.md), [VP-001 Validation Protocol](validation/VP-001-validation-protocol.md), [Traceability matrix](TRACEABILITY_MATRIX.md) |

## 1. Purpose

To define a repeatable, checkable way of placing an engineer's seal image, date and
caption on PDF drawing sets with the Engineering Stamp Placer, so that every
issued sheet is stamped in the right place, no content is hidden, and any problem
is recorded and handled.

## 2. Scope

Applies to anyone using the tool (`app.py`, started with Streamlit) to apply a seal
image to PDF drawings. It covers preparation, stamping, checking and records.

It does **not** cover: deciding whether a drawing may be sealed, engineering review
of the drawing, or the professional regulator's rules on sealing. Applying an image
is not engineering approval (see README). Only the licensed engineer decides to
seal.

## 3. Definitions

| Term | Plain meaning |
| --- | --- |
| Seal | The image of the engineer's seal, kept in `stamps/` (never committed to Git). |
| Placement | Where the tool puts the seal on one page, and how much ink lies under it (coverage). |
| Designated cell | A title-block box labelled ENGINEER STAMP (or a common spelling) in real PDF text. |
| Keep-out | The reserved top-right region where automatic placement is never allowed. |
| Deviation | Anything that does not follow this SOP or the acceptance checks in section 7. |
| Validated state | The tool's files match the current IQ/OQ record (`python quality/oq_report.py --check` passes). |

## 4. Responsibilities

| Role | Responsibility |
| --- | --- |
| Operator | Runs the tool, reviews every page, keeps the stamping record, raises deviations. |
| Engineer of record | Authorises sealing of the drawing set, and signs off the stamped output. Remains responsible for the seal. |
| Independent checker | A second person who repeats the section 7 checks on the issued files. Recommended where the team allows; the Operator must not be the only checker of their own work for issued sets. |
| Seal custodian | Controls access to the seal file(s) in `stamps/`. |
| Tool owner | Keeps the tool in a validated state under SOP-002 and answers deviations about the tool itself. |

One person can hold more than one role in a small team, except that the Operator
should not be the only person checking issued output.

## 5. Prerequisites

1. The tool is in its validated state: run `python quality/oq_report.py --check`. If it
   fails, do not use the tool for issued drawings; contact the Tool owner (SOP-002).
2. The Engineer of record has authorised sealing of this drawing set, in writing.
3. The seal image is the current, authorised seal and sits in `stamps/` (or is
   uploaded for the session). Seals and client drawings are never committed to Git.
4. Source PDFs are kept unchanged. The tool never edits the source; it produces new files.

## 6. Procedure

1. **Start the tool.** From the repository root with the virtual environment active:
   `python -m streamlit run app.py --server.address=127.0.0.1 --server.port=8501 --server.headless=true --browser.gatherUsageStats=false`
   then open `http://127.0.0.1:8501`. Processing stays on this computer.
2. **Choose the seal** (sidebar, "1. Seal & date"). Confirm the thumbnail is the right seal.
3. **Set the date** to the date the Engineer of record signs off. Do not leave the default
   (today) unchecked. Confirm the caption text (default FOR STRUCTURAL ITEMS ONLY; clear it to print none).
4. **Check placement settings** (sidebar, "2. Placement settings"). Leave defaults unless
   the Engineer of record or the project drawing standard says otherwise. Record any change in the stamping record.
5. **Upload the drawing set** (PDF files). If a file is skipped with a message (unreadable,
   password-protected, no pages), fix the file and re-upload. Do not continue without it.
6. **Review every page, riskiest first.** The tool lists pages by descending coverage. For each page check:
   - the seal is in the designated cell, or in clear space;
   - it is outside the reserved top-right region (the tool warns if a manual placement is inside);
   - it hides no linework, text, dimension or revision cloud (zoom in if coverage is above 0%);
   - the date reads correctly and the caption does not run onto other content.
7. **Adjust where needed.** Click to move the seal, remove it from a page that must not be
   stamped, restore it with "Add stamp back", or apply a position to every page. Record each manual change.
8. **Download.** Use the per-file download or "Download all". Output names end in `_stamped.pdf`.
   Leave "Flatten output" off unless the issuing procedure requires it; flattening turns pages into images.
9. **Check the output** using the acceptance checks in section 7 on the downloaded PDFs, not on the screen preview.
   The PDF is the reference for final appearance.
10. **Record and hand over.** Complete the stamping record (appendix A). Pass the stamped files and
    record to the Engineer of record (and the Independent checker if used).
11. **Stop the tool** with Ctrl-C and close the browser tab.

## 7. Acceptance checks

All must be true for each stamped file before it is issued:

| # | Check | Pass when |
| --- | --- | --- |
| A1 | Page count | Stamped PDF has the same number of pages as the source. |
| A2 | Seal present | A seal is on every page that should carry one, and on no page that should not. |
| A3 | Position | Seal is inside the page margins, outside the reserved top-right region, and in the designated cell where one exists. |
| A4 | No obscured content | No linework, text or dimension is hidden by the seal. The tool reports ink under the seal but defines no pass limit: judge each non-zero page. |
| A5 | Date and caption | Date equals the sign-off date; caption is as intended and readable. |
| A6 | Source unchanged | The original PDF is unmodified (compare file date and size, or checksum). |
| A7 | File name | Name ends in the agreed suffix and cannot be confused with the source. |

## 8. Deviations

A deviation is raised when any check in section 7 fails, a warning or error is shown that
cannot be cleared, the tool is not in its validated state, or the procedure is not followed.

1. **Stop.** Do not issue the affected files.
2. **Record** it (appendix B): what happened, which file and page, who found it, when.
3. **Contain.** Delete the affected `_stamped.pdf` outputs. Re-stamp from the unchanged source.
4. **Assess impact.** Was anything already issued? If yes, tell the Engineer of record at once.
5. **Find the cause.** Operator error, unusual drawing, or a tool fault? A tool fault becomes a change request under SOP-002.
6. **Close.** The Engineer of record agrees the correction. File the record with the stamping record.

## 9. Records

Stamping records (appendix A) and deviation records (appendix B) are kept with the project file
under the organisation's own retention rules. The tool itself writes no log or audit trail
(see [GAMP 5 and Part 11 notes](GAMP5-PART11-NOTES.md)); this paper or controlled-document record is the audit trail.

## Appendix A. Stamping record (template)

| Field | Entry |
| --- | --- |
| Project / drawing set | |
| Source file names | |
| Tool state checked (`oq_report.py --check`) and commit | |
| Seal used | |
| Sign-off date printed | |
| Settings changed from default | |
| Manual changes (page, action) | |
| Checks A1 to A7 passed | |
| Deviation numbers (or none) | |
| Operator, date | |
| Independent checker, date | |
| Engineer of record, date | |

## Appendix B. Deviation record (template)

| Field | Entry |
| --- | --- |
| Deviation no. | DEV-YYYY-nnn |
| Found by / date | |
| File and page | |
| What happened | |
| Containment | |
| Issued already? | |
| Cause | |
| Tool change request no. (if any) | |
| Corrected and rechecked by / date | |
| Closed by Engineer of record / date | |

## Approval

| Role | Name | Signature | Date |
| --- | --- | --- | --- |
| Author | Jack Lai | _not signed_ | |
| Reviewer | _none (demonstration)_ | | |
| Approver | _none (demonstration)_ | | |
