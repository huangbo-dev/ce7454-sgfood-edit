"""Everything Table 1 and Figure 3 need, from one judging pass against a shared reference.

Arms are derived at every budget k <= K from one K-run per prompt set (retry paths and seed lists are prefix-consistent):
  single        seed0
  best_check@k  highest checker score among seed0..seed{k-1}
  best_clip@k   highest CLIP margin among seed0..seed{k-1}       (needs evaluate/clip_select.py on the run)
  retry@k       best checker score among the first k steps of the retry path; generations used = min(k, path length)
  tint          colour transfer, T2 only                          (needs sgedit.tint_baseline on the run)
Every distinct selected output is judged once against the REFERENCE output of the same job (default: baseline
prompt, single-shot), in both orders, with the GPT judge. That gives per-output judge scores (success, realism) and a
win rate against the reference for every row of Table 1 and every point of Figure 3a, and lets Figure 3b compare
the checker's pass verdict with the judge's on exactly the outputs the checker selected.

  python evaluate/report_tables.py build  --name test_report --runs tuned=test_tuned baseline=test_baseline
  python evaluate/judge.py --items-dir $SGEDIT_WORK/runs/test_report/judge --model gpt-5.5-2026-04-23
  python evaluate/report_tables.py report --name test_report [--k-main 4]
Outputs: $SGEDIT_WORK/runs/<name>/{selections.json, judge/, tables.json}. Success = judge edit 2 and nothing added,
averaged over the two presentation orders. 95% CIs: bootstrap over photos.
"""
import argparse, glob, hashlib, json, random, shutil, sys
from collections import defaultdict
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from sgedit.paths import RUNS  # noqa: E402
from evaluate.judge_arms import photo_box, export  # noqa: E402

MODEL = 'gpt-5.5-2026-04-23'
KS = (1, 2, 4, 8)


def cand(R, key, tag):
    return json.loads((R / 'candidates' / key / f'{tag}.json').read_text())


def select(R, ks):
    """Per job: {arm@k: (tag, generations used)} derived from one run."""
    res = [json.loads(l) for f in sorted(R.glob('results_shard*.jsonl')) for l in open(f)]
    clip = {d['key']: d['margins'] for d in map(json.loads, open(R / 'clip_select.jsonl'))} \
        if (R / 'clip_select.jsonl').exists() else {}
    tint = {d['key'] for d in map(json.loads, open(R / 'tint.jsonl'))} if (R / 'tint.jsonl').exists() else set()
    out = {}
    for r in res:
        K, seeds, path = r['K'], r['seed_tags'], r['retry_steps']
        score = {t: cand(R, r['key'], t)['score'] for t in set(seeds) | set(path)}
        s = {'single': ('seed0', 1)}
        for k in ks:
            if k > K:
                continue
            s[f'best_check@{k}'] = (max(seeds[:k], key=score.get), k)
            if r['key'] in clip:
                s[f'best_clip@{k}'] = (max(seeds[:k], key=clip[r['key']].get), k)
            s[f'retry@{k}'] = (max(path[:k], key=score.get), min(k, len(path)))
        if r['key'] in tint:
            s['tint'] = ('tint', 0)
        out[r['key']] = {'task': r['task'], 'dish': r['dish'], 'source': r['source'], 'image_id': r['image_id'], 'arms': s}
    return out


def build(name, runs, ref):
    ref_prompt, ref_arm = ref.split(':')
    Rs = {p: RUNS / run for p, run in runs.items()}
    sel = {p: select(R, KS) for p, R in Rs.items()}
    keys = sorted(set.intersection(*(set(s) for s in sel.values())))
    out = RUNS / name; media = out / 'judge' / 'media'; media.mkdir(parents=True, exist_ok=True)
    shutil.copy(HERE / 'rubric.json', out / 'judge' / 'rubric.json')
    jobs = {j['key']: j for j in json.loads((Rs[ref_prompt] / 'jobs.json').read_text())}
    rng = random.Random(20261108)
    items, key = [], {}
    for k in keys:
        o = jobs[k]['original_path']; box = photo_box(o); oname = export(o, media, box)
        ref_tag = sel[ref_prompt][k]['arms'][ref_arm][0]
        ref_c = cand(Rs[ref_prompt], k, ref_tag); ref_img = export(ref_c['path'], media, box)
        outputs = {}   # sha -> (prompt, tag): judge each distinct output once
        for p, s in sel.items():
            for arm, (tag, _) in s[k]['arms'].items():
                c = cand(Rs[p], k, tag)
                outputs.setdefault(c['sha256'], (p, tag, c['path']))
        for sha, (p, tag, path) in outputs.items():
            if sha == ref_c['sha256'] and len(outputs) > 1:
                continue    # the reference's own scores come from its other pairs
            names = {'ref': ref_img, 'out': export(path, media, box)}
            order = ['ref', 'out']; rng.shuffle(order)
            iid = hashlib.sha256(f'{k}|{sha}'.encode()).hexdigest()[:12]
            items.append({'id': iid, 'task': sel[ref_prompt][k]['task'], 'dish': sel[ref_prompt][k]['dish'],
                          'source': sel[ref_prompt][k]['source'], 'original': oname, 'crop_box': list(box),
                          'A': names[order[0]], 'B': names[order[1]]})
            key[iid] = {'job': k, 'A': order[0], 'B': order[1], 'out_sha': sha, 'ref_sha': ref_c['sha256']}
    sha = hashlib.sha256((out / 'judge' / 'rubric.json').read_bytes()).hexdigest()
    (out / 'judge' / 'items.json').write_text(json.dumps({'rubric_sha256': sha, 'items': items}, indent=1))
    (out / 'judge' / 'items_key.json').write_text(json.dumps(key, indent=1))
    sels = {p: {k: v for k, v in s.items() if k in keys} for p, s in sel.items()}
    (out / 'selections.json').write_text(json.dumps({'runs': runs, 'ref': ref, 'selections': sels}, indent=1))
    print(f'{len(keys)} jobs; {len(items)} outputs to judge against {ref} ({2 * len(items)} judge calls)')


