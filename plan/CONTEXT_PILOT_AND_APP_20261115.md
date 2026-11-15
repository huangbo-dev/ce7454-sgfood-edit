# Development context pilot and app reliability · 15 November 2026

Status: Spark02 completed all 48 outputs at 2026-11-15 02:01:40 UTC (exit 0).
Expected case/seed/condition coverage, output hashes and finite preservation metrics passed.
Visual naturalness review remains pending. This is a development diagnostic, not a new test result.
The earlier DNS blockage has cleared. Termius SSH works; SFTP copying stalled, so the
isolated checkout was cloned using Spark02's existing GitHub SSH authorization.

Execution checkout: `/home/lily/ce7454-work/context-pilot-code-20261115`, commit
`c03cf4432fc14ca520e1cb320844ea15246bc383`. Inputs and all 18 actual model files have
SHA256 records. The 12 task cases represent **nine source photos**, not 12 independent
photos. `10e4869ba5d7-T1-B` has identical crop bounds and is retained and flagged.
Original M1 masks were copied unchanged and conservatively marked `needs-review` because
no new semantic QA verdict was available. The protected region is explicitly the M1
complement; its metric duplicates outside-mask preservation, not independent ground truth.

The NVIDIA GB10 was idle at launch; CUDA and the installed BrushNet classes were verified.
A separate process uses the existing environment, cached weights only, a PyTorch memory
fraction cap of 0.18, and a 45-minute supervisor timeout. Existing live services were not
restarted. The live worker continued responding during generation.

`gpu_ready: false` in the older live worker checks catalogue fixture completeness; tofu
input/mask files are absent. This is not a failed GPU check. `photo_ready: true` is also
only a configuration/source-code test, not proof of end-to-end image generation.

## Why this experiment

The current editor zeros the editable region and enlarges its crop before synthesis.
More surrounding context might improve food scale and placement. This is a hypothesis,
not a finding. Use the existing BrushNet editor and compare crop margin 0.25 with 0.50,
holding prompts, masks, guidance, steps and paired seeds fixed. Do not change the
broccoli-on-staple task into a side-vegetable task, train weights, or replace frozen outputs.
This is a concrete, supported first experiment within the broader 13 November pilot proposal;
it does not implement reference conditioning or model fine-tuning.

## Cohort and analysis

Select six T1-B and six T2 cases from the documented development cohort, by sorted ID
within task among technically eligible inputs, before generating new outputs. Preserve
original mask QA flags. Do not select based on whether existing output looks good.
Use seeds 1107 and 2207: 12 cases × 2 seeds × 2 crop conditions = 48 outputs.
Record common source-photo group IDs across repeated tasks/variants.
Retain and flag identical crop boxes caused by clipping; do not replace those cases.

Blind method/order for naturalness, task completion and preservation ratings, with
ties, neither and unsure available. A single author's review is exploratory, not independent
validation. Summarize within photo first; a bootstrap must resample source photos, not
treat 48 generated images as independent observations. Keep all failures.
Outside-mask, protected-region and far-outside MAE are preservation diagnostics, not
naturalness measures. Near-boundary differences are expected from feathered paste-back.
Do not choose a winner using the same checker that will subsequently evaluate it.

## Required private manifest

JSON object with `study_type: development_crop_context_diagnostic`, `selection_rule`,
`split_evidence` (path/hash of the existing development registry), and 12 `cases`.
Each case requires:

- `case_id`, `photo_group`, `split: dev`, `task: T1-B|T2`, `source: rice|noodles`,
  `mask_qa: accept|needs-review`.
- `image`, `mask`, `protected_mask`: paths relative to `--work`.
- `image_sha256`, `mask_sha256`, `protected_mask_sha256`.

All canvases are 1024 square. Masks are single-channel binary, nonempty and not full-frame;
protected and editable regions must not overlap. The protected mask can be the complement
of the existing edit mask if that definition is explicitly recorded; it is not new semantic
ground truth. Check split membership against the original registry; a `dev` label alone
does not prove it. Never commit private photos or reviewer mappings.

`--model-audit` is JSON with a `files` list of `{path, sha256}` records covering the actual
BrushNet/SDXL weights, config and tokenizer files used by `sgedit.paths`.

## Reproduction command

Use the existing BrushNet Python environment; set `SGEDIT_BASELINE` to the verified model
workspace. Commit the reviewed code and use a fresh output directory outside Git.

```sh
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
python -m sgedit.context_pilot --manifest "$DEV_MANIFEST" --work "$SGEDIT_WORK" \
  --model-audit "$MODEL_AUDIT" --run "$NEW_RUN_DIR" --preflight-only
# After checking GPU availability, free memory and the preflight:
python -m sgedit.context_pilot --manifest "$DEV_MANIFEST" --work "$SGEDIT_WORK" \
  --model-audit "$MODEL_AUDIT" --run "$NEW_RUN_DIR"
```

