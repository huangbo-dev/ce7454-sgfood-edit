# CE7454: remaining evidence pipeline, 9 November 2026

## Completed here

Added `analysis/checker_join.py` and synthetic regression tests. This is an
isolated offline addition, not a deployment or a change to the frozen review
package. The existing comparative analyzer and endpoint were copied unchanged
only to make the addition runnable and testable.

The new tool closes the software gap for report question Q3: joining each
selected output's checker verdict to the same output's author rubric judgment.
It does not close the evidence gap: no real ratings were read or collected, and
no real checker/author result has been computed.

It provides:

- An extractor that verifies the raw run's result/lock receipts against the
  frozen review mapping, checks all referenced candidate bytes, recomputes
  checker thresholds and ranking scores, and verifies first-maximum selection
  and stopping behavior.
- An exact condition, photo, task, candidate tag and full SHA256 join to the
  reviewed A/B pixels. An extractor checksum receipt is required by analysis.
- Separate false acceptance among checker passes and false-positive rate among
  author failures. The two have different denominators.
- Fixed-author, case-weighted author success and checker-minus-author rates.
  Each author's four rubric fields are thresholded before aggregation.
- Missing and Unsure counts, with worst/best-case identification bounds. These
  bounds are not confidence intervals or invented ratings. A point estimate is
  withheld whenever its relevant denominator contains unknown outcomes.
- The existing identical-output conflict gate. Conflicting endpoints on
  identical A/B pixels withhold that condition's diagnostics without rewriting,
  dropping or averaging away responses.
- Overall and separate T1-B/T2 summaries. Call counts are policy generation
  counts per case, not multiplied by reviewers and not standalone latency.

The original comparative analyzer still owns the primary paired photo-cluster
bootstrap. This addition does not reinterpret checker results as independent
quality evidence and does not add a significance test.

Provenance is deliberately narrower than a historical checker audit: results,
policy locks, selected tags and image pixels are tied to frozen receipts. Every
referenced candidate JSON receives an extraction-time hash, but no independently
preserved historical checker-JSON hash manifest was available. A consistent
historical score edit could survive those checks when selection and the frozen
result verdict remain unchanged. Reports disclose this limit. Obtain and verify
the historical candidate-metadata audit manifest before claiming the checker
metadata itself is historically unchanged. The extractor receipt protects the
new snapshot afterward; it does not establish its past authenticity.

## Provenance checked locally

The local frozen review package was freshly verified with `compare.load_package`
on 9 November: all locked manifests/media match, 68 pairs, study version
`d8aba9859afa277bbe0b`. Package-lock SHA256:

`bc4cf1deccd0e1aa5483093789c00bf8a5385b30c496738ad2a01adfe56326f8`

The latest available downloaded Overleaf source was read from the 9 November
10:14 SGT export. It already contains the 0/34 unchanged-photo control, the
method diagram, cost plot, revised-prompt task reversal, cluster interval and
seed-only early-stop control. No redundant GPU control or live report rewrite
was performed. Live Overleaf is not freshly synchronized by this package.

The source document remains a shared-photo retrospective study, not independent
held-out evidence. Seven flagged masks remain in the frozen cohort.

## Run only after authorized source access is available

Run from this folder with Python 3.12 or later; the module uses only the standard
library. Keep all outputs private and outside public frontend assets or Git.
The following are examples, not evidence commands already ran on real data.

### 1. Extract checker metadata from the locked run

```text
python analysis/checker_join.py extract --data-dir /home/lily/ce7454-author-review-20261108/data --run-root /home/lily/ce7454-work/runs/shared_hawker_20261108_k4 --output /private/approved-location/checker-metadata.json
```

The study package is on Spark and the run is on GPU04. They must be readable on
the same authorized executor before that example can run. Use the existing
authorized transfer workflow and verify hashes. Do not invent access, bypass
SSH trust, or move FoodSG images to a new recipient. The extractor checks pixels
but does not save or transmit image content. Preserve the printed report SHA256
separately as the extractor receipt.

### 2. Analyze real exported answers only after roster freeze and collection

```text
python analysis/checker_join.py analyze --data-dir /approved/frozen/data --metadata /private/checker-metadata.json --metadata-sha256 RECEIPT_FROM_EXTRACT --roster /private/precollection-roster.json --exports /private/author-one-export.json /private/author-two-export.json --output /private/new-checker-author-report.json
```

Use the actual fixed roster, exposure declarations and unmodified latest export
from each author. Do not manufacture a roster or pass the synthetic fixtures as
research data. Existing output paths are rejected rather than overwritten.

Point and bounds statuses are explicit in each metric. If identical-output
conflicts exist, resolve them through documented author review while retaining
raw revisions; never force ratings to agree in code.

### 3. Tests

```text
python -m unittest discover -s tests -v
python -m compileall -q analysis tests
```

Tests use invented author responses, synthetic non-image bytes and temporary
directories only. They do not access the real response database or mutate the
study package.

## Remaining gates and useful team contributions

1. Confirm actual Project 2 authors, full names/student IDs/order, existing work
   and prior exposure. Course Group 12 membership alone is not final authorship.
2. Freeze the author/exposure roster before the first real rating. Ask teammates
   whether ratings/masks already exist before repeating work.
3. Activate the staged private review route and issue review access only with
   the required approval. No route or credential was changed here.
4. Collect the 34 primary revised-prompt pairs; each output needs edit,
   preservation, realism and extras, with Unsure allowed. Preference alone
   cannot answer joint success. Original-prompt ratings are supplementary.
5. Run the existing comparison and the new checker join on verified exports.
   Report author familiarity, missingness, task differences and consistency
   conflicts. A reference/reproducibility audit can proceed without sharing
   images; it is a suitable immediate teammate contribution.
6. Only then select declared qualitative cases for the report, preserving
   reviewer blinding/exposure records. New-photo confirmation and unfinished
   CLIP/colour controls remain distinct work, not claimed complete.

## Current access limits

The existing Windows strict SSH attempt to GPU04 failed at connection with
`Permission denied`, before authentication. No trust or credential change was
attempted. The GitHub connector could not resolve the study repository (404).
Thus this package is local-only, unpushed and not yet exercised against the raw
GPU04 metadata. The 16 initial software tests passed; see the validation record
for the final test count after review.

No human review codes, author identities, private mappings, images or real
responses belong in a distributable code archive.
