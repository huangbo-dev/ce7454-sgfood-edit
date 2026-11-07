"""Analyse the team's blinded annotation: which arm do annotators prefer, and do they rate it as more done / realistic?

Annotators are project-team members (no external participants; see study/site_server.py). Results are reported as
blinded author annotation, alongside the GPT judge, never as a user study.

  python study/analyze.py [--boot 10000]          # writes study/responses/analysis.json (git-ignored)

Inclusion: annotator confirmed blind, independent annotation; every attention check passed. Answers are stored by
item side (A/B), so display flips do not matter.
Reported per task and overall:
  agreement    mean pairwise agreement and Cohen's kappa between annotators on the preference (arm / tie)
  preference   share of judgements preferring each arm, 95% CI from an annotator-clustered bootstrap
  sign test    per item, the majority preference across raters; two-sided binomial test over non-tied items
  criteria     mean (second arm - first arm) for each rated criterion
  repeats      share of repeated pairs (sides swapped) given the same preference as the first time
  identical    pairs not shown because both arms produced the same image (count as ties in the paper)
"""
import argparse, json
from collections import defaultdict
from pathlib import Path
import numpy as np
from scipy.stats import binomtest

HERE = Path(__file__).resolve().parent
RESP = HERE / 'responses'


def latest(path):
    """Latest record per (rater, screen key)."""
    out = {}
    for line in path.read_text().splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        out[(r['rater'], r['key'])] = r
    return list(out.values())


def agreement(main, key):
    """Pairwise agreement and Cohen's kappa on the preferred arm (or tie), over items both annotators rated."""
    lab = defaultdict(dict)
    for r in main:
        lab[r['rater']][r['item']] = key[r['item']][r['preference']] if r['preference'] in 'AB' else 'tie'
    raters, agree, kappa = sorted(lab), [], []
    for i, a in enumerate(raters):
        for b in raters[i + 1:]:
            common = sorted(set(lab[a]) & set(lab[b]))
            if len(common) < 5:
                continue
            x, y = [lab[a][k] for k in common], [lab[b][k] for k in common]
            po = np.mean([u == v for u, v in zip(x, y)])
            cats = set(x) | set(y)
            pe = sum((x.count(c) / len(x)) * (y.count(c) / len(y)) for c in cats)
            agree.append(po); kappa.append((po - pe) / (1 - pe) if pe < 1 else 1.0)
    return {'pairs': len(agree), 'percent_agreement': round(float(np.mean(agree)), 3) if agree else None,
            'cohen_kappa': round(float(np.mean(kappa)), 3) if kappa else None}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--boot', type=int, default=10000)
    a = ap.parse_args()
    key = json.loads((HERE / 'items_key.json').read_text())
    meta = key.pop('_meta', {})
    recs = latest(RESP / 'site_ratings.jsonl')
    prof = {}
    for line in (RESP / 'site_profiles.jsonl').read_text().splitlines():
        p = json.loads(line); prof[p['rater']] = p
    failed = {r['rater'] for r in recs if r.get('kind') == 'gold' and r.get('gold_pass') is False}
    groups = {'main': lambda rid: rid in prof and prof[rid].get('consent') and rid not in failed}
    report = {'annotators': {'signed_in': len(prof), 'failed_attention': len(failed)},
              'identical_pairs': meta.get('identical', {})}
    rng = np.random.default_rng(20261110)
    for g, keep in groups.items():
        main = [r for r in recs if r.get('kind') == 'main' and r['item'] in key and keep(r['rater'])]
        if not main:
            continue
        arms = sorted({key[r['item']]['A'] for r in main} | {key[r['item']]['B'] for r in main})
        first, second = meta.get('pair', arms)
        res = {'n_raters': len({r['rater'] for r in main}), 'n_judgements': len(main)}
        for task in ('all', 'T1-B', 'T2'):
            rs = [r for r in main if task == 'all' or r['task'] == task]
            if not rs:
                continue
            arm = lambda r: key[r['item']][r['preference']] if r['preference'] in 'AB' else 'tie'
            by_rater = defaultdict(list)
            for r in rs:
                by_rater[r['rater']].append(arm(r))
            raters = list(by_rater)
            share = {k: float(np.mean([arm(r) == k for r in rs])) for k in (first, second, 'tie')}
            boot = []
            for _ in range(a.boot):
                pick = rng.choice(len(raters), len(raters))
                v = [x for i in pick for x in by_rater[raters[i]]]
                boot.append(np.mean([x == second for x in v]) - np.mean([x == first for x in v]))
            per_item = defaultdict(list)
            for r in rs:
                per_item[r['item']].append(arm(r))
            maj = [max((first, second), key=v.count) if v.count(first) != v.count(second) else 'tie'
                   for v in per_item.values()]
            w2, w1 = maj.count(second), maj.count(first)
            crit = defaultdict(list)
            for r in rs:
                side = {key[r['item']]['A']: 'A', key[r['item']]['B']: 'B'}
                for c in r['A']:
                    crit[c].append(r[side[second]][c] - r[side[first]][c])
            res[task] = {
                'preference_share': {k: round(v, 3) for k, v in share.items()},
                f'{second}_minus_{first}': round(share[second] - share[first], 3),
                'ci95': [round(float(np.percentile(boot, q)), 3) for q in (2.5, 97.5)],
                'items': len(per_item), 'item_majority': {first: w1, second: w2, 'tie': maj.count('tie')},
                'sign_test_p': round(binomtest(w2, w1 + w2).pvalue, 4) if w1 + w2 else None,
                f'criteria_mean({second}-{first})': {c: round(float(np.mean(v)), 3) for c, v in crit.items()}}
        reps = {(r['rater'], r['item']): arm for r in recs if r.get('kind') == 'repeat' and keep(r['rater'])
                for arm in [r['preference']]}
        firsts = {(r['rater'], r['item']): r['preference'] for r in main}
        same = [firsts[k] == v for k, v in reps.items() if k in firsts]
        res['repeat_consistency'] = round(float(np.mean(same)), 3) if same else None
        res['agreement'] = agreement(main, key)
        report[g] = res
    (RESP / 'analysis.json').write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))


if __name__ == '__main__':
    main()
