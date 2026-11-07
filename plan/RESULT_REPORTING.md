# Selected-output reporting contract

## Scope

This is a metadata-only correction to the existing score-based selection policy.
The retry loop still stops at the first passing attempt or its generation budget,
then returns the highest-scoring candidate tried (the first candidate wins ties).
A passing last attempt can therefore coexist with a failed selected output.
No thresholds, weights, prompts, seeds, model settings, or selection rules change.

## Result schema

New result rows have `result_schema_version: 2`:

- `retry`: tag of the selected retry-arm output.
- `retry_passed`: checker pass flag of that selected output.
- `retry_last_passed`: checker pass flag of the final attempt, which controls stopping.
- `retry_steps`: attempted tags in order, including the shared first candidate.

The existing single-shot and best-of-K tags remain unchanged. The console labels
selected and last-attempt pass flags separately.

Historical unversioned rows used `retry_passed` for the final attempt, not the
selected image. Do not relabel, overwrite, or silently reinterpret those records.
For historical or mixed-version summaries, resolve `retry` to its candidate JSON
and read that candidate's `pass`. Schema version is per row, not per directory.
The helper does not write files or mutate its input candidates.

These flags are checker-derived diagnostics, not independent quality judgments,
held-out performance, human judgments, nutritional evidence, or health outcomes.

## Read-only validation replay, 7 November 2026

Source runs: `$SGEDIT_WORK/runs/val_v2_baseline` and
`$SGEDIT_WORK/runs/val_v2_tuned`, each with 35 jobs.

- Baseline prompts: selected retry outputs pass 18/35; historical final-attempt
  flags also pass 18/35.
- Tuned prompts: selected retry outputs pass 30/35; historical final-attempt
  flags pass 32/35. Two rows selected a failing earlier candidate despite a
  passing final attempt.

Replaying metadata construction against all 70 recorded candidate sets preserved
every selected tag, candidate order, budget, and job key. SHA-256 checks confirmed
all 367 JSON/JSONL metadata files in the two runs remained unchanged. Images and
model files were not rewritten or regenerated. The old logged metrics remain
intact; the corrected selected-output counts are a separate audit.

## Offline regression checks

Run from the repository root:

```sh
python3 -m unittest discover -s tests -v
```

Eight tests cover selected/last-attempt disagreement, a selected passing retry,
all-failure selection, first-attempt success, score ties, input immutability,
and the real `Runner.run` control flow with model/config imports and candidate
generation stubbed. They do not load model weights, call a checker/API, or use a GPU.
No new experiment or independent evaluation is implied by these tests.
