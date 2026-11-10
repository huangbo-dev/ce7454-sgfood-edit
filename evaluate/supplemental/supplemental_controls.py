"""Frozen supplemental E3/E4 preparation. No source file is modified.

These are retrospective shared-photo diagnostics, not independent human or
held-out evidence. Freeze parameters before scoring. Cached local models only.
"""
from __future__ import annotations
import argparse, colorsys, hashlib, json, math, os, re, sys
from datetime import datetime, timezone
from pathlib import Path

PROTOCOL = {
    "version": "ce7454-supplemental-e3-e4-v1",
    "classification": "retrospective shared-photo diagnostic",
    "e3": {
        "condition": "tuned", "cases": 34, "photos": 20, "candidates_per_case": 4,
        "model": "openai/clip-vit-large-patch14",
        "model_revision": "exact local file hashes required in the run lock",
        "score": "cosine of CLIP projected image and text embeddings, official model preprocessing",
        "target_texts": {
            "T1-B": "A photograph of a Singapore hawker meal with clearly visible cooked broccoli added to the rice or noodles.",
            "T2": "A photograph of a Singapore hawker meal with light brown wholegrain rice."
        },
        "tie_rule": "first maximum in archived seed_tags order",
        "numeric_mode": "float32, deterministic algorithms, TF32 disabled",
        "source_results_sha256": "3f3d639f3223128aa131026ab771e8225b6969ca9f209f2261d9688f3b9fbb74",
        "source_lock_sha256": "a5809a70568701aee000e192569dc197328f9155a80a6702e8c9b667b558099f"
    },
    "e4": {
        "cases": 14, "task": "T2", "source": "rice",
        "hue_degrees": 30.0, "saturation": 0.35, "value_scale": 0.82,
        "pixel_rule": "Only existing binary-mask pixels: HSV H=30deg, S=0.35, V=0.82*original V. Round RGB half-up to uint8. No resizing, feathering or per-image tuning.",
        "checker_thresholds": {"edit": 1.5, "preserve": 1.5, "realism": 3.0, "extra": 0.5},
        "interpretation": "Chromatic-shortcut stress control. Acceptance is not a false acceptance without the same output's blinded human failure label."
    },
    "human_status": "not collected by this tool",
    "source_policy": "read-only; new output directory; no paid API; no model download"
}

def now():
    return datetime.now(timezone.utc).isoformat()

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def write_new(path, obj):
    with Path(path).open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")

def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))

def require(condition, message):
    if not condition:
        raise ValueError(message)

def safe_token(value):
    require(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]+", value), "Unsafe identifier.")
    return value

def safe_path(root, relative):
    require(isinstance(relative, str) and not Path(relative).is_absolute(), "Use a relative input path.")
    path = (Path(root).resolve() / relative).resolve()
    require(path.is_relative_to(Path(root).resolve()) and path.is_file(), "Input must be a file within its source root.")
    return path

def first_max(scores):
    require(bool(scores) and all(isinstance(x, (float, int)) and math.isfinite(x) for x in scores),
            "Selector scores must be nonempty and finite.")
    return max(range(len(scores)), key=scores.__getitem__)

def checker_pass(check, thresholds):
    return (check["edit"]["score"] >= thresholds["edit"] and
            check["preserve"]["score"] >= thresholds["preserve"] and
            check["realism"]["score"] >= thresholds["realism"] and
            check["extra"]["score"] <= thresholds["extra"])

def checker_score(check, weights):
    return (weights["edit"] * check["edit"]["score"] / 2 +
            weights["preserve"] * check["preserve"]["score"] / 2 +
            weights["realism"] * (check["realism"]["score"] - 1) / 4 -
            weights["extra"] * check["extra"]["score"])

