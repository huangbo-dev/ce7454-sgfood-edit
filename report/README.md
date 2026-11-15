# Report source (final, 15 November 2026)

`main.tex` is the live Overleaf source exported 15 Nov 2026 21:37 SGT, with six wording cuts made so it compiles to **four pages including references** (Tectonic 0.17; no undefined references). No number or finding was changed. All Table 1 counts match `../evidence/fixed-ladder-20261111/SUMMARY.json`.

Omitted from Git: `figures/qualitative_examples_revised.pdf` (source-photo panels) and the author e-mail line (kept in the private Overleaf copy). A local build without the figure will fail at `\includegraphics`; use the Overleaf project or the private copy in `~/ce7454-final-submission/` for the submission PDF.

Earlier history follows.

# Report source snapshot

Source: reviewed Overleaf export downloaded 10 November 2026 at 09:02 SGT, after the four-page E3/E4 review. Source archive hash is in `../evidence/supplemental-20261110/SOURCE_RECEIPTS.json`.

14 November 2026: this copy is superseded. The live Overleaf report has since been rewritten (new section structure, a whole-image baseline table, an author-judgment table) and already contains the fixed-ladder row (29/34 in 67 generations against 28/34 in 68), matching `../evidence/fixed-ladder-20261111/SUMMARY.json`. It compiled to four pages with no errors or warnings when checked. Treat `main.tex` here as a historical 10 November snapshot until a fresh GitHub-safe export of the live source replaces it; the evidence for the live report's whole-image and author-judgment tables is not in this repository yet.

This is a GitHub-safe copy. Author contact/student identifiers remain in the private Overleaf report. `qualitative_examples.pdf` contains source-photo panels and is deliberately omitted; `main.tex` uses a clearly labelled placeholder if it is absent. The actual reviewed PDF and source export are unchanged. Do not use a placeholder build as the submission PDF.

Build the source for a textual check with `pdflatex main`, `bibtex main`, and `pdflatex main` twice. For the actual report, use the already authorized private figure and confirmed author block, then compile and inspect all pages again. The layout of the public placeholder copy may differ from the reviewed draft.

Outstanding: two names, four student IDs, human ratings/checker-error analysis, author/exposure freeze, new-photo confirmation if claimed, cross-course reuse confirmation and final submission checks. See `../plan/REMAINING_WORK_20261110.md`.
