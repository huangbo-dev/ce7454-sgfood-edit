# CE7454 report handover · 11 November 2026

Start in the [live Overleaf report](https://www.overleaf.com/project/6adb5f7ac2e32fc02215c7b2). On 11 November the viewer showed **five pages**, with the end of the FoodSG citation on page five. Table 1 already includes seed-only stopping. It still omits the completed fixed-ladder comparison. The [repository TeX](../report/main.tex) is a sanitized 10 November snapshot with different figure and author handling. Edit from the live source to preserve the authors’ changes.

The designated FY2025 Project 2 handout and this cohort’s FY2026 handout agree on a four-page CVPR report and four equally weighted criteria below. The team wants four total pages including references. The FY2026 handout gives **15 November 2026, 23:59 Singapore time** for the report and presentation video. One group member submits both. The rubric specifies no minimum model count, trained-model requirement or target accuracy.

## First editing pass

1. **Experimental analysis (25%).** In Table 1 insert “Fixed prompt ladder” immediately above adaptive retry. Put dashes in both original-prompt cells and **29 / 67** in the revised pass and generation columns. Only revised prompts were tested for this control. Keep seed-only stopping as its own row. Replace the proposed ladder experiment in the source and update the abstract, methods, results and conclusion so all describe the completed comparison. Retain the original adaptive-versus-best-of-four contrast as the earlier experiment. The ladder test is a follow-up specified after those results.
2. **Novelty and difficulty (25%).** Give the introduction one concrete research question: after a failed edit, does choosing the next setting from the failure label help beyond following a predetermined schedule? Credit CE6190/PlateEdit for its assets and mask QA, and identify the CE7454 work: matching photos, seeds and budgets across policies, separating prompt revision from retry, and testing the checker's influence on selection. In related work, use the existing iterative-editing and verifier-guided search citations to explain which comparison those precedents motivate.
3. **Technical soundness (25%).** Describe exactly what changes. Seed-only stopping retains the base prompt. The fixed ladder advances through each task’s existing prompt/guidance schedule after any failure. Adaptive retry advances for edit failures and takes a new seed at base guidance for the other labels. Both ladder policies stop on the first pass or at four attempts and return the first maximum-score image seen. Both use Qwen to stop, rank and measure the selected output. Keep the realism and paste-artefact calibration caveats. The separate development judge covered 66 outputs and supplied no ratings for these 34 cases.
4. **Clarity (25%).** Recover space by removing repeated Table 1 totals from the budget and conclusion paragraphs, shortening the two verbatim CLIP prompts to the scoring rule, and reducing the HSV implementation detail to “one fixed within-mask recolouring, 0/14 accepted.” Give the saved space to the ladder result and one sentence on what the human evaluation could establish. Keep the figure at readable size and preserve the CVPR style. Download the newly compiled PDF, check its physical page count (e.g. with `pdfinfo`), and inspect the last reference, both table headers, the figure, author block and citation warnings. Acceptance is four total pages with the full final reference visible.

Suggested results text:

> Across 34 paired edits, the fixed ladder passed the checker on 29 in 67 attempts and adaptive retry on 28 in 68. Both passed 28 cases, the ladder alone passed one rice edit, and both failed five. Adaptive minus fixed ladder was −2.9 percentage points (exploratory 95% photo-cluster bootstrap interval −9.1 to 0.0). Failure-dependent settings changed the retry path in four cases. This comparison gives no observed checker-pass advantage for choosing a retry from the failure label. Human judgement of visual quality remains open.

## Evidence for the next editor

| Revised prompts | Broccoli passes / 20 | Rice passes / 14 | Overall / 34 | Generation attempts |
|---|---:|---:|---:|---:|
| Fixed prompt, seed-only stopping | 14 | 12 | 26 | 68 |
| Fixed prompt ladder | 17 | 12 | 29 | 67 |
| Adaptive retry | 17 | 11 | 28 | 68 |

The seed-only task breakdown was replayed directly from the archived candidate order on 11 November. The ladder matched 58 archived candidates exactly and required nine newly generated and checked candidates. The 67 is the policy's attempt count. All three rows use the same 20 photos and report the verdict on the returned image. The 30 byte-identical selections between ladder and adaptive explain why the two policies had few opportunities to disagree. The 95% interval resamples 20 photos with all their tasks, 10,000 times. The original/revised single-shot rice contrast (0/14 to 10/14) measures the effect of revising the base prompt; the adaptive-versus-ladder contrast tests the use of failure labels.

Use the [aggregate ladder and stopping receipt](../evidence/fixed-ladder-20261111/SUMMARY.json) and [earlier CLIP and recolouring results](../evidence/supplemental-20261110/SUMMARY.json). For a read-only replay on GPU04, run the following in the existing Termius session. The verifier reads saved outputs and needs no new inference.

```sh
run_dir=~/ce7454-work/runs/fixed_ladder_tuned_20261111_4mBh2W
python3 "$run_dir/verify_pairs.py" "$run_dir"
```

The run’s `LOCK.json`, `compare.py`, `cases.jsonl` and `COMPLETE.json` retain the schedules, execution, candidate paths and aggregate receipt. Raw photos, generated outputs, reviewer mappings and responses stay in the private experiment workspace.

## Highest-value remaining evidence

**Blinded visual ratings by the project authors** would address the largest gap in technical soundness and experimental analysis. The live report contains no human ratings on the 34 study cases. Check privately with the team for existing exports, their protocol and coverage before scheduling work. The [categorical review instructions](../study/public_review/README.md) describe 34 revised best-of-four/adaptive pairs, including seven identical pairs. That package predates the fixed ladder.

- **Before collection:** define the three Yes/No/Unsure outcomes (edit achieved, other food preserved, plausible appearance), how disagreement, prior exposure, Unsure and missing ratings will be reported, and the paired estimand. Freeze the author roster, output identities and blinded order. The [older numeric analysis](../study/author_analysis/README.md) uses a different endpoint. A categorical analysis needs a compatible reader and a verified denominator for each result.
- **For the ladder contrast:** 30 ladder/adaptive selections have identical bytes. Join on source photo, task and output hash before reusing any per-image judgement. Cross-check the four differing pairs against the existing package to identify which additional outputs actually need ratings. If the team reviews only these four pairs, describe a targeted disagreement audit and report its denominator. An overall human pass rate needs coverage of the full cohort.
- **What to report:** give the number of raters, photos and rated outputs, followed by per-question counts and agreement. If coverage permits, compare methods within photos and count how often authors reject a checker-passing image. State the denominator, handle Unsure explicitly and keep example images blinded until ratings are frozen. If ratings are unavailable by the deadline, report the checker-only result and retain the limitation.
- **If time remains:** inspect the four divergent paths to explain the concrete changes in the edited food or surroundings. Label examples by how they were selected. A new-photo replication could test generalisation, but requires a separately frozen cohort. Another round of tuning on these same 20 photos would not answer that question.

## Final team checks

Confirm the CE6190 reuse disclosure and any course-team correspondence, retain the description of the retrospective cohort and all seven flagged masks, and check the video uses the same numbers as the final PDF. Recheck the exported four-page file after the last edit. The [10 November checklist](REMAINING_WORK_20261110.md) contains the earlier study and app tasks; the items above are the report priorities.
