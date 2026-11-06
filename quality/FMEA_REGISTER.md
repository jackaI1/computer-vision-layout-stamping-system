# Seal-stamping design/process FMEA register

Document: QMS-FMEA-001, revision 4. **GENERATED**; edit `fmea.json`.

Method, scoring rubric and limits: [FMEA.md](FMEA.md). Regenerate with `python quality/fmea_report.py`.

**17 failure modes; 17 verified software actions; 17 open actions.** Scores describe current controls. No residual reduction or field failure rates are claimed. Software evidence is limited to synthetic tests; see the [executed IQ/OQ record](validation/IQ-OQ-EXECUTED.md).

High-severity modes (S >= 8) appear first, then descending RPN within each group. Review triggers do not constitute production acceptance.

| Mode | Type / step | Failure mode | S | O | D | RPN | Review trigger |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| [FM-01](#fm-01) | design / Analyze / search | Seal hides faint or crowded drawing content | 8 | 5 | 7 | 280 | Review before issue |
| [FM-08](#fm-08) | process / Set date / caption | Wrong date or caption obscures content outside scored footprint | 8 | 5 | 7 | 280 | Review before issue |
| [FM-17](#fm-17) | design / Fixed-camera carrier and label inspection | A missing or wrong carrier receives a passing station decision | 8 | 5 | 7 | 280 | Review before issue |
| [FM-11](#fm-11) | process / Authorize / issue | Applying an image is mistaken for engineering approval | 9 | 3 | 8 | 216 | Review before issue |
| [FM-03](#fm-03) | design / Detect title-block cell | Wrong or unrecognized designated cell is selected | 8 | 4 | 6 | 192 | Review before issue |
| [FM-05](#fm-05) | design / Cache / manual override | Stale automatic location or manual override reaches export | 8 | 4 | 6 | 192 | Review before issue |
| [FM-09](#fm-09) | process / Load seal | Wrong or damaged seal image is used | 9 | 3 | 7 | 189 | Review before issue |
| [FM-12](#fm-12) | process / Handle files / publish changes | Confidential drawings or real seals leave the intended local workflow | 9 | 3 | 7 | 189 | Review before issue |
| [FM-06](#fm-06) | process / Review page set / download | A required page is missed or an excluded page is stamped | 8 | 4 | 5 | 160 | Review before issue |
| [FM-15](#fm-15) | design / CAD import, stamp and plot | CAD sheet omits referenced content or places a seal at the wrong printed size | 8 | 4 | 4 | 128 | Review before issue |
| [FM-04](#fm-04) | design / Write transformed overlay | Export differs from reviewed coordinates on rotated or offset pages | 8 | 3 | 5 | 120 | Review before issue |
| [FM-02](#fm-02) | design / Fit / keep-out | Automatic seal clips off page or enters reserved corner | 8 | 3 | 4 | 96 | Review before issue |
| [FM-07](#fm-07) | design / Export PDF | Original content is degraded or unintentionally flattened | 8 | 3 | 4 | 96 | Review before issue |
| [FM-10](#fm-10) | design / Validate / analyze inputs | Skipped or failed input is mistaken for a completed zero-coverage page | 8 | 3 | 3 | 72 | Review before issue |
| [FM-14](#fm-14) | process / Change / revalidate | FMEA actions or validation evidence silently become stale | 7 | 4 | 3 | 84 | Planned improvement |
| [FM-16](#fm-16) | process / Commercialization review | Readiness or IP decision cites missing or invented evidence | 5 | 3 | 5 | 75 | Maintain controls |
| [FM-13](#fm-13) | design / Serve review preview | Dependency incompatibility prevents reliable visual review | 6 | 3 | 3 | 54 | Maintain controls |

## FM-01

**Seal hides faint or crowded drawing content** (design; Analyze / search).

- Effect: A dimension, revision or line can become unreadable in an issued drawing.
- Cause: Thresholding ignores faint ink; square grid search is approximate and crowded pages may have no blank disk.
- Requirements: [REQ-01](TRACEABILITY_MATRIX.md), [REQ-02](TRACEABILITY_MATRIX.md), [REQ-03](TRACEABILITY_MATRIX.md), [REQ-04](TRACEABILITY_MATRIX.md)
- Current prevention: Integral-image search evaluates eligible grid positions; ink minimization takes precedence over clearance.
- Current detection: Disk coverage orders review, but neither zero coverage nor the square score proves semantic clearance (SOP-001 A4).

| Score | Current rating | Rationale |
| --- | ---: | --- |
| Severity | 8 | Hidden technical content requires withholding the affected output. |
| Occurrence | 5 | Faint and crowded sheets are plausible inputs; no representative production frequency is measured. |
| Detection | 7 | Synthetic numerical tests detect algorithm regressions, but faint content can escape the metric; human output review is required. |

| Action | Owner | Status | Acceptance / closure evidence | Verification tests |
| --- | --- | --- | --- | --- |
| ACT-01: Retain grid-reference tests and explicitly demonstrate the faint-ink blind spot. | Maintainer | verified_automated | Grid minimum matches brute force; a real faint vector crossing the disk can still report zero coverage. This characterizes a limit, not its elimination. | [`tests/test_occupancy.py::test_full_grid_search_matches_bruteforce_global_square_minimum`](../tests/test_occupancy.py#L266)<br>[`tests/test_pipeline.py::test_faint_linework_can_be_present_when_reported_coverage_is_zero`](../tests/test_pipeline.py#L270) |
| ACT-02: Perform enlarged output review on faint, scanned and crowded sheets; evaluate adaptive thresholding only through a separate change request. | Operator / tool owner | open | Record SOP-001 A4 on every output page and representative PQ examples. Open: no real-drawing PQ or automated semantic-clearance control is supplied. | [`tests/test_occupancy.py::test_full_grid_search_matches_bruteforce_global_square_minimum`](../tests/test_occupancy.py#L266)<br>[`tests/test_pipeline.py::test_faint_linework_can_be_present_when_reported_coverage_is_zero`](../tests/test_pipeline.py#L270) |

## FM-08

**Wrong date or caption obscures content outside scored footprint** (process; Set date / caption).

- Effect: Output misstates intended date/scope or a caption collides with drawing content despite zero disk coverage.
- Cause: Default date is accepted without checking; caption below the circle is excluded from collision scoring.
- Requirements: [REQ-13](TRACEABILITY_MATRIX.md)
- Current prevention: Editable date/caption, selectable text insertion and small-seal date font sizing; caption can be cleared.
- Current detection: Exported-text and caption-boundary tests; SOP-001 A5 requires checking actual output.

| Score | Current rating | Rationale |
| --- | ---: | --- |
| Severity | 8 | Misleading date/scope or obscured technical content requires withholding output. |
| Occurrence | 5 | Default values and tight cells are plausible recurring workflow conditions; no measured rate. |
| Detection | 7 | String tests prove selected values render, not that they are authorized; disk coverage does not detect caption collisions. |

| Action | Owner | Status | Acceptance / closure evidence | Verification tests |
| --- | --- | --- | --- | --- |
| ACT-15: Document the caption footprint limit with exported-PDF geometry and retain date/text checks. | Maintainer | verified_automated | Chosen date/caption render; small date is not dropped; caption bounds demonstrate extension beyond scored disk. | [`tests/test_pipeline.py::test_caption_extends_beyond_the_scored_seal_footprint`](../tests/test_pipeline.py#L289)<br>[`tests/test_pipeline.py::test_date_font_colour_and_caption_reach_pdf`](../tests/test_pipeline.py#L208)<br>[`tests/test_pipeline.py::test_small_seal_date_is_not_silently_dropped`](../tests/test_pipeline.py#L137) |
| ACT-16: Confirm authorized date/caption and inspect space below the seal; move, shorten or clear caption if needed. Consider expanded collision bounds in a separate change. | Operator / tool owner | open | Record A4/A5 on downloaded output. Caption-aware automatic clearance and project authorization are not implemented by these tests. | [`tests/test_pipeline.py::test_caption_extends_beyond_the_scored_seal_footprint`](../tests/test_pipeline.py#L289)<br>[`tests/test_pipeline.py::test_date_font_colour_and_caption_reach_pdf`](../tests/test_pipeline.py#L208)<br>[`tests/test_pipeline.py::test_small_seal_date_is_not_silently_dropped`](../tests/test_pipeline.py#L137) |

## FM-17

**A missing or wrong carrier receives a passing station decision** (design; Fixed-camera carrier and label inspection).

- Effect: A downstream stamping step could start with the wrong loaded carrier or drawing revision.
- Cause: Poor lighting, glare, uncalibrated area limits, detached labels, stale captures or an output adapter holding a previous pass.
- Requirements: [REQ-26](TRACEABILITY_MATRIX.md)
- Current prevention: Require bounded changed area and centroid, valid reference/frame lighting, limited glare and exact code identities in separate regions. Emit one fresh decision and fail low on processing faults.
- Current detection: Synthetic light/contrast/glare sweep, real 1D/2D decoding and CLI error regressions. No physical output or capture freshness validation is claimed.

| Score | Current rating | Rationale |
| --- | ---: | --- |
| Severity | 8 | A wrong carrier or revision could cause required stamping to be incomplete; independent drawing review is still required. |
| Occurrence | 5 | Real camera, label and fixture variation are unmeasured; same-area objects and detached labels remain plausible. |
| Detection | 7 | Synthetic checks cannot establish real part identity, capture freshness or adapter wiring; commissioning and independent review remain necessary. |

| Action | Owner | Status | Acceptance / closure evidence | Verification tests |
| --- | --- | --- | --- | --- |
| ACT-33: Exercise loaded and empty fixtures under changed brightness, contrast and glare; reject wrong codes and processing faults. | Maintainer | verified_automated | All 44 synthetic sweep decisions match expected outcomes; the current result is LOW for inspection and processing failures. | [`tests/test_station.py::test_lighting_and_contrast_sensitivity`](../tests/test_station.py#L19)<br>[`tests/test_station.py::test_small_oversize_and_shifted_parts_fail_even_with_good_codes`](../tests/test_station.py#L92)<br>[`tests/test_station.py::test_cli_processing_errors_emit_fail_low_json`](../tests/test_station.py#L178)<br>[`tests/test_station.py::test_cli_pass_then_fail_does_not_reuse_previous_high`](../tests/test_station.py#L165) |
| ACT-34: Commission the real camera, fixture and isolated PLC adapter with fresh-cycle IDs, watchdog timeouts and held-out good/bad images. | Station owner | open | Record physical timing, fault and wiring trials and real image results before use. Software tests do not close this action. | [`tests/test_station.py::test_cli_pass_then_fail_does_not_reuse_previous_high`](../tests/test_station.py#L165) |

## FM-11

**Applying an image is mistaken for engineering approval** (process; Authorize / issue).

- Effect: A drawing may be issued without the responsible engineer authorizing the seal or reviewing the design.
- Cause: Automation is treated as approval; tool has no login, signature verification or approval audit trail.
- Requirements: [REQ-10](TRACEABILITY_MATRIX.md), [REQ-13](TRACEABILITY_MATRIX.md)
- Current prevention: SOP-001 requires written authorization and engineer-of-record sign-off; tool permits correction/removal but does not enforce approval.
- Current detection: Independent procedural authorization check; UI/export tests only establish editing fidelity.

| Score | Current rating | Rationale |
| --- | ---: | --- |
| Severity | 9 | Unauthorized issue is a serious process failure regardless of geometrically correct placement. |
| Occurrence | 3 | There is a credible misuse path; no field incident frequency or permission model is claimed. |
| Detection | 8 | Software cannot detect lack of authority; detection depends on external review and records. |

| Action | Owner | Status | Acceptance / closure evidence | Verification tests |
| --- | --- | --- | --- | --- |
| ACT-21: Retain tested ability to remove/move seals and choose output text; do not label it approval enforcement. | Maintainer | verified_automated | Output follows operator decisions and text settings only. Tests do not verify professional authority or authorize any issue. | [`tests/test_ui.py::test_manual_edits_and_removal_reach_live_download`](../tests/test_ui.py#L81)<br>[`tests/test_pipeline.py::test_date_font_colour_and_caption_reach_pdf`](../tests/test_pipeline.py#L208) |
| ACT-22: Require written engineer authorization, independent final checking and controlled issue records outside this tool. | Engineer of record / independent checker | open | SOP-001 prerequisites and handover records complete; this public demonstration has no production approval, real-drawing PQ or electronic-signature claim. | [`tests/test_ui.py::test_manual_edits_and_removal_reach_live_download`](../tests/test_ui.py#L81)<br>[`tests/test_pipeline.py::test_date_font_colour_and_caption_reach_pdf`](../tests/test_pipeline.py#L208) |

## FM-03

**Wrong or unrecognized designated cell is selected** (design; Detect title-block cell).

- Effect: Seal may occupy a plausible but unintended title-block region.
- Cause: Label matching assumes extractable text and common spellings; scans and unusual ruling lines can defeat cell derivation.
- Requirements: [REQ-07](TRACEABILITY_MATRIX.md)
- Current prevention: Text-label search and line-derived cell bounds; fitting cell required, otherwise whitespace fallback.
- Current detection: Synthetic common-label and cell-fit tests plus operator inspection of the intended cell.

| Score | Current rating | Rationale |
| --- | ---: | --- |
| Severity | 8 | Wrong title-block placement can obscure information or breach intended layout. |
| Occurrence | 4 | Unfamiliar/scanned layouts are plausible; the fixture set is not a frequency sample. |
| Detection | 6 | Tests cover known labels only; a false-positive cell can look credible and requires layout review. |

| Action | Owner | Status | Acceptance / closure evidence | Verification tests |
| --- | --- | --- | --- | --- |
| ACT-05: Maintain fitting-cell and label variants as regression evidence. | Maintainer | verified_automated | Synthetic designated cell is centered and fitted even when it overrides automatic keep-out; supported label variants are recognized. | [`tests/test_pipeline.py::test_cover_detects_and_fits_designated_cell_despite_keepout`](../tests/test_pipeline.py#L31)<br>[`tests/test_pipeline.py::test_detects_common_stamp_box_labels`](../tests/test_pipeline.py#L103) |
| ACT-06: Qualify each new title-block family, including scans and multiple engineer labels, before relying on automatic cell detection. | Tool owner / operator | open | Attach representative PQ results showing the intended cell or an explicitly reviewed manual placement; unfamiliar layouts remain unqualified. | [`tests/test_pipeline.py::test_cover_detects_and_fits_designated_cell_despite_keepout`](../tests/test_pipeline.py#L31)<br>[`tests/test_pipeline.py::test_detects_common_stamp_box_labels`](../tests/test_pipeline.py#L103) |

## FM-05

**Stale automatic location or manual override reaches export** (design; Cache / manual override).

- Effect: Changed settings can leave an automatic seal in a forbidden corner; an intentional manual move can cover content.
- Cause: Session/cache reuse or an operator overrides keep-out; manual placements are deliberately not relocated.
- Requirements: [REQ-09](TRACEABILITY_MATRIX.md), [REQ-10](TRACEABILITY_MATRIX.md), [REQ-15](TRACEABILITY_MATRIX.md)
- Current prevention: Placement/render cache keys and download-time sanitization; manual decisions preserved with UI warning.
- Current detection: Live download tests confirm stale relocation and preservation of manual edits; review still required for overrides.

| Score | Current rating | Rationale |
| --- | ---: | --- |
| Severity | 8 | Stale or manual position can obscure critical content. |
| Occurrence | 4 | Settings changes and manual adjustments are routine opportunities, not measured incident rates. |
| Detection | 6 | Automatic stale-corner checks are tested; manual content overlap is not prevented. |

| Action | Owner | Status | Acceptance / closure evidence | Verification tests |
| --- | --- | --- | --- | --- |
| ACT-09: Retain end-to-end downloaded-byte tests for late stale state and explicit manual edits. | Maintainer | verified_automated | Late automatic placement is sanitized and downloaded bytes reflect deliberate edits/removals. | [`tests/test_ui.py::test_download_sanitizes_late_stale_automatic_placement`](../tests/test_ui.py#L106)<br>[`tests/test_ui.py::test_manual_edits_and_removal_reach_live_download`](../tests/test_ui.py#L81) |
| ACT-10: Record each manual override and independently verify final clearance after bulk apply or settings changes. | Operator / independent checker | open | SOP-001 stamping record lists manual changes and A3/A4 results. Automatic tests do not authorize manual keep-out overlap. | [`tests/test_ui.py::test_download_sanitizes_late_stale_automatic_placement`](../tests/test_ui.py#L106)<br>[`tests/test_ui.py::test_manual_edits_and_removal_reach_live_download`](../tests/test_ui.py#L81) |

## FM-09

**Wrong or damaged seal image is used** (process; Load seal).

- Effect: Output carries the wrong identity or an unreadable/incomplete seal.
- Cause: Operator selects wrong asset; white-background/crop processing damages image; replacing a file reuses stale bytes.
- Requirements: [REQ-14](TRACEABILITY_MATRIX.md), [REQ-15](TRACEABILITY_MATRIX.md)
- Current prevention: Content hash, transparent-background preparation and seal cache invalidation.
- Current detection: Image-processing and file-replacement regressions plus operator thumbnail/output identity check.

| Score | Current rating | Rationale |
| --- | ---: | --- |
| Severity | 9 | Wrong seal identity is an authorization-critical error even if placement is correct. |
| Occurrence | 3 | Manual selection and asset replacement are plausible but unmeasured opportunities. |
| Detection | 7 | Tests verify pixels/cache identity only; there is no automated identity or authorization verification. |

| Action | Owner | Status | Acceptance / closure evidence | Verification tests |
| --- | --- | --- | --- | --- |
| ACT-17: Keep transparent-image and content-hash/cache replacement tests. | Maintainer | verified_automated | White background becomes transparent while ring ink survives. Identical source bytes yield stable hash, changed input changes it, and replacing a seal refreshes bytes. Identity remains a human check. | [`tests/test_stamp_image.py::test_white_background_becomes_transparent_and_ink_is_kept`](../tests/test_stamp_image.py#L27)<br>[`tests/test_stamp_image.py::test_digest_identifies_the_source_bytes`](../tests/test_stamp_image.py#L54)<br>[`tests/test_ui.py::test_replacing_seal_file_invalidates_cached_bytes`](../tests/test_ui.py#L70) |
| ACT-18: Confirm the current authorized seal with its custodian and inspect preparation for clipping before any issue. | Seal custodian / operator | open | SOP-001 prerequisites 2/3 and thumbnail/output checks recorded privately; no real seal, signature or authorization record is published. | [`tests/test_stamp_image.py::test_white_background_becomes_transparent_and_ink_is_kept`](../tests/test_stamp_image.py#L27)<br>[`tests/test_stamp_image.py::test_digest_identifies_the_source_bytes`](../tests/test_stamp_image.py#L54)<br>[`tests/test_ui.py::test_replacing_seal_file_invalidates_cached_bytes`](../tests/test_ui.py#L70) |

## FM-12

**Confidential drawings or real seals leave the intended local workflow** (process; Handle files / publish changes).

- Effect: Private project content or seal identity could be exposed.
- Cause: A future network dependency or accidental commit bypasses local-processing/public-fixture conventions.
- Requirements: [REQ-17](TRACEABILITY_MATRIX.md)
- Current prevention: Local stamper pipeline and ignored private asset directories; only generated fixtures belong in the public repository.
- Current detection: Static no-network-import test for stamper plus human staged-diff inspection; not a whole-system security audit.

| Score | Current rating | Rationale |
| --- | ---: | --- |
| Severity | 9 | Exposure of seal/client data is an authorization-critical failure. |
| Occurrence | 3 | Accidental publishing is possible; no organization-specific incident data is available. |
| Detection | 7 | Import checks cover only stamper, not arbitrary file copies, browser behavior or transitive network activity. |

| Action | Owner | Status | Acceptance / closure evidence | Verification tests |
| --- | --- | --- | --- | --- |
| ACT-23: Retain the package network-import boundary test. | Maintainer | verified_automated | stamper has no imports from the tested network-module set. This does not prove system-wide data isolation. | [`tests/test_controls.py::test_stamper_package_imports_no_network_modules`](../tests/test_controls.py#L41) |
| ACT-24: Review staged changes and generated artifacts before publication; keep real drawings and seals in controlled local storage. | Maintainer / seal custodian | open | Public commits contain generated fixtures and source only; private asset/data review recorded locally, without adding those records to Git. | [`tests/test_controls.py::test_stamper_package_imports_no_network_modules`](../tests/test_controls.py#L41) |

## FM-06

**A required page is missed or an excluded page is stamped** (process; Review page set / download).

- Effect: Incomplete or incorrectly stamped drawing set is handed over.
- Cause: Riskiest-first ordering differs from page order; remove/restore decisions or bulk downloads are misunderstood.
- Requirements: [REQ-08](TRACEABILITY_MATRIX.md), [REQ-10](TRACEABILITY_MATRIX.md)
- Current prevention: Per-page placements retain indices; removal is explicit; downloads preserve source page count.
- Current detection: Ten-sheet export and removal tests; SOP-001 A1/A2 compares source and issued set.

| Score | Current rating | Rationale |
| --- | ---: | --- |
| Severity | 8 | Wrong scope of stamping requires stopping issue and regenerating affected files. |
| Occurrence | 4 | Multi-page and manual removal workflows create plausible human error opportunities. |
| Detection | 5 | Tests detect indexing/export regressions; software cannot infer which pages ought to be sealed. |

| Action | Owner | Status | Acceptance / closure evidence | Verification tests |
| --- | --- | --- | --- | --- |
| ACT-11: Keep multi-page export and manual removal regression checks. | Maintainer | verified_automated | Synthetic ten-sheet set retains every page and expected seal; explicit removals reach downloaded PDF. | [`tests/test_pipeline.py::test_ten_sheet_set_is_stamped_on_every_page`](../tests/test_pipeline.py#L227)<br>[`tests/test_ui.py::test_manual_edits_and_removal_reach_live_download`](../tests/test_ui.py#L81) |
| ACT-12: Reconcile page count, sheet identifiers and expected seal presence against the authorized source set. | Independent checker | open | Record A1/A2 for each file, including intended omissions, before issue. No automatic engineering-scope determination exists. | [`tests/test_pipeline.py::test_ten_sheet_set_is_stamped_on_every_page`](../tests/test_pipeline.py#L227)<br>[`tests/test_ui.py::test_manual_edits_and_removal_reach_live_download`](../tests/test_ui.py#L81) |

## FM-15

**CAD sheet omits referenced content or places a seal at the wrong printed size** (design; CAD import, stamp and plot).

- Effect: An incomplete or misleading review drawing is exported, or a seal covers drawing content.
- Cause: Missing/nested references, wrong paper units or origins, hidden layers, unsupported CAD objects or an unreviewed manual position.
- Requirements: [REQ-21](TRACEABILITY_MATRIX.md), [REQ-22](TRACEABILITY_MATRIX.md), [REQ-23](TRACEABILITY_MATRIX.md), [REQ-24](TRACEABILITY_MATRIX.md)
- Current prevention: Bind references bottom-up, reject missing/cyclic paths, preserve paper units and origin, contain the seal block, and refuse output overwrite.
- Current detection: Real DXF/DWG roundtrips, PDF page/ink checks, generated sample plots and an explicit user review step.

| Score | Current rating | Rationale |
| --- | ---: | --- |
| Severity | 8 | A misleading drawing can inform a bad engineering decision; applying the seal itself is not approval. |
| Occurrence | 4 | The tests cover synthetic 2D sheets; the variety and frequency of unsupported production CAD content are unknown. |
| Detection | 4 | Automated checks catch defined reference, geometry and plotting errors; real sheet completeness and overlap still require review. |

| Action | Owner | Status | Acceptance / closure evidence | Verification tests |
| --- | --- | --- | --- | --- |
| ACT-29: Run file/reference, paper-space seal, physical plot and CLI tests, including real ODA conversion in its CI job. | Maintainer | verified_automated | Reopened outputs retain seal inserts and reference geometry; expected dimensions and ink are verified; closed outlines remain hollow. | [`tests/test_cad_io.py::test_nested_xrefs_bind_relative_to_each_file_and_preserve_host`](../tests/test_cad_io.py#L44)<br>[`tests/test_cad_stamp.py::test_inch_sheet_uses_paper_units_and_reopens_with_seal`](../tests/test_cad_stamp.py#L67)<br>[`tests/test_cad_plot.py::test_pdf_preserves_paper_size_and_absolute_seal_position`](../tests/test_cad_plot.py#L19)<br>[`tests/test_cad_plot.py::test_closed_polylines_plot_as_outlines_without_solid_fill`](../tests/test_cad_plot.py#L77)<br>[`tests/test_cad_cli.py::test_real_oda_dwg_roundtrip_and_stamp`](../tests/test_cad_cli.py#L91) |
| ACT-30: Review representative real sheets, fonts, title blocks and seal overlap before production use; use native CAD plotting for unsupported content. | Tool owner / drawing reviewer | open | Record a manual review of every intended drawing family. Generated examples do not establish production suitability. | [`tests/test_cad_cli.py::test_documented_inspect_edit_stamp_plot_workflow`](../tests/test_cad_cli.py#L22) |

## FM-04

**Export differs from reviewed coordinates on rotated or offset pages** (design; Write transformed overlay).

- Effect: Seal/date could be shifted over technical content or off sheet despite a plausible preview.
- Cause: Mixing displayed, rotated and MediaBox-origin coordinate systems.
- Requirements: [REQ-12](TRACEABILITY_MATRIX.md)
- Current prevention: Separate derotation handling for image and text insertion; explicit origin corrections.
- Current detection: Rendered PDF geometry regressions for four right-angle rotations and nonzero origins; downloaded PDF is reference.

| Score | Current rating | Rationale |
| --- | ---: | --- |
| Severity | 8 | Shifted overlay can hide technical content. |
| Occurrence | 3 | Rotation/origin variants occur but are bounded cases covered by tests; estimate only. |
| Detection | 5 | Tests measure actual exported geometry; preview alone would miss insertion-only errors. |

| Action | Owner | Status | Acceptance / closure evidence | Verification tests |
| --- | --- | --- | --- | --- |
| ACT-07: Retain exported-image and text geometry checks across supported rotations. | Maintainer | verified_automated | Exported overlay bounds match displayed placement for 0/90/180/270 degrees and offset origins. | [`tests/test_pipeline.py::test_pdf_overlay_preserves_content_and_upright_geometry`](../tests/test_pipeline.py#L111)<br>[`tests/test_pipeline.py::test_nonzero_page_origin_keeps_overlay_at_display_position`](../tests/test_pipeline.py#L193) |
| ACT-08: Inspect downloaded PDFs for each incoming rotation/crop convention, especially beyond the synthetic fixtures. | Independent checker | open | SOP-001 A3/A4 recorded on final files; untested crop conventions require a new fixture and PQ review. | [`tests/test_pipeline.py::test_pdf_overlay_preserves_content_and_upright_geometry`](../tests/test_pipeline.py#L111)<br>[`tests/test_pipeline.py::test_nonzero_page_origin_keeps_overlay_at_display_position`](../tests/test_pipeline.py#L193) |

## FM-02

**Automatic seal clips off page or enters reserved corner** (design; Fit / keep-out).

- Effect: Seal is incomplete or covers a revision/title-block region.
- Cause: Small sheets, fractional coordinates or keep-out settings leave no legal position.
- Requirements: [REQ-05](TRACEABILITY_MATRIX.md), [REQ-06](TRACEABILITY_MATRIX.md)
- Current prevention: Margins and keep-out reject invalid candidates; small-page fallback shrinks to fit or raises an explicit error.
- Current detection: Boundary tests and fully reserved-page refusal; SOP-001 A3 checks final geometry.

| Score | Current rating | Rationale |
| --- | ---: | --- |
| Severity | 8 | An incomplete or misplaced seal invalidates the intended output. |
| Occurrence | 3 | Edge cases are known but confined to constrained geometry; frequency is estimated. |
| Detection | 4 | Deterministic geometry tests cover defined boundaries; actual drawing conventions still need visual checks. |

| Action | Owner | Status | Acceptance / closure evidence | Verification tests |
| --- | --- | --- | --- | --- |
| ACT-03: Keep fail-explicit and small-page geometry regression coverage. | Maintainer | verified_automated | Fully reserved page raises; small-page seal stays inside page and outside keep-out. | [`tests/test_pipeline.py::test_fully_reserved_page_refuses_automatic_placement`](../tests/test_pipeline.py#L85)<br>[`tests/test_pipeline.py::test_tiny_page_fallback_stays_outside_reserved_corner`](../tests/test_pipeline.py#L77) |
| ACT-04: Check legibility after any automatic shrink and confirm project keep-out dimensions before issue. | Operator | open | SOP-001 A3 confirms readable size and intended reserved area on every changed sheet size; no universal minimum legibility is inferred from fit tests. | [`tests/test_pipeline.py::test_fully_reserved_page_refuses_automatic_placement`](../tests/test_pipeline.py#L85)<br>[`tests/test_pipeline.py::test_tiny_page_fallback_stays_outside_reserved_corner`](../tests/test_pipeline.py#L77) |

## FM-07

**Original content is degraded or unintentionally flattened** (design; Export PDF).

- Effect: Selectable text, vector fidelity or embedded raster data can be lost.
- Cause: Wrong output option or a PDF writer regression rewrites original streams.
- Requirements: [REQ-11](TRACEABILITY_MATRIX.md)
- Current prevention: Default overlay path retains original streams; raster flattening is an explicit choice.
- Current detection: Content-stream/raster preservation and optional-flatten tests; compare downloaded output to original.

| Score | Current rating | Rationale |
| --- | ---: | --- |
| Severity | 8 | Loss of original drawing fidelity can affect interpretation. |
| Occurrence | 3 | Overlay is default and tested; accidental flatten selection remains plausible. |
| Detection | 4 | Tests compare streams and raster bytes; output review must confirm the chosen export mode. |

| Action | Owner | Status | Acceptance / closure evidence | Verification tests |
| --- | --- | --- | --- | --- |
| ACT-13: Retain original-content and optional-flatten regressions. | Maintainer | verified_automated | Original raster bytes remain exact in overlay mode; flattening is exercised only when requested. | [`tests/test_pipeline.py::test_original_raster_image_bytes_are_preserved`](../tests/test_pipeline.py#L242)<br>[`tests/test_pipeline.py::test_removal_leaves_page_unstamped_and_flatten_is_optional`](../tests/test_pipeline.py#L147) |
| ACT-14: Confirm the required export mode and retain unchanged source files/checksums. | Operator | open | SOP-001 A6 plus release record states whether flattening was explicitly required; real drawing fidelity remains a PQ check. | [`tests/test_pipeline.py::test_original_raster_image_bytes_are_preserved`](../tests/test_pipeline.py#L242)<br>[`tests/test_pipeline.py::test_removal_leaves_page_unstamped_and_flatten_is_optional`](../tests/test_pipeline.py#L147) |

## FM-10

**Skipped or failed input is mistaken for a completed zero-coverage page** (design; Validate / analyze inputs).

- Effect: Missing/unprocessed drawing is omitted from the issued set or incorrectly considered safe.
- Cause: Unreadable/password-protected input or raster-analysis failure is ignored.
- Requirements: [REQ-16](TRACEABILITY_MATRIX.md)
- Current prevention: Input validation states a skip reason; analysis failure raises with page number rather than guessed zero coverage.
- Current detection: Bad-input and injected analysis-failure tests; operator reconciles uploaded versus exported files.

| Score | Current rating | Rationale |
| --- | ---: | --- |
| Severity | 8 | Omitted processing can lead to an incomplete drawing set. |
| Occurrence | 3 | Unsupported or damaged PDFs are occasional plausible inputs, not measured frequency. |
| Detection | 3 | Explicit errors make detection strong when attended; operator can still ignore a skipped file. |

| Action | Owner | Status | Acceptance / closure evidence | Verification tests |
| --- | --- | --- | --- | --- |
| ACT-19: Retain rejected-input reasons and fail-explicit analysis checks. | Maintainer | verified_automated | Bad/encrypted input is rejected with a reason and an analysis failure identifies the page. | [`tests/test_controls.py::test_non_pdf_bytes_are_rejected_with_a_reason`](../tests/test_controls.py#L31)<br>[`tests/test_controls.py::test_password_protected_pdf_is_rejected_with_a_reason`](../tests/test_controls.py#L36)<br>[`tests/test_pipeline.py::test_analysis_failure_is_reported_instead_of_zero_coverage`](../tests/test_pipeline.py#L181) |
| ACT-20: Resolve every skip/error and reconcile the source file list before handing over output. | Operator | open | Each expected source has an output or documented intentional exclusion; unresolved processing error blocks issue under SOP-001 section 8. | [`tests/test_controls.py::test_non_pdf_bytes_are_rejected_with_a_reason`](../tests/test_controls.py#L31)<br>[`tests/test_controls.py::test_password_protected_pdf_is_rejected_with_a_reason`](../tests/test_controls.py#L36)<br>[`tests/test_pipeline.py::test_analysis_failure_is_reported_instead_of_zero_coverage`](../tests/test_pipeline.py#L181) |

## FM-14

**FMEA actions or validation evidence silently become stale** (process; Change / revalidate).

- Effect: A change ships with unsupported mitigations, invalid scoring or obsolete test links.
- Cause: Requirement/test renaming, missing actions or edited source leaves quality records disconnected.
- Requirements: [REQ-19](TRACEABILITY_MATRIX.md), [REQ-20](TRACEABILITY_MATRIX.md)
- Current prevention: Versioned JSON register, generated reports, exact requirement/test linking, fingerprint and PR CI gates.
- Current detection: Validator corruption/staleness tests, traceability check and IQ/OQ fingerprint check.

| Score | Current rating | Rationale |
| --- | ---: | --- |
| Severity | 7 | False confidence in evidence can conceal regressions; application output still has a separate inspection step. |
| Occurrence | 4 | Changes routinely alter tests/requirements; frequency of an actual escape is unknown. |
| Detection | 3 | CI detects defined integrity errors; neither report generation nor tests prove adequacy of engineering judgment. |

| Action | Owner | Status | Acceptance / closure evidence | Verification tests |
| --- | --- | --- | --- | --- |
| ACT-27: Validate scores, ownership/status, exact related test IDs, high-severity review priority and generated-report freshness in CI. | Maintainer | verified_automated | Invalid/unrelated evidence fails; stale report returns nonzero without overwrite; S >= 8 triggers review even at low RPN. | [`tests/test_fmea.py::test_fmea_rejects_test_evidence_unrelated_to_linked_requirements`](../tests/test_fmea.py#L92)<br>[`tests/test_fmea.py::test_fmea_cli_detects_drift_and_invalid_input_without_overwriting`](../tests/test_fmea.py#L126)<br>[`tests/test_fmea.py::test_fmea_priority_keeps_high_severity_visible`](../tests/test_fmea.py#L60) |
| ACT-28: Reassess scores/actions after deviations, new drawing families or changes to placement/export/settings/dependencies. | Tool owner / reviewer | open | Review FMEA with each change request, rerun CI/IQ-OQ and document representative PQ before production. Open actions require real evidence, not merely a linked test name. | [`tests/test_fmea.py::test_fmea_rejects_test_evidence_unrelated_to_linked_requirements`](../tests/test_fmea.py#L92)<br>[`tests/test_fmea.py::test_fmea_cli_detects_drift_and_invalid_input_without_overwriting`](../tests/test_fmea.py#L126)<br>[`tests/test_fmea.py::test_fmea_priority_keeps_high_severity_visible`](../tests/test_fmea.py#L60) |

## FM-16

**Readiness or IP decision cites missing or invented evidence** (process; Commercialization review).

- Effect: A release or research proposal overstates the available support.
- Cause: Paths move, patent numbers are mistyped or external publication metadata changes.
- Requirements: [REQ-25](TRACEABILITY_MATRIX.md)
- Current prevention: Dated reviewed publication register; explicit public-prototype TRL scope and unresolved field gates.
- Current detection: Offline path and citation checks in CI; optional live number/title verification. Neither establishes legal status or field readiness.

| Score | Current rating | Rationale |
| --- | ---: | --- |
| Severity | 5 | An unsupported decision can waste pilot resources; this document does not authorise drawing issue. |
| Occurrence | 3 | Manual citation edits and source changes are plausible, with no measured rate. |
| Detection | 5 | Automated checks catch broken citations, but interpretation needs qualified review. |

| Action | Owner | Status | Acceptance / closure evidence | Verification tests |
| --- | --- | --- | --- | --- |
| ACT-31: Reject missing paths, unreviewed numbers and mismatched live publication identity. | Maintainer | verified_automated | Valid evidence passes; broken citations, invented numbers, mismatched metadata and network failure are rejected. | [`tests/test_commercialization.py::test_assessment_citations_and_cli`](../tests/test_commercialization.py#L23)<br>[`tests/test_commercialization.py::test_broken_or_invented_citations_fail`](../tests/test_commercialization.py#L37)<br>[`tests/test_commercialization.py::test_live_metadata_requires_number_and_title`](../tests/test_commercialization.py#L53)<br>[`tests/test_commercialization.py::test_network_failure_is_not_a_pass`](../tests/test_commercialization.py#L60) |
| ACT-32: Obtain supervised pilot evidence and professional IP review before broader commercial release. | Tool owner | open | Record fixed-release field outcomes and legal review privately. Citation integrity is not acceptance of maturity or freedom to operate. | [`tests/test_commercialization.py::test_assessment_citations_and_cli`](../tests/test_commercialization.py#L23) |

## FM-13

**Dependency incompatibility prevents reliable visual review** (design; Serve review preview).

- Effect: Operator cannot reliably inspect previews and could proceed with incomplete review.
- Cause: Media response headers/gzip behavior change across UI dependency versions.
- Requirements: [REQ-18](TRACEABILITY_MATRIX.md)
- Current prevention: Pinned direct/transitive dependencies with verified media compatibility.
- Current detection: Identity/gzip HTTP response tests and operator preview check.

| Score | Current rating | Rationale |
| --- | ---: | --- |
| Severity | 6 | Review interruption is visible and recoverable before issue when SOP is followed. |
| Occurrence | 3 | Pinned versions limit drift; compatibility regression remains plausible. |
| Detection | 3 | Response tests exercise both encodings and a missing preview is generally visible. |

| Action | Owner | Status | Acceptance / closure evidence | Verification tests |
| --- | --- | --- | --- | --- |
| ACT-25: Keep preview response tests on the pinned runtime. | Maintainer | verified_automated | Media responses provide correct HTTP headers under identity and gzip encoding. | [`tests/test_runtime_compat.py::test_preview_media_responses_include_http_headers`](../tests/test_runtime_compat.py#L10) |
| ACT-26: Stop issue when preview cannot be inspected; qualify the packaged Windows runtime separately before deployment. | Tool owner / operator | open | Correct runtime installed and every page inspected; Windows packaging/browser coverage is not claimed by source-environment tests. | [`tests/test_runtime_compat.py::test_preview_media_responses_include_http_headers`](../tests/test_runtime_compat.py#L10) |
