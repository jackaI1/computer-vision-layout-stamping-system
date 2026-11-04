# Could I turn the stamping tool into a product?

I built this guide because saving time with my drawing tool at one firm does not tell me whether it is ready for other firms. My tool places a seal image on engineering drawings while looking for space away from notes and linework; I review the proposed positions before exporting. This commercialization assessment is my guide to the checks I need before offering it more widely. I separate three questions: does it work, what rights might affect it, and who could support the next experiment? This is my assessment as of 2026-11-04, not an independent certification or an awarded funding application.

My decision is to keep the public tool available and plan a supervised pilot before a broader release. I rate the **public PDF prototype at TRL 6**, meaning a working system demonstrated in a simulated setting. My original workplace use is useful context, but I cannot use private drawings or a reported time saving to qualify every change in this public version. The newer CAD workflow has its own tests and does not inherit a field-use rating from the PDF tool.

## Terms I use

Intellectual property (IP) means rights in creations such as software and inventions. A patent publication is a public description of a proposed invention, not proof of a currently enforceable right. MIT is the short name of the reuse licence on the original code; dependency obligations are the separate conditions on packages the tool uses. In the funding table, IRAP is the Industrial Research Assistance Program, SR&ED is Scientific Research and Experimental Development tax support, and Mitacs Accelerate funds supervised research internships. I explain their practical limits below.

## How I use this assessment

I read the evidence and next steps below before planning a release. From the repository root I run:

```sh
python scripts/check_commercialization.py
python scripts/check_commercialization.py --online
python -m pytest tests/test_commercialization.py -q
```

The first command checks every local Markdown citation relative to this document and checks every patent number against my dated [publication register](patents.json). The second also retrieves each publication and checks the number and title returned by Google Patents. It fails on a timeout, access denial or mismatched metadata, rather than claiming a number exists because it looks plausible. Offline CI uses the reviewed register so a third-party outage cannot silently change a test result. Neither mode verifies legal status, claim scope or my TRL judgement. To add prior art, I open the publication, review its relevance, add its exact title/number/date to the register, then add a linked row here and rerun both commands.

## Technology readiness, from idea to field use

