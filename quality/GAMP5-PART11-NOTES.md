# GAMP 5 and 21 CFR Part 11 in plain words, applied to this tool

**Honest framing.** This is an internal engineering tool. GAMP 5 and 21 CFR Part 11 come
from pharmaceutical and medical manufacturing. They do not legally apply to engineer-seal
software; sealing is governed by the professional regulator in the relevant jurisdiction.
The `quality/` folder uses those ideas as a framework to show how a tool like this would be
controlled if it did sit in a regulated process. Nothing here claims compliance or certification.

## GAMP 5 (a risk-based way to make software "fit for intended use")

| Idea | Plain meaning | How it shows up here |
| --- | --- | --- |
| Intended use first | Write down what the software must do before judging if it works. | [`requirements.json`](requirements.json): 19 requirements. |
| Software category | More custom code means more checking. | The application is **custom** (Category 5). It is built on off-the-shelf libraries (PyMuPDF, Streamlit, Pillow, NumPy) that are used as supplied (Category 3), pinned and installation-checked. |
| Risk-based effort | Test hardest where a failure hurts most. | Each requirement has a risk rating. A seal over linework or in the reserved corner is rated High; the strongest tests (brute-force comparisons, all four rotations) sit there. |
| Specification to test links | Show every requirement is tested and every test has a reason. | Generated [traceability matrix](TRACEABILITY_MATRIX.md); CI fails on gaps. |
| IQ / OQ / PQ | Installed correctly; works as specified; works in real use. | [VP-001](validation/VP-001-validation-protocol.md). IQ and OQ are executed by script; PQ is a protocol only. |
| Change control | Never change a validated system casually. | [SOP-002](SOP-002-change-control.md) and [change log](CHANGE_LOG.md). |
| Operating procedure | People use it the same way every time. | [SOP-001](SOP-001-stamp-placement.md). |

## 21 CFR Part 11 (rules for electronic records and signatures)

| Part 11 topic | Plain meaning | Status in this tool |
| --- | --- | --- |
| Validation (11.10a) | Prove the system does what it should. | **Addressed** in demonstration form: VP-001, matrix, executed IQ/OQ. PQ not executed. |
| Accurate, complete copies (11.10b) | Records can be shown in readable form. | **Met in practice**: output is an ordinary PDF; original content preserved unless flatten is chosen. |
| Record protection and retention (11.10c) | Records are kept safe and retrievable. | **Not provided by the tool.** Depends on the file system and the organisation's retention. |
| Access limits (11.10d) | Only authorised people use the system. | **Not provided.** The tool has no log-in; the operating system and the seal custodian control access (SOP-001). |
| Audit trail (11.10e) | A secure, time-stamped log of who did what. | **Not implemented.** The tool writes no log. Compensating control: the stamping record in SOP-001 appendix A. Git history is an audit trail for code changes only. |
| Authority checks (11.10g) | Only the right person can do each step. | **Procedural only** (SOP-001 roles). |
| Documentation and change control (11.10k) | Control the system's documents and changes. | **Addressed**: SOP-002, change log, Git history. |
| Electronic signatures (11.50, 11.70, 11.100 to 11.300) | Signature shows name, date and meaning, is linked to its record and is unique to one person. | **Not implemented.** The applied seal image is not a Part 11 electronic signature: it is an image anyone with the file can apply. Controls are procedural (seal custodian, Engineer of record sign-off). |

**Conclusion.** The tool is not Part 11 compliant and is not presented as such. The gaps above
(no audit trail, no log-in, no cryptographic signature) are the first things a real regulated
deployment would need to close.

## Limits of the validation evidence

- IQ/OQ are automated and use synthetic PDFs and a generated seal. No real seal or client drawing is in the repository.
- OQ shows the tool meets the written requirements. It does not show the requirements are complete.
- PQ on real drawings is defined but not executed.
- The record has no human reviewer or approver. Signature blocks are left blank deliberately.
