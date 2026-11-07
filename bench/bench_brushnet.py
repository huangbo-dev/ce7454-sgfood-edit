"""Speed/memory benchmark for BrushNet-SDXL on a 16 GB V100 (CE7454 feasibility check, not evidence).

Compares the baseline setup (bf16 + CPU offload, ~94 s/img) with fp16 fully on the GPU, at 20 and 40 steps.
One photo, one prompt, fixed seed. Writes bench/out/*.png and bench/bench_brushnet.json.
"""
import json, os, time, sys
from pathlib import Path
import numpy as np, torch
from PIL import Image

PROJ = Path(os.environ.get('SGEDIT_BASELINE', Path.home() / 'plateedit-v10'))
RUN = PROJ / 'data/extracted/run'
OUT = Path(__file__).resolve().parent / 'out'
SDXL = PROJ / 'work/cache/hf/models--stabilityai--stable-diffusion-xl-base-1.0/snapshots/462165984030d82259a11f4367a4eed129e94a7b'
IMG = sys.argv[1] if len(sys.argv) > 1 else None
PROMPT = 'Replace all visible white rice with cooked whole-grain brown rice. Keep every other food, the plate and background unchanged. Photorealistic food photograph.'


def pick_image():
    d = sorted((RUN / 'masks/project').iterdir())[0]
    return d.name


def main():
    import diffusers
    OUT.mkdir(exist_ok=True)
    iid = IMG or pick_image()
    im = Image.open(RUN / 'data/project' / iid / 'image.png').convert('RGB')
    M = np.asarray(Image.open(RUN / 'masks/project' / iid / 'M1.png')) > 0
    M = M[..., 0] if M.ndim == 3 else M
    arr = np.asarray(im).copy(); arr[M] = 0
    mask = Image.fromarray(M.astype('uint8') * 255).convert('RGB')

    brush = diffusers.BrushNetModel.from_pretrained(PROJ / 'work/models/brushnet_sdxl_seg', torch_dtype=torch.float16)
    pipe = diffusers.StableDiffusionXLBrushNetPipeline.from_pretrained(SDXL, brushnet=brush, torch_dtype=torch.float16, use_safetensors=True)
    pipe.scheduler = diffusers.DPMSolverMultistepScheduler.from_config(pipe.scheduler.config)
    pipe.to('cuda')
    # The fp16 SDXL VAE overflows (NaN -> black images). Keep the VAE in fp32 for both the masked-image encode
    # inside the pipeline and our own decode; everything else stays fp16.
    vae32 = pipe.vae.to(torch.float32)
    _enc = vae32.encode
    def encode32(x, *a, **k):
        out = _enc(x.float(), *a, **k)
        dist, smp = out.latent_dist, out.latent_dist.sample
        dist.sample = lambda generator=None: smp(generator).half()
        return out
    vae32.encode = encode32
    pipe.set_progress_bar_config(disable=True)
    res = []
    for steps in (20, 20, 40):  # first 20-step run includes warm-up
        g = torch.Generator('cpu').manual_seed(1107)
        torch.cuda.synchronize(); torch.cuda.reset_peak_memory_stats(); t = time.perf_counter()
        with torch.inference_mode():
            lat = pipe(prompt=PROMPT, image=Image.fromarray(arr), mask=mask, height=1024, width=1024,
                       num_inference_steps=steps, guidance_scale=7.5, brushnet_conditioning_scale=1.0,
                       generator=g, output_type='latent').images
            nan_latent = bool(torch.isnan(lat).any())
            x = vae32.decode(lat.float() / vae32.config.scaling_factor).sample
            out = pipe.image_processor.postprocess(x, output_type='pil')[0].convert('RGB')
        torch.cuda.synchronize(); sec = time.perf_counter() - t
        a = np.asarray(out).astype(float)
        p = OUT / f'fp16_{steps}steps_{len(res)}.png'; out.save(p)
        r = {'steps': steps, 'seconds': round(sec, 2), 'peak_GiB': round(torch.cuda.max_memory_allocated() / 2**30, 2),
             'mean_pixel': round(a.mean(), 1), 'blank': bool(a.std() < 2), 'nan_latent': nan_latent, 'path': str(p)}
        res.append(r); print(r, flush=True)
    info = {'image_id': iid, 'gpu': torch.cuda.get_device_name(), 'dtype': 'float16 (UNet+BrushNet), fp32 VAE decode', 'offload': False,
            'baseline_v0': {'dtype': 'bfloat16', 'offload': True, 'steps': 40, 'median_seconds': 94.2}, 'runs': res}
    (OUT.parent / 'bench_brushnet.json').write_text(json.dumps(info, indent=1))


if __name__ == '__main__':
    main()
