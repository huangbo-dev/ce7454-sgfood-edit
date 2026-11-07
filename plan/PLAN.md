# SgFood-Edit (CE7454 Project 2) — plan, 7–15 Nov 2026

Due **15 Nov 2026, 23:59** (late: −5 %/day, max 3 days). 4-page CVPR report (40 %): novelty/difficulty,
technical soundness, experimental analysis, clarity — 25 % each. Presentation video (10 %): clarity 20,
visualisation 20, logic flow 20, overall 40. Source: the FY2026 handout.

## Question
Off-the-shelf diffusion editors are unreliable for fine-grained, local edits. Does a vision-language checker in the
loop — selecting among outputs and retrying failed ones with a change targeted at the failure — make them reliable
without retraining, at a matched compute budget? Test case: healthier-swap previews of Singaporean hawker meals
(T1-B add broccoli on the staple; T2 white → brown rice). The health swap is motivation only (`DESIGN_REVIEW.md`).

The PlateEdit baseline is reused as disclosed infrastructure; **no baseline-run number is CE7454 evidence**.

## System (implemented)
1. **Mask**: frozen baseline masks for validation photos; for new test photos, a person-checked mask per photo
   (SAM 2.1 from a box/click, or a manual polygon), supplied to `sgedit/test_split.py`.
2. **Editor**: BrushNet-SDXL, fp16 UNet + fp32 VAE on a V100 (8 s/edit), crop around the mask, feathered paste-back,
   77-token prompt guard.
3. **Prompts**: two sets — *baseline* (original instruction) and *tuned* (validation prompt search). T2 tuned ladder:
   `r1_hawker` → `r2_warm` → `r1_tan`, shared negative prompt naming red/purple/wild rice.
4. **Checker (selection only)**: Qwen2.5-VL-7B 4-bit on the second GPU.
5. **Retry policy** (validation only): edit not done → next prompt on the ladder, then higher guidance; unrealistic /
   unrequested addition / changed surroundings → new seed. Stop at pass or budget K.
6. **Baselines**: single-shot; best-of-K by CLIP margin; best-of-K by checker; colour transfer (T2, no generation).

## Experimental design
- **Prompt × arm**: every arm under both prompt sets (`run_arms --prompts tuned|baseline`).
- **GPT-5.5 judge** (`evaluate/`): blinded pairs in both orders — single vs retry, single vs best_check,
  best_check vs retry (selection vs targeted retries), single vs best_clip, tint vs single.
- **Selector inflation**: checker vs judge verdicts on checker-selected vs first outputs.
- **Ablations**: K = 2/4/8; checker with one criterion removed.
- **Human evaluation**: blinded annotation by the project team of the headline contrast
  (`test_baseline:single` vs `test_tuned:retry`), with attention checks, repeats and inter-annotator agreement.

## Ethics (decided 7 Nov)
NTU policy: student coursework involving human subjects that counts as research (a systematic investigation,
including evaluation, e.g. surveys) needs School ERC / NTU-IRB approval **before** data collection, CITI training
for students, and no retrospective approval. Not feasible by 15 Nov. Therefore:
- **No external participants**: no user study, survey or feedback from people outside the team.
- Human judgement = blinded annotation by the authors, reported as such (not a user study), plus the GPT judge.
- Test photos: food only, taken by team members (or with the right to use); no identifiable people in frame.
- The video may show a demo run by team members on their own meal photos.
Sources: NTU-IRB "Students conducting human subjects research", "Do I need IRB approval", and the
School-level ethics review guideline for student research.

## Data
- **Validation**: the 20 baseline development photos (15 rice, 5 noodles). Never the baseline test photos.
- **Test (new)**: 30–40 photos of rice and noodle hawker meals taken by the team. Frozen with
  `python -m sgedit.test_split --photos <folder>` and committed (`data/test_manifest.json`) before any test run.

## Timeline
| Day | Work |
|---|---|
| Fri 7 Nov | Done: editor, checker + calibration, retry loop, arms, prompt search (T2 ladder), evaluation tools, colour baseline, design review, ethics decision |
| Sat 8 Nov | Validation run v2 (both prompt sets) and judge check; collect test photos and masks |
| Sun 9 Nov | Freeze test split (commit manifest); K=8 test runs, both prompt sets (~2–4 GPU hours) |
| Mon 10 Nov | CLIP arm, colour baseline, `report_tables` build + GPT judging; annotation set; team annotates |
| Tue 11 Nov | Analysis: arms, prompt × arm, selector inflation, ablations, failure cases |
| Wed 12–Thu 13 Nov | Report (4 pages) and figures, following `report/README.md` (page budget, element → data source) |
| Fri 14 Nov | Video (≤ 5 min, team demo), final checks |
| Sat 15 Nov | Submit (one member) |

## Findings so far (validation only)
- Checker (Qwen2.5-VL-7B 4-bit, chosen over 3B): Spearman with the GPT judge 0.70 edit, 0.34 preserve,
  0.25 realism, 0.08 extras; 21/31 pair choices agree.
- `val_v1` (original prompt): T1-B passes within 1–3 tries; T2 failed in every job — grey, washed-out rice.
  Causes: "white rice" inside negations (CLIP cannot negate) and a retry suffix cut off at CLIP's 77 tokens.
- Prompt search (15 rice photos × 2 seeds): `r1_hawker` passes *edit done* in 97 % vs 7 % for the original prompt,
  red/purple drift 1 %. Round-2 refinements were all worse (83 %, 87 %, 73 %, 47 %).
- Risk (design review): with the tuned prompt the loop rarely triggers; the prompt × arm design keeps the
  comparison informative.

## Open decisions (team)
- Group members and owners per workstream; who takes the test photos (30–40, by Sun 9 Nov).
- T2 target: pure brown rice, or the brown/white mix many stalls serve? (The checker gives a mix half credit.)
- Baseline reuse: the report states what is reused; confirm the course allows building on the earlier project.
- Optional, only if time allows: IP-Adapter reference image or a brown-rice LoRA for the remaining colour gap.
