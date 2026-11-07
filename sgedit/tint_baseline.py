"""Non-learned brown-rice baseline: colour transfer inside the rice mask (no generation).

Shows whether generation is needed at all for T2. Each photo's rice region is mapped in CIELAB to the colour
statistics of brown rice (Reinhard-style statistics transfer, per channel, with robust statistics), then pasted back with the editor's
feathered mask. Texture and grain shape stay those of the white rice.

TARGET was measured once on VALIDATION photos only: the rice region of the 22 tuned-prompt validation outputs
(prompt search round 1, r1_hawker) that the checker rated as brown rice with probability >= 0.9.
White rice in the same photos measured L 78.5, a 0.4, b 13.5.

  python -m sgedit.tint_baseline --run <run>       # adds candidates/<key>/tint.{png,json} for T2 jobs + tint.jsonl
"""
import argparse, hashlib, json
import numpy as np
from PIL import Image, ImageCms

from .paths import RUNS
from .editor import feather_alpha
from .run_arms import load

TARGET = {'mean': (59.92, 5.18, 19.13), 'std': (15.58, 6.22, 7.43)}   # CIELAB L*, a*, b*
SD_FLOOR = np.array([6.0, 2.0, 3.0])   # minimum source spread per channel, so flat rice is not over-stretched
_SRGB, _LAB = ImageCms.createProfile('sRGB'), ImageCms.createProfile('LAB')
_TO_LAB = ImageCms.buildTransformFromOpenProfiles(_SRGB, _LAB, 'RGB', 'LAB')
_TO_RGB = ImageCms.buildTransformFromOpenProfiles(_LAB, _SRGB, 'LAB', 'RGB')


def to_lab(img):
    a = np.asarray(ImageCms.applyTransform(img.convert('RGB'), _TO_LAB)).astype(float)
    a[..., 1:] = np.where(a[..., 1:] > 127, a[..., 1:] - 256, a[..., 1:])   # PIL stores a*, b* as wrapped int8
    a[..., 0] *= 100 / 255
    return a


def from_lab(a):
    a = a.copy()
    a[..., 0] = np.clip(a[..., 0], 0, 100) * 255 / 100
    a[..., 1:] = np.clip(np.rint(a[..., 1:]), -128, 127) % 256
    return ImageCms.applyTransform(Image.fromarray(np.rint(a).astype('uint8'), 'LAB'), _TO_RGB)


def tint(img, mask):
    lab = to_lab(img)
    x = lab[mask]
    # Robust per-channel statistics (median, scaled MAD with a floor) and clipped z-scores: over-exposed rice has
    # almost no spread, and a plain std would stretch the few dark edge pixels into a black outline.
    mu = np.median(x, 0)
    sd = np.maximum(1.4826 * np.median(np.abs(x - mu), 0), SD_FLOOR)
    z = np.clip((x - mu) / sd, -2.5, 2.5)
    y = z * np.array(TARGET['std']) + np.array(TARGET['mean'])
    # Only rice-like pixels are recoloured: masks catch some leaf, shadow or plate edge, which is much darker than
    # the rice. Weight 1 within 15 L* of the rice median, fading to 0 at 30 below it.
    w = np.clip((x[:, :1] - (mu[0] - 30)) / 15, 0, 1)
    lab[mask] = w * y + (1 - w) * x
    raw = np.asarray(from_lab(lab), 'float64')
    al = feather_alpha(mask)[..., None]
    out = al * raw + (1 - al) * np.asarray(img.convert('RGB'), 'float64')
    return Image.fromarray(np.clip(np.rint(out), 0, 255).astype('uint8'))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--run', required=True)
    a = ap.parse_args()
    R = RUNS / a.run
    jobs = [j for j in json.loads((R / 'jobs.json').read_text()) if j['task'] == 'T2']
    with open(R / 'tint.jsonl', 'w') as log:
        for j in jobs:
            img, mask = load(j)
            d = R / 'candidates' / j['key']; d.mkdir(parents=True, exist_ok=True)
            out = tint(img, mask); out.save(d / 'tint.png')
            rec = {'tag': 'tint', 'path': str(d / 'tint.png'),
                   'sha256': hashlib.sha256((d / 'tint.png').read_bytes()).hexdigest(), 'target': TARGET}
            (d / 'tint.json').write_text(json.dumps(rec, indent=1))
            log.write(json.dumps({'key': j['key'], 'tint': 'tint'}) + '\n')
    print(f'{len(jobs)} T2 jobs tinted -> {R / "tint.jsonl"}')


if __name__ == '__main__':
    main()