The script records hashes, code commit, device, full specs, crop boxes and all output metrics.
It refuses existing output directories. A failure keeps partial outputs and a failure receipt.
Preflight checks inputs/config; it does not claim GPU compatibility or memory suitability.
No human naturalness benefit can be claimed until outputs are reviewed.

## Four-case cached audit remains first

The report says fixed ladder and adaptive select identical images in 30/34 cases.
The four differing selections need exact case IDs, output hashes, prompts, settings and
ratings from `fixed_ladder_tuned_20261111_4mBh2W/cases.jsonl` and `LOCK.json` on the research host.
Those records are not present in the checked Mac snapshot. Do not reconstruct them from totals.
This audit needs no new generation. Do not claim overall human ladder performance from
only four pairs; the existing author ratings compare best-of-four with adaptive.

## App changes and remaining limitations

- GPU HTTP requests now fail fast with 429 when another request is active, including model
  loading; the Rust gateway maps that to its existing `gpu_busy` UI error.
- Malformed JSON selection types get a structured 400 instead of a handler exception.
- Request logging includes model-load and generation elapsed time, without tokens or images.
- Use `--warm` when deploying. First-generation/checker latency can still exceed the gateway
  deadline; the retry budget is not a hard execution timeout.
- A real asynchronous job API (ID, status, cancellation and result retrieval) is still needed
  for long runs. Do not auto-resubmit after timeout: the original run may still be active.
- This Mac snapshot has predefined-fixture inference. The live Spark worker additionally has
  a photo-upload route; it must be reconciled before deploying these local worker changes.
  Do not overwrite the newer uploaded-photo route with this older local snapshot.
  Segmentation quality, texture/flavour control and daily-meal performance remain separate work.
- The standalone live app source was backed up to `huangbo-dev/senior-meal-preview`, branch
  `sync/spark-photo-worker-20261115`, commit `d818a1e755ec657602f43f5cace722a2035f2c01`.
  This preserves the current uploaded-photo code; main/production and the running service were not changed.
- No new naturalness benefit, comparative speedup, public deployment or live report revision is claimed here.

## Local verification

- Six manifest-contract unit tests passed (eligibility, hashes, path containment, duplicates).
- Five GPU-worker unit/HTTP tests passed, including busy rejection, lock release after failure,
  malformed selection types, authentication and explicit dry-run behaviour.
- Rust API regression test passed for 429/busy, 422/unsupported, 503/not-ready and 500/unreachable.
- Python compilation and experiment CLI help passed; `git diff --check` passed.
- HTTP tests required localhost socket access outside the sandbox. No public listener was created.
- Spark image/model preflight and all 48 output/hash checks passed. The supervisor exited 0.
  Human naturalness review and deployment of app fixes remain pending.

## Completed diagnostic: interpretation and remaining checks

| Task | Crop | Outputs | Mean outside-mask MAE | Median generation seconds |
|---|---|---:|---:|---:|
| T1-B broccoli | 0.25 control | 12 | 0.0004883024182984907 | 10.77 |
| T1-B broccoli | 0.50 wider | 12 | 0.0005085863965523351 | 10.76 |
| T2 brown rice | 0.25 control | 12 | 0.00018836200381185846 | 10.79 |
| T2 brown rice | 0.50 wider | 12 | 0.0002074614891263748 | 10.79 |

Far-outside MAE was zero for every output, partly enforced by paste-back. Wider context
had slightly higher boundary-inclusive outside MAE; this cannot establish a naturalness
winner. Timings are warm edit calls, not upload-to-result app latency or cold-start time.
There are 24 review pairs, clustered within nine source photos. Two pairs have identical
crop bounds but nonidentical output bytes: do not attribute their differences to crop margin.
Inspect repeat-run determinism before interpreting small paired differences, and report a
sensitivity summary excluding the ineffective crop case. Do not silently discard it.

Analysis receipt: `/home/lily/ce7454-work/runs/context-pilot-20261115-analysis/summary.json`.
Results SHA256: `6233c5f02b72736e347cc168896495992fcdfc01a9889e41daec96c898ab5c90`.
The existing report's frozen cohorts and human responses were unchanged. Do not replace
live Overleaf with this repository's older `report/main.tex`; reconcile with the latest live copy first.

## Standalone app patch prepared

The older extension fixes have now been reconciled with the live uploaded-photo app lineage,
in `huangbo-dev/senior-meal-preview`, branch `fix/spark-photo-request-admission`, commit
`c5affb5`. Both photo and catalogue inference routes share admission, and worker 429 maps to
`gpu_busy`. 27 Rust API tests and 16 Python tests passed; 21 research-adapter tests require
Spark dependencies and were skipped locally. The running service was not changed. Follow
`docs/SPARK_REQUEST_ADMISSION_20261115.md` in the app branch before deployment.