def snapshot_run(run_root):
    root = Path(run_root).resolve() / "tuned"
    require(sha(root / "results.jsonl") == PROTOCOL["e3"]["source_results_sha256"], "Wrong frozen revised results.")
    require(sha(root / "LOCK.json") == PROTOCOL["e3"]["source_lock_sha256"], "Wrong frozen revised policy lock.")
    policy = read_json(root / "LOCK.json")["policy"]
    rows = [json.loads(x) for x in (root / "results.jsonl").read_text().splitlines() if x.strip()]
    complete = read_json(root / "COMPLETE.json")
    require(len(rows) == complete["completed_jobs"] == 34, "Expected all 34 complete cases.")
    require(complete["results_sha256"] == sha(root / "results.jsonl"), "Completion receipt mismatch.")
    require(len({r["image_id"] for r in rows}) == 20, "Expected all 20 photo clusters.")
    require(len({r["key"] for r in rows}) == 34, "Duplicate case keys.")
    files = {name: sha(root / name) for name in ("results.jsonl", "LOCK.json", "COMPLETE.json")}
    cases = []
    for row in rows:
        key = safe_token(row["key"])
        require(row["task"] in ("T1-B", "T2"), "Unexpected task.")
        tags = row["seed_tags"]
        require(tags == ["seed0", "seed1", "seed2", "seed3"], "Expected the original four ordered base candidates.")
        records = {}
        for tag in dict.fromkeys(tags + [row["retry"], row["best_check"]]):
            tag = safe_token(tag)
            relative = "candidates/" + key + "/" + tag
            meta_path, png_path = root / (relative + ".json"), root / (relative + ".png")
            record = read_json(meta_path)
            require(record["tag"] == tag and sha(png_path) == record["sha256"], "Candidate identity or image hash mismatch.")
            passed = checker_pass(record["check"], policy["pass"])
            score = checker_score(record["check"], policy["weights"])
            require(passed == record["pass"] and math.isclose(score, record["score"], abs_tol=1e-12), "Checker metadata mismatch.")
            files[relative + ".json"], files[relative + ".png"] = sha(meta_path), sha(png_path)
            records[tag] = record
        require(tags[first_max([records[t]["score"] for t in tags])] == row["best_check"], "Existing base selection mismatch.")
        cases.append({"key": key, "photo_id": row["image_id"], "task": row["task"],
                      "source": row["source"], "seed_tags": tags,
                      "best_check": row["best_check"], "retry": row["retry"],
                      "records": records})
    return {"root": str(root), "files": files, "cases": cases}

def snapshot_model(model_dir):
    root = Path(model_dir).resolve()
    require(root.is_dir(), "A pre-existing local CLIP model snapshot is required; no download is attempted.")
    required = ("config.json", "preprocessor_config.json", "tokenizer_config.json")
    require(all((root / name).is_file() for name in required), "Incomplete local model/processor configuration.")
    config = read_json(root / "config.json")
    require(config.get("model_type") == "clip", "Expected a CLIP model.")
    require(config.get("vision_config", {}).get("patch_size") == 14, "Expected ViT-L/14 patch size.")
    require(config.get("vision_config", {}).get("hidden_size") == 1024, "Expected ViT-L vision hidden size.")
    require(any(root.glob("*.safetensors")) or any(root.glob("pytorch_model*.bin")), "No local model weights.")
    files = {str(p.relative_to(root)): sha(p) for p in sorted(root.rglob("*")) if p.is_file()}
    return {"root": str(root), "files": files}

def output_root(value, source_roots):
    path = Path(value).resolve()
    for root in source_roots:
        require(not path.is_relative_to(Path(root).resolve()), "Output must be outside every frozen input/model directory.")
    require(not path.exists(), "Output directory already exists; do not overwrite or silently resume.")
    path.mkdir(parents=True)
    return path

def freeze_e3(run_root, model_dir, out_dir):
    run = snapshot_run(run_root)
    model = snapshot_model(model_dir)
    out = output_root(out_dir, [run_root, model_dir])
    lock = {"created_utc": now(), "study": "E3", "protocol": PROTOCOL,
            "code_sha256": sha(__file__), "source": run, "model": model,
            "status": "frozen_before_scoring", "human_results": None}
    write_new(out / "LOCK.json", lock)
    return lock

def verify_files(root, files):
    for relative, expected in files.items():
        require(sha(safe_path(root, relative)) == expected, "Locked input changed: " + relative)

