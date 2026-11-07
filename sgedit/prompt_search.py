"""Prompt search for a task on VALIDATION photos only (never test).

Each round is a JSON list of candidates {"id", "prompt", "negative", "guidance"?}. Every candidate is generated on
every validation photo of the task with the same seeds, scored by the checker service (selection model, not the
evaluator) and by simple colour statistics of the edited region, and summarised in a table plus a contact sheet.
Candidates are cached by content hash, so rounds can be re-run and extended cheaply.

  CUDA_VISIBLE_DEVICES=0 $BRUSH_PY -m sgedit.prompt_search --task T2 --round r1 --candidates r1.json
Outputs go to RUNS/promptsearch_<task>/ (outside Git).
"""
import argparse, hashlib, json, time
import numpy as np
from PIL import Image, ImageDraw

from .paths import RUNS
from .run_arms import validation_jobs, job_key, load
from .loop import CheckerClient
from .editor import EditSpec, crop_box


def colour_stats(img, mask):
    """Median hue (deg), mean saturation and brightness of the masked region, plus the share of red/purple pixels."""
    hsv = np.asarray(img.convert('HSV'), 'float64')[mask] / 255.0
    h, s, v = hsv[:, 0] * 360, hsv[:, 1], hsv[:, 2]
    coloured = s > 0.12
    red = coloured & ((h < 15) | (h > 300))
    hue = float(np.median(h[coloured])) if coloured.any() else None
    return {'hue': hue, 'sat': round(float(s.mean()), 3), 'val': round(float(v.mean()), 3),
            'red_frac': round(float(red.mean()), 3)}


def summarise(rows):
    def m(key):
        xs = [r[key] for r in rows if r.get(key) is not None]
        return round(float(np.mean(xs)), 3) if xs else None
    return {k: m(k) for k in ('p_brown', 'p_mix', 'p_white', 'edit', 'p_real', 'realism', 'preserve', 'extra',
                              'hue', 'sat', 'val', 'red_frac')} | {
        'pass_edit': round(float(np.mean([r['edit'] >= 1.5 for r in rows])), 3), 'n': len(rows)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--task', default='T2')
    ap.add_argument('--round', required=True)
    ap.add_argument('--candidates', required=True)
    ap.add_argument('--seeds', default='1107,2207')
    ap.add_argument('--checker', default='http://127.0.0.1:8781')
    a = ap.parse_args()
    out = RUNS / f'promptsearch_{a.task}'; (out / 'cands').mkdir(parents=True, exist_ok=True)
    cands = json.load(open(a.candidates))
    (out / f'{a.round}_candidates.json').write_text(json.dumps(cands, indent=1))
    seeds = [int(s) for s in a.seeds.split(',')]
    jobs = [j for j in validation_jobs() if j['task'] == a.task]
    for j in jobs:
        j['key'] = job_key(j['image_id'], j['task']); j['image'], j['mask'] = load(j)
        j['orig_colour'] = colour_stats(j['image'], j['mask'])
    from .editor import Editor
    from .prompts import assert_fits
    ed, chk = Editor(), CheckerClient(a.checker)
    for c in cands:
        assert_fits(c['prompt'], ed.tokenizers, f"{c['id']} prompt"); assert_fits(c.get('negative'), ed.tokenizers)
    table, W = [], 160
    for c in cands:
        spec0 = EditSpec(prompt=c['prompt'], negative_prompt=c.get('negative'), guidance=c.get('guidance', 7.5))
        rows = []
        sheet = Image.new('RGB', (W * (1 + len(seeds)), W * len(jobs)), 'white')
        for i, j in enumerate(jobs):
            box = list(crop_box(j['mask'], 0.25, 256, j['image'].size[0]))
            sheet.paste(j['image'].crop(box).resize((W, W)), (0, i * W))
            for k, seed in enumerate(seeds):
                spec = EditSpec(**{**spec0.__dict__, 'seed': seed})
                h = hashlib.sha256(json.dumps([spec.__dict__, j['key']], sort_keys=True).encode()).hexdigest()[:16]
                png, meta = out / 'cands' / f'{h}.png', out / 'cands' / f'{h}.json'
                if meta.exists():
                    r = json.loads(meta.read_text())
                else:
                    t = time.perf_counter()
                    img, gen = ed.edit(j['image'], j['mask'], spec); img.save(png)
                    ck = chk.check(j['original_path'], png, j['task'], j['source'], box)
                    rt = ck['raw']['rice_type']['probs'] if 'rice_type' in ck.get('raw', {}) else {}
                    r = {'cand': c['id'], 'key': j['key'], 'image_id': j['image_id'], 'dish': j['dish'], 'seed': seed,
                         'path': str(png), 'gen': gen, 'check': ck,
                         'p_white': rt.get('A'), 'p_brown': rt.get('B'), 'p_mix': rt.get('C'),
                         'edit': ck['edit']['score'], 'realism': ck['realism']['score'],
                         'p_real': ck.get('raw', {}).get('real', {}).get('probs', {}).get('A'),
                         'preserve': ck['preserve']['score'], 'extra': ck['extra']['score'],
                         **colour_stats(img, j['mask']), 'orig': j['orig_colour'],
                         'seconds': round(time.perf_counter() - t, 1)}
                    meta.write_text(json.dumps(r, indent=1))
                rows.append(r)
                sheet.paste(Image.open(r['path']).convert('RGB').crop(box).resize((W, W)), ((k + 1) * W, i * W))
                d = ImageDraw.Draw(sheet)
                d.rectangle(((k + 1) * W, i * W, (k + 1) * W + 120, i * W + 12), fill='black')
                d.text(((k + 1) * W + 2, i * W), f"B{r['p_brown']:.2f} M{r['p_mix']:.2f} h{r['hue'] or 0:.0f}",
                       fill='yellow')
        sheet.save(out / f"{a.round}_{c['id']}.jpg", quality=85)
        s = summarise(rows) | {'cand': c['id'], 'round': a.round}
        table.append(s)
        print(json.dumps(s), flush=True)
    with open(out / 'summary.jsonl', 'a') as f:
        for s in table:
            f.write(json.dumps(s) + '\n')


if __name__ == '__main__':
    main()
