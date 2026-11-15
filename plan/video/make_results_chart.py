"""Results chart for the video, from evidence/fixed-ladder-20261111/SUMMARY.json numbers."""
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
rows = [("Seed-only stopping", 26, 68), ("Fixed prompt ladder", 29, 67), ("Adaptive retry\n(failure-label)", 28, 68)]
fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150)
cols = ["#9aa5b1", "#2f6f9f", "#d08c2f"]
for i, (n, p, a) in enumerate(rows):
    ax.bar(i, p, color=cols[i], width=0.6)
    ax.text(i, p + 0.4, f"{p}/34\n{a} generations", ha="center", va="bottom", fontsize=17)
ax.set_xticks(range(3), [r[0] for r in rows], fontsize=17)
ax.set_ylim(0, 36); ax.set_ylabel("Checker passes (of 34 edits)", fontsize=16)
ax.set_title("Revised prompts · 20 photos · 34 edits · max 4 attempts", fontsize=18)
for s in ("top", "right"): ax.spines[s].set_visible(False)
fig.text(0.5, 0.01, "Adaptive − ladder = −2.9 pp (exploratory 95% photo-bootstrap CI −9.1 to 0.0) · 30/34 selected images identical",
         ha="center", fontsize=13)
fig.tight_layout(rect=(0, 0.04, 1, 1)); fig.savefig("results_chart.png")
