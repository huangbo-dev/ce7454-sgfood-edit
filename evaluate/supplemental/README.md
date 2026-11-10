# Supplemental E3/E4 controls

These are the exact frozen v1 preparation code, protocol and synthetic tests used for the completed 10 November 2026 studies. The original code bytes are preserved. Run `python -B -m unittest -v test_supplemental_controls` from this folder for software checks.

E3 selected among all 136 archived base candidates for 34 revised-prompt tasks using cached OpenAI CLIP ViT-L/14 revision `32bd64288804d66eefd0ccbe215aa642df71cc41`. It used full-image target cosine, FP32 and first-maximum seed-order ties. No diffusion output was generated. Same-Qwen-checker pass counts were 20 single, 22 CLIP, 26 best-of-four and 28 retry.

E4 fixed HSV hue to 30 degrees, saturation to 0.35 and value to 0.82 times original inside the 14 original masks, with half-up RGB rounding and no outside-mask change. The unchanged Qwen checker accepted 0/14 jointly. This single stress control does not establish general specificity or human false acceptance.

See `../../evidence/supplemental-20261110/SUMMARY.json` for audited aggregates, intervals and receipt hashes. Original source photographs, masks, raw per-photo receipts, model files and review mappings remain private outside Git. The aggregate projection does not replace those original locks.

The CLI includes freeze/run commands, but this README is not authorization to rerun inference, download weights, make paid calls or change the frozen protocol. Follow the verified private input and cached-model workflow. Model inference is not part of the synthetic tests.
