"""Development-only crop-context pilot; never overwrites an existing experiment.

Twelve preselected cases, two matched seeds, two crop margins = 48 outputs.
No checker selects outputs. All outputs are retained for blinded visual review.
"""
import argparse
from collections import Counter
from dataclasses import asdict, replace
import json
import os
from pathlib import Path
import subprocess
import time

from .robustness_run import digest, validate_geometry, write_new_json

PURPOSE = "development_crop_context_diagnostic"
SEEDS = (1107, 2207)
MARGINS = {"control": 0.25, "wider_context": 0.5}


def validate_manifest(path, work):
    work = Path(work).resolve()
    data = json.loads(Path(path).read_text())
    if data.get("study_type") != PURPOSE:
        raise ValueError("Development diagnostic classification required")
    if not data.get("selection_rule") or not data.get("split_evidence"):
        raise ValueError("Record selection rule and development split evidence before viewing outputs")
    cases = data.get("cases", [])
    if len(cases) != 12 or len({c["case_id"] for c in cases}) != 12:
        raise ValueError("Exactly 12 unique cases required")
    if Counter(c["task"] for c in cases) != {"T1-B": 6, "T2": 6}:
        raise ValueError("Need six broccoli and six brown-rice cases")
    if len({(c["image_sha256"], c["task"]) for c in cases}) != 12:
        raise ValueError("Do not duplicate a photo/task case")
    groups = {}
    for c in cases:
        groups.setdefault(c["image_sha256"], set()).add(c.get("photo_group"))
    if any(len(g) != 1 for g in groups.values()):
        raise ValueError("Repeated source images must share the same photo_group")
    jobs = []
    for c in cases:
        if c.get("split") != "dev" or not c.get("photo_group"):
            raise ValueError("Only dev cases with source-photo grouping are allowed")
        if c.get("source") not in ("rice", "noodles") or (c["task"] == "T2" and c["source"] != "rice"):
            raise ValueError("Invalid task/source pairing")
        if c.get("mask_qa") not in ("accept", "needs-review"):
            raise ValueError("Record mask QA; do not silently drop difficult masks")
        job = dict(c)
        for field in ("image", "mask", "protected_mask"):
            relative = Path(c[field])
            target = (work / relative).resolve()
            if relative.is_absolute() or ".." in relative.parts or work not in target.parents:
                raise ValueError("Input paths must remain within --work")
            if digest(target) != c[field + "_sha256"]:
                raise ValueError("Input hash mismatch: " + c["case_id"] + "/" + field)
            job[field] = str(target)
        jobs.append(job)
    return data, jobs


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--work", type=Path, required=True)
    ap.add_argument("--model-audit", type=Path, required=True)
    ap.add_argument("--run", type=Path, required=True, help="New output directory; never reuse a frozen run")
    ap.add_argument("--preflight-only", action="store_true")
    args = ap.parse_args()
    data, jobs = validate_manifest(args.manifest, args.work)
    if args.run.exists():
        raise ValueError("Run directory already exists; refusing to overwrite or resume implicitly")
    audit = json.loads(args.model_audit.read_text())
    if not audit.get("files"):
        raise ValueError("Model audit must list checkpoint/config files and SHA256 hashes")
    for f in audit["files"]:
        if digest(f["path"]) != f["sha256"]:
            raise ValueError("Model audit mismatch: " + f["path"])
    import numpy as np
    from PIL import Image
    from .editor import crop_box, feather_alpha
    from .loop import base_spec
    prepared, ineffective = [], []
    for j in jobs:
        image = Image.open(j["image"]).convert("RGB")
        raw_mask = Image.open(j["mask"])
        mask_array = np.asarray(raw_mask)
        validate_geometry(image.size, raw_mask.size, np.unique(mask_array).tolist())
        if mask_array.ndim != 2:
            raise ValueError("Use single-channel binary masks")
        mask = mask_array > 0
        raw_protected = Image.open(j["protected_mask"])
        protected_array = np.asarray(raw_protected)
        validate_geometry(image.size, raw_protected.size, np.unique(protected_array).tolist())
        if protected_array.ndim != 2:
            raise ValueError("Use single-channel protected masks")
        protected = protected_array > 0
        if np.any(mask & protected):
            raise ValueError("Editable and protected masks overlap")
        boxes = {k: list(crop_box(mask, v, 384, image.width)) for k, v in MARGINS.items()}
        if boxes["control"] == boxes["wider_context"]:
            ineffective.append(j["case_id"])
        prepared.append((j, image, mask, protected, boxes))
    # Identical/clipped boxes are retained and flagged, not replaced after inspection.
    specs = [dict(case_id=j["case_id"], condition=condition, spec=asdict(replace(
        base_spec(j["task"], j["source"], seed, "tuned"), crop_margin=margin)))
        for j in jobs for seed in SEEDS for condition, margin in MARGINS.items()]
    from .paths import REPO
    from .paths import BRUSHNET_CKPT, SDXL
    # Audit must cover files the actual editor will load, not an unrelated checkpoint.
    audited = {Path(f["path"]).resolve() for f in audit["files"]}
    for model_root in (BRUSHNET_CKPT, SDXL):
        required = {p.resolve() for p in model_root.rglob("*")
                    if p.is_file() and p.suffix in (".json", ".txt", ".safetensors", ".bin")}
        if not required or not required.issubset(audited):
            raise ValueError("Audit must cover current checkpoint/config/tokenizer files: " + str(model_root))
    code_hashes = {p.name: digest(p) for p in sorted((REPO / "sgedit").glob("*.py"))}
    lock = dict(study_type=PURPOSE, manifest=data, manifest_sha256=digest(args.manifest),
                model_audit=audit, model_audit_sha256=digest(args.model_audit),
                code_sha256=code_hashes, specs=specs, outputs_expected=48,
                identical_crop_cases=ineffective,
                primary="Blinded naturalness, task completion, and preservation; ties/unsure allowed",
                analysis="Exploratory paired differences clustered by photo_group; seeds are repeated measures",
                disclaimer="Inspected development data; no held-out or health-effect claim")
    if args.preflight_only:
        print(json.dumps({"preflight": "inputs_verified", "outputs_expected": 48,
                          "identical_crop_cases": ineffective, "gpu_execution_verified": False}, indent=2))
        return
    if any(os.environ.get(k) != "1" for k in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")):
        raise ValueError("Use cached weights in offline mode")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=REPO, text=True).strip():
        raise ValueError("Commit the reviewed code before running")
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable")
    lock["git_commit"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    lock["gpu"] = torch.cuda.get_device_name()
    lock["cuda_visible_devices"] = os.environ.get("CUDA_VISIBLE_DEVICES", "not_set")
    lock["torch_version"] = torch.__version__
    lock["locked_at_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    args.run.mkdir(parents=True, exist_ok=False)
    write_new_json(args.run / "LOCK.json", lock)
    count = 0
    try:
        from .editor import Editor
        editor = Editor()
        with (args.run / "results.jsonl").open("x") as log:
            for index, (j, image, mask, protected, boxes) in enumerate(prepared):
                # Alternate order to reduce systematic warmup/order effects.
                for seed_index, seed in enumerate(SEEDS):
                    conditions = list(MARGINS)
                    if (index + seed_index) % 2:
                        conditions.reverse()
                    for condition in conditions:
                        spec = replace(base_spec(j["task"], j["source"], seed, "tuned"),
                                       crop_margin=MARGINS[condition])
                        output, meta = editor.edit(image, mask, spec)
                        filename = f"{index:02d}-{seed}-{condition}.png"
                        path = args.run / filename
                        output.save(path)
                        delta = np.abs(np.asarray(output, dtype=float) - np.asarray(image, dtype=float)) / 255
                        outside = ~mask
                        far = feather_alpha(mask) < 1e-6
                        rec = dict(case_id=j["case_id"], photo_group=j["photo_group"], task=j["task"],
                                   seed=seed, condition=condition, path=filename, sha256=digest(path), gen=meta,
                                   outside_mae=float(delta[outside].mean()),
                                   protected_mae=float(delta[protected].mean()),
                                   far_outside_mae=float(delta[far].mean()) if far.any() else None,
                                   crop_box=boxes[condition], identical_crop=j["case_id"] in ineffective)
                        log.write(json.dumps(rec) + "\n"); log.flush()
                        count += 1
                        print(f"{count}/48 {j['case_id']} seed={seed} {condition}", flush=True)
        write_new_json(args.run / "COMPLETE.json", {"outputs": count, "results_sha256": digest(args.run / "results.jsonl"),
                                                   "visual_review_pending": True})
    except Exception as exc:
        write_new_json(args.run / "FAILURE.json", {"completed_outputs": count, "error": repr(exc)})
        raise


if __name__ == "__main__":
    main()
