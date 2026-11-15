# Recording shot list · Jianying-style video · target 5:30

Deadline 16 Nov 23:59 SGT. MP4, zipped with the PDF (≤ 500 MB). Captions on every spoken number; markers may watch muted.
**Before export, check every number against the final PDF.** Numbers below are from `evidence/fixed-ladder-20261111/SUMMARY.json`.

## Record these first (raw footage)

| # | Footage | How |
|---|---|---|
| A | Phone screen: open SG Food Edit → My photo → take a photo of a real rice meal → Brown rice → drag slider | Android screen recorder, portrait. Team member's own meal only |
| B | Same, "Add broccoli" (~20 s wait; keep the progress bar, speed ×4 in edit) | Screen recorder |
| C | Hand holding phone over a hawker plate, snapping the photo | Second phone, 5–8 s, landscape |
| D | Results chart | `plan/video/results_chart.png` (regenerate with `make_results_chart.py`) |
| E | Loop diagram: photo → BrushNet edit → Qwen checker → pass? stop : retry (max 4) | Draw in Jianying text/shapes or Keynote, export PNG |
| F | 2–3 research examples: original vs selected output, one failure | From the report figure (same images as the PDF) |
| G | Team face cam, 1–2 lines each (optional) | Front camera |

Do not show: the tofu fixture, unreviewed context-pilot outputs, anyone outside the team.

## Voice-over and edit (Jianying timeline)

**0:00–0:25 Hook** (C → A slider reveal; upbeat music, big caption)
> Can AI show you a healthier version of your own hawker meal, before you order it?

**0:25–1:05 Problem** (failure examples F; caption "AI edits are unreliable")
> Image editors are good at big changes but unreliable at small, local ones, like turning white rice brown or adding broccoli on the rice. They often redraw the plate or paste something fake. We asked: if an automatic checker spots a failure, how should we retry?

**1:05–2:00 Method** (diagram E, animate arrows step by step)
> We edit with BrushNet SDXL and check each result with the Qwen2.5-VL vision-language model. If it fails, we retry, up to four attempts. We compared three ways to retry: a new random seed only; a fixed ladder of stronger prompts; and an adaptive policy that picks the next setting from the checker's failure label. Same 20 photos, 34 edits, same budget. Photos and masks reuse our CE6190 PlateEdit assets.

**2:00–3:20 Results** (D, bars appear one by one; then a 2×2 paired table)
> Revising the prompt mattered most: for brown rice, single-shot passes went from 0 to 10 of 14. With retries, seed-only passed 26 of 34, the fixed ladder 29, adaptive 28, at about 68 generations each. The two ladder policies chose the identical image in 30 of 34 cases; adaptive minus ladder was −2.9 points, interval −9.1 to 0. So structured retry helps, but choosing the retry from the failure label gave no measurable advantage.

**3:20–4:00 Human check and limits** (F, captions)
> The checker selects images; it is not ground truth. Blinded annotation by the authors [insert raters / outputs / key counts from the PDF]. It is a small, retrospective set of 20 photos, and the checker misses realism and paste artefacts.

**4:00–5:00 Product demo** (A, then B at ×4; caption "Prototype · not nutrition advice")
> We built this into SG Food Edit. Take a photo, the app finds the rice, and brown rice takes about three seconds: it recolours your real rice. Adding broccoli uses the AI editor and takes about twenty seconds; it is still rough. Nothing is stored and nothing is reviewed by a person.

**5:00–5:30 Takeaways** (G or text cards)
> One: prompt design gave the biggest gain. Two: checker-guided retry beats retrying with random seeds alone. Three: making the retry adaptive did not help here. Next: human-rated quality on new photos.

## Export

1080p, 30 fps, MP4 (H.264). Name e.g. `CE7454_P2_<all members>_video.mp4`. Watch once fully with sound off to check captions.