def load_lock(out_dir, study):
    out = Path(out_dir).resolve()
    lock = read_json(out / "LOCK.json")
    require(lock["study"] == study and lock["protocol"] == PROTOCOL, "Wrong study/protocol.")
    require(lock["code_sha256"] == sha(__file__), "Code changed after freeze; use a new run.")
    require(not (out / "RUNNING.json").exists() and not (out / "COMPLETE.json").exists()
            and not (out / "FAILURE.json").exists(), "Run already started; inspect it rather than rerun.")
    return out, lock

def result_summary(rows):
    result = {"status": "checker diagnostics only; no human-quality result",
              "cases": len(rows), "photos": len({r["photo_id"] for r in rows}),
              "checker_passes": sum(r["checker_passed"] for r in rows),
              "additional_output_judgments_vs_existing_pairs": sum(not r["in_existing_pair"] for r in rows),
              "by_task": {}}
    for task in sorted({r["task"] for r in rows}):
        selected = [r for r in rows if r["task"] == task]
        result["by_task"][task] = {"cases": len(selected), "checker_passes": sum(r["checker_passed"] for r in selected)}
    return result

def run_e3(out_dir, device="cpu"):
    out, lock = load_lock(out_dir, "E3")
    verify_files(lock["source"]["root"], lock["source"]["files"])
    verify_files(lock["model"]["root"], lock["model"]["files"])
    write_new(out / "RUNNING.json", {"started_utc": now(), "device": device})
    rows = []
    try:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
        import torch, transformers
        torch.use_deterministic_algorithms(True)
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        torch.backends.cudnn.benchmark = False
        from PIL import Image
        from transformers import CLIPModel, CLIPProcessor
        processor = CLIPProcessor.from_pretrained(lock["model"]["root"], local_files_only=True)
        model = CLIPModel.from_pretrained(lock["model"]["root"], local_files_only=True).float().eval().to(device)
        tasks = ["T1-B", "T2"]
        texts = [PROTOCOL["e3"]["target_texts"][task] for task in tasks]
        source_root = Path(lock["source"]["root"])
        with (out / "selections.jsonl").open("x", encoding="utf-8") as stream:
            for case in lock["source"]["cases"]:
                images = []
                for tag in case["seed_tags"]:
                    with Image.open(source_root / "candidates" / case["key"] / (tag + ".png")) as image:
                        images.append(image.convert("RGB"))
                batch = processor(text=texts, images=images, return_tensors="pt", padding=True)
                batch = {key: value.to(device) for key, value in batch.items()}
                with torch.inference_mode():
                    outputs = model(**batch)
                    image_embeds = torch.nn.functional.normalize(outputs.image_embeds.float(), dim=-1)
                    text_embeds = torch.nn.functional.normalize(outputs.text_embeds.float(), dim=-1)
                    scores = (image_embeds @ text_embeds.T)[:, tasks.index(case["task"])].cpu().tolist()
                index = first_max(scores)
                tag = case["seed_tags"][index]
                selected = case["records"][tag]
                pair_hashes = {case["records"][case[a]]["sha256"] for a in ("best_check", "retry")}
                row = {"key": case["key"], "photo_id": case["photo_id"], "task": case["task"],
                       "selected_tag": tag, "selected_sha256": selected["sha256"],
                       "scores": dict(zip(case["seed_tags"], scores)),
                       "checker_passed": selected["pass"], "in_existing_pair": selected["sha256"] in pair_hashes,
                       "human_result": None}
                rows.append(row); stream.write(json.dumps(row) + "\n"); stream.flush()
        verify_files(lock["source"]["root"], lock["source"]["files"])
        verify_files(lock["model"]["root"], lock["model"]["files"])
        summary = result_summary(rows)
        summary["runtime"] = {"python": sys.version, "torch": torch.__version__, "transformers": transformers.__version__, "device": device}
        summary["provenance_limit"] = "New snapshot hashes do not independently establish historical authenticity of candidate checker JSON."
        write_new(out / "SUMMARY.json", summary)
        write_new(out / "COMPLETE.json", {"completed_utc": now(), "cases": len(rows), "selections_sha256": sha(out / "selections.jsonl")})
        return summary
    except Exception as exc:
        write_new(out / "FAILURE.json", {"utc": now(), "completed_cases": len(rows), "error": type(exc).__name__, "message": str(exc)})
        raise