def boot_ci(per_photo, n=5000, seed=0):
    """per_photo: {photo: [values]} -> 95% CI of the mean, resampling photos."""
    rng = np.random.default_rng(seed); photos = list(per_photo)
    if not photos:
        return None
    means = []
    for _ in range(n):
        pick = rng.choice(len(photos), len(photos))
        v = [x for i in pick for x in per_photo[photos[i]]]
        means.append(np.mean(v))
    return [round(float(np.percentile(means, q)), 3) for q in (2.5, 97.5)]


def report(name, model=MODEL, k_main=4):
    out = RUNS / name
    S = json.loads((out / 'selections.json').read_text())
    Rs = {p: RUNS / run for p, run in S['runs'].items()}
    key = json.loads((out / 'judge' / 'items_key.json').read_text())
    J = defaultdict(dict)
    for f in glob.glob(str(out / 'judge' / 'judge_out' / model.replace('/', '_') / '*.json')):
        r = json.load(open(f)); J[r['item']][r['order']] = r['canonical']
    score, win = {}, {}   # (job, sha) -> per-order judge scores of that output; win rate vs the reference
    ref_scores = defaultdict(list)
    for iid, k in key.items():
        if set(J[iid]) != {'AB', 'BA'}:
            continue
        side = {k['A']: 'A', k['B']: 'B'}
        score[(k['job'], k['out_sha'])] = [J[iid][o][side['out']] for o in ('AB', 'BA')]
        ref_scores[k['job']] += [J[iid][o][side['ref']] for o in ('AB', 'BA')]
        prefs = [J[iid][o]['preference'] for o in ('AB', 'BA')]
        win[(k['job'], k['out_sha'])] = np.mean([1.0 if p == side['out'] else 0.5 if p == 'tie' else 0.0 for p in prefs])
    ref_sha = {k['job']: k['ref_sha'] for k in key.values()}
    for job, sc in ref_scores.items():
        score[(job, ref_sha[job])] = sc
        win[(job, ref_sha[job])] = 0.5

    def success(s):
        return float(np.mean([x['edit'] == 2 and x['extra'] == 0 for x in s]))

    rows = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))   # (prompt, arm) -> metric -> photo -> values
    for p, sel in S['selections'].items():
        for job, d in sel.items():
            for arm, (tag, gens) in d['arms'].items():
                c = cand(Rs[p], job, tag)
                if (job, c['sha256']) not in score:
                    continue
                sc = score[(job, c['sha256'])]
                for task in ('all', d['task']):
                    r = rows[(p, arm, task)]
                    r['success'][d['image_id']].append(success(sc))
                    r['realism'][d['image_id']].append(float(np.mean([x['realism'] for x in sc])))
                    r['win'][d['image_id']].append(win[(job, c['sha256'])])
                    r['gens'][d['image_id']].append(gens)
                    if 'check' in c:   # checker verdict on the same output (Figure 3b)
                        r['checker_pass'][d['image_id']].append(float(c['pass']))
    tables = {}
    for (p, arm, task), r in sorted(rows.items()):
        t = {m: round(float(np.mean([x for v in r[m].values() for x in v])), 3) for m in r}
        t['n'] = sum(len(v) for v in r['success'].values())
        t['success_ci'] = boot_ci(r['success']); t['win_ci'] = boot_ci(r['win'])
        if 'checker_pass' in t:
            t['inflation'] = round(t['checker_pass'] - t['success'], 3)
        tables[f'{p}|{arm}|{task}'] = t
    (out / 'tables.json').write_text(json.dumps(tables, indent=1))
    print(f"{'prompt':9} {'arm':14} {'task':5} {'succ':>5} {'real':>5} {'win':>5} {'gens':>5} {'chk':>5} {'infl':>5}  n")
    for name_, t in tables.items():
        p, arm, task = name_.split('|')
        if '@' in arm and not arm.endswith(f'@{k_main}'):
            continue
        print(f"{p:9} {arm:14} {task:5} {t['success']:5.2f} {t['realism']:5.2f} {t['win']:5.2f} {t['gens']:5.2f} "
              f"{t.get('checker_pass', float('nan')):5.2f} {t.get('inflation', float('nan')):5.2f}  {t['n']}")


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['build', 'report']); ap.add_argument('--name', required=True)
    ap.add_argument('--runs', nargs='+', help='prompt=run pairs, e.g. tuned=test_tuned baseline=test_baseline')
    ap.add_argument('--ref', default='baseline:single'); ap.add_argument('--model', default=MODEL)
    ap.add_argument('--k-main', type=int, default=4)
    a = ap.parse_args()
    if a.cmd == 'build':
        build(a.name, dict(x.split('=') for x in a.runs), a.ref)
    else:
        report(a.name, a.model, a.k_main)
