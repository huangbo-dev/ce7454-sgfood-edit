#!/usr/bin/env python3
"""Adapter between the Senior Meal Preview GPU worker and the research `sgedit` pipeline.

Scope (first integration milestone): only the two edits the research evaluated, one per request,
on rice dishes with no texture or flavour preference:

  extra_vegetables -> task 'T1-B' (add cooked broccoli on the rice)
  brown_rice       -> task 'T2'   (replace white rice with brown rice)

The adapter does not re-implement the research method. It uses, unchanged:
  sgedit.loop.Runner.candidate   generate one candidate, save it, check it, cache it on disk
  sgedit.loop.base_spec          base prompt and settings for the task
  sgedit.loop.next_spec          what to change after a failed check
  sgedit.loop.POLICY             thresholds, seeds and prompt ladders
and repeats only the check-and-retry arm of `Runner.run` (generate, check, stop at the first
pass, otherwise change settings; return the best-scoring candidate tried). `Runner.run` itself
also generates every best-of-K seed candidate for the arm comparison, which the app does not need.

Nothing here imports torch or loads a model at import time; the caller passes in the editor
and checker objects, so tests can use test doubles.
"""

from __future__ import annotations

import hashlib
import importlib
import os
import sys
from pathlib import Path

# change_id -> research task. Anything else is refused by the model path.
SUPPORTED_CHANGES = {"extra_vegetables": "T1-B", "brown_rice": "T2"}
# Dishes whose staple is rice. The research prompts cover rice (both tasks) and noodles (T1-B only).
RICE_DISHES = ("chicken_rice", "tofu_rice")
SOURCE = "rice"
INPUT_NAME = "input.png"
MASK_NAME = "mask_rice.png"
CANVAS = 1024
MAX_ATTEMPTS = 4


class UnsupportedRequest(ValueError):
    """The request is outside the two studied edits; the model path must not run it."""


class PipelineUnready(RuntimeError):
    """Fixtures, research code, model or checker are missing or unusable."""


def resolve_task(dish_id: str, change_ids: list[str], texture: str = "any", flavour: str = "any") -> str:
    """Return the research task for a request, or raise UnsupportedRequest."""
    if dish_id not in RICE_DISHES:
        raise UnsupportedRequest(f"The model path supports only rice dishes {RICE_DISHES}, not '{dish_id}'.")
    if len(change_ids) != 1:
        raise UnsupportedRequest("The model path supports exactly one change per request.")
    if change_ids[0] not in SUPPORTED_CHANGES:
        raise UnsupportedRequest(f"'{change_ids[0]}' is not one of the studied edits {tuple(SUPPORTED_CHANGES)}.")
    if texture != "any" or flavour != "any":
        raise UnsupportedRequest("Texture and flavour preferences are not applied by the model path.")
    return SUPPORTED_CHANGES[change_ids[0]]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fixture_paths(fixture_dir: str | Path, dish_id: str) -> tuple[Path, Path]:
    base = Path(fixture_dir) / dish_id
    return base / INPUT_NAME, base / MASK_NAME


def fixtures_present(fixture_dir: str | Path) -> bool:
    return all(p.is_file() for d in RICE_DISHES for p in fixture_paths(fixture_dir, d))


def load_fixture(fixture_dir: str | Path, dish_id: str):
    """Load the dish photo and its rice mask the way sgedit.run_arms.load does.

    Returns (PIL RGB image, bool HxW mask, input path, mask path).
    """
    import numpy as np
    from PIL import Image

    input_path, mask_path = fixture_paths(fixture_dir, dish_id)
    for p in (input_path, mask_path):
        if not p.is_file():
            raise PipelineUnready(f"Missing fixture: {p}")
    image = Image.open(input_path).convert("RGB")
    m = np.asarray(Image.open(mask_path)) > 0
    mask = m[..., 0] if m.ndim == 3 else m
    if image.size != (CANVAS, CANVAS):
        raise PipelineUnready(f"{input_path} must be {CANVAS}x{CANVAS}, got {image.size}.")
    if mask.shape != (CANVAS, CANVAS):
        raise PipelineUnready(f"{mask_path} must be {CANVAS}x{CANVAS}, got {mask.shape[::-1]}.")
    if not mask.any():
        raise PipelineUnready(f"{mask_path} is empty (no editable region).")
    return image, mask, input_path, mask_path


def default_sgedit_repo() -> Path | None:
    """SGEDIT_REPO if set, otherwise the checkout this file lives in (…/extensions/<app>/gpu-worker)."""
    env = os.environ.get("SGEDIT_REPO", "").strip()
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    if len(here.parents) > 3 and (here.parents[3] / "sgedit" / "loop.py").is_file():
        return here.parents[3]
    return None


