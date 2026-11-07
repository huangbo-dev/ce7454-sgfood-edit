# Design review — motivation, research value and the user study (7 Nov 2026)

A critical pass over whether SgFood-Edit is worth doing as framed, and what to change so that it scores well on the
CE7454 criteria (novelty and difficulty, technical soundness, experimental analysis, clarity; 25 % each) within the
8 days left. Decisions are marked **Decided** (7 Nov) or **Decide** (still open).

## 1. Does the problem make sense?

**What holds up**

- The application context is real and local: Health Promotion Board guidance (*My Healthy Plate*, whole grains) and
  the push for brown rice at hawker stalls are documented and citable.
- Generation is genuinely needed for "this exact plate": a colour tint of the rice looks plastic and fails on
  over-exposed rice (we tried it on validation photos), and a stock photo of brown rice loses the person's own meal.
- The technical problem is hard in a measurable way. Brown rice differs from white rice mainly in colour and grain
  detail, and SDXL's notion of "brown rice" drifts to red or purple rice — a domain gap for a local ingredient.

**What is weak and must not be over-claimed**

- **Seeing is not the barrier for brown rice.** Most people in Singapore already know what brown rice looks like;
  the commonly cited barriers are taste, texture and habit. A preview of one's own plate is at best a nudge, and we
  cannot test behaviour in a week. The report must present the health angle as *motivation*, not as an outcome.
- **"Add vegetables" is the more convincing preview.** *My Healthy Plate* is about plate composition (half fruit and
  vegetables); showing one's own plate with vegetables added communicates something a person cannot easily picture.
- **Misleading imagery.** An edited food photo can misrepresent a dish. Any use (app, menu) should label images as
  AI-edited; the report should say so in one sentence.

**Recommended framing**

Lead with the *technical* problem and keep the social case modest:

> Off-the-shelf diffusion editors cannot be relied on for fine-grained, local edits: a single attempt often fails
> in ways that text–image scores miss. We study whether a vision-language checker in the loop — selecting and
> retrying — makes such edits reliable without retraining, using healthier-swap previews of Singaporean hawker meals
> as a concrete, culturally specific test case.

Concrete uses to name (as possibilities, not findings): a personal "what if" preview in a food-logging or health
app, and a stall or delivery app showing a healthier variant (brown rice, extra vegetables) of an existing menu photo
without a new photo shoot.

## 2. Is there research value?

Related work already shows that verifiers help at inference time (best-of-N search for diffusion, Self-Refine for
language models) and that VLMs can judge edits. Our project is credible research only if it answers questions those
works leave open. Three do:

1. **Selection vs targeted retry at the same budget.** `best_check vs retry` in `evaluate/judge_arms.py` isolates
   what *acting on the failure reason* adds over simply picking the best of K.
2. **Can a small local checker be trusted as a selector?** We already measure checker–judge agreement (strong on
   *edit done*, weak on realism and extras). The new part: **selection inflates the selector's own scores.**
   Compare the checker's and the judge's verdicts on checker-*selected* outputs versus random outputs; the gap is
   the Goodhart effect of optimising against an imperfect checker. This generalises beyond food.
3. **Prompt failure modes in CLIP-conditioned editors.** Negations and silent truncation at 77 tokens explained the
   brown-rice failure; fixing them took the checker's edit-pass rate from 7 % to 97 % on validation. Simple, but
   quantified and widely applicable.

### The main risk: the prompt fix leaves little for the loop to do

With the tuned brown-rice prompt passing the checker on ~97 % of validation attempts, check-and-retry will rarely
trigger, most `single vs retry` pairs will be identical, and the headline comparison will show "no difference".
That is a legitimate finding, but a weak story. Two remedies, both cheap:

- **Decided — factorial design.** Run the arms with *both* prompts: baseline prompt and tuned prompt.
  This answers "how much comes from the prompt, how much from the loop, and does the loop rescue a weak prompt?" —
  a clean 2 × 4 table instead of one comparison. Cost: about double the test generation (~1–2 GPU hours).
- **Make the checker see what it currently misses.** The remaining brown-rice flaws (cold grey colour, crumbly
  "fried-rice" texture) are not caught by the current questions. A colour criterion (hue/saturation of the edited
  region, already computed by `prompt_search.py`) could become a checker criterion, chosen on validation.

Also add a **non-learned baseline** for brown rice (colour transfer inside the mask): it shows in one image why
generation is needed and costs nothing to run. **Decided — implemented** (`sgedit/tint_baseline.py`); on validation
it gives plausible tinted rice on textured photos and a flat paste on over-exposed rice, which is the point.

## 3. Human evaluation (was: the user study)

**Ethics — Decided.** NTU's IRB guidance treats student coursework that involves human subjects and counts as
research (a systematic investigation, including evaluation, e.g. surveys) as needing School ERC or NTU-IRB approval
*before* data collection, with CITI training for students; approval is never retrospective. That cannot be done by
15 Nov, so **no one outside the project team is recruited** — no user study, survey or feedback collection.

**What replaces it — Decided.** Blinded annotation by the project team on the existing site (`study/`), reported
as author annotation, not as a user study:
- the headline contrast only: *baseline prompt, single-shot* vs *tuned prompt, check-and-retry*
  (`study/build_study.py --first test_baseline:single --second test_tuned:retry`), so a few annotators suffice;
- blind to method, sides and order randomised, practice item, attention checks, repeated pairs; annotators confirm
  they rate independently;
- reported with inter-annotator agreement (Cohen's kappa) and judge–annotator agreement, which also validates the
  GPT judge that carries the detailed comparisons;
- limitation stated in the report: annotators are the authors, so a user study with approval is future work.

**Still sound from the original design:** identical outputs are not shown and count as ties; names never reach
the annotation records; the video can show a demo run by team members on their own meals.

## 4. What this changes in the plan

| Item | Status |
|---|---|
| Report framing: technical problem first, health swap as motivation, AI-edited labelling | **Done** in `report/main.tex` |
| Factorial prompt × arm on test | **Decided**; `run_arms --prompts tuned/baseline` |
| Colour criterion in the checker (validation-tuned) | optional, after prompt search |
| Colour-transfer baseline for brown rice | **Done** (`sgedit/tint_baseline.py`, judged as `tint vs single`) |
| Selector-inflation analysis (checker vs judge on selected vs random outputs) | add to `evaluate/` once the test run exists |
| Human evaluation: blinded team annotation of the headline contrast across runs | **Done** (`study/`) |
| Ethics: no external participants without prior ERC/IRB approval | **Decided** |
