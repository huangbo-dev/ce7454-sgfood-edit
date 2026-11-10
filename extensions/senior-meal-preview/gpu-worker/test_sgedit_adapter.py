#!/usr/bin/env python3
"""Contract tests: the app adapter against the real research `sgedit.loop`, with a fake editor and checker.

These run without a GPU. `sgedit.loop` is imported for real (so the prompt ladder, pass thresholds,
scoring, retry policy and on-disk candidate cache are the research code), while the BrushNet editor and
the Qwen checker are replaced by test doubles. Where torch or scipy are not installed, minimal stand-ins
are registered only so that `sgedit.editor` can be imported; no model code is executed.

A real GPU acceptance run (`gpu_worker.py --mode gpu --warm`) is a separate, required gate.
"""

from __future__ import annotations

import base64
import importlib
import inspect
import io
import json
import os
import sys
import tempfile
import threading
import types
import unittest
import urllib.error
import urllib.request
from dataclasses import asdict
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

import gpu_worker
import sgedit_adapter as sa

_TMP = tempfile.TemporaryDirectory(prefix="smp-contract-")
_LOOP = None
_SKIP = None


def _load_research_loop():
    """Import sgedit.loop from SGEDIT_REPO (or this checkout) with a temporary baseline prompt file."""
    global _LOOP, _SKIP
    repo = sa.default_sgedit_repo()
    if repo is None:
        _SKIP = "research sgedit/ not found (set SGEDIT_REPO)"
        return
    try:
        import numpy  # noqa: F401
        from PIL import Image  # noqa: F401
    except Exception as exc:
        _SKIP = f"numpy and Pillow are required: {exc}"
        return
    baseline = Path(_TMP.name) / "baseline"
    cfg = baseline / "experiment" / "config"
    cfg.mkdir(parents=True)
    (cfg / "generation_prompts.json").write_text(json.dumps({
        "T1-B_rice": "test baseline prompt: add broccoli on the rice",
        "T1-B_noodles": "test baseline prompt: add broccoli on the noodles",
        "T2_rice": "test baseline prompt: brown rice",
    }))
    os.environ["SGEDIT_BASELINE"] = str(baseline)
    try:
        import torch  # noqa: F401
    except Exception:
        stub = types.ModuleType("torch")
        stub.inference_mode = lambda: (lambda fn: fn)
        sys.modules["torch"] = stub
    try:
        import scipy.ndimage  # noqa: F401
    except Exception:
        nd = types.ModuleType("scipy.ndimage")
        nd.binary_dilation = nd.gaussian_filter = None
        pkg = types.ModuleType("scipy")
        pkg.ndimage = nd
        sys.modules["scipy"], sys.modules["scipy.ndimage"] = pkg, nd
    try:
        _LOOP = sa.import_sgedit_loop(repo)
    except sa.PipelineUnready as exc:
        _SKIP = str(exc)


_load_research_loop()


def checker_result(edit=2.0, preserve=2.0, realism=5.0, extra=0.0):
    return {"edit": {"score": edit}, "preserve": {"score": preserve}, "realism": {"score": realism},
            "extra": {"score": extra}, "model": "fake-checker", "qset": "v2"}


class FakeEditor:
    """Same call contract as sgedit.editor.Editor.edit: (PIL image, bool mask, EditSpec) -> (PIL image, meta)."""

    def __init__(self):
        self.specs = []

    def edit(self, image, mask, spec):
        assert image.size == (1024, 1024), image.size
        assert mask.dtype == bool and mask.shape == (1024, 1024), (mask.dtype, mask.shape)
        self.specs.append(spec)
        out = image.copy()
        out.putpixel((0, 0), (len(self.specs) % 255, 0, 0))  # each candidate file differs
        return out, {**asdict(spec), "crop_box": None, "seconds": 0.0}


