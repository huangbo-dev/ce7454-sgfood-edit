"""BrushNet-SDXL editor for a 16 GB V100.

fp16 UNet + BrushNet with the VAE in fp32 (the fp16 SDXL VAE overflows to black images on encode and decode).
Benchmark (bench/bench_brushnet.json): ~8 s per 1024px edit at 20 steps, 12.5 GiB peak, vs 94 s for the baseline's
bf16 + CPU-offload setup. Runs in the BrushNet environment (sgedit.paths.BRUSH_PY).

Modes
  full  edit the 1024 canvas with the mask
  crop  edit a square crop around the mask (bbox + margin, at least min_px), upscaled to 1024, then pasted back
Both finish with feathered paste-back: original outside a softened mask boundary, generated pixels inside the mask.
"""
import time
from dataclasses import dataclass, asdict
import numpy as np
import torch
from PIL import Image
from scipy.ndimage import binary_dilation, gaussian_filter

from .paths import BRUSHNET_CKPT, SDXL


@dataclass
class EditSpec:
    prompt: str
    seed: int = 1107
    steps: int = 20
    guidance: float = 7.5
    conditioning_scale: float = 1.0
    mode: str = 'crop'            # 'crop' | 'full'
    crop_margin: float = 0.25
    crop_min_px: int = 384
    dilate_px: int = 0            # grow the mask before editing (0 = as given)
    negative_prompt: str | None = None


def disk(r):
    y, x = np.ogrid[-r:r + 1, -r:r + 1]
    return x * x + y * y <= r * r


def feather_alpha(mask, radius=4, sigma=3.0):
    """1 inside the mask, soft fall-off just outside (same rule as the baseline's locked paste-back)."""
    a = gaussian_filter(binary_dilation(mask, disk(radius)).astype('float64'), sigma)
    return np.maximum(a, mask.astype('float64'))


def crop_box(mask, margin, min_px, size):
    ys, xs = np.where(mask)
    x0, y0, x1, y1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
    s = int(min(size, max(min_px, round(max(x1 - x0, y1 - y0) * (1 + 2 * margin)))))
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    X0 = int(np.clip(round(cx - s / 2), 0, size - s)); Y0 = int(np.clip(round(cy - s / 2), 0, size - s))
    return X0, Y0, X0 + s, Y0 + s


class Editor:
    def __init__(self, device='cuda'):
        import diffusers
        torch.backends.cudnn.benchmark = False      # autotuning picks different kernels per run
        torch.backends.cudnn.deterministic = True
        self.device = device
        brush = diffusers.BrushNetModel.from_pretrained(BRUSHNET_CKPT, torch_dtype=torch.float16)
        pipe = diffusers.StableDiffusionXLBrushNetPipeline.from_pretrained(SDXL, brushnet=brush, torch_dtype=torch.float16,
                                                                           use_safetensors=True)
        pipe.scheduler = diffusers.DPMSolverMultistepScheduler.from_config(pipe.scheduler.config)
        pipe.to(device)
        vae = pipe.vae.to(torch.float32)
        enc = vae.encode

        def encode32(x, *a, **k):
            out = enc(x.float(), *a, **k)
            dist, smp = out.latent_dist, out.latent_dist.sample
            dist.sample = lambda generator=None: smp(generator).half()
            return out
        vae.encode = encode32
        pipe.set_progress_bar_config(disable=True)
        self.pipe, self.vae = pipe, vae

    @property
    def tokenizers(self):
        return [self.pipe.tokenizer, self.pipe.tokenizer_2]

    @torch.inference_mode()
    def _generate(self, img, mask, spec):
        from .prompts import assert_fits
        assert_fits(spec.prompt, self.tokenizers, 'prompt')
        assert_fits(spec.negative_prompt, self.tokenizers, 'negative prompt')
        arr = np.asarray(img).copy(); arr[mask] = 0
        m = Image.fromarray(mask.astype('uint8') * 255).convert('RGB')
        g = torch.Generator('cpu').manual_seed(int(spec.seed))
        lat = self.pipe(prompt=spec.prompt, negative_prompt=spec.negative_prompt, image=Image.fromarray(arr), mask=m,
                        height=1024, width=1024, num_inference_steps=spec.steps, guidance_scale=spec.guidance,
                        brushnet_conditioning_scale=spec.conditioning_scale, generator=g, output_type='latent').images
        if torch.isnan(lat).any():
            raise FloatingPointError('NaN latents')
        x = self.vae.decode(lat.float() / self.vae.config.scaling_factor).sample
        return self.pipe.image_processor.postprocess(x, output_type='pil')[0].convert('RGB')

    def edit(self, image, mask, spec: EditSpec):
        """image: 1024x1024 PIL RGB; mask: bool HxW (True = editable). Returns (PIL image, meta dict)."""
        image = image.convert('RGB')
        size = image.size[0]
        assert image.size == (size, size) == mask.shape[::-1], 'expects a square canvas matching the mask'
        mask = mask.astype(bool)
        if spec.dilate_px:
            mask = binary_dilation(mask, disk(spec.dilate_px))
        torch.cuda.synchronize(); t = time.perf_counter()
        box = None
        if spec.mode == 'crop':
            box = crop_box(mask, spec.crop_margin, spec.crop_min_px, size)
            src = image.crop(box).resize((1024, 1024), Image.LANCZOS)
            m = np.asarray(Image.fromarray(mask[box[1]:box[3], box[0]:box[2]].astype('uint8') * 255)
                           .resize((1024, 1024), Image.NEAREST)) > 127
            out = self._generate(src, m, spec).resize((box[2] - box[0], box[3] - box[1]), Image.LANCZOS)
            raw = image.copy(); raw.paste(out, box[:2])
        else:
            raw = self._generate(image.resize((1024, 1024)), mask, spec).resize(image.size, Image.LANCZOS)
        a = feather_alpha(mask)[..., None]
        comp = np.clip(np.rint(a * np.asarray(raw, 'float64') + (1 - a) * np.asarray(image, 'float64')), 0, 255).astype('uint8')
        torch.cuda.synchronize()
        meta = {**asdict(spec), 'crop_box': box, 'seconds': round(time.perf_counter() - t, 2),
                'mask_pixels': int(mask.sum()), 'gpu': torch.cuda.get_device_name()}
        return Image.fromarray(comp), meta
