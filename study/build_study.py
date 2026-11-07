"""Build the blinded team-annotation site from TEST runs: site/{items.json, media/} + items_key.json (never served).

The two compared outputs may come from different runs, e.g. the headline contrast
  python study/build_study.py --first test_baseline:single --second test_tuned:retry@4 [--gold 3] [--repeats 2]
(original prompt, single attempt vs corrected prompt, check-and-retry). Jobs are matched by key.

Main screens: one per job where the two arms differ (identical outputs are not shown; their count is reported).
Checks: 1 practice + N attention checks whose "trap" side is the original photo itself (expected: edit = Not done);
the other side is a real output of the same job. Repeats: pairs shown again later with sides swapped (in the page).
"""
import argparse, hashlib, json, random, sys
from collections import defaultdict
from pathlib import Path
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from sgedit.paths import RUNS  # noqa: E402

CRITERIA = [
    {'key': 'edit', 'question': 'Was the requested change made?',
     'options': [[0, 'Not done'], [1, 'Partly'], [2, 'Clearly done']],
     'scale': {'0': 'No visible requested change, or a different change.',
               '1': 'Visible but incomplete (rice only tinted or patchy; one tiny floret; the rice or noodles disappeared).',
               '2': 'The change is obvious and complete.'}},
    {'key': 'realism', 'question': 'Does it look like a real food photo?',
     'options': [[1, 'No'], [2, 'Somewhat'], [3, 'Yes']],
     'scale': {'1': 'Clearly fake, smeared or broken.', '2': 'Plausible, with visible flaws.', '3': 'Looks like a real photo.'}},
]
GOALS = {'T1-B': 'Add a few cooked broccoli florets on top of the {src}, keeping the {src} and the rest of the meal.',
         'T2': 'Replace the white rice with real-looking cooked brown rice, keeping the rest of the meal.'}


def photo_box(p):
    a = np.asarray(Image.open(p).convert('RGB')).astype(int)
    diff = np.abs(a - a[0, 0]).max(axis=2) > 3
    ys, xs = np.where(diff)
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def export(src, media, box):
    im = Image.open(src).convert('RGB').crop(box)
    tmp = media / '_t.jpg'; im.save(tmp, 'JPEG', quality=90)
    name = hashlib.sha256(tmp.read_bytes()).hexdigest()[:20] + '.jpg'
    tmp.replace(media / name)
    return name


def arm_spec(text):
    """'RUN:ARM' -> (run, arm, label)."""
    run, arm = text.split(':')
    return run, arm, f'{run}:{arm}'


def load_run(run, arm):
    """Results keyed by job, with the chosen arm's tag under r['_tag']. Arms at a budget (e.g. retry@4) are
    derived from a larger-K run with the same selection rules as evaluate/report_tables.py."""
    R = RUNS / run
    lock = json.loads((R / 'LOCK.json').read_text())
    assert lock['set'] == 'test', f'{run}: the annotation uses test runs only'
    res = {json.loads(l)['key']: json.loads(l) for f in sorted(R.glob('results_shard*.jsonl')) for l in open(f)}
    if '@' in arm:
        from evaluate.report_tables import select
        sel = select(R, [int(arm.split('@')[1])])
        for k, r in res.items():
            r['_tag'] = sel[k]['arms'][arm][0]
    else:
        for r in res.values():
            r['_tag'] = r[arm]
    orig = {j['key']: j['original_path'] for j in json.loads((R / 'jobs.json').read_text())}
    return R, res, orig


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--first', required=True, help='reference, RUN:ARM, e.g. test_baseline:single')
    ap.add_argument('--second', required=True, help='method, RUN:ARM, e.g. test_tuned:retry')
    ap.add_argument('--gold', type=int, default=3); ap.add_argument('--repeats', type=int, default=2)
    a = ap.parse_args()
    (run_a, arm_a, lab_a), (run_b, arm_b, lab_b) = arm_spec(a.first), arm_spec(a.second)
    RA, res_a, orig = load_run(run_a, arm_a)
    RB, res_b, _ = load_run(run_b, arm_b)
    keys = sorted(set(res_a) & set(res_b))
    assert keys, 'the two runs share no jobs'
    site = HERE / 'site'; media = site / 'media'; media.mkdir(parents=True, exist_ok=True)
    rng = random.Random(20261110)
    items, key, pool, ident_by_task = [], {}, [], defaultdict(int)
    for k in keys:
        r = res_a[k]
        ca = json.loads((RA / 'candidates' / k / f"{r['_tag']}.json").read_text())
        cb = json.loads((RB / 'candidates' / k / f"{res_b[k]['_tag']}.json").read_text())
        box = photo_box(orig[k]); o = export(orig[k], media, box)
        pool.append((r, o, export(ca['path'], media, box)))
        if ca['sha256'] == cb['sha256']:
            ident_by_task[r['task']] += 1; continue
        order = [lab_a, lab_b]; rng.shuffle(order)
        names = {lab_a: pool[-1][2], lab_b: export(cb['path'], media, box)}
        iid = hashlib.sha256(f"{k}|{lab_a}|{lab_b}".encode()).hexdigest()[:10]
        items.append({'id': iid, 'task': r['task'], 'dish': r['dish'], 'source': r['source'], 'original': o,
                      'A': names[order[0]], 'B': names[order[1]], 'kind': 'main'})
        key[iid] = {'job': k, 'A': order[0], 'B': order[1], 'task': r['task'], 'image_id': r['image_id']}
    rng.shuffle(pool)
    checks = []
    for n, (r, o, real) in enumerate(pool[: a.gold + 1]):
        side = rng.choice('AB')
        checks.append({'id': f"{'p' if n == 0 else 'g'}{n}-{r['key'][:6]}", 'kind': 'practice' if n == 0 else 'gold',
                       'task': r['task'], 'dish': r['dish'], 'source': r['source'], 'original': o, 'trap': 'unchanged',
                       'trap_side': side, 'A': o if side == 'A' else real, 'B': real if side == 'A' else o,
                       'expect': {'edit': [0]}})
    n_screens = len(items) + a.gold + min(a.repeats, len(items))
    (site / 'items.json').write_text(json.dumps({'items': items, 'checks': checks, 'criteria': CRITERIA, 'goals': GOALS,
                                                 'n_screens': n_screens, 'n_repeats': min(a.repeats, len(items))}))
    key['_meta'] = {'pair': [lab_a, lab_b], 'identical': dict(ident_by_task), 'jobs': len(keys)}
    (HERE / 'items_key.json').write_text(json.dumps(key, indent=1))
    print(f'{len(keys)} jobs: {len(items)} pairs ({lab_a} vs {lab_b}), {sum(ident_by_task.values())} identical '
          f'(not shown); {len(checks)} checks; {n_screens} screens per annotator')


if __name__ == '__main__':
    main()