def recolour_pixel(pixel):
    value = max(pixel) / 255 * PROTOCOL["e4"]["value_scale"]
    rgb = colorsys.hsv_to_rgb(PROTOCOL["e4"]["hue_degrees"] / 360, PROTOCOL["e4"]["saturation"], value)
    return tuple(min(255, max(0, math.floor(x * 255 + 0.5))) for x in rgb)

REVIEW_LOCK_SHA256 = "bc4cf1deccd0e1aa5483093789c00bf8a5385b30c496738ad2a01adfe56326f8"

def review_t2_cohort(review_data):
    root = Path(review_data).resolve()
    require(sha(root / "PACKAGE_LOCK.json") == REVIEW_LOCK_SHA256, "Wrong frozen author-review package.")
    package = read_json(root / "PACKAGE_LOCK.json")
    for name in ("public_manifest.json", "private_map.json"):
        require(sha(root / name) == package["files"][name]["sha256"], "Review mapping changed.")
    public = {r["id"]: r for r in read_json(root / "public_manifest.json")["items"]}
    private = read_json(root / "private_map.json")["items"]
    result = {}
    for key, row in private.items():
        if row["condition"] == "tuned" and row["task"] == "T2":
            original = "media/" + public[key]["original"]
            expected = package["files"][original]["sha256"]
            require(sha(safe_path(root, original)) == expected, "Frozen source photo changed.")
            require(row["photo_id"] not in result, "Duplicate frozen T2 photo.")
            result[row["photo_id"]] = expected
    require(len(result) == 14 and len(set(result.values())) == 14, "Expected 14 distinct frozen T2 sources.")
    return result

def snapshot_e4_inputs(input_root, manifest_path, review_data):
    root = Path(input_root).resolve()
    manifest = read_json(manifest_path)
    cases = manifest["cases"]
    require(manifest["schema_version"] == 1 and len(cases) == 14, "E4 requires all 14 frozen T2 cases.")
    require(len({r["photo_id"] for r in cases}) == 14, "Duplicate source photos.")
    cohort = review_t2_cohort(review_data)
    require({r["photo_id"] for r in cases} == set(cohort), "E4 cohort differs from frozen T2 sources.")
    files = {}
    for row in cases:
        safe_token(row["photo_id"])
        require(row["image_sha256"] == cohort[row["photo_id"]], "E4 source does not match the frozen photo.")
        require(row["task"] == "T2" and row["source"] == "rice", "Wrong E4 task/source.")
        for field in ("image", "mask"):
            path = safe_path(root, row[field])
            require(sha(path) == row[field + "_sha256"], "Frozen image/mask hash mismatch.")
            files[row[field]] = sha(path)
    return {"root": str(root), "manifest_sha256": sha(manifest_path), "cases": cases, "files": files}

def freeze_e4(input_root, manifest_path, out_dir, review_data):
    inputs = snapshot_e4_inputs(input_root, manifest_path, review_data)
    out = output_root(out_dir, [input_root])
    lock = {"created_utc": now(), "study": "E4", "protocol": PROTOCOL, "code_sha256": sha(__file__),
            "source": inputs, "status": "frozen_before_transformation", "human_results": None}
    write_new(out / "LOCK.json", lock)
    return lock

def recolour_arrays(image, mask):
    import numpy as np
    require(image.dtype == np.uint8 and image.ndim == 3 and image.shape[2] == 3, "Expected RGB uint8 image.")
    require(mask.dtype == bool and mask.shape == image.shape[:2] and mask.any() and not mask.all(), "Expected nonempty/nonfull boolean mask.")
    output = image.copy()
    values = image[mask].max(axis=1).astype(np.float64) / 255 * PROTOCOL["e4"]["value_scale"]
    multipliers = colorsys.hsv_to_rgb(PROTOCOL["e4"]["hue_degrees"] / 360, PROTOCOL["e4"]["saturation"], 1.0)
    output[mask] = np.floor(values[:, None] * np.asarray(multipliers) * 255 + 0.5).clip(0, 255).astype(np.uint8)
    require(np.array_equal(output[~mask], image[~mask]), "Unmasked pixels changed.")
    return output

