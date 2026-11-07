# Report — SgFood-Edit (CE7454 Project 2)

Four-page CVPR-format report (official CVPR 2026 author kit, 10 pt, two columns, US Letter, named authors).
Build: `latexmk -pdf main.tex` (build files are ignored by Git).

**Page limit.** The handout says "4-page report in CVPR format" and links the CVPR author kit; by CVPR convention the
limit covers text and figures, and references follow (page 5). *Confirm with the TA.* If references must fit inside
four pages, cut in this order: Fig. 2 → inline text, Related Work → 4 sentences, Fig. 3 → one panel.

## Story (what an A+ report has to make obvious)

> Diffusion editors are unreliable for fine-grained local edits and the usual scores don't notice. A VLM checker in
> the loop makes them reliable without retraining — and we measure exactly where the gain comes from (prompt vs.
> loop, selection vs. targeted retry) and what it costs (budget, selector inflation), on a culturally specific task.

Three questions carry the paper; every figure and table answers one of them.
- **Q1** selection vs. targeted retries at equal budget
- **Q2** prompt correction vs. the loop (prompt × arm)
- **Q3** can the checker be trusted as selector; how much does selection inflate its scores

## Page budget (8 columns) and where every element comes from

| Page | Element | Size | Answers | Data / tool |
|---|---|---|---|---|
| 1 | Title, abstract (~150 words) | 0.5 col | — | final numbers from `tables.json` |
| 1 | **Fig. 1** teaser: original / original-prompt single / corrected + retry, 2 photos, checker verdicts | 0.45 col | story | test run images |
| 1 | §1 Introduction: problem, why hard, Q1–Q3, 3 contributions | 0.9 col | novelty | — |
| 2 | §2 Related work (2 paragraphs) | 0.4 col | novelty | `main.bib` |
| 2 | **Fig. 2** pipeline with failure → action table | 0.35 col | clarity | draw (draw.io / TikZ) |
| 2 | §3 Method: editor, checker (score formula), retry policy & arms, prompt diagnosis | 1.1 col | soundness | — |
| 3 | §4 Data, evaluation protocol, calibration numbers | 0.45 col | soundness | `calib/calib_report_v2_7b4bit.json` |
| 3 | **Table 1** prompt × arm at K=4: success T1/T2, realism, win vs. S, generations | 0.45 col | Q1, Q2 | `evaluate/report_tables.py` |
| 3 | Q2 and Q1 paragraphs | 0.45 col | analysis | `tables.json`, `evaluate/judge_arms.py` (best_check vs retry) |
| 3 | **Fig. 3** (a) success vs. K; (b) checker vs. judge success of selected outputs vs. K | 0.45 col | Q1, Q3 | `tables.json` (all `@k` rows) |
| 4 | Budget + selector-inflation paragraph; human annotation paragraph | 0.4 col | Q3, soundness | `tables.json`; `study/analyze.py` |
| 4 | **Fig. 4** full width, 3 rows × 5 columns incl. a checker false positive | 0.6 col | analysis | test run images |
| 4 | Failure analysis with counts; limitations; conclusion | 0.6 col | analysis | judge observations, annotation notes |

Current draft: all elements placed with sized grey boxes and red **xx** for numbers; it compiles to 4 pages with
about one column of slack for the real results text.

## Rubric checklist

- **Novelty & difficulty** — Q1/Q3 are not answered by prior verifier work; fine-grained local ingredient with a
  measured domain gap (red/purple "brown rice"); culturally specific application stated in one paragraph only.
- **Technical soundness** — matched budget; checker (selector) ≠ judge (evaluator), different model families;
  validation-only tuning, frozen hashed test split, run locks; both presentation orders; bootstrap CIs over photos
  and paired tests; non-generative baseline; prompt × arm factorial.
- **Experimental analysis** — every claim has a number with a CI; budget curve and selector inflation explain *why*;
  failure analysis with counts, including what the checker misses; limitations named (author-only annotation,
  15 validation photos, VLM judge).
- **Clarity** — teaser shows the result before the reader starts; one question per figure; captions state the
  takeaway; consistent names (single-shot, best-of-K, check-and-retry; original vs. corrected prompt).

## Producing the numbers (after the test split is frozen)

```bash
run_arms --set test --run test_tuned    --K 8 --prompts tuned       # one K=8 run gives every K <= 8
run_arms --set test --run test_baseline --K 8 --prompts baseline
evaluate/clip_select.py --run test_tuned; evaluate/clip_select.py --run test_baseline
sgedit.tint_baseline --run test_baseline
evaluate/report_tables.py build --name test_report --runs tuned=test_tuned baseline=test_baseline
evaluate/judge.py --items-dir $SGEDIT_WORK/runs/test_report/judge --model gpt-5.5-2026-04-23   # ~600-1200 calls
evaluate/report_tables.py report --name test_report --k-main 4                                 # Table 1, Fig. 3
study/build_study.py --first test_baseline:single --second test_tuned:retry@4                  # team annotation
```

## Conventions

- Blue **Draft** text, grey boxes and red **xx** are placeholders, not results.
- Report only test-set results from locked runs; validation results may motivate design choices, labelled as such.
- Human evaluation is "blinded annotation by the authors", never a user study (no external participants; NTU
  requires ethics approval before data collection).
- No claims about nutrition, health or behaviour change.
- Citations to check against primary sources: `bai2025qwen25vl`, `madaan2023selfrefine`, `ma2025inferencescaling`.
- Author names and student IDs still to be filled in.

## Marking criteria (FY2026 handout)

Report 40 % of the course grade: novelty and difficulty, technical soundness, experimental analysis, clarity (25 %
each). Presentation video 10 %: clarity 20, visualisation 20, logic flow 20, overall quality 40. Due 15 Nov 2026, 23:59.
