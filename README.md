# SgFood-Edit

**Check-and-retry editing of Singaporean meal photographs** — CE7454 Project 2
(Nanyang Technological University, 2026).

Given a photo of a hawker meal, SgFood-Edit shows the *same* meal with one familiar swap — white rice replaced by
brown rice, or a few broccoli florets added — while the rest of the plate stays as it was. Instead of returning its
first attempt, the editor inspects each output with a vision-language model and retries the ones that failed, with a
change chosen by *why* they failed.

> **Status (7 Nov 2026):** method implemented and tuned on validation photos. Test results, the blinded annotation
> and the report are in progress. Nothing in this repository is a final result yet.

---

## Contents

- [Motivation](#motivation)
- [Research question](#research-question)
- [Method](#method)
- [Experimental design](#experimental-design)
- [Findings so far (validation only)](#findings-so-far-validation-only)
- [Repository layout](#repository-layout)
- [Setup](#setup)
- [Running](#running)
- [Data, privacy and integrity](#data-privacy-and-integrity)
- [What is reused and what is new](#what-is-reused-and-what-is-new)
- [Course information](#course-information)

## Motivation

Singapore's dietary guidance favours small, familiar swaps over new diets. *My Healthy Plate* recommends half a plate
of fruit and vegetables and a quarter of whole grains, and switching from white to brown rice has been promoted by the
Health Promotion Board and in the 2017 National Day Rally. A realistic preview of **one's own meal** with one ingredient
changed is one way to show such a swap.

This project studies only the image-editing problem. It makes no claim about nutrition, health outcomes or behaviour.

The problem is harder than it looks:

- the edited ingredient touches other food, yet everything outside it must stay recognisable;
- **brown rice is a fine-grained edit** — source and target share shape, texture and context and differ mainly in colour
  and grain detail;
- single-shot masked inpainting fails in predictable ways (rice only partly browned or turned grey, broccoli replacing
  the staple instead of sitting on it, a new picture pasted into the mask), and text–image similarity scores such as
  CLIP miss many of these failures.

A person editing a photo would look at the result and try again. SgFood-Edit automates that loop.

## Research question

> At a matched compute budget of *K* generations per photo, does an editor that **checks its outputs and retries the
> failed ones** produce better local-food edits than single-shot masked inpainting? And is a VLM checker a better
> selector than a cheap CLIP score?

Two properties make this a deep-learning question rather than plumbing. First, the checker is itself an imperfect
model, so we measure how far its judgements agree with an independent judge before relying on it, and keep selection
and evaluation on different models. Second, the brown-rice task probes what a general image generator actually knows
about a local ingredient, and separates failures caused by the prompt from failures of the model's prior.

## Method

```
 photo + mask + task
        │
        ▼
 ┌──────────────────────┐    candidate    ┌──────────────────────────────┐
 │ Editor               │ ──────────────► │ Checker (Qwen2.5-VL-7B, 4b)  │
 │ BrushNet-SDXL on a   │                 │ edit done? rest kept?        │
 │ crop around the mask │                 │ realistic? anything added?   │
 │ + feathered paste    │                 └──────────────┬───────────────┘
 └──────────▲───────────┘                                │
            │      pass ─────────────────────────────────┼──► output
            │                                            │
            └──── retry action ◄──── failure reason ◄────┘
                  edit not done → next prompt on the task's ladder, then higher guidance
                  unrealistic / unrequested addition / changed surroundings → new seed
```

| Component | File | Details |
|---|---|---|
| **Editor** | `sgedit/editor.py` | BrushNet-SDXL masked inpainting on an upscaled 1024 px crop around the mask, pasted back with a feathered mask so pixels outside it are the original. fp16 UNet with fp32 VAE on a 16 GB V100: ~8 s per edit. Prompts over CLIP's 77-token limit are rejected rather than silently truncated. |
| **Prompts** | `sgedit/prompts.py` | Per task: a short, positive base prompt, a negative prompt, and a *ladder* of stronger variants used on retries. |
| **Prompt search** | `sgedit/prompt_search.py` | Chooses prompts on validation photos: generates every candidate with fixed seeds and scores it by checker probabilities and colour statistics of the edited region, then saves contact sheets for visual inspection. |
| **Checker** | `sgedit/checker.py` | Qwen2.5-VL-7B-Instruct (4-bit) answers fixed one-letter questions (rice type, broccoli present, staple visible, pasted-in object, real photo?). Scores are expectations over answer probabilities, so they are deterministic and continuous. Used for **selection only**. |
| **Retry loop and arms** | `sgedit/loop.py`, `sgedit/run_arms.py` | Implements the four comparison arms at a shared budget, under either prompt set (`--prompts tuned/baseline`); thresholds, weights and prompts are written to each run's `LOCK.json`. |
| **Colour-transfer baseline** | `sgedit/tint_baseline.py` | Non-generative brown-rice baseline: CIELAB statistics transfer inside the mask, target measured on validation outputs. |
| **Blinded annotation** | `study/` | Self-hosted pairwise annotation site for the project team: annotator codes, practice item, attention checks, repeated pairs; analysis with inter-annotator agreement. |

## Experimental design

**Tasks.** T1-B: add a few broccoli florets on top of the rice or noodles, keeping the staple. T2: replace white rice
with cooked brown rice.

**Arms** (same photos, masks, prompts and seeds; at most *K* generations each):

| Arm | What it tests |
|---|---|
| Single-shot | Baseline: the first generation |
| Best-of-*K*, CLIP margin | Is a cheap automatic score enough to pick? |
| Best-of-*K*, checker | Value of the checker as a selector |
| Check-and-retry | Selection plus retries targeted at the failure |
| Colour transfer (T2 only) | Is generation needed at all? |
| Ablations | *K* ∈ {2, 4, 8}; checker with one criterion removed |

**Prompt × arm.** Every arm runs under two prompt sets: the *baseline* wording (the original long instruction) and the
*tuned* prompts chosen on validation. This separates what the wording fixes from what the loop adds, and shows
whether the loop rescues a weak prompt.

**Evaluation.** A GPT-5.5 judge with a fixed rubric compares outputs pairwise in both orders and scores edit
success, preservation, realism and unrequested additions; it is a different model family from the checker, so
selection and evaluation do not share blind spots. Project-team members annotate the headline contrast (baseline
prompt, single-shot vs tuned prompt, check-and-retry) blind to method; we report inter-annotator and judge–annotator
agreement. To measure selection bias we compare checker and judge verdicts on checker-selected versus first outputs.

**No external participants.** Collecting ratings from people outside the team counts as human-subjects research
under NTU's policy and needs School ethics (ERC/NTU-IRB) approval *before* data collection; approval cannot be given
retrospectively and was not feasible in the project timeline. Human judgement therefore comes only from blinded
annotation by the authors, reported as such.

**Splits.** *Validation*: 20 development photos (15 rice, 5 noodles), used only to calibrate the checker and choose
prompts, thresholds and retry rules. *Test*: new photos of rice and noodle hawker meals, frozen in
`data/test_manifest.json` (paths and SHA-256 hashes) before any test generation.

## Findings so far (validation only)

These guide design choices; they are not test results.

- **Checker vs judge** (`calib/calib_report_v2_7b4bit.json`, 66 outputs): Spearman agreement 0.70 on *edit done*,
  0.34 on *preserved*, 0.25 on *realism* and 0.08 on *unrequested additions*; the two pick the same one of two
  candidates in 21 of 31 pairs. The 7B model was chosen over 3B on this agreement.
- **Brown rice is the bottleneck.** With the original long prompt, broccoli usually passed within 1–3 tries but every
  brown-rice job failed after 4: the rice came out grey and washed-out. Two prompt causes were found and fixed:
  1. the prompt said "white rice" three times inside negations, which CLIP's text encoder cannot read as negations;
  2. the retry wording pushed the prompt past CLIP's 77 tokens, so retries silently lost it.
- With a short positive prompt plus a negative prompt the colour changes strongly but drifts to red or purple rice:
  the generator's idea of "brown rice" is not the light-tan rice served at hawker stalls. Naming red, purple and wild
  rice in the negative prompt removes the drift (red/purple pixels 30 % → 1 %).
- **Prompt search** (15 validation rice photos × 2 seeds, 10 prompts): the best prompt passes the checker's
  *edit done* test in 97 % of attempts vs 7 % for the original; refinements (longer negative prompt, "warm golden",
  lower guidance, "steamed, fluffy") all did worse. Remaining visible flaws: colour slightly cold, occasional crumbly
  texture or an added bowl rim.

See `plan/DESIGN_REVIEW.md` for a critical review of the motivation, the research value and the human evaluation,
and the decisions taken.

## Repository layout

```
sgedit/        CE7454 method: editor, prompts, prompt search, checker, retry loop, arms runner, test-split freezing
evaluate/      GPT judge, blinded arm judging, best-of-K CLIP selector, report tables (Table 1, Fig. 3)
calib/         checker calibration against the GPT judge on validation photos (scripts + JSON summaries)
bench/         editor speed and memory benchmark (feasibility check on a V100)
study/         blinded pairwise team-annotation site and its analysis
plan/          project plan, findings log, design review and open decisions
report/        4-page CVPR-format report (main.tex, main.bib)
requirements/  pinned environments: brushnet (editor), checker (checker + judge)
```

## Setup

Hardware used: 2 × NVIDIA V100 16 GB (editor on one GPU, checker on the other), Python 3.12, CUDA 12.4.

**Environments**

| Environment | Requirements | Used by |
|---|---|---|
| Editor | `requirements/brushnet.txt` + the official TencentARC BrushNet `diffusers` fork at commit `0f9d9e54` | `sgedit.editor`, `run_arms`, `prompt_search`, `bench/` |
| Checker | `requirements/checker.txt` | `sgedit.checker`, `calib/` (GPT judge) |

**Models** (downloaded separately, not in this repository): Stable Diffusion XL base 1.0, the BrushNet-SDXL
segmentation-mask checkpoint, and Qwen2.5-VL-7B-Instruct.

**Locations** are set by environment variables (defaults in brackets):

| Variable | Meaning |
|---|---|
| `SGEDIT_BASELINE` [`~/plateedit-v10`] | PlateEdit baseline project: development photos and masks, baseline prompts, BrushNet and SDXL weights, editor environment |
| `SGEDIT_WORK` [`~/ce7454-work`] | CE7454 runs, caches and environments |
| `SITE_TS_DIR`, `SITE_PORT`, `SITE_HOST`, `SITE_PY` | annotation-site launcher: Tailscale folder, port, tailnet name, Python (for hosting it elsewhere, e.g. the Spark) |
| `HF_HUB_CACHE` | Hugging Face model cache (we use `$SGEDIT_WORK/cache/hf`) |
| `OPENAI_API_KEY` | GPT judge (`evaluate/judge.py`); never commit it |

## Running

```bash
export HF_HUB_CACHE=${SGEDIT_WORK:-$HOME/ce7454-work}/cache/hf
# 1. Checker service on GPU 1
CUDA_VISIBLE_DEVICES=1 python -m sgedit.checker serve --port 8781            # checker environment

# 2. Prompt search on validation photos (repeat per round with a new candidates file)
CUDA_VISIBLE_DEVICES=0 python -m sgedit.prompt_search --task T2 --round r1 --candidates r1.json   # editor env

# 3. All arms on validation (one run name per policy version and prompt set)
CUDA_VISIBLE_DEVICES=0 python -m sgedit.run_arms --set validation --run val_v2_<date> --K 4 --prompts tuned

# 4. Freeze the test split (photos.csv + photos + masks), commit data/test_manifest.json, then run the test arms
python -m sgedit.test_split --photos <folder>
# K=8: arms at every budget K <= 8 are derived from one run (retry paths and seed lists are prefix-consistent)
CUDA_VISIBLE_DEVICES=0 python -m sgedit.run_arms --set test --run test_tuned --K 8 --prompts tuned
CUDA_VISIBLE_DEVICES=0 python -m sgedit.run_arms --set test --run test_baseline --K 8 --prompts baseline

# 5. Evaluation: CLIP selector arm and colour-transfer baseline, then every distinct selected output judged
#    against the shared reference (baseline prompt, single-shot) -> Table 1 and Figure 3
python evaluate/clip_select.py --run test_tuned; python evaluate/clip_select.py --run test_baseline   # checker env
python -m sgedit.tint_baseline --run test_baseline
python evaluate/report_tables.py build --name test_report --runs tuned=test_tuned baseline=test_baseline
python evaluate/judge.py --items-dir $SGEDIT_WORK/runs/test_report/judge --model gpt-5.5-2026-04-23
python evaluate/report_tables.py report --name test_report --k-main 4
# optional within-run pairs (e.g. best_check vs retry at the run's K): evaluate/judge_arms.py build|report --run ...

# 6. Blinded team annotation of the headline contrast
python study/build_study.py --first test_baseline:single --second test_tuned:retry@4
./study/start_site.sh
python study/site_server.py add-rater "Annotator 1"                           # one code per team member
python study/analyze.py
```
```

Every run writes `LOCK.json` (policy, prompts, code hashes, input hashes). A test run refuses to continue if any of
them changes.

## Data, privacy and integrity

- **Not in this repository:** meal photographs (FoodSG-233 and new test photos), masks, generated images, model
  weights, API keys, rater identities and answers, environments. FoodSG-233 must be obtained under its own access terms.
- **Test photos** are taken or collected for this project; anyone identifiable in a photo must have given consent.
- **Human annotation:** project-team members only, signed in with annotator codes; names stay on the server machine
  and never enter the annotation records or Git. No external participants (see *No external participants* above).
- **No tuning on test.** Prompts, thresholds and retry rules are chosen on validation photos only. The checker selects;
  the judge and people evaluate. Checker scores are never reported as the result.

## What is reused and what is new

The baseline comes from our earlier PlateEdit project (CE6190). This repository does not copy its code; it reads its
development photos, frozen masks, baseline prompts and model weights from `$SGEDIT_BASELINE`, read-only. No result from
that project is presented as CE7454 evidence; every comparison is re-run under the CE7454 protocol.

| Part | Origin |
|---|---|
| Development photos (FoodSG-233 subset), frozen masks, baseline prompts, BrushNet/SDXL weights | PlateEdit baseline, read from `$SGEDIT_BASELINE` |
| Feathered paste-back rule and crop-around-mask editing | PlateEdit baseline findings, re-implemented in `sgedit/editor.py` |
| `sgedit/`: fast editor, prompt ladders and 77-token guard, prompt search, VLM checker, check-and-retry loop, matched-budget arms | **CE7454** |
| `calib/`: checker-vs-judge calibration | **CE7454** |
| `bench/`: fp16 BrushNet on a V100 (8 s vs 94 s per edit) | **CE7454** |
| `evaluate/`: GPT judge, arm comparison, CLIP selector; `study/`: blinded team annotation (adapted from the baseline's rating tools) | **CE7454** |
| `sgedit/tint_baseline.py`: colour-transfer baseline | **CE7454** |
| New test photos, test runs, judge evaluation, annotation, report | **CE7454** (in progress) |

## Course information

CE7454 Project 2, FY2026: groups of 4–6; due 15 November 2026, 23:59. Deliverables are a 4-page CVPR-format report
(novelty and difficulty, technical soundness, experimental analysis, clarity) and a presentation video.