class FakeChecker:
    """Same call contract as sgedit.loop.CheckerClient.check; returns scripted score dicts."""

    def __init__(self, results):
        self.results, self.calls = list(results), []

    def check(self, original_path, edited_path, task, source, crop_box):
        assert Path(original_path).is_file() and Path(edited_path).is_file()
        assert len(crop_box) == 4
        self.calls.append({"original": str(original_path), "edited": str(edited_path), "task": task,
                           "source": source, "crop_box": list(crop_box)})
        return self.results[min(len(self.calls), len(self.results)) - 1]


def make_fixtures(root: Path, size=1024):
    import numpy as np
    from PIL import Image

    for n, dish in enumerate(sa.RICE_DISHES):
        d = root / dish
        d.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (size, size), (200, 180 - 20 * n, 150)).save(d / sa.INPUT_NAME)
        m = np.zeros((size, size), "uint8")
        m[size // 4: size // 2, size // 4: size // 2] = 255
        Image.fromarray(m).save(d / sa.MASK_NAME)
    return root


@unittest.skipIf(_SKIP, _SKIP or "")
class AdapterContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(dir=_TMP.name))
        self.fixtures = make_fixtures(self.tmp / "fixtures")
        self.editor = FakeEditor()

    def adapter(self, results, **kw):
        self.checker = FakeChecker(results)
        return sa.SgeditAdapter(_LOOP, self.editor, self.checker, self.fixtures, self.tmp / "candidates", **kw)

    def test_research_signatures_match_what_the_adapter_calls(self):
        params = lambda fn: list(inspect.signature(fn).parameters)
        self.assertEqual(params(_LOOP.base_spec)[:3], ["task", "source", "seed"])
        self.assertEqual(params(_LOOP.next_spec)[:6], ["spec", "task", "source", "why", "n_tried", "seeds"])
        self.assertEqual(params(_LOOP.Runner.candidate), ["self", "job", "spec", "tag"])
        self.assertEqual(params(_LOOP.Runner.__init__)[:4], ["self", "editor", "checker", "out_dir"])
        self.assertEqual(params(_LOOP.CheckerClient.check),
                         ["self", "original_path", "edited_path", "task", "source", "crop_box"])
        self.assertEqual(params(_LOOP.CheckerClient.__init__), ["self", "url"])
        for task in sa.SUPPORTED_CHANGES.values():
            self.assertTrue(_LOOP.ladder(task, sa.SOURCE), f"no prompts for {task}/rice")

    def test_first_attempt_passes_brown_rice(self):
        ev = self.adapter([checker_result()]).run("chicken_rice", ["brown_rice"])
        self.assertEqual((ev["task"], ev["source"], ev["attempts"]), ("T2", "rice", 1))
        self.assertEqual(ev["selected_tag"], "seed0")
        self.assertTrue(ev["selected_passed"] and ev["last_passed"])
        self.assertEqual(ev["seed"], _LOOP.POLICY["seeds"][0])
        self.assertEqual(ev["prompt_step"], 0)
        self.assertEqual(ev["policy_version"], _LOOP.POLICY["version"])
        call = self.checker.calls[0]
        self.assertEqual((call["task"], call["source"]), ("T2", "rice"))
        self.assertEqual(call["original"], str((self.fixtures / "chicken_rice" / sa.INPUT_NAME).resolve()))
        self.assertEqual(ev["input_sha256"], sa.sha256_file(self.fixtures / "chicken_rice" / sa.INPUT_NAME))
        self.assertEqual(ev["image_sha256"], sa.sha256_file(ev["image_path"]))
        spec = self.editor.specs[0]
        prompt, neg = _LOOP.ladder("T2", "rice")[0]
        self.assertEqual((spec.prompt, spec.negative_prompt), (prompt, neg))
        self.assertEqual((spec.steps, spec.guidance, spec.mode), (20, 7.5, "crop"))

    def test_broccoli_maps_to_t1b(self):
        ev = self.adapter([checker_result()]).run("tofu_rice", ["extra_vegetables"])
        self.assertEqual(ev["task"], "T1-B")
        self.assertEqual(self.checker.calls[0]["task"], "T1-B")
        self.assertEqual(self.editor.specs[0].prompt, _LOOP.ladder("T1-B", "rice")[0][0])

    def test_edit_failures_walk_the_prompt_ladder_then_pass(self):
        results = [checker_result(edit=0.2), checker_result(edit=0.8), checker_result(edit=2.0)]
        ev = self.adapter(results).run("chicken_rice", ["brown_rice"])
        self.assertEqual(ev["attempts"], 3)
        self.assertEqual(ev["attempt_tags"], ["seed0", "retry1", "retry2"])
        self.assertEqual(ev["selected_tag"], "retry2")
        self.assertTrue(ev["selected_passed"])
        ladder, seeds = _LOOP.ladder("T2", "rice"), _LOOP.POLICY["seeds"]
        self.assertEqual([s.prompt for s in self.editor.specs], [p for p, _ in ladder[:3]])
        self.assertEqual([s.seed for s in self.editor.specs], seeds[:3])
        self.assertEqual(ev["prompt_step"], 2)

    def test_non_edit_failure_keeps_prompt_and_changes_seed(self):
        results = [checker_result(realism=1.5), checker_result()]
        ev = self.adapter(results).run("chicken_rice", ["brown_rice"])
        self.assertEqual(ev["attempts"], 2)
        self.assertEqual(self.editor.specs[0].prompt, self.editor.specs[1].prompt)
        self.assertNotEqual(self.editor.specs[0].seed, self.editor.specs[1].seed)

    def test_never_passing_returns_best_scoring_attempt_marked_not_passed(self):
        results = [checker_result(edit=e) for e in (0.2, 1.0, 0.6, 0.4)]
        ev = self.adapter(results).run("chicken_rice", ["brown_rice"])
        self.assertEqual(ev["attempts"], sa.MAX_ATTEMPTS)
        self.assertEqual(ev["selected_tag"], "retry1")
        self.assertFalse(ev["selected_passed"])
        self.assertFalse(ev["last_passed"])
        self.assertEqual(ev["selected_failure"], "edit")
        self.assertEqual(len(self.editor.specs), sa.MAX_ATTEMPTS)

    def test_unsupported_requests_never_reach_the_model(self):
        adapter = self.adapter([checker_result()])
        for args in (
            ("fish_soup", ["extra_vegetables"]),
            ("chicken_rice", ["sauce_on_side"]),
            ("chicken_rice", ["brown_rice", "extra_vegetables"]),
            ("chicken_rice", []),
            ("chicken_rice", ["brown_rice"], "soft", "any"),
            ("chicken_rice", ["brown_rice"], "any", "mild"),
        ):
            with self.assertRaises(sa.UnsupportedRequest, msg=str(args)):
                adapter.run(*args)
        self.assertEqual(self.editor.specs, [])
        self.assertEqual(self.checker.calls, [])

    def test_candidates_are_cached_and_a_new_mask_starts_a_new_job(self):
        adapter = self.adapter([checker_result()])
        first = adapter.run("chicken_rice", ["brown_rice"])
        again = adapter.run("chicken_rice", ["brown_rice"])
        self.assertEqual(len(self.editor.specs), 1)
        self.assertEqual(first["image_sha256"], again["image_sha256"])
        import numpy as np
        from PIL import Image
        m = np.zeros((1024, 1024), "uint8"); m[100:300, 100:300] = 255
        Image.fromarray(m).save(self.fixtures / "chicken_rice" / sa.MASK_NAME)
        changed = adapter.run("chicken_rice", ["brown_rice"])
        self.assertEqual(len(self.editor.specs), 2)
        self.assertNotEqual(first["job_key"], changed["job_key"])

    def test_bad_fixtures_fail_closed(self):
        from PIL import Image
        adapter = self.adapter([checker_result()])
        Image.new("RGB", (800, 600)).save(self.fixtures / "tofu_rice" / sa.INPUT_NAME)
        with self.assertRaises(sa.PipelineUnready):
            adapter.run("tofu_rice", ["brown_rice"])
        Image.new("L", (1024, 1024), 0).save(self.fixtures / "chicken_rice" / sa.MASK_NAME)
        with self.assertRaises(sa.PipelineUnready):
            adapter.run("chicken_rice", ["brown_rice"])
        self.assertEqual(self.editor.specs, [])

    def test_checker_errors_fail_closed(self):
        class Broken:
            def check(self, *a):
                raise RuntimeError("checker down")
        adapter = sa.SgeditAdapter(_LOOP, self.editor, Broken(), self.fixtures, self.tmp / "candidates")
        with self.assertRaises(sa.PipelineUnready):
            adapter.run("chicken_rice", ["brown_rice"])

    # --- through the worker's HTTP handler -------------------------------------------------

    def _serve(self):
        class Handler(gpu_worker.WorkerHandler):
            expected_token = "t"
            mode = "gpu"
            def log_message(self, fmt, *args):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return "http://%s:%d" % server.server_address[:2]

    def _post(self, base, body):
        req = urllib.request.Request(base + "/v1/generate", data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json", "Authorization": "Bearer t"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            with e:
                return e.code, json.loads(e.read())

    def test_worker_returns_a_valid_artifact_and_rejects_unsupported_selections(self):
        from PIL import Image
        adapter = self.adapter([checker_result(edit=0.2), checker_result()])
        env = {"WORKER_FIXTURE_DIR": str(self.fixtures), "WORKER_GPU_CMD": ""}
        base = self._serve()
        with mock.patch.dict(os.environ, env), mock.patch.object(gpu_worker, "_ADAPTER", adapter):
            status, art = self._post(base, {"dish_id": "chicken_rice", "change_ids": ["brown_rice"],
                                            "texture": "any", "flavour": "any"})
            self.assertEqual(status, 200, art)
            self.assertEqual(set(art), {"provider", "model", "prompt_id", "seed", "attempts", "checker_passed",
                                        "image_data_url", "generated_label"})  # Rust struct denies unknown fields
            self.assertEqual(art["provider"], "tailscale-gpu-worker")
            self.assertEqual(art["prompt_id"], f"{_LOOP.POLICY['version']}:T2:rice:step1")
            self.assertEqual(art["attempts"], 2)
            self.assertTrue(art["checker_passed"])
            self.assertIn("not", art["generated_label"].lower())
            prefix = "data:image/png;base64,"
            self.assertTrue(art["image_data_url"].startswith(prefix))
            self.assertLess(len(json.dumps(art)), 4 * 1024 * 1024)
            img = Image.open(io.BytesIO(base64.b64decode(art["image_data_url"][len(prefix):])))
            self.assertEqual((img.format, max(img.size)), ("PNG", gpu_worker.PREVIEW_MAX_SIDE))

            for body in (
                {"dish_id": "chicken_rice", "change_ids": ["sauce_on_side"]},
                {"dish_id": "fish_soup", "change_ids": ["extra_vegetables"]},
                {"dish_id": "chicken_rice", "change_ids": ["brown_rice", "extra_vegetables"]},
                {"dish_id": "chicken_rice", "change_ids": ["brown_rice"], "texture": "soft"},
            ):
                status, err = self._post(base, body)
                self.assertEqual((status, err.get("error")), (422, "gpu_unsupported_selection"), body)
            self.assertEqual(len(self.editor.specs), 2)

    def test_healthz_needs_loaded_model_fixtures_and_checker(self):
        env = {"WORKER_FIXTURE_DIR": str(self.fixtures), "WORKER_GPU_CMD": ""}
        with mock.patch.dict(os.environ, env):
            with mock.patch.object(gpu_worker, "_ADAPTER", None):
                self.assertFalse(gpu_worker.is_gpu_pipeline_ready())
            with mock.patch.object(gpu_worker, "_ADAPTER", object()):
                with mock.patch.object(gpu_worker, "checker_reachable", return_value=False):
                    self.assertFalse(gpu_worker.is_gpu_pipeline_ready())
                with mock.patch.object(gpu_worker, "checker_reachable", return_value=True):
                    self.assertTrue(gpu_worker.is_gpu_pipeline_ready())


if __name__ == "__main__":
    unittest.main()
