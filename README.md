# SgFood-Edit

Check-and-retry editing of Singaporean meal photographs, CE7454 Project 2.

## Report handover · 11 November 2026

Start with the [rubric review and next actions](plan/REPORT_HANDOVER_20261111.md) and the [fixed-ladder results](evidence/fixed-ladder-20261111/SUMMARY.json). The fixed ladder returned 29/34 checker passes in 67 attempts. Adaptive retry returned 28/34 in 68. The live Overleaf draft still needs this comparison and currently renders to five pages including references.

## Research snapshot · 10 November 2026

The shared-photo retrospective study and supplemental CLIP/recolouring controls are complete. Human ratings, independent new-photo confirmation and final submission checks remain open. The report is a reviewed draft, not a submitted or submission-ready report.

This research snapshot includes the selected-output reporting fix, frozen study runner, 10 November report text, offline author-analysis tools and aggregate supplemental receipts. The optional meal-preview app remains isolated on `app/senior-meal-preview`; it is not part of the research submission or evidence of model deployment.

### Verified checker diagnostics

For revised prompts, on 20 photos and 34 tasks:

| Task | Cases | Single | CLIP selector | Best-of-four checker | Adaptive retry |
|---|---:|---:|---:|---:|---:|
| Add broccoli (T1-B) | 20 | 10 | 12 | 14 | 17 |
| Brown-rice appearance (T2) | 14 | 10 | 10 | 12 | 11 |
| All | 34 | 20 | 22 | 26 | 28 |

These are selected-output verdicts from the same Qwen checker that selects the checker-based methods. They do not establish independent visual-quality superiority. The retry-minus-best difference is +5.88 percentage points, with exploratory photo-cluster 95% interval [-5.71, 17.14]. The task effects have opposite signs.

Fixed-prompt early stopping also gives 26/34 using 68 generations, the same aggregate generation count as adaptive retry. CLIP uses full-image target-text cosine, not target-minus-source margin. The fixed HSV stress control passes 0/14; rejection of one recipe does not establish general checker specificity or human false acceptance. The reviewed report records no real human ratings as of 09:02 SGT on 10 November; this sync did not read the response database or collect ratings.

See [aggregate results](evidence/supplemental-20261110/SUMMARY.json), [method details](evaluate/supplemental/README.md), [report source](report/main.tex), and [remaining work](plan/REMAINING_WORK_20261110.md).

## Method and provenance

A frozen BrushNet-SDXL editor produces masked meal edits. A Qwen2.5-VL-7B-Instruct checker evaluates edit completion, preservation, realism and unrequested additions. Failure-directed retries change prompts, guidance or seeds, with at most four generations. Selection returns the first maximum of the frozen weighted score; stopping and selected-output success are distinct.

Development used 20 meal photos and 35 tasks. The later sample contains 20 author-owned photos reused from CE6190 S5 (14 rice, six noodle), giving 34 tasks per prompt condition. It is a shared-photo retrospective robustness sample, not an independent held-out test. All seven flagged masks remain included; mask-quality strata are confounded with food type. No model weights are trained.

The completed generation used commit `f025ee0dafad708eafff2a3c0b68cb8f345eb454`, which includes reporting fix `18fb9b2` and protocol preparation `9d4d237`. Supplemental control code and protocol were frozen before their execution. This synchronization does not modify source runs, model weights, prompts, thresholds, reviewer records or private study packages.

## Repository layout

- `sgedit/`: editor, checker, prompts, retry loop, reporting, preflight and locked robustness runner.
- `evaluate/`: original evaluation tools; `evaluate/supplemental/` contains the executed E3/E4 controls and synthetic tests.
- `study/`: original team-annotation site; `study/author_analysis/` contains the separate protocol-aligned offline comparative and checker/author analyzers. See its README before use.
- `evidence/`: small aggregate receipts, without photographs, masks or reviewer identities.
- `report/`: GitHub-safe snapshot of the reviewed report text, with private author identifiers and image panels omitted.
- `plan/`: protocols, prior design notes and current remaining-work checklist.
- `requirements/`, `calib/`, `bench/`: environment requirements and development tools.

## Offline verification

Use an already provisioned compatible environment. These commands do not run models or collect ratings:

```sh
python -m unittest discover -s tests -v
(cd evaluate/supplemental && python -B -m unittest -v test_supplemental_controls)
(cd study/author_analysis && python -B -m unittest discover -s tests -v)
```

Model execution requires separately approved inputs, the exact cached weights and runtime, verified locks and an available authorized GPU. Keep source data and all new run outputs outside Git. The original judge tools can incur API cost and are not part of the commands above.

## Data and privacy

Do not commit source or generated meal images, masks, model weights, credentials, reviewer codes, rosters, mappings or responses. FoodSG assets retain their original access terms. Use exact byte/hash joins for author evaluation; do not invent labels or derive them from checker outcomes. Keep missing and Unsure answers explicit.

The private reviewed report contains actual qualitative panels. This GitHub copy uses a placeholder when the locally supplied figure is absent and omits author contact/student identifiers. It is not byte-identical to the submission draft. No raw images or compiled PDF are published here.

No outside-team ratings, surveys or feedback are authorized by this repository; ethics approval is required before such collection. Appearance alone does not establish nutrition, wholegrain content, health benefit or behaviour change.

## Course deliverables

The repository records the course deadline as 15 November 2026, 23:59, with a four-page CVPR-format report and presentation video. Keep four total pages unless the instructor confirms an exemption. Final roster, identifiers, reuse disclosure, human evidence and submission remain to be checked. A five-minute demo is a presentation preference, not a verified course requirement.
