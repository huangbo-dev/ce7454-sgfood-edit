# Analysis for the categorical author-annotation portal

Written 11 November 2026, before any real response existed (the live database held zero events).

The live portal (`ce7454-public-categorical-v1-20261110`) shows 34 blinded pairs and asks three
questions per output, each Yes / No / Unsure: change achieved, other food preserved, looks plausible.
The numeric tools in `../author_analysis` expect a different format and must not be used on these exports.

## Rule fixed in advance

- Per rater and output: success if all three answers are Yes, failure if any answer is No, otherwise unknown.
- Per case: mean of known outcomes across raters for each method; paired difference is retry minus best-of-four.
- Interval: 95% percentile bootstrap over the 20 photos (10,000 replicates, seed 7454), each photo drawn with all its cases.
- Unknown answers are never imputed; pooled lower and upper bounds are reported.
- The seven identical-output pairs stay in every estimate; a second summary excludes them, and same-answer consistency on them is reported.
- Agreement per question: Krippendorff's alpha (nominal) and mean pairwise agreement.

## Use

Each reviewer downloads their own export from the portal. Keep exports, the private mapping and the
output outside this repository.

```text
python -B analyze.py --data-dir <portal>/data --exports r1.json r2.json ... --coverage-only --output coverage.json
python -B analyze.py --data-dir <portal>/data --exports r1.json r2.json ... --output report.json
python -B analyze.py ... --checker-metadata <private checker metadata>.json --output report-with-checker.json
```

`--coverage-only` reports who has rated how many items and reveals no method outcome; use it while
collection is still running. The checker option accepts any JSON containing `output_sha256` and
`checker_pass` records, such as the E3 snapshot import.

Tests: `python -B -m unittest discover -s tests -v` (invented answers only).

The annotators are the non-naive authors. Results are exploratory and are not a user study, a
held-out result, or nutrition or health evidence.
