# Short cut · ~3:00 · record now

Footage needed (only 3): **A** phone screen recording, brown rice on a team member's own rice meal (open app → My photo → photo → Brown rice → drag slider). **B** `results_chart.png`. **C** loop diagram (4 boxes: Photo → Edit (BrushNet) → Check (Qwen) → Pass? Stop : Retry ≤4).

| Time | Visual | Voice-over (read as written) | Caption |
|---|---|---|---|
| 0:00–0:20 | A: slider reveal | "Can AI show you a healthier version of your own hawker meal before you order it? We built SG Food Edit to try." | Healthier swap preview |
| 0:20–0:45 | Report example images (failure) | "But AI image editors are unreliable at small edits like white to brown rice. They often redraw the plate. So we asked: when an automatic checker spots a failure, how should we retry?" | AI edits often fail |
| 0:45–1:25 | C, arrows animate | "Each edit is made by BrushNet and checked by the Qwen vision-language model, with up to four attempts. We compared three retry rules on the same 20 photos and 34 edits: new seed only, a fixed ladder of stronger prompts, and an adaptive rule that picks the next setting from the failure type." | 20 photos · 34 edits · ≤4 attempts |
| 1:25–2:15 | B, bars one by one | "Rewriting the prompt helped most: brown rice went from 0 to 10 of 14. With retries, seed-only passed 26 of 34, the fixed ladder 29, and adaptive 28. The adaptive rule gave no gain over the fixed ladder; they chose the same image 30 times out of 34." | 26 · 29 · 28 / 34 |
| 2:15–2:40 | A again (sped up) | "In the app, brown rice recolours your real rice in about three seconds. It's a prototype: no person reviews it, and it's not nutrition advice." | Prototype · not nutrition advice |
| 2:40–3:00 | Text card | "Takeaways: prompt design matters most, checked retries beat random retries, and adaptive retry did not help here. Thank you." | 3 takeaways |

Before export: confirm 26 / 29 / 28, 0→10/14 and 30/34 against the final PDF. Export 1080p MP4.
