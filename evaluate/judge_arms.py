"""Judge the comparison arms of a run (validation or test) with the GPT judge: blinded pairs, both orders.

  python evaluate/judge_arms.py build  --run <run>        # items for arm pairs -> $SGEDIT_WORK/runs/<run>/judge/
  python evaluate/judge.py --items-dir $SGEDIT_WORK/runs/<run>/judge --model gpt-5.5-2026-04-23
  python evaluate/judge_arms.py report --run <run> [--model ...]

Pairs (first arm is the reference):
  single     vs retry        does the full method beat the first attempt?
  single     vs best_check   value of checker selection alone
  best_check vs retry        value of targeted retries over selection at the same budget
  single     vs best_clip    value of a cheap CLIP selector (needs evaluate/clip_select.py first)
  tint       vs single       T2 only: is generation needed at all? (needs sgedit.tint_baseline first)
Identical outputs (e.g. the loop kept its first candidate) are not judged and count as ties.
On validation runs this only informs whether a policy is worth freezing; reported numbers come from test runs.
"""
import argparse, glob, hashlib, json, random, shutil, sys
from collections import defaultdict
from pathlib import Path
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from sgedit.paths import RUNS  # noqa: E402

PAIRS = [('single', 'retry'), ('single', 'best_check'), ('best_check', 'retry'), ('single', 'best_clip'),
         ('tint', 'single')]
CRIT = ('edit', 'preserve', 'realism', 'extra')
MODEL = 'gpt-5.5-2026-04-23'


def photo_box(p):
    """Bounding box of the photo inside its grey letterbox padding."""
    a = np.asarray(Image.open(p).convert('RGB')).astype(int)
    diff = np.abs(a - a[0, 0]).max(axis=2) > 3
    ys, xs = np.where(diff)
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def export(src, media, box):
    im = Image.open(src).convert('RGB').crop(box)
    tmp = media / '_t.jpg'; im.save(tmp, 'JPEG', quality=92)
    name = hashlib.sha256(tmp.read_bytes()).hexdigest()[:20] + '.jpg'
    tmp.replace(media / name)
    return name


def load_results(R):
    res = [json.loads(l) for f in sorted(R.glob('results_shard*.jsonl')) for l in open(f)]
    for fname, arm in (('clip_select.jsonl', 'best_clip'), ('tint.jsonl', 'tint')):
        if (R / fname).exists():
            got = {d['key']: d[arm] for d in map(json.loads, open(R / fname))}
            for r in res:
                r[arm] = got.get(r['key'])
    return res


def build(run):
    R = RUNS / run
    res = load_results(R)
    jobs = {j['key']: j for j in json.loads((R / 'jobs.json').read_text())}
    out = R / 'judge'; media = out / 'media'; media.mkdir(parents=True, exist_ok=True)
    shutil.copy(HERE / 'rubric.json', out / 'rubric.json')
    rng = random.Random(20261107)
    items, key, ties, skipped = [], {}, defaultdict(int), defaultdict(int)
    for r in res:
        cand = lambda tag: json.loads((R / 'candidates' / r['key'] / f'{tag}.json').read_text())
        o = jobs[r['key']]['original_path']; box = photo_box(o); oname = export(o, media, box)
        for a, b in PAIRS:
            if not (r.get(a) and r.get(b)):
                skipped[f'{a}|{b}'] += 1; continue
            ca, cb = cand(r[a]), cand(r[b])
            if ca['sha256'] == cb['sha256']:
                ties[f'{a}|{b}'] += 1; continue
            order = [a, b]; rng.shuffle(order)
            iid = hashlib.sha256(f"{r['key']}|{a}|{b}".encode()).hexdigest()[:10]
            names = {arm: export(cand(r[arm])['path'], media, box) for arm in (a, b)}
            items.append({'id': iid, 'task': r['task'], 'dish': r['dish'], 'source': r['source'], 'original': oname,
                          'crop_box': list(box), 'A': names[order[0]], 'B': names[order[1]]})
            key[iid] = {'job': r['key'], 'pair': f'{a}|{b}', 'A': order[0], 'B': order[1], 'task': r['task'],
                        'image_id': r['image_id']}
    sha = hashlib.sha256((out / 'rubric.json').read_bytes()).hexdigest()
    (out / 'items.json').write_text(json.dumps({'rubric_sha256': sha, 'items': items}, indent=1))
    (out / 'items_key.json').write_text(json.dumps(key, indent=1))
    (out / 'ties.json').write_text(json.dumps(ties, indent=1))
    print(f'{len(res)} jobs; {len(items)} pairs to judge; identical (ties): {dict(ties)}; '
          f'arm missing: {dict(skipped)}')


def report(run, model=MODEL):
    out = RUNS / run / 'judge'
    key = json.loads((out / 'items_key.json').read_text()); ties = json.loads((out / 'ties.json').read_text())
    J = defaultdict(dict)
    for p in glob.glob(str(out / 'judge_out' / model.replace('/', '_') / '*.json')):
        r = json.load(open(p)); J[r['item']][r['order']] = r['canonical']
    rep = {}
    for a, b in PAIRS:
        pk = f'{a}|{b}'
        for task in ('all', 'T1-B', 'T2'):
            wins = {a: 0, b: 0, 'split': 0}; diff = defaultdict(list)
            for iid, k in key.items():
                if k['pair'] != pk or (task != 'all' and k['task'] != task) or set(J[iid]) != {'AB', 'BA'}:
                    continue
                prefs = [k[J[iid][o]['preference']] if J[iid][o]['preference'] in 'AB' else 'tie' for o in ('AB', 'BA')]
                wins[prefs[0] if prefs[0] == prefs[1] and prefs[0] != 'tie' else 'split'] += 1
                side = {k['A']: 'A', k['B']: 'B'}
                for c in CRIT:
                    diff[c].append(np.mean([J[iid][o][side[b]][c] - J[iid][o][side[a]][c] for o in ('AB', 'BA')]))
            if not sum(wins.values()):
                continue
            rep[f'{pk}|{task}'] = {'judged': sum(wins.values()), 'preferred': wins,
                                   f'mean({b} - {a})': {c: round(float(np.mean(v)), 3) for c, v in diff.items()}}
        rep[f'{pk}|identical'] = ties.get(pk, 0)
    (out / 'report.json').write_text(json.dumps(rep, indent=1))
    print(json.dumps(rep, indent=1))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['build', 'report']); ap.add_argument('--run', required=True)
    ap.add_argument('--model', default=MODEL)
    a = ap.parse_args()
    build(a.run) if a.cmd == 'build' else report(a.run, a.model)
