"""Calibrate the checker (Qwen2.5-VL-3B or -7B) against the GPT-5.5 judge on VALIDATION outputs only.

Items: calib/items.json (33 baseline development pairs at the frozen settings; built by build_items.py;
judged by evaluate/judge.py --items-dir calib).
  1. score every output with the checker  -> checker_out/<item>_<side>.json
  2. compare with the GPT judge (mean over both presentation orders), per criterion -> calib_report.json

  python calib/run_checker.py            # both steps (GPU for step 1)
  python calib/run_checker.py --compare  # step 2 only
"""
import argparse, glob, json, sys
from collections import defaultdict
from pathlib import Path
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from sgedit.paths import BASE_RUN  # noqa: E402
from sgedit.editor import crop_box  # noqa: E402

ITEMS = json.load(open(HERE / 'items.json'))['items']
KEY = json.load(open(HERE / 'items_key.json'))
CRIT = ('edit', 'preserve', 'realism', 'extra')
JUDGE = 'gpt-5.5-2026-04-23'


def mask_box(item):
    """M1 mask of this photo, cropped to the photo area like the media files, then bbox + 25 % margin."""
    k = KEY[item['id']]
    M = np.asarray(Image.open(BASE_RUN / 'masks/project' / k['image_id'] / 'M1.png')) > 0
    M = M[..., 0] if M.ndim == 3 else M
    x0, y0, x1, y1 = item['crop_box']
    M = M[y0:y1, x0:x1]
    sq = max(M.shape)
    pad = np.zeros((sq, sq), bool); pad[:M.shape[0], :M.shape[1]] = M
    bx = crop_box(pad, 0.25, 256, sq)
    return [bx[0], bx[1], min(bx[2], M.shape[1]), min(bx[3], M.shape[0])]


def score_all(qset, model, quant4, tag):
    from sgedit.checker import Checker
    ck = Checker(qset=qset, model=model, quant4=quant4)
    out = HERE / f'checker_out_{tag}'; out.mkdir(exist_ok=True)
    for n, it in enumerate(ITEMS, 1):
        orig = Image.open(HERE / 'media' / it['original'])
        box = mask_box(it)
        for side in 'AB':
            p = out / f'{it["id"]}_{side}.json'
            if p.exists():
                continue
            r = ck.check(orig, Image.open(HERE / 'media' / it[side]), it['task'], it['source'], box)
            r['crop_box'] = box
            p.write_text(json.dumps(r, indent=1))
        print(f'{n}/{len(ITEMS)}', r['seconds'], 's', {k: round(r[k]['score'], 2) for k in CRIT}, flush=True)


def judge_scores():
    J = defaultdict(dict)
    for p in glob.glob(str(HERE / 'judge_out' / JUDGE / '*.json')):
        r = json.load(open(p)); J[r['item']][r['order']] = r['canonical']
    out = {}
    for iid, d in J.items():
        if set(d) != {'AB', 'BA'}:
            continue
        for side in 'AB':
            out[(iid, side)] = {c: float(np.mean([d[o][side][c] for o in d])) for c in CRIT}
    return out


def compare(tag):
    from scipy.stats import spearmanr
    J = judge_scores()
    rows = []
    for it in ITEMS:
        for side in 'AB':
            p = HERE / f'checker_out_{tag}' / f'{it["id"]}_{side}.json'
            if p.exists() and (it['id'], side) in J:
                c = json.load(open(p))
                rows.append({'iid': it['id'], 'side': side, 'task': it['task'], 'model': KEY[it['id']][side],
                             'checker': {k: c[k]['score'] for k in CRIT}, 'judge': J[(it['id'], side)],
                             'valid_mass': min(c[k]['valid_mass'] for k in CRIT)})
    rep = {'n_outputs': len(rows), 'min_valid_mass': round(min(r['valid_mass'] for r in rows), 3) if rows else None}
    for scope in ('all', 'T1-B', 'T2'):
        R = [r for r in rows if scope == 'all' or r['task'] == scope]
        rep[scope] = {}
        for k in CRIT:
            x, y = [r['checker'][k] for r in R], [r['judge'][k] for r in R]
            s = spearmanr(x, y) if len(set(y)) > 1 and len(set(x)) > 1 else None
            rep[scope][k] = {'spearman': round(float(s.statistic), 3) if s else None,
                             'p': round(float(s.pvalue), 4) if s else None, 'n': len(R),
                             'checker_mean': round(float(np.mean(x)), 3), 'judge_mean': round(float(np.mean(y)), 3)}
    pairs = defaultdict(dict)
    for r in rows:
        pairs[r['iid']][r['side']] = r
    from sgedit.loop import score as ck_score
    agree = []
    for iid, d in pairs.items():
        if set(d) != {'A', 'B'}:
            continue
        cs = {s: ck_score({k: {'score': d[s]['checker'][k]} for k in CRIT}) for s in 'AB'}
        js = {s: ck_score({k: {'score': d[s]['judge'][k]} for k in CRIT}) for s in 'AB'}
        if js['A'] != js['B']:
            agree.append((cs['A'] > cs['B']) == (js['A'] > js['B']))
    rep['pair_choice_agreement'] = {'agree': sum(agree), 'n': len(agree)}
    (HERE / f'calib_report_{tag}.json').write_text(json.dumps(rep, indent=1))
    print(json.dumps(rep, indent=1))


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--compare', action='store_true'); ap.add_argument('--qset', default='v2')
    ap.add_argument('--model', default='Qwen/Qwen2.5-VL-3B-Instruct'); ap.add_argument('--quant4', action='store_true')
    a = ap.parse_args()
    tag = a.qset + ('' if '3B' in a.model else '_7b4bit' if a.quant4 else '_' + a.model.split('/')[-1])
    if not a.compare:
        score_all(a.qset, a.model, a.quant4, tag)
    compare(tag)
