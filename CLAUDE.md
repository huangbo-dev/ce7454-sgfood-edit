# SgFood-Edit (CE7454) repository guidance

- Baseline assets (photos, masks, weights, baseline prompts) are read from $SGEDIT_BASELINE (the PlateEdit project), never copied into this repo; keep that provenance visible (README).
- Never present baseline-run results as CE7454 evidence. New experiments need their own run directory, locked config and validation-only setting selection.
- Keep photographs, generated images, model weights, API keys, lecture notes and environments out of Git.
- Do not push, make public, or tag releases without the user's direction.
- Prompts live in sgedit/prompts.py and must fit CLIP's 77 tokens (the editor raises otherwise). Write prompts as positive descriptions; put what to avoid in the negative prompt (CLIP cannot read negation).
- Prompts, thresholds and retry rules are chosen on the validation photos only. Any change to sgedit/loop.py POLICY or the prompt ladders needs a new validation run name; test runs are locked.
- The checker selects candidates; the GPT judge and the team's blinded annotation evaluate. Do not report checker scores as the result.
- No ratings, surveys or feedback collected from people outside the project team (a demo recorded by team members is fine): under NTU policy that needs ERC/IRB approval before data collection, which the timeline does not allow. Call the human evaluation "blinded annotation by the authors", never a user study.
