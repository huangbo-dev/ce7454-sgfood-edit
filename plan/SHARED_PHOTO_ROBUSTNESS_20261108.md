# Shared-photo robustness experiment, 8 November 2026

This retrospective shared-photo robustness study is separate from the clean primary held-out test in EXPERIMENT_PROTOCOL_20261108.md. The user expressly approved retaining the reviewed 20-photo S5 cohort and all seven flagged masks. It must not be described as a pristine independent test. No photographs are selected based on editing outputs.

## Fixed cohort and contrasts

Use all 20 previously selected S5 meal photos: 14 white-rice and six noodle cases. Generate 34 edit cases per prompt condition: T1-B for all 20 and T2 for the 14 rice photos. Preserve the 13 accepted and seven flagged automatic SAM3 masks unchanged. These are pre-existing single-author mask-QA labels, not human edit-success labels. Keep the 11 unselected eligible photos outside this run.

Run original and revised prompts at K=4 with the unchanged BrushNet-SDXL editor, Qwen2.5-VL checker, seed sequence, prompt ladders, score ranking, first-maximum tie rule, stopping policy and checker error handling from reporting-fix commit 18fb9b2. Each condition supplies single-shot, best-of-K checker and targeted-retry outputs. The single shot is the first candidate in the same baseline seed pool used by best-of-K. Freeze both condition locks, input/model hashes and code/protocol hashes before loading the editor. The existing runner precomputes four baseline candidates and may generate up to three additional adaptive candidates per case. Report actual generation/checker calls and stopping; K is an equal cap, not a promise of equal realized cost. No paid judge, external participant recruitment, model training or changed permissions.

## Interpretation and evaluation

Treat selected-output checker diagnostics, candidate counts and timing as exploratory. The main contrast is revised-prompt retry versus revised-prompt best-of-K checker; original-versus-revised comparisons separate prompt repair from retries. The checker's own score is not independent visual-quality evidence. Batch wall time includes precomputed candidates and is not deployed retry latency. Record and retain every failure; do not selectively rerun unfavorable outputs.

Separate prior mask-QA strata and rice/noodle tasks descriptively. The accepted stratum contains 12 rice photos and one noodle photo; the flagged stratum contains two rice photos and five noodle photos. This confounding prevents a causal claim about mask quality. Accepted masks are not proven accurate, and no pixel-reference IoU/Dice was measured. Do not repair masks after seeing outputs and pool the rerun into this cohort.

Future author evaluation must separately blind the CE7454 selected outputs, method labels, checker flags and prior mask-QA labels. Do not reuse CE6190 mask QA as edit ratings. The paired unit is the photo: 20 clusters, not 34 independent observations. Any cluster bootstrap must keep all tasks, prompt conditions, methods and ratings belonging to a photo together. Repair and test the downstream human-analysis tie handling and bootstrap unit before final human analysis; that separate analyzer does not affect generation or candidate selection.

No nutrient measurement, awareness improvement, dietary-behavior change, older-adult benefit or health outcome is established by this experiment. T2 is a visual full-rice replacement task, not a quantitative implementation of a half-portion wholegrain guideline.

## Provenance and leakage checks

The user confirmed that all source photos were taken by them. All 37 originals remain preserved on the Mac; 31 eligible candidates have stripped copies on GPU04. Twenty were sampled with seed 20261107 before S5 inference on 7 November, after retrospective intake, orientation/cleanup and same-plate deduplication. This was not prospective preregistration. Cross-course reuse must be disclosed; course-team approval for academic reuse remains a separate reporting requirement.

On 8 November, all 31 supplied candidate hashes matched the upload manifest. Against all 40 FoodSG baseline photos covering CE7454 development and the CE6190 base split, there were zero byte/normalized-image hash matches and no 64-bit dHash cross-set or within-pool candidate at the prespecified distance threshold of eight. The minimum cross-set distance was 17. This screen reduces obvious duplicate risk, but does not prove independence. No generated outputs were used for cohort selection. Private source filenames, EXIF and full audit/input/model manifests remain outside Git.

## Safety and reproducibility gates

Copy only the frozen binary masks and necessary manifests from Spark. Verify all 20 source IDs and mask hashes against the reviewed provenance, and join exact prior QA records by photo ID. The 20 prepared original-image hashes already match the QA-reviewed images. Preserve original geometry and masks; require matching 1024-square canvases before inference. Do not reconstruct masks from overlays. No inpainting before the complete input manifest and both condition locks exist.

Use a new unique run directory, never resume under changed code/models or overwrite archived results. A failure creates FAILURE.json and stops; incomplete output remains visible. Record model/runtime revisions, source hashes and code commit. Use existing local cached models in offline mode. Keep main and published fixes unchanged. This local experiment does not authorize uploading photos/results, participant recruiting, paid API calls or publishing a new branch.
