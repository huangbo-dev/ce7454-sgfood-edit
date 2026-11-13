# Local-food naturalness: proposed CE7454 follow-up

Date: 13 November 2026. Status: proposal only; no new generation or quality improvement claimed.

## Decision

Do not promote a longer prompt as the solution. First correct the task/layout contract, then compare structural and reference-conditioned editing on development images. Keep the existing checker-and-retry study, frozen outputs and human-review package unchanged. A new side-vegetable objective is an app extension, not a replacement score for the original broccoli-on-staple task.

## Evidence inspected

- Published research base: `2ef85100d9c32ecded6d45dd7d0e8ae36fb6506e` (`sync/research-evidence-20261110`). Main is older; this proposal does not merge unrelated evidence or change main.
- `sgedit/prompts.py`: the T1 retry explicitly requests bright-green broccoli "sitting on top" of the staple. This is a plausible contributor to the user's unnatural chicken-rice topping, not proof of a causal effect.
- T2 wording was selected using the same Qwen checker's edit-done measure, not Singapore diners' authenticity ratings. Beige/brown colour alone is not evidence of cooked wholegrain rice.
- `sgedit/editor.py`: pixels inside the mask are zeroed before generation; a crop is enlarged to 1024 and resized back. The model must reconstruct grain/food detail. Crop scale and context may affect apparent grain/floret size; this needs an ablation, not an asserted diagnosis.
- `sgedit/loop.py`: realism failures change seed at base guidance; edit failures can escalate guidance to 10/12.5. Neither action explicitly repairs layout, local-food texture or contact geometry.
- A separate 13 Nov review of the 12 Nov internal technical diagnostic found no basis to promote its richer cooked-texture prompt. It remains an internal development observation, not independent human evidence. No current human responses were read for this proposal.

## 1. Vegetables: use a plausible serving location, not a conspicuous topping

### Task contract

Distinguish `add_side_vegetables`, `replace_existing_vegetables`, and the original `T1-B` broccoli-on-staple objective. Do not silently turn addition into replacement, remove chicken/cucumber, or change the requested vegetable species. Choy sum/kai lan are options only if the person chooses them; broccoli remains broccoli when requested.

For the new app side-vegetable objective, ask the user to tap a suitable empty plate/side area. Segment/protect chicken, rice, cucumber, sauce, utensils and plate edge. If there is no plausible free area, return "choose another area" rather than inventing a new plate or covering chicken. A feasible reference serving establishes portion size; generic fixed pixel percentages would be unreliable across zoom levels.

Generate cooked vegetables with realistic stem/floret proportions, restrained colour, matching perspective/light, and contact shadows on the plate. Preserve the chicken-rice arrangement. A small soft boundary can harmonize contact, but evaluate its entire changed region: hard paste-back can preserve pixels while leaving an obvious seam, whereas broad feathering can alter protected food.

### Model changes to test

1. Development-only mask/layout-constrained BrushNet control, same seeds/steps/checker as the current baseline, to isolate the mask/layout effect.
2. A compatible structure-conditioning branch (e.g. segmentation/edge/depth conditioning) that retains meal layout. Validate adapter compatibility before claiming it works with this BrushNet/SDXL checkpoint.
3. A compatible reference-conditioned editor using a consented cooked-vegetable example, selected on development data. Keep source geometry and target texture signals separate to avoid copying the reference plate/background.
4. Retry by failure category: placement -> revise allowed ROI; scale/texture -> different validated conditioning; preservation failure -> reject; no automatic guidance escalation as a cure for realism. These are proposed new policies and must be evaluated at equal generation budgets.

## 2. Brown rice: learn appearance from the intended local serving

There is no single universal Singapore brown-rice appearance. Distinguish 100% cooked brown rice from a brown/white mixture, and record rice variety, mixture ratio when known, lighting and serving style. Do not call a mixed-rice preview 100% brown rice. Do not confuse dark sauce-coated chicken rice, fried rice or uncooked grains with the target.

Collect a small consented reference set initially: approximately 20–30 distinct real cooked servings covering hawker/canteen/home settings, with both whole-plate and grain-detail crops. This is a starting curation target, not a guarantee that a model can be trained effectively. Remove faces/identifying receipts; record provenance, permission and target labels. The references should show actual grain shape, subtle bran colouring, moisture/clumping, translucency and portion geometry, not merely a brown hue.