def generate_e4(out_dir):
    out, lock = load_lock(out_dir, "E4")
    verify_files(lock["source"]["root"], lock["source"]["files"])
    write_new(out / "RUNNING.json", {"started_utc": now(), "diffusion_calls": 0})
    rows = []
    try:
        import numpy as np
        from PIL import Image
        root = Path(lock["source"]["root"]); media = out / "controls"; media.mkdir()
        for case in lock["source"]["cases"]:
            with Image.open(safe_path(root, case["image"])) as image:
                require(image.size == (1024, 1024), "Frozen source must be 1024 square.")
                pixels = np.asarray(image.convert("RGB"))
            with Image.open(safe_path(root, case["mask"])) as mask:
                require(mask.mode == "L" and mask.size == (1024, 1024), "Frozen mask must be 1024-square grayscale L.")
                raw_mask = np.asarray(mask)
                require(set(np.unique(raw_mask).tolist()) == {0, 255}, "Mask must be binary, nonempty and nonfull.")
                binary = raw_mask == 255
            output = recolour_arrays(pixels, binary)
            path = media / (case["photo_id"] + ".png")
            Image.fromarray(output).save(path, format="PNG")
            rows.append({**case, "control": str(path.relative_to(out)), "control_sha256": sha(path),
                         "outside_mask_unchanged": True, "checker_result": None, "human_result": None})
        verify_files(lock["source"]["root"], lock["source"]["files"])
        write_new(out / "CONTROL_MANIFEST.json", {"cases": rows, "protocol": PROTOCOL["e4"], "checker_status": "not_run", "human_status": "not_collected"})
        write_new(out / "COMPLETE.json", {"completed_utc": now(), "controls": len(rows), "diffusion_calls": 0,
                                         "manifest_sha256": sha(out / "CONTROL_MANIFEST.json")})
        return {"controls": len(rows), "checker": "not_run", "human": "not_collected"}
    except Exception as exc:
        write_new(out / "FAILURE.json", {"utc": now(), "completed_controls": len(rows), "error": type(exc).__name__, "message": str(exc)})
        raise

def checker_crop_box(mask_path):
    from PIL import Image
    with Image.open(mask_path) as mask:
        require(mask.mode == "L" and mask.size == (1024, 1024), "Wrong checker mask geometry.")
        bounds = mask.getbbox()
    require(bounds is not None, "Empty mask.")
    x0, y0, x1, y1 = bounds
    size = min(1024, max(256, round(max(x1-x0, y1-y0) * 1.5)))
    cx, cy = (x0+x1)/2, (y0+y1)/2
    left = min(max(round(cx-size/2), 0), 1024-size)
    top = min(max(round(cy-size/2), 0), 1024-size)
    return [left, top, left+size, top+size]

