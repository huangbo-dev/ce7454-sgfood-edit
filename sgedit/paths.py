"""Shared locations. PlateEdit baseline assets are reused read-only and named here so the reuse stays visible."""
import os
from pathlib import Path

HOME = Path.home()
REPO = Path(__file__).resolve().parents[1]

# Reused from the PlateEdit baseline (read-only): BrushNet weights, SDXL snapshot, prompts, the 40 FoodSG photos + M1 masks.
PLATEEDIT = Path(os.environ.get('SGEDIT_BASELINE', HOME / 'plateedit-v10'))
BASE_RUN = PLATEEDIT / 'data/extracted/run'
BRUSHNET_CKPT = PLATEEDIT / 'work/models/brushnet_sdxl_seg'
SDXL = PLATEEDIT / 'work/cache/hf/models--stabilityai--stable-diffusion-xl-base-1.0/snapshots/462165984030d82259a11f4367a4eed129e94a7b'
BASE_PROMPTS = PLATEEDIT / 'experiment/config/generation_prompts.json'

# New for CE7454 (outside Git): run directories, environments. Model caches: set HF_HUB_CACHE (e.g. $SGEDIT_WORK/cache/hf).
WORK = Path(os.environ.get('SGEDIT_WORK', HOME / 'ce7454-work'))
RUNS = WORK / 'runs'
MAIN_PY = WORK / 'envs/main/bin/python'          # checker (transformers 4.57)
BRUSH_PY = PLATEEDIT / 'work/envs/brushnet/bin/python'  # editor (BrushNet vendor, reused)
