# Presentation video kit · 15 November 2026

Target length 4:30–4:50. The team plan says ≤ 5 min; confirm against the FY2026 handout before upload.
Video rubric (10 %): clarity 20, visualisation 20, logic flow 20, overall 40.
**Every number below must match the final exported PDF.** If the live Overleaf differs, the PDF wins: edit this script, not the report.

Numbers source: `evidence/fixed-ladder-20261111/SUMMARY.json` and `plan/REPORT_HANDOVER_20261111.md`.
Chart: `results_chart.png` (regenerate with `make_results_chart.py`).

## Results section script (1:50–3:10, about 80 s, ~200 words)

Wording rules from `CLAUDE.md`: checker passes are the *selection signal*, not the result of human quality; human evaluation is "blinded annotation by the authors", never a user study.

**[Slide: two rice crops, original vs revised prompt]** (≈15 s)
> First, the prompt itself matters most. For white-to-brown rice, the original prompt passed our checker on zero of fourteen edits in a single shot. A revised prompt passed ten of fourteen. All later comparisons use the revised prompts.

**[Slide: `results_chart.png`, bars appear one at a time]** (≈35 s)
> We then compared three retry policies on the same twenty photos and thirty-four edits, each with at most four attempts and the same Qwen checker. Retrying with new seeds and the same prompt passed 26 of 34. A fixed prompt ladder, which steps through a predetermined schedule after any failure, passed 29 of 34 in 67 generations. Our adaptive policy, which picks the next setting from the checker's failure label, passed 28 of 34 in 68.

**[Slide: paired 2×2: both pass 28 · ladder only 1 · adaptive only 0 · neither 5]** (≈20 s)
> Paired by photo, adaptive minus ladder is minus 2.9 percentage points, with an exploratory bootstrap interval from minus 9.1 to zero. The two policies returned the identical image in 30 of 34 cases; the failure label changed the retry path in only four.

**[Slide: one-line takeaway]** (≈10 s)
> So structured retry helps over seed-only retry, but choosing the retry from the failure label gave no checker-measured advantage over a fixed schedule.

Follow immediately with the limitations section (author annotation, checker blind spots for realism and paste artefacts, 20-photo retrospective cohort). Fill the author-annotation counts **from the final PDF table**: raters, outputs rated, per-question Yes/No/Unsure.

## Full running order

| Time | Section | Visual |
|---|---|---|
| 0:00–0:25 | Hook: previewing a healthier hawker plate | Original vs edited photo |
| 0:25–0:55 | Question: after a failed edit, does choosing the next setting from the failure label beat a fixed schedule? | Question on screen |
| 0:55–1:50 | Method: BrushNet edit → Qwen checker → stop / rank / retry; three matched policies; credit CE6190/PlateEdit assets | Loop diagram |
| 1:50–3:10 | Results (script above) | Chart, paired table |
| 3:10–3:50 | Blinded author annotation and limitations | Checker-pass image the authors rejected (blinded example, labelled by how chosen) |
| 3:50–4:30 | Prototype app demo (pre-recorded, sped up) | Screen capture |
| 4:30–4:45 | Takeaways | Three bullets |

## Demo recording rules

- Record ahead of time on a warmed worker (`--warm`); cut waiting time and say it was sped up.
- Use broccoli or brown-rice fixtures only. Do **not** show the tofu fixture (visible pasted patches).
- On-screen label: "Research prototype · simulated preview · no nutrition or health claim".
- Only team members' own photos; no one outside the team rates or appears.
- If a generation fails on camera, keep it; do not imply every run passes.

## Final-submission checklist (critical issues that need a human with Overleaf/team access)

1. **Report PDF.** Insert the two names and four student IDs, keep the CE6190/PlateEdit reuse disclosure, export the PDF and check `pdfinfo` = 4 pages, the last reference visible, both table headers, the figure and no citation warnings.
2. **Author annotation.** The table states raters, photos, rated outputs, Unsure handling and that only 4/34 ladder/adaptive selections differ. No new ratings tonight; write a limitation if coverage is partial.
3. **Framing.** Present the null result plainly (script above). Keep the 15 Nov crop-context pilot **out** of the report: unreviewed development diagnostic.
4. **Video.** Record, check length ≤ handout limit, cross-check every number against the PDF.
5. **App.** No deployment tonight. Use the pre-recorded clip only.
6. **Submission.** One member uploads both the PDF and video before 23:59 SGT (late: −5 %/day).
