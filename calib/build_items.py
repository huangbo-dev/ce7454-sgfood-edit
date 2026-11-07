"""Build the checker-calibration items: pairs of baseline outputs on the DEVELOPMENT (validation) photos only
(SAM-guided M1 masks, FLUX 40/30 vs BrushNet 40/7.5, T1-B and T2, both seeds). Adapted from the baseline's
rating-item builder. The GPT judge scores these pairs (evaluate/judge.py --items-dir calib) and the checker scores
the same outputs (calib/run_checker.py), giving the agreement numbers in calib_report_*.json.

Writes (all outside the frozen run):
  media/<hash>.jpg      downscaled copies of originals and outputs (names reveal nothing)
  items.json            what raters/judge see: item id, task, instruction, original, A, B
  items_key.json        server-side only: which model is A/B, run ids, source hashes
"""
import os, argparse, csv, hashlib, json, random
from pathlib import Path
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
RUN = Path(os.environ.get('SGEDIT_BASELINE', Path.home() / 'plateedit-v10')) / 'data/extracted/run'
PROMPTS = json.load(open(RUN.parents[2] / 'experiment/config/generation_prompts.json'))
TASKS = ('T1-B', 'T2')
SIZE = 1024
SHUFFLE_SEED = 20261107
FROZEN = {('flux', '40', '30.0'), ('brushnet', '40', '7.5')}


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def photo_box(original):
    """Bounding box of the real photo inside the square canvas (padding is a flat colour)."""
    a = np.asarray(Image.open(original).convert('RGB')).astype(int)
    pad = a[0, 0]
    diff = np.abs(a - pad).max(axis=2) > 3
    ys, xs = np.where(diff)
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def export(src, media, box):
    h = sha(src)
    out = media / f'{h[:20]}.jpg'
    if not out.exists():
        im = Image.open(src).convert('RGB').crop(box)
        if max(im.size) > SIZE:
            im.thumbnail((SIZE, SIZE), Image.LANCZOS)
        im.save(out, 'JPEG', quality=92)
    return out.name, h


def main():
    ap = argparse.ArgumentParser()
    ap.parse_args()
    media = HERE / 'media'
    media.mkdir(exist_ok=True)
    rows = [r for r in csv.DictReader(open(RUN / 'metrics/per_run.csv'))
            if r['stage'] == 'development' and r['task'] in TASKS and r['generation_mask_mode'] == 'selected_local'
            and (r['model'], r['steps'], r['guidance']) in FROZEN
            and r['status'] == 'ok']
    by = {}
    for r in rows:
        by.setdefault((r['task'], r['image_id'], r['seed']), {})[r['model']] = r
    rng = random.Random(SHUFFLE_SEED)
    items, key, skipped = [], {}, []
    for (task, image_id, seed), d in sorted(by.items()):
        assert set(d) == {'flux', 'brushnet'}, (task, image_id, seed, set(d))
        f, b = d['flux'], d['brushnet']
        if not all((RUN / 'raw/development' / r['run_id'] / 'raw.png').exists() for r in (f, b)):
            skipped.append((task, image_id, seed)); continue  # output missing from the extracted archive
        orig_f = RUN / 'raw/development' / f['run_id'] / 'original_input.png'
        orig_b = RUN / 'raw/development' / b['run_id'] / 'original_input.png'
        assert sha(orig_f) == sha(orig_b), 'paired outputs must share the same original'
        box = photo_box(orig_f)
        o_name, o_hash = export(orig_f, media, box)
        outs = {}
        for m, r in (('flux', f), ('brushnet', b)):
            p = RUN / 'raw/development' / r['run_id'] / 'raw.png'
            name, h = export(p, media, box)
            assert h == r['raw_sha256'], f'raw hash mismatch for {r["run_id"]}'
            outs[m] = (name, r['run_id'], h)
        order = ['flux', 'brushnet']
        rng.shuffle(order)
        iid = hashlib.sha256(f'{task}|{image_id}|{seed}'.encode()).hexdigest()[:10]
        source = f['source']
        items.append({'id': iid, 'task': task, 'dish': f['dish'], 'source': source,
                      'instruction': PROMPTS[f'{task}_{source}'],
                      'original': o_name, 'crop_box': box, 'A': outs[order[0]][0], 'B': outs[order[1]][0]})
        key[iid] = {'task': task, 'image_id': image_id, 'seed': int(seed), 'dish': f['dish'],
                    'A': order[0], 'B': order[1], 'original_sha256': o_hash,
                    'run_ids': {m: outs[m][1] for m in outs}, 'raw_sha256': {m: outs[m][2] for m in outs}}
    rng.shuffle(items)  # presentation order
    json.dump({'rubric_sha256': sha(HERE / 'rubric.json'), 'items': items}, open(HERE / 'items.json', 'w'), indent=1)
    json.dump(key, open(HERE / 'items_key.json', 'w'), indent=1)
    print(f'{len(items)} pairs; skipped {len(skipped)} with a missing output: {skipped}')
    n = {t: sum(i['task'] == t for i in items) for t in TASKS}
    print(f'{len(items)} items {n}; A=flux in {sum(k["A"] == "flux" for k in key.values())}; media files {len(list(media.iterdir()))}')


if __name__ == '__main__':
    main()
