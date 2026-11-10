#!/usr/bin/env python3
"""Private Tailscale GPU model-worker bridge for Senior Meal Preview.

This service runs on the GPU machine joined to the same Tailscale tailnet as the
EC2 Rust API server. It binds strictly to a Tailscale CGNAT IPv4 address
(100.64.0.0/10), Tailscale IPv6 (fd7a:115c:a1e0::/48), or loopback (127.0.0.1),
never 0.0.0.0 or a public interface.

Modes:
- `dry-run`: Returns a deterministic, dependency-free PNG fixture labelled
  `provider="tailscale-gpu-dry-run"` and `model="dry_run_fixture"` for Tailscale
  connectivity and smoke tests.
- `gpu`: Invokes either an external GPU runner (`WORKER_GPU_CMD`) or the research
  `sgedit` BrushNet + Qwen2.5-VL check-and-retry pipeline through `sgedit_adapter`,
  against dish fixtures in `WORKER_FIXTURE_DIR`. The built-in path accepts only the two
  studied edits (broccoli addition, brown-rice replacement), one per request, on rice
  dishes with no texture/flavour preference; anything else gets HTTP 422. Fails closed
  with HTTP 503 if fixtures, research code, weights or the checker are unavailable
  (never silently falls back to a synthetic dry-run image).

`--warm` runs the four supported jobs once and exits, so later requests are served from
the on-disk candidate cache.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import io
import ipaddress
import json
import os
import shlex
import socket
import struct
import subprocess
import sys
import threading
import urllib.parse
import zlib
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ALLOWED_DISHES = {"chicken_rice", "fish_soup", "tofu_rice"}
ALLOWED_CHANGES = {"extra_vegetables", "brown_rice", "sauce_on_side"}
ALLOWED_TEXTURES = {"any", "soft"}
ALLOWED_FLAVOURS = {"any", "mild"}

PROMPT_MAP = {
    ("chicken_rice", ("brown_rice",)): "t2_r1_hawker_brown_rice",
    ("chicken_rice", ("extra_vegetables",)): "t1b_steamed_broccoli_side",
    ("chicken_rice", ("brown_rice", "extra_vegetables")): "t2_r1_hawker_plus_t1b_broccoli",
    ("tofu_rice", ("brown_rice",)): "t2_r1_hawker_tofu_brown_rice",
    ("fish_soup", ("extra_vegetables",)): "t1b_fish_soup_greens",
}

DISH_RGB = {
    "chicken_rice": (202, 129, 74),
    "fish_soup": (141, 188, 195),
    "tofu_rice": (167, 186, 133),
}

GENERATED_DISCLOSURE = (
    "AI-generated preview via private Tailscale GPU worker · "
    "Not a real meal or clinical verification"
)


DEFAULT_CHECKER_URL = "http://127.0.0.1:8781"  # sgedit.checker serve --port 8781
PREVIEW_MAX_SIDE = 768  # keeps the base64 PNG well under the backend's 4 MiB response limit


class GpuPipelineUnreadyError(RuntimeError):
    """Raised when `--mode gpu` is active but GPU fixtures or weights are unavailable."""


class GpuUnsupportedSelectionError(ValueError):
    """Raised when the built-in model path is asked for anything but the two studied edits."""


_ADAPTER = None
_ADAPTER_INIT_LOCK = threading.Lock()
_GPU_LOCK = threading.Lock()  # one generation at a time on the GPU


def checker_url() -> str:
    return os.environ.get("WORKER_CHECKER_URL", "").strip() or DEFAULT_CHECKER_URL


def checker_reachable(timeout: float = 1.0) -> bool:
    """True if something accepts TCP connections at the checker address."""
    parts = urllib.parse.urlsplit(checker_url())
    try:
        with socket.create_connection((parts.hostname or "127.0.0.1", parts.port or 80), timeout=timeout):
            return True
    except (OSError, ValueError):
        return False


def candidate_dir(fixture_dir: str) -> str:
    return os.environ.get("WORKER_OUT_DIR", "").strip() or str(Path(fixture_dir).parent / "candidates")


def get_adapter():
    """Load the research code and BrushNet model once; later calls reuse them."""
    global _ADAPTER
    with _ADAPTER_INIT_LOCK:
        if _ADAPTER is not None:
            return _ADAPTER
        fixture_dir = os.environ.get("WORKER_FIXTURE_DIR", "").strip()
        if not fixture_dir:
            raise GpuPipelineUnreadyError(
                "GPU mode requires WORKER_FIXTURE_DIR (dish input and rice-mask PNGs) or WORKER_GPU_CMD. "
                "Refusing to return a synthetic dry-run fixture while in '--mode gpu'."
            )
        import sgedit_adapter

        try:
            _ADAPTER = sgedit_adapter.build_real_adapter(
                fixture_dir, candidate_dir(fixture_dir), checker_url()
            )
        except sgedit_adapter.PipelineUnready as exc:
            raise GpuPipelineUnreadyError(str(exc)) from exc
        return _ADAPTER


def png_data_url_from_file(path: str, max_side: int = PREVIEW_MAX_SIDE) -> str:
    from PIL import Image

    img = Image.open(path).convert("RGB")
    if max(img.size) > max_side:
        scale = max_side / max(img.size)
        img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def artifact_from_evidence(evidence: dict[str, object]) -> dict[str, object]:
    """Map adapter evidence onto the GpuArtifact schema the Rust backend validates."""
    return {
        "provider": "tailscale-gpu-worker",
        "model": "brushnet-sdxl+qwen2.5-vl-7b-4bit",
        "prompt_id": "{policy_version}:{task}:{source}:step{prompt_step}".format(**evidence),
        "seed": int(evidence["seed"]),
        "attempts": max(1, min(8, int(evidence["attempts"]))),
        # Refers to the selected (best-scoring) image, as in sgedit.results schema 2.
        "checker_passed": bool(evidence["selected_passed"]),
        "image_data_url": png_data_url_from_file(str(evidence["image_path"])),
        "generated_label": GENERATED_DISCLOSURE,
    }


def is_allowed_bind_ip(addr: str) -> bool:
    if addr == "localhost":
        return True
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    tailscale_v4 = ipaddress.ip_network("100.64.0.0/10")
    tailscale_v6 = ipaddress.ip_network("fd7a:115c:a1e0::/48")
    return ip.is_loopback or ip in tailscale_v4 or ip in tailscale_v6


def detect_tailscale_ipv4() -> str:
    result = subprocess.run(
        ["tailscale", "ip", "-4"],
        capture_output=True,
        text=True,
        check=True,
        timeout=5,
    )
    for line in result.stdout.splitlines():
        candidate = line.strip()
        if candidate and is_allowed_bind_ip(candidate):
            return candidate
    raise RuntimeError("No valid Tailscale IPv4 address returned by 'tailscale ip -4'.")


def make_solid_png_data_url(rgb: tuple[int, int, int], width: int = 96, height: int = 64) -> str:
    """Create a small, dependency-free PNG data URL for dry-run connectivity checks."""
    r, g, b = rgb
    raw_rows = b"".join(b"\x00" + bytes((r, g, b)) * width for _ in range(height))

    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw_rows, level=6))
        + chunk(b"IEND", b"")
    )
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def is_gpu_pipeline_ready() -> bool:
    """True if WORKER_GPU_CMD is set, or the built-in path has its model loaded, its fixtures
    present and a checker listening. Configuration alone is not readiness."""
    gpu_cmd = os.environ.get("WORKER_GPU_CMD", "").strip()
    if gpu_cmd:
        return True
    fixture_dir = os.environ.get("WORKER_FIXTURE_DIR", "").strip()
    if not fixture_dir or _ADAPTER is None:
        return False
    import sgedit_adapter

    return sgedit_adapter.fixtures_present(fixture_dir) and checker_reachable()


def build_dry_run_artifact(
    dish_id: str,
    change_ids: list[str],
    prompt_id: str,
    seed: int,
) -> dict[str, object]:
    base_r, base_g, base_b = DISH_RGB[dish_id]
    if "extra_vegetables" in change_ids:
        base_g = min(255, base_g + 35)
    if "brown_rice" in change_ids:
        base_r = max(80, base_r - 25)
    return {
        "provider": "tailscale-gpu-dry-run",
        "model": "dry_run_fixture",
        "prompt_id": prompt_id,
        "seed": seed,
        "attempts": 1,
        "checker_passed": True,
        "image_data_url": make_solid_png_data_url((base_r, base_g, base_b)),
        "generated_label": GENERATED_DISCLOSURE,
    }


def run_gpu_pipeline(
    dish_id: str,
    change_ids: list[str],
    texture: str,
    flavour: str,
    prompt_id: str,
    seed: int,
) -> dict[str, object]:
    """Execute the real GPU pipeline or fail closed with GpuPipelineUnreadyError."""
    gpu_cmd = os.environ.get("WORKER_GPU_CMD", "").strip()
    if gpu_cmd:
        req_payload = {
            "dish_id": dish_id,
            "change_ids": change_ids,
            "texture": texture,
            "flavour": flavour,
            "prompt_id": prompt_id,
            "seed": seed,
        }
        try:
            proc = subprocess.run(
                shlex.split(gpu_cmd),
                input=json.dumps(req_payload),
                capture_output=True,
                text=True,
                shell=False,
                check=True,
                timeout=int(os.environ.get("WORKER_GPU_TIMEOUT_SECS", "20")),
            )
            result = json.loads(proc.stdout)
        except Exception as exc:
            raise GpuPipelineUnreadyError(f"External WORKER_GPU_CMD failed: {exc}") from exc

        image_data_url = str(result.get("image_data_url", ""))
        if not image_data_url.startswith("data:image/png;base64,"):
            raise GpuPipelineUnreadyError(
                "WORKER_GPU_CMD did not return a valid 'data:image/png;base64,...' image_data_url."
            )
        return {
            "provider": str(result.get("provider", "tailscale-gpu-worker")),
            "model": str(result.get("model", "brushnet-sdxl+qwen2.5-vl-7b-4bit")),
            "prompt_id": str(result.get("prompt_id", prompt_id)),
            "seed": int(result.get("seed", seed)),
            "attempts": max(1, min(8, int(result.get("attempts", 1)))),
            "checker_passed": bool(result.get("checker_passed", False)),
            "image_data_url": image_data_url,
            "generated_label": str(result.get("generated_label", GENERATED_DISCLOSURE)),
        }

    import sgedit_adapter

    # Refuse unsupported requests before touching the model.
    try:
        sgedit_adapter.resolve_task(dish_id, change_ids, texture, flavour)
    except sgedit_adapter.UnsupportedRequest as exc:
        raise GpuUnsupportedSelectionError(str(exc)) from exc

    adapter = get_adapter()
    try:
        with _GPU_LOCK:
            evidence = adapter.run(dish_id, change_ids, texture, flavour)
        artifact = artifact_from_evidence(evidence)
    except sgedit_adapter.PipelineUnready as exc:
        raise GpuPipelineUnreadyError(str(exc)) from exc
    except Exception as exc:
        raise GpuPipelineUnreadyError(f"sgedit GPU execution failed: {exc}") from exc
    sys.stderr.write(
        "[gpu-worker] job={job_key} task={task} attempts={attempts} selected={selected_tag} "
        "passed={selected_passed} image_sha256={image_sha256}\n".format(**evidence)
    )
    return artifact


class WorkerHandler(BaseHTTPRequestHandler):
    expected_token: str | None = None
    mode: str = "dry-run"

    def log_message(self, fmt: str, *args: object) -> None:
        # Redact request bodies and tokens; log only status and path.
        sys.stderr.write(f"[gpu-worker] {self.command} {self.path} -> {fmt % args}\n")

    def _send_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _check_auth(self) -> bool:
        if not self.expected_token:
            return True
        header = self.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return False
        provided = header[len("Bearer ") :].strip()
        return hmac.compare_digest(
            provided.encode("utf-8"), self.expected_token.encode("utf-8")
        )

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/healthz":
            self._send_json(
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "worker_mode": self.mode,
                    "gpu_ready": True if self.mode == "dry-run" else is_gpu_pipeline_ready(),
                },
            )
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/v1/generate":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        if not self._check_auth():
            self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid_length"})
            return
        if length <= 0 or length > 16 * 1024:
            self._send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "body_size"})
            return

        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            self._send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": "invalid_json"})
            return

        dish_id = data.get("dish_id")
        change_ids = data.get("change_ids")
        texture = data.get("texture", "any")
        flavour = data.get("flavour", "any")
        if (
            dish_id not in ALLOWED_DISHES
            or not isinstance(change_ids, list)
            or not (1 <= len(change_ids) <= 2)
            or any(cid not in ALLOWED_CHANGES for cid in change_ids)
            or texture not in ALLOWED_TEXTURES
            or flavour not in ALLOWED_FLAVOURS
        ):
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid_selection"})
            return

        key = (dish_id, tuple(sorted(change_ids)))
        prompt_id = PROMPT_MAP.get(key, f"locked_{dish_id}_{'_'.join(sorted(change_ids))}")
        seed_bytes = hashlib.sha256(f"{dish_id}:{','.join(change_ids)}".encode()).digest()[:4]
        seed = int.from_bytes(seed_bytes, "big")

        if self.mode == "dry-run":
            artifact = build_dry_run_artifact(dish_id, change_ids, prompt_id, seed)
            self._send_json(HTTPStatus.OK, artifact)
            return

        try:
            artifact = run_gpu_pipeline(
                dish_id=dish_id,
                change_ids=change_ids,
                texture=texture,
                flavour=flavour,
                prompt_id=prompt_id,
                seed=seed,
            )
        except GpuUnsupportedSelectionError as exc:
            self._send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                {"error": "gpu_unsupported_selection", "message": str(exc)},
            )
            return
        except GpuPipelineUnreadyError as exc:
            self._send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"error": "gpu_pipeline_unready", "message": str(exc)},
            )
            return

        self._send_json(HTTPStatus.OK, artifact)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bind",
        default=os.environ.get("WORKER_BIND_ADDR", ""),
        help="Tailscale IP (100.64.0.0/10) or 127.0.0.1. Auto-detects via 'tailscale ip -4' if omitted.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("WORKER_PORT", "8790")),
        help="TCP port (default: 8790).",
    )
    parser.add_argument(
        "--mode",
        choices=("dry-run", "gpu"),
        default=os.environ.get("WORKER_MODE", "dry-run"),
        help="Execution mode (default: dry-run).",
    )
    parser.add_argument(
        "--warm",
        action="store_true",
        help="Run the four supported sgedit jobs once (filling the candidate cache), print the "
        "evidence as JSON and exit. Needs the GPU, the fixtures and a running checker.",
    )
    args = parser.parse_args()

    if args.warm:
        import sgedit_adapter

        try:
            adapter = get_adapter()
        except GpuPipelineUnreadyError as exc:
            raise SystemExit(f"Cannot warm the cache: {exc}") from exc
        report = []
        for dish in sgedit_adapter.RICE_DISHES:
            for change in sgedit_adapter.SUPPORTED_CHANGES:
                report.append(adapter.run(dish, [change]))
        print(json.dumps(report, indent=1))
        return

    bind_addr = args.bind.strip() or detect_tailscale_ipv4()
    if not is_allowed_bind_ip(bind_addr):
        raise SystemExit(
            f"Refusing to bind GPU worker to non-Tailscale/non-loopback address '{bind_addr}'."
        )
    token = os.environ.get("MODEL_WORKER_TOKEN", "").strip() or None
    if not token and bind_addr not in ("127.0.0.1", "::1", "localhost"):
        raise SystemExit(
            "MODEL_WORKER_TOKEN is required when binding the GPU worker to a Tailscale interface."
        )

    WorkerHandler.expected_token = token
    WorkerHandler.mode = args.mode
    if args.mode == "gpu" and not os.environ.get("WORKER_GPU_CMD", "").strip():
        # Load the model before serving so the first request does not pay for it.
        try:
            get_adapter()
        except GpuPipelineUnreadyError as exc:
            print(f"GPU pipeline not ready; requests will get HTTP 503: {exc}", flush=True)
    server = ThreadingHTTPServer((bind_addr, args.port), WorkerHandler)
    print(
        f"Tailscale GPU worker listening on http://{bind_addr}:{args.port} (mode={args.mode})",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
