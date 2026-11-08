# CE7454 pre-test protocol, 8 November 2026

Status: prepared before held-out generation, NOT a frozen or completed test. The audited checkouts have no data/test_manifest.json. No paid judge calls, public recruitment, or new GPU generation were performed for this update.

## Question and scope
Does failure-directed retry improve the visual reliability of Singaporean meal edits relative to selecting among repeated samples, with the same maximum generation budget? Keep BrushNet-SDXL and local Qwen2.5-VL-7B, without weight training. Public-health relevance is motivation only: these images do not establish nutrient composition, awareness gains, dietary change, or health benefit.

T1-B adds cooked broccoli while retaining the original staple. T2 replaces the visible white rice completely with a plausible brown-rice appearance. Preserve evaluate/rubric.json; HealthHub's half-white-rice substitution is distinct motivational guidance, not this task's operational target.

## Prespecified primary comparison
- Revised prompts: targeted retry versus best-of-K checker, K=4. Same eligible photos, masks and initial seeds. Preserve the 18fb9b2 policy and prompt ladder; no post-test tuning.
- Primary outcome: joint visual success per author rating, edit=2 AND preservation=2 AND realism>=3 AND extras=0. Average ratings per edit case, then average paired retry-minus-best differences across cases. Rice photos have two cases, noodles one; this estimand weights cases equally. Also show per-task results so rice's extra task is visible.
- Primary interval: percentile 95% bootstrap, 10,000 replicates, seed 20261108, sampling photos with replacement and carrying all their tasks and ratings together. The fixed small author panel limits generalisation; this is not a population-of-raters confidence interval. Report counts and the interval without a claimed powered hypothesis test.
- No data-dependent sample-size stopping. Before generation, record the entire eligible photo pool, exclusions and reason, final counts, and available author roster. If too small, label the study exploratory rather than invent power.

## Secondary contrasts and costs
- For every arm, compare original versus revised prompts. The prompt-by-policy comparison prevents crediting prompt repair to retry.
- Single-shot and CLIP best-of-K use the same base candidate pool; T2 colour transfer is a non-generative diagnostic control. K=1,2 and 8 are secondary budgets, never a replacement for an unfavourable K=4 result. Record which budgets actually complete.
- A shared cap is not equal realised cost. Log actual editor/checker calls per arm and per-case latency; report distributions. The runner precomputes baseline candidates, so its total batch runtime is not deployment latency. Do not infer speedup from that runtime.
- Report each rubric dimension, per-task results, author agreement and explicit tie counts. For checker false acceptance, compute each author's joint failure indicator on checker-passing selected outputs, average within case, then average across checker-passing cases. Report the number of such cases and ratings; do not silently turn a divided panel into a binary verdict. Do not interpret expected token scores as calibrated success probabilities.
- Optional distinct GPT-family judge: only after explicit API budget and exact model/version are approved, with both pair orders. It is secondary to author evaluation and may share model biases.

## Blinded author-only annotation
Display original alongside each candidate; hide method, prompt family, checker verdict and candidate history. Randomise presentation with a saved mapping. Authors must disclose prior exposure. Record eligibility, completion, repeat/attention checks and exclusions before analysis, using existing study rules unless an amendment is made before collection. Do not recruit external participants without the required ethics clearance. Do not reuse CE6190 ratings as CE7454 evidence.

Hash-identical selected outputs have structural equality, not evidence favouring an arm. Keep tie votes; do not convert a weak plurality into a strict majority. Fix and unit-test study/analyze.py's tie aggregation and photo-cluster resampling before any final analysis. That existing analyzer remains unchanged by this preparation. The standalone preflight checker below is not an annotation analyzer.

## Release gates, in order
1. Confirm course-team permission for cross-course baseline reuse; confirm author names and the four-page/reference rule. Record these outside sensitive/public files as appropriate.
2. Supply eligible new food-only photos and human-checked binary staple masks with photos.csv (file,dish,source; source rice/noodles). Confirm image-use permission and no identifying people. Record visual mask review and near-duplicate/derivative review against tuning images. Hash disjointness alone does not prove independence.
3. Freeze with the existing sgedit.test_split only after review. It writes processed images outside Git and a tracked manifest of hashes/jobs. Never put photos, model weights, credentials, or generated outputs in Git. Do not regenerate a frozen manifest silently.
4. Run python -m sgedit.preflight --manifest data/test_manifest.json --work /home/lily/ce7454-work --development-hashes <verified-json-array-of-source-sha256>. This reads only. It checks the existing manifest contract and processed hashes; it cannot verify consent, mask semantics, near duplicates, image validity, or study approval. Exit 0 means these technical checks only, NOT permission to launch.
5. Verify model checkpoints/revisions, dependency versions, tokenizer limits, code hashes, policy, prompts, seeds and new unique run names. Existing run resume checks do not enforce source-code hash equality; manually compare LOCK.json code_sha256 or add a tested gate before resuming. Run from corrected code, not stale main.
6. Fix/test author analysis and lock this protocol, input manifest, code and analysis revisions together before generation. Keep a dated amendment if anything changes. Launch local K=4 runs only when gates pass; no old-run overwrites. A system error with no delivered image counts as visual failure. Missing author ratings remain missing, not zero: complete paired primary ratings before final analysis, disclose missingness, and never drop cases based on quality. Record all generator/checker errors.
7. Build blinded author-only screens from selected output tags, collect ratings, analyze using the locked code, and populate Overleaf with verified numbers and panels. No API spend or participant outreach is implied.

## Audit and source record
Base code: 18fb9b28a6ba9765229bdeb86020e9f450a82fcc, fix/selected-output-pass. It corrects pass metadata, not ranking or stop policy. Eight offline tests, 70 historical result replays and unchanged 367 archived JSON/JSONL hashes were verified in the preceding fix audit. Tuned development counts are first=24/35, selected=30/35, last=32/35; baseline 12/35,18/35,18/35. These are checker-selected development diagnostics, not independent held-out gains.

Live report: https://www.overleaf.com/project/6adb5f7ac2e32fc02215c7b2 . History label before editing: Before evidence and protocol update - 8 Nov 2026. This branch synchronises the revised live main.tex/main.bib; older repository versions remain in Git history. Main and the published reporting-fix branch remain untouched.

Official sources: https://www.healthhub.sg/programmes/nutrition-hub/eat-more (undated; accessed 8 November 2026); https://go.gov.sg/nnsreport2025 (released 3 October 2026). NNS2025 reports carbohydrate from refined staples 154 g/day in 2019 versus 166 g/day in 2025, not rice/bread food weight. NNS is cross-sectional and does not establish effects of this system.