def import_sgedit_loop(repo: str | Path | None = None):
    """Import the research `sgedit.loop` module from `repo` (a directory containing `sgedit/`)."""
    repo = Path(repo) if repo else default_sgedit_repo()
    if repo is None or not (repo / "sgedit" / "loop.py").is_file():
        raise PipelineUnready(
            "Research code not found. Set SGEDIT_REPO to the directory that contains sgedit/."
        )
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    try:
        return importlib.import_module("sgedit.loop")
    except Exception as exc:  # torch, diffusers or the baseline prompt file missing
        raise PipelineUnready(f"Cannot import sgedit.loop from {repo}: {type(exc).__name__}: {exc}") from exc


class SgeditAdapter:
    """Runs one supported request through the research check-and-retry loop."""

    def __init__(self, loop_module, editor, checker, fixture_dir, out_dir, max_attempts: int = MAX_ATTEMPTS):
        self.loop = loop_module
        self.fixture_dir = Path(fixture_dir)
        self.max_attempts = max(1, min(8, int(max_attempts)))
        self.policy_version = str(loop_module.POLICY["version"])
        # One cache directory per policy version, so a policy change never serves old candidates.
        self.out_dir = Path(out_dir) / self.policy_version
        self.runner = loop_module.Runner(editor, checker, self.out_dir)

    def run(self, dish_id: str, change_ids: list[str], texture: str = "any", flavour: str = "any") -> dict:
        task = resolve_task(dish_id, change_ids, texture, flavour)
        image, mask, input_path, mask_path = load_fixture(self.fixture_dir, dish_id)
        input_sha, mask_sha = sha256_file(input_path), sha256_file(mask_path)
        loop = self.loop
        # The photo and mask hashes are part of the cache key: replacing a fixture starts a new job.
        image_id = f"app:{dish_id}:{input_sha[:16]}:{mask_sha[:16]}"
        job = {
            "key": loop.job_key(image_id, task),
            "image": image,
            "mask": mask,
            "original_path": str(input_path.resolve()),
            "task": task,
            "source": SOURCE,
        }
        seeds = loop.POLICY["seeds"]
        try:
            # Same sequence and tags as the retry arm in sgedit.loop.Runner.run.
            spec = loop.base_spec(task, SOURCE, seeds[0])
            tried = [self.runner.candidate(job, spec, "seed0")]
            while not tried[-1]["pass"] and len(tried) < self.max_attempts:
                spec = loop.next_spec(spec, task, SOURCE, tried[-1]["failure"], len(tried), seeds)
                tried.append(self.runner.candidate(job, spec, f"retry{len(tried)}"))
        except (UnsupportedRequest, PipelineUnready):
            raise
        except Exception as exc:
            raise PipelineUnready(f"sgedit execution failed: {type(exc).__name__}: {exc}") from exc

        # Selection rule of sgedit.results.summarize_result: best score, first wins ties.
        selected = max(tried, key=lambda c: c["score"])
        gen = selected.get("gen", {})
        steps = loop.ladder(task, SOURCE)
        prompt_step = next(
            (i for i, (p, neg) in enumerate(steps)
             if p == gen.get("prompt") and neg == gen.get("negative_prompt")),
            -1,
        )
        return {
            "dish_id": dish_id,
            "change_id": change_ids[0],
            "task": task,
            "source": SOURCE,
            "policy_version": self.policy_version,
            "job_key": job["key"],
            "attempts": len(tried),
            "attempt_tags": [c["tag"] for c in tried],
            "selected_tag": selected["tag"],
            "selected_passed": bool(selected["pass"]),
            "last_passed": bool(tried[-1]["pass"]),
            "selected_score": float(selected["score"]),
            "selected_failure": selected.get("failure"),
            "seed": int(gen.get("seed", seeds[0])),
            "guidance": gen.get("guidance"),
            "prompt_step": prompt_step,
            "image_path": selected["path"],
            "image_sha256": selected["sha256"],
            "input_sha256": input_sha,
            "mask_sha256": mask_sha,
            "checker_model": selected.get("check", {}).get("model"),
        }


def build_real_adapter(fixture_dir, out_dir, checker_url: str, repo=None, max_attempts: int = MAX_ATTEMPTS) -> SgeditAdapter:
    """Load the research code and the BrushNet model (slow; call once at worker start)."""
    if not fixtures_present(fixture_dir):
        raise PipelineUnready(
            f"Fixtures missing under {fixture_dir}: need <dish>/{INPUT_NAME} and <dish>/{MASK_NAME} "
            f"for {RICE_DISHES}."
        )
    loop = import_sgedit_loop(repo)
    try:
        editor_mod = importlib.import_module("sgedit.editor")
        editor = editor_mod.Editor()
    except Exception as exc:
        raise PipelineUnready(f"Cannot load the BrushNet editor: {type(exc).__name__}: {exc}") from exc
    return SgeditAdapter(loop, editor, loop.CheckerClient(checker_url), fixture_dir, out_dir, max_attempts)
