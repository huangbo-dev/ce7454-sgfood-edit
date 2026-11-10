# Offline author comparison and checker join

This is the isolated analysis package prepared on 9 November. Code and synthetic fixtures are copied unchanged; `ORIGINAL_VALIDATION.json` records the original file hashes and validation. `HISTORICAL_HANDOFF.md` preserves the detailed usage/provenance explanation, but its old GPU access and unfinished E3/E4 statements are historical. The current project checklist and supplemental receipts supersede those status statements.

Run `python -B -m unittest discover -s tests -v` from this directory. Tests use invented responses and synthetic bytes only. The real-response analysis is still pending; no human labels or checker/author estimates are created by publication.

Use `analysis/compare.py` for the frozen per-author endpoint and photo-cluster analysis, and `analysis/checker_join.py` for exact candidate-hash joins. Roster/exposure freeze, private package locks, actual exported answers and the extraction receipt are required. Keep data, outputs, identities, codes, mappings and raw answers outside this repository.

This addition does not replace or deploy the older `study/` portal and does not activate any route. Do not use the older preference-only analyzer to infer the new per-output joint endpoint. E3's 23 extra outputs and the fixed-stopping output need a separately frozen extension if independently rated; the current primary package is the original 68-pair two-condition package.
