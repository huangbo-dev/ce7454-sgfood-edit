# Data and reference collection brief

13 November 2026. Planning targets, not proven sample-size or training requirements.

## Start with references, not a training run

For each target (cooked broccoli and the chosen brown-rice type), aim first for 20-30 genuinely different consented servings: whole plate plus one close crop from the same photograph. Crops and repeated shots are NOT additional independent examples. Include ordinary Singapore hawker/canteen/home meals, several vendors/cooks and lighting conditions, overhead and oblique views, modest and larger portions, and natural sauce/contact variations. Match the intended chicken-rice context rather than collecting only studio bowls.

Brown rice: record whether it is 100% brown rice or a blend, known grain variety and cooked/uncooked state. If composition is unknown, label unknown; appearance alone cannot establish it. Include realistic light-tan bran and normal moisture/clumping, not only dark grains. Keep white rice with dark sauce, fried rice and red/black rice as labelled counterexamples, never silently as the positive target.

Vegetables: record actual species, cooked/raw state and serving location. Capture plausible stems/florets, contact shadows and portion scales. Broccoli examples do not justify silently substituting choy sum or kai lan. Include both natural side servings and examples where no free placement is possible, so the app can reject unsupported edits.

## What each upload needs

- Pseudonymous photo ID; original image; optional detail crop; original capture/session group ID.
- Consent/ownership and permitted uses: local model development, private human review, training if specifically granted. Do not assume a public web photo is licensed for training.
- Dish/context and target type; cooked state; known mixture ratio; lighting/viewpoint; uncertainty notes.
- Separate ingredient mask, allowed edit mask and protected chicken/cucumber/sauce/utensil regions; intended add versus replace action; desired placement.
- For rice, annotate the rice silhouette and a representative grain-scale region. For vegetables, mark contact/placement region and whether sufficient space exists.
- Keep originals private; strip unnecessary location/identity metadata from shared copies; exclude faces, receipts, patient data and reviewer credentials. Commit only schema/code and safe aggregate metadata to Git.

Suggested CSV columns:
`photo_id,session_group,split,target,meal_context,cooked_state,rice_type,mixture_ratio,vegetable_species,action,placement,consent_reference,consent_training,image_sha256,ingredient_mask_sha256,allowed_mask_sha256,protected_mask_sha256,notes`

## If adaptation is still needed

Only proceed after the reference/structure pilot shows recurring failures and a compatible base model is selected. A rough first acquisition budget is 100-300 distinct consented servings per target for a small adapter feasibility study. This is not a guaranteed minimum or enough to promise generalization; diverse sources and clean labels matter more than repeated near-duplicates. Start with a smaller development experiment to determine whether more data helps before collecting at scale.

Single-image target crops can teach appearance but do not by themselves teach faithful local editing. For supervised source-to-edited-target learning, collect valid before/after pairs of the same scene with the intended physical change, camera/lighting as stable as possible, plus correspondence/mask checks. Unrelated white-rice and brown-rice photographs are not pixel-aligned pairs. Do not treat synthetic self-generated outputs as ground truth without independent checks. If reliable paired data cannot be obtained, prefer reference conditioning or an appearance adapter with explicit preservation evaluation over pretending the task is paired supervision.

Split by original meal/session/vendor source before augmentation and reference retrieval. A provisional 60/20/20 train/development/confirmation allocation is a planning example; use group splits and verify target coverage, then lock it before training. The confirmation set must contain new sources not viewed during selection. Never use its photos as reference exemplars. All crops, repeats and near-duplicates stay with their parent group. Existing inspected coursework photos remain diagnostic.

Store preprocessing, base-checkpoint license/hash, adapter settings, trainable layers, rank, learning rate, steps, seed and stopping rule. Select hyperparameters on development only; compare to the unchanged non-finetuned baseline at equal inference budget. Monitor memorization/reference copying, preservation, authenticity and latency. Report negative outcomes.

Spark02 is the preferred inference node, but adapter compatibility, memory, numerical stability and estimated training time must be measured with a bounded smoke test. No reliable training duration or final quality can be promised from the current evidence. No download, paid model use, training or new GPU job is launched by this proposal.
