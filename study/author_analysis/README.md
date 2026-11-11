# Offline author comparison and checker join

This isolated analysis package was prepared on 9 November and extended on 10 November with a preserved-E3-snapshot import. `ORIGINAL_VALIDATION.json` records the original file hashes, not the current revision of checker_join.py. compare.py, endpoint.py and the original fixtures remain unchanged. `HISTORICAL_HANDOFF.md` preserves prior usage/provenance explanations; its old access and unfinished E3/E4 statements are historical. Current revision receipts and the project checklist supersede those status statements.

Run `python -B -m unittest discover -s tests -v` from this directory. Tests use invented responses and synthetic bytes only. The real-response analysis is still pending; no human labels or checker/author estimates are created by publication.

Use `analysis/compare.py` for the frozen per-author endpoint and photo-cluster analysis, and `analysis/checker_join.py` for exact candidate-hash joins. Roster/exposure freeze, private package locks, actual exported answers and the extraction receipt are required. Keep data, outputs, identities, codes, mappings and raw answers outside this repository.

This addition does not replace or deploy the older `study/` portal and does not activate any route. Do not use the older preference-only analyzer to infer the new per-output joint endpoint. E3's 23 extra outputs and the fixed-stopping output need a separately frozen extension if independently rated; the current primary package is the original 68-pair two-condition package.

## Preserved E3 snapshot import

The completed E3 archive retains 149 candidate checker records and hashes,
covering all 34 selected revised best-of-four and all 34 revised retry outputs.
`extract-e3` verifies the independently retained E3 lock checksum, its original
source result/policy receipts, the case cohort and selected image hashes. It
recomputes checker scores/pass rules and best-of-four first-maximum selection.
The real local import reproduced 26/34 best-of-four and 28/34 retry checker
passes and joined all 68 selected method slots to the locked review pixels.
No human answers were read, created or inferred.

```text
python -B analysis/checker_join.py extract-e3 --data-dir /approved/frozen-review/data --e3-lock /private/E3/LOCK.json --e3-lock-sha256 dc389e33a3dfa0260b3c05ffe6ca56951e0f71739094ed19708d44eb644f212d --output /private/new-primary-checker-metadata.json
```

Keep that output and its printed SHA256 private. The existing analyze command
requires this receipt, the frozen actual author roster and real exported
answers. Schema 2 explicitly withholds original-condition diagnostics when
those checker records are unavailable. It reports unknown retry generation
counts, since the E3 snapshot does not contain the entire retry trajectory.
Four best-of-four calls are known. Never infer retry length from its selected
tag or substitute the aggregate 68-call count into every case.

This import authenticates the preserved 9 November E3 pre-study snapshot, not
the original 8 November inference-time immutability. It is not a fresh GPU04
read. The existing live-run extractor remains available when authorized host
access works and gives full trajectories, with its explicit provenance limits.