Technology readiness level (TRL) is a nine-step maturity scale. I use [ISED's Canadian definitions](https://ised-isde.canada.ca/site/innovation-canada/en/technology-readiness-levels), with [NASA's explanation](https://www.nasa.gov/directorates/somd/space-communications-navigation-program/technology-readiness-levels/) as context. I translate flight conditions into drawing-office conditions; this is a software assessment, not a NASA rating. These rows describe what the current repository supports, not invented dates for historical milestones.

| Level | My judgement and repository evidence | Evidence I need to go further |
| --- | --- | --- |
| 1: principles observed | Reached. Counting dark pixels provides a measurable proxy for occupied space, explained in [placement](placement.md). | Formulate a specific drawing-stamping workflow. |
| 2: concept formulated | Reached. [Assumptions](../ASSUMPTIONS.md) defines the seal, caption and reserved corner; [README](../README.md) describes operator review. | Demonstrate the critical search function. |
| 3: proof of concept | Reached. [Occupancy tests](../tests/test_occupancy.py) compare search results with independent reference calculations. | Integrate search with actual PDF writing. |
| 4: integrated lab validation | Reached. [Pipeline tests](../tests/test_pipeline.py) exercise placement, rotation and PDF content preservation together. | Exercise representative simulated sheets and the operator controls. |
| 5: simulated environment validation | Reached within synthetic scope. [Sample generator](../examples/make_sample_sheet.py) creates a cover and notes sheet; [interface tests](../tests/test_ui.py) exercise uploads and review controls. | Show an end-to-end system with a repeatable operating procedure. |
| 6: system prototype demonstration | Reached. The [validation protocol](../quality/validation/VP-001-validation-protocol.md), [executed IQ/OQ record](../quality/validation/IQ-OQ-EXECUTED.md) and [placement procedure](../quality/SOP-001-stamp-placement.md) support a working simulated workflow. IQ checks installation; OQ checks operation against written requirements. | Complete the supervised real-drawing pilot below on a fixed release. |
| 7: operational prototype | Not claimed for this public release. [Reported workplace results](placement.md) describe 20 minutes reduced to under one minute. Firm-wide use is owner-reported context, not a public adoption log or evidence that today's release was field-tested. | An authorised operator and independent checker run the protocol on representative drawings, recording version, corrections and deviations privately. Publish only an approved aggregate summary. |
| 8: completed and qualified | Not claimed. The [protocol](../quality/validation/VP-001-validation-protocol.md) explicitly leaves performance qualification (PQ), checks in real use, unexecuted. | Close pilot deviations, freeze requirements, qualify the final package on supported machines and obtain recorded acceptance. |
| 9: proven deployment | Not claimed. A public test suite and past workplace use do not establish sustained deployment of this exact release. | Retain accepted release records, repeat-use outcomes, support incidents and change/revalidation history under real operating conditions. |

My next gate is the protocol's PQ-1 through PQ-5: at least ten representative sheets covering a designated box, no box, rotation and dense linework, with a trained operator and an independent check of every issued output. I would record elapsed time, manual moves and all A1-A7 output checks, requiring those checks to pass and deviations to close before accepting the pilot. Timing is measured, not a pass threshold. [Current risks](../quality/FMEA_REGISTER.md) include faint linework and captions outside the scored seal area. A stamp image never substitutes for an engineer's approval.

## Patent landscape I would take to a patent professional

I searched Google Patents on 2026-11-04 for `automatic stamp placement document blank area`, `engineering drawing title block detection`, and `seal stamp placement plans`. I followed publication pages and family links, including the Canadian publication below. This is seven real publications across six families, including published applications; it is not seven granted, enforceable patents. I selected them for functional overlap, not title similarity alone. Older disclosures can matter for novelty even when no enforceable right remains.

| Publication | Title | Why I kept it |
| --- | --- | --- |
| [US20070188805A1](https://patents.google.com/patent/US20070188805A1/en) | Image processing apparatus | Detects blank areas and sizes a stamp across pages; closest lead for whitespace placement. |
| [WO2023069491A1](https://patents.google.com/patent/WO2023069491A1/en) | System and method for evaluating solar installation plans, structural and electrical analyses, and permit preparation | Figure 6 and paragraph 0083 teach seal/stamp placement from a manually positioned example. |
| [CA3235429A1](https://patents.google.com/patent/CA3235429A1/en) | System and method for evaluating solar installation plans, structural and electrical analyses, and permit preparation | Canadian member of the preceding family; a Canadian review lead, not a separate invention. |
| [US20240212381A1](https://patents.google.com/patent/US20240212381A1/en) | Systems and methods for automatic detection of features on a sheet | Detects title boxes and their cells; relevant to finding a designated stamp box. |
| [US20230234240A1](https://patents.google.com/patent/US20230234240A1/en) | Engineering drawing review using robotic process automation | Identifies drawing sections and checks rules; relevant to automated layout review. |
| [US20260038294A1](https://patents.google.com/patent/US20260038294A1/en) | Detection of technical data in an image of a technical drawing | Separates views, annotations and title blocks; relevant to avoiding drawing content. |
| [EP1136938A1](https://patents.google.com/patent/EP1136938A1/en) | A method of recognizing and indexing documents | Recognizes drawing information zones for indexing; earlier layout-segmentation context. |

The blank-area and seal-learning disclosures are the closest leads for automatic placement; the other records help bound drawing-layout prior art. I would compare actual independent claims with [placement code](../stamper/placement.py), [PDF export](../stamper/pdf_writer.py) and [CAD stamping](../stamper/cad_stamp.py), element by element, before selling or distributing a changed product. A similar description alone does not prove infringement. Different implementation details alone do not prove clearance.

Freedom to operate means checking whether making, using or selling the product could fall within enforceable claims in the intended country. The Canadian family needs a current [CIPO database](https://ised-isde.canada.ca/site/canadian-intellectual-property-office/en/canadian-patents-database) check for prosecution, grants and claim changes. US and European publications are leads to territorial families, not automatic Canadian rights. Google's status labels are not legal conclusions. My search can miss terminology, continuations, unpublished applications and claims outside these examples. I have not commissioned a claim chart or a legal-status search. **This is not legal advice or a freedom-to-operate opinion.**

## What I can protect, and what I have already shared

I use [CIPO's software IP guide](https://ised-isde.canada.ca/site/canadian-intellectual-property-office/en/intellectual-property-rights-software-canada) to distinguish these choices:

- **Copyright:** protects original code and written material, rather than the general idea of finding empty space. The [MIT licence](../LICENSE) names D.L. Engineering Inc. as copyright holder. I do not claim personal ownership merely because I wrote the tool. The [publication note](../README.md) records the firm's permission; permission to publish is not evidence of a patent assignment.
- **Trade secret:** could protect genuinely confidential future know-how or customer information with access controls and confidentiality agreements. The published algorithm cannot remain a secret. I keep client sheets, actual seals and private experiment records out of this repository.
- **Possible patent:** a new, useful and non-obvious technical improvement might merit review, but I have not established patentability. Existing placement disclosures make a broad claim to automatic stamping difficult to justify. Public disclosure can damage filing options, with country-specific rules and deadlines; I would resolve employer rights and ask a registered professional before disclosing a new improvement. A patent would not itself grant freedom to operate.

MIT permits reuse of the original source subject to its notice conditions. Dependencies need their own review: [third-party notices](../THIRD_PARTY_NOTICES.md) describe PyMuPDF's AGPL-3.0 obligations and other packages. I would review combined distributions and network use before choosing an open-source service or a proprietary package. Open source does not clear third-party patents or grant authority to use a professional seal.

## Canadian routes for the next experiment

These are potential routes, not funding I have secured. I would approach them through the eligible firm or research partner, with an agreed IP arrangement and a cost ledger.

| Route and official source | How I would apply it | Gate and next action |
| --- | --- | --- |
| [NRC IRAP](https://nrc.canada.ca/en/support-technology-innovation/financial-support-technology-innovation), advisory and possible R&D funding | Propose a technical project on reliable placement across unfamiliar drawing layouts, with measurable collision errors and review effort. | The applicant must be incorporated, for profit, operating in Canada and employ up to 500 full-time equivalents. Support is discretionary. I would discuss technical risk, growth potential, budget and timing with an industrial technology advisor before committing funded work; a personal GitHub repo is not an eligible firm by itself. |
| [SR&ED](https://www.canada.ca/en/revenue-agency/services/scientific-research-experimental-development-tax-incentive-program/sred-eligibility.html), tax incentives for eligible Canadian research | Separate experiments on unresolved technological uncertainty from routine interface work, packaging and ordinary debugging. Record the uncertainty, hypothesis, method, result and conclusion, including failures, alongside time and costs. | CRA requires advancement and systematic investigation by experiment or analysis. A time saving alone is not eligibility. I would have the claimant and tax advisor review the work and filing requirements rather than label all commits R&D. |
| [Mitacs Accelerate](https://www.mitacs.ca/our-programs/accelerate/), supervised academic-industry research internships | Work with a Waterloo supervisor and eligible partner to compare layout methods on authorised or synthetic sheets, with a research question and reproducible error analysis. | I would confirm my student eligibility, supervisor, partner contribution and IP/publication agreement with Mitacs before starting. Standard partner contributions start at $7,500 for a $15,000 research award; confirm the current stream and terms. This is not automatic co-op wage reimbursement. |
| [Ontario Innovation Tax Credit](https://www.ontario.ca/page/ontario-innovation-tax-credit), refundable provincial R&D credit | Ask an eligible corporation performing Ontario SR&ED whether the same experimental work qualifies provincially. | Check Ontario establishment, federal eligibility, expenditure limits and corporate filing conditions. I would retain a separate assistance/cost reconciliation rather than assume a second full reimbursement. |
| [Ontario OCI Collaborate 2 Commercialize](https://www.oc-innovation.ca/programs/collaborate-2-commercialize/), academic-industry collaboration | A future research partner could help validate more difficult layouts and commercialization needs. | The current page requires an Ontario company incorporated for two years with five Ontario FTEs and academic participation. The listed 2026 AI call closed September 15; I would check a future suitable call with OCI, not budget this as open money today. |

I would start with an unfunded pilot scope and ownership review, then talk to IRAP and a university supervisor about genuine remaining research. I would keep grant-covered costs and claimant-funded costs separate and have the firm's accountant reconcile assistance before any tax claim. Program rules and intakes change; these links are starting points to recheck, not promises.

At D.L. Engineering I kept 431 dated R&D entries for the firm's SR&ED filing, recording technological uncertainty, hypothesis and result. That is my account of the work, not a claim that CRA approved every entry or that the stamping tool generated all 431. Those private records are not part of this demo. Here I show the same evidence-first habit through public tests, explicit maturity limits and a dated patent register.