def check_e4(out_dir, checker_url, runtime_receipt):
    # Separate from generation; it never silently starts or reconfigures a model service.
    from urllib.parse import urlparse
    import urllib.request
    url = urlparse(checker_url)
    require(url.scheme == "http" and url.hostname in {"127.0.0.1", "::1", "localhost"}
            and not url.username and not url.password and not url.query and not url.fragment,
            "Use the existing local research checker, not an external endpoint.")
    receipt = read_json(runtime_receipt)
    for field in ("checker_model_id", "checker_model_files_sha256", "checker_source_sha256", "question_version"):
        require(isinstance(receipt.get(field), str) and receipt[field].strip(), "A verified runtime identity receipt is required.")
    out = Path(out_dir).resolve()
    lock = read_json(out / "LOCK.json")
    require(lock["study"] == "E4" and lock["protocol"] == PROTOCOL and lock["code_sha256"] == sha(__file__), "E4 code/protocol changed after freeze.")
    complete = read_json(out / "COMPLETE.json")
    require(complete["manifest_sha256"] == sha(out / "CONTROL_MANIFEST.json"), "Control manifest changed.")
    manifest = read_json(out / "CONTROL_MANIFEST.json")
    require(len(manifest["cases"]) == 14, "Require all 14 controls.")
    verify_files(lock["source"]["root"], lock["source"]["files"])
    for row in manifest["cases"]:
        require(sha(safe_path(out, row["control"])) == row["control_sha256"], "Control pixels changed.")
    require(not (out / "CHECKER_RUNNING.json").exists(), "Checker run already started; do not silently repeat it.")
    write_new(out / "CHECKER_RUNNING.json", {"utc": now(), "url": checker_url, "runtime_receipt_sha256": sha(runtime_receipt), "receipt": receipt})
    rows = []
    try:
        with (out / "checker_results.jsonl").open("x", encoding="utf-8") as stream:
            for row in manifest["cases"]:
                body = {"original": str(safe_path(lock["source"]["root"], row["image"])),
                        "edited": str(safe_path(out, row["control"])),
                        "task": "T2", "source": "rice",
                        "crop_box": checker_crop_box(safe_path(lock["source"]["root"], row["mask"]))}
                request = urllib.request.Request(checker_url, json.dumps(body).encode(), {"Content-Type": "application/json"})
                with urllib.request.urlopen(request, timeout=120) as response:
                    check = json.load(response)
                require("error" not in check, "Checker reported an error.")
                for name, low, high in (("edit",0,2),("preserve",0,2),("realism",1,5),("extra",0,1)):
                    value = check[name]["score"]
                    require(type(value) in (int,float) and math.isfinite(value) and low <= value <= high, "Invalid checker rubric output.")
                record = {"photo_id": row["photo_id"], "control_sha256": row["control_sha256"], "check": check,
                          "checker_passed": checker_pass(check, PROTOCOL["e4"]["checker_thresholds"]),
                          "human_result": None}
                rows.append(record); stream.write(json.dumps(record) + "\n"); stream.flush()
        verify_files(lock["source"]["root"], lock["source"]["files"])
        summary = {"cases": 14, "checker_passes": sum(r["checker_passed"] for r in rows),
                   "human_status": "not_collected", "false_acceptance": None,
                   "interpretation": PROTOCOL["e4"]["interpretation"], "runtime_receipt_sha256": sha(runtime_receipt)}
        write_new(out / "CHECKER_SUMMARY.json", summary)
        write_new(out / "CHECKER_COMPLETE.json", {"utc": now(), "results_sha256": sha(out / "checker_results.jsonl")})
        return summary
    except Exception as exc:
        write_new(out / "CHECKER_FAILURE.json", {"utc": now(), "completed": len(rows), "error": type(exc).__name__, "message": str(exc)})
        raise

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    e3 = sub.add_parser("freeze-e3"); e3.add_argument("--run-root", required=True); e3.add_argument("--model-dir", required=True); e3.add_argument("--out", required=True)
    run = sub.add_parser("run-e3"); run.add_argument("--out", required=True); run.add_argument("--device", default="cpu")
    e4 = sub.add_parser("freeze-e4"); e4.add_argument("--input-root", required=True); e4.add_argument("--manifest", required=True); e4.add_argument("--out", required=True); e4.add_argument("--review-data", required=True)
    generate = sub.add_parser("generate-e4"); generate.add_argument("--out", required=True)
    check = sub.add_parser("check-e4"); check.add_argument("--out", required=True); check.add_argument("--checker-url", default="http://127.0.0.1:8781"); check.add_argument("--runtime-receipt", required=True)
    args = parser.parse_args()
    if args.command == "freeze-e3": result = freeze_e3(args.run_root, args.model_dir, args.out)
    elif args.command == "run-e3": result = run_e3(args.out, args.device)
    elif args.command == "freeze-e4": result = freeze_e4(args.input_root, args.manifest, args.out, args.review_data)
    elif args.command == "generate-e4": result = generate_e4(args.out)
    else: result = check_e4(args.out, args.checker_url, args.runtime_receipt)
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
