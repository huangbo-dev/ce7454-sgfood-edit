"""Freeze the CE7454 test split BEFORE any test generation.

Input folder (outside Git), one row per photo in photos.csv:
  file,dish,source            e.g.  IMG_0412.jpg,chicken rice,rice
  <file>                      the meal photo (taken for this project; consent for anyone identifiable)
  <stem>_mask.png             binary staple mask (white = rice or noodles), checked by a person
Each photo and mask is letterboxed to the editor's 1024 px square canvas (grey 127 padding, as for the development
photos) and written to $SGEDIT_WORK/data/test/<image_id>/{image,mask}.png. The manifest data/test_manifest.json (tracked
in Git) records source and processed SHA-256 hashes and the job list; it is never overwritten.

  python -m sgedit.test_split --photos <folder>
Tasks: rice -> T1-B and T2; noodles -> T1-B.
"""
import argparse, csv, hashlib, json, sys, time
from pathlib import Path
import numpy as np
from PIL import Image, ImageOps

from .paths import REPO, WORK

SIZE, PAD = 1024, (127, 127, 127)
TASKS = {'rice': ['T1-B', 'T2'], 'noodles': ['T1-B']}


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def letterbox(im, fill, resample):
    im = ImageOps.exif_transpose(im)
    s = SIZE / max(im.size)
    im = im.resize((round(im.width * s), round(im.height * s)), resample)
    canvas = Image.new(im.mode, (SIZE, SIZE), fill)
    canvas.paste(im, ((SIZE - im.width) // 2, (SIZE - im.height) // 2))
    return canvas


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--photos', required=True)
    a = ap.parse_args()
    manifest = REPO / 'data/test_manifest.json'
    if manifest.exists():
        sys.exit(f'{manifest} exists: the test split is frozen. Delete it only if no test generation has run.')
    src = Path(a.photos)
    rows = list(csv.DictReader(open(src / 'photos.csv')))
    out_root = WORK / 'data/test'
    photos, jobs, seen = [], [], set()
    for r in rows:
        f, dish, source = src / r['file'], r['dish'].strip(), r['source'].strip()
        assert source in TASKS, f'{r["file"]}: source must be rice or noodles'
        mf = f.with_name(f.stem + '_mask.png')
        assert f.exists() and mf.exists(), f'missing photo or mask for {r["file"]}'
        h = sha(f)
        assert h not in seen, f'duplicate photo {r["file"]}'
        seen.add(h)
        iid = h[:12]
        img = letterbox(Image.open(f).convert('RGB'), PAD, Image.LANCZOS)
        m = Image.open(mf).convert('L').point(lambda v: 255 if v > 127 else 0)
        assert ImageOps.exif_transpose(Image.open(f)).size == ImageOps.exif_transpose(m).size, f'mask size differs for {r["file"]}'
        m = letterbox(m, 0, Image.NEAREST)
        cover = float((np.asarray(m) > 0).mean())
        assert 0.01 < cover < 0.8, f'{r["file"]}: mask covers {cover:.1%} of the canvas; check it'
        d = out_root / iid; d.mkdir(parents=True, exist_ok=True)
        img.save(d / 'image.png'); m.save(d / 'mask.png')
        photos.append({'image_id': iid, 'file': r['file'], 'dish': dish, 'source': source, 'source_sha256': h,
                       'mask_source_sha256': sha(mf), 'image_sha256': sha(d / 'image.png'),
                       'mask_sha256': sha(d / 'mask.png'), 'mask_coverage': round(cover, 4)})
        for t in TASKS[source]:
            jobs.append({'image_id': iid, 'dish': dish, 'source': source, 'task': t,
                         'original_path': f'data/test/{iid}/image.png', 'mask_path': f'data/test/{iid}/mask.png'})
    manifest.parent.mkdir(exist_ok=True)
    manifest.write_text(json.dumps({'frozen_at': time.strftime('%Y-%m-%d %H:%M:%S'), 'n_photos': len(photos),
                                    'photos': photos, 'jobs': jobs}, indent=1))
    print(f'{len(photos)} photos, {len(jobs)} jobs -> {manifest}. Commit it before running any test generation.')


if __name__ == '__main__':
    main()
