# Development context pilot and app reliability · 15 November 2026

Status: implementation prepared locally; GPU execution and visual review are not complete.
The Mac could not resolve `angel-zqs-spark02.dynip.ntu.edu.sg` in SSH or Termius.
This is an access failure, not evidence that Spark itself is down.

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

## Run after connectivity returns

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
- Current inference accepts predefined meal fixtures and one supported edit. Personal-photo
  upload, segmentation, texture/flavour control and performance on daily meals remain separate work.
- No new image-quality result, speedup, public deployment or report revision is claimed here.

## Local verification

- Six manifest-contract unit tests passed (eligibility, hashes, path containment, duplicates).
- Five GPU-worker unit/HTTP tests passed, including busy rejection, lock release after failure,
  malformed selection types, authentication and explicit dry-run behaviour.
- Rust API regression test passed for 429/busy, 422/unsupported, 503/not-ready and 500/unreachable.
- Python compilation and experiment CLI help passed; `git diff --check` passed.
- HTTP tests required localhost socket access outside the sandbox. No public listener was created.
- CUDA inference, full image preflight, real model naturalness and live app deployment remain untested.