Test reference conditioning with a mask restricted to rice and a protected non-rice mask. Preserve the rice mound silhouette and approximate grain scale. Where the editor supports it, compare lower-strength image-to-image/structure conditioning to full inpainting; current BrushNet blank-mask input has no equivalent denoise-strength switch, so do not invent one in configuration. Evaluate guidance and strength on development only, with identical controls and budgets.

Do not fine-tune first. If reference/structure conditioning still fails consistently, collect a larger diverse consented training set and test a small adapter/LoRA against the non-finetuned baseline. A handful of uploaded images is not sufficient evidence for generalization. Split by original photo/session/source before augmentation; prevent the same meal or near-duplicate reference crossing training/development/test. Record compute/memory and licensing feasibility before training.

## 3. Staged study, not an unbounded rerun

### Stage A: controlled development pilot (48 outputs)

- Twelve eligible development cases: six vegetable, six rice; two fixed seeds; two conditions. 48 total. Existing inspected cases remain diagnostic, not held-out.
- Freeze case identities, allowed masks, protected masks, target definitions and hashes before generation. Exclude or separately label cases whose new side-vegetable intent cannot satisfy the original T1-B contract.
- Compare two policies at the same target: control vs layout/structure intervention. If side placement changes the original objective, both arms must use the new objective and results must be reported separately from T1-B.
- Use the same model checkpoint, step count and budget unless the changed factor is explicitly the method under test. Do not bundle prompt+mask+CFG changes and attribute the gain to one component.
- Proposed seed IDs 1107 and 2207 are design choices, not results. Check actual model availability/memory and obtain execution approval before GPU generation.

### Stage B: reference conditioning

Only after compatible implementation and references exist, compare the selected Stage A setting with/without reference conditioning on a separate development batch. Hold reference-selection rules fixed. If changing the generator, label a model comparison and report latency/memory as well as quality, rather than claiming a clean reference-only ablation.

### Confirmation

Freeze the selected policy before collecting/evaluating new unseen meals. Keep the existing author-review cohort unchanged. Independent-photo confirmation requires new photos not used in prompt/mask/model selection; merely using another judge does not make old photos held-out.

## 4. Evaluation and rejection

Primary rubric, separate dimensions: requested change, local-food naturalness, plausible serving/portion, preservation, and obvious artifacts. Report both full-image and detail-crop judgments. Separate vegetable placement/contact from rice grain texture/authenticity. Allow ties, neither acceptable, and unsure. Blind method names and randomize side/order; assess repeated consistency and report reviewer exposure.

An independent VLM may supplement quality control, but not serve as both tuner and final evidence. Same-Qwen success remains a secondary diagnostic. Human reviewers familiar with local meals should judge authenticity; authors are a convenience sample and not evidence of senior usability. Keep model-specific suggestions out of participant instructions.

Use paired analysis clustered by source photo (seeds are not independent people/photos), report failures and missing cases, confidence intervals and per-task results. Predeclare acceptance/non-inferiority criteria after a small rubric calibration but before the confirmation run. Measure protected-region changes, boundary artifacts, end-to-end latency including queue/checker/retries, and rejection rate. Pixel preservation is not realism. A prettier image is not evidence of lower calories or better health.

App fallback: reject or label uncertain results, offer another placement/photo, never display an unchanged/recoloured image as a successful validated nutritional transformation. The preview is illustrative, not a food composition or clinical assessment.

## 5. Implementation and report checklist

- [ ] Add explicit target/intent and allowed/protected ROI contracts in the separate app repo (`senior-meal-preview`).
- [ ] Curate consented vegetable and local cooked-rice reference manifests; no raw private images/credentials in Git.
- [ ] Implement/test optional conditioning in a development-only adapter; verify model support, dimensions and failure paths.
- [ ] Freeze registries/code/config/checkpoint/input hashes and run the approved 48-output pilot in a new run directory.
- [ ] Audit output identities/hashes/dimensions and collect blinded technical ratings; do not overwrite frozen human-review files.
- [ ] Compare latency and quality; promote only if predefined criteria pass, with rollback/fallback.
- [ ] Add a failure-mode figure and a short limitation/proposed remedy to the report now; add numerical improvement claims only after completed evaluation. Respect the four-page body limit and actual course rules.

This commit is a proposed solution and experiment design, not a model fix already proven, a deployment, a fine-tune, or authorization to launch GPU jobs. No frozen source/results were edited.

