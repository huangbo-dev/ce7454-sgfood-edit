"""Run single / best-of-K / check-and-retry on a photo set (editor on this GPU, checker service elsewhere).

  python -m sgedit.run_arms --set validation --run val_20261107 --K 4
  python -m sgedit.run_arms --set test --run test_tuned --K 8 --prompts tuned   # only after the test split is frozen

Sets
  validation  the 20 baseline development photos with their M1 masks (tuning only; never reported as test)
  test        new CE7454 photos listed in a frozen manifest (data/test_manifest.json), added later
A lock (config, policy, code hashes, photo list) is written before the first generation and checked on resume.
"""
import argparse, csv, hashlib, json, sys, time
from pathlib import Path
import numpy as np
from PIL import Image

from .paths import BASE_RUN, RUNS, REPO, WORK
from .loop import POLICY, Runner, CheckerClient, job_key


def sha_file(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def validation_jobs():
    rows = [r for r in csv.DictReader(open(BASE_RUN / 'metrics/per_run.csv')) if r['stage'] == 'development']
    photos = sorted({(r['image_id'], r['dish'], r['source']) for r in rows})
    jobs = []
    for iid, dish, src in photos:
        for task in (['T1-B', 'T2'] if src == 'rice' else ['T1-B']):
            jobs.append({'image_id': iid, 'dish': dish, 'source': src, 'task': task,
                         'original_path': str(BASE_RUN / 'data/project' / iid / 'image.png'),
                         'mask_path': str(BASE_RUN / 'masks/project' / iid / 'M1.png')})
    return jobs


def test_jobs():
    m = REPO / 'data/test_manifest.json'
    if not m.exists():
        sys.exit('No frozen test manifest yet (data/test_manifest.json).')
    jobs = json.loads(m.read_text())['jobs']
    for j in jobs:
        j['original_path'], j['mask_path'] = str(WORK / j['original_path']), str(WORK / j['mask_path'])
    return jobs


def load(job):
    img = Image.open(job['original_path']).convert('RGB')
    M = np.asarray(Image.open(job['mask_path'])) > 0
    return img, (M[..., 0] if M.ndim == 3 else M)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--set', choices=['validation', 'test'], required=True)
    ap.add_argument('--run', required=True)
    ap.add_argument('--K', type=int, default=4)
    ap.add_argument('--prompts', choices=['tuned', 'baseline'], default='tuned',
                    help='prompt set (factorial design: run every arm under both)')
    ap.add_argument('--checker', default='http://127.0.0.1:8781')
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--shard', type=int, default=0)
    ap.add_argument('--shards', type=int, default=1)
    a = ap.parse_args()
    from .prompts import ladder
    jobs = validation_jobs() if a.set == 'validation' else test_jobs()
    for j in jobs:
        j['key'] = job_key(j['image_id'], j['task'])
        steps = ladder(j['task'], j['source'], a.prompts)
        if not steps:
            sys.exit(f"No prompts for {j['task']}/{j['source']} in the '{a.prompts}' set yet (sgedit/prompts.py).")
        j['prompt'] = steps[0][0]
    run = RUNS / a.run
    run.mkdir(parents=True, exist_ok=True)
    code = {p.name: sha_file(p) for p in sorted((REPO / 'sgedit').glob('*.py'))}
    lock = {'set': a.set, 'K': a.K, 'prompt_set': a.prompts, 'policy': POLICY, 'code_sha256': code,
            'jobs': [{k: j[k] for k in ('key', 'image_id', 'task', 'source', 'dish')} |
                     {'original_sha256': sha_file(j['original_path']), 'mask_sha256': sha_file(j['mask_path'])} for j in jobs]}
    lp = run / 'LOCK.json'
    policy = json.loads(json.dumps(POLICY))   # as stored in the lock (tuples become lists)
    if lp.exists():
        old = json.loads(lp.read_text())
        if a.set == 'test':
            assert (old['policy'] == policy and old['jobs'] == lock['jobs'] and old['K'] == a.K
                    and old.get('prompt_set', 'tuned') == a.prompts), 'test lock changed'
        elif old['policy'] != policy or old.get('prompt_set', 'tuned') != a.prompts:
            sys.exit('Policy changed: use a new --run name for each validation policy version.')
    else:
        lock['locked_at'] = time.strftime('%Y-%m-%d %H:%M:%S'); lp.write_text(json.dumps(lock, indent=1))
    (run / 'jobs.json').write_text(json.dumps([{k: j[k] for k in ('key', 'image_id', 'task', 'source', 'dish', 'prompt',
                                                                   'original_path', 'mask_path')} for j in jobs], indent=1))
    from .editor import Editor
    runner = Runner(Editor(), CheckerClient(a.checker), run / 'candidates', prompt_set=a.prompts)
    jobs = jobs[a.shard::a.shards][: a.limit or None]
    out = run / f'results_shard{a.shard}.jsonl'
    done = {json.loads(l)['key'] for l in open(out)} if out.exists() else set()   # resume: skip finished jobs
    if done:
        print(f'resuming: {len(done)} of {len(jobs)} jobs already finished', flush=True)
    with open(out, 'a') as log:
        for n, j in enumerate(jobs, 1):
            if j['key'] in done:
                continue
            j['image'], j['mask'] = load(j)
            t = time.perf_counter()
            res = runner.run(j, K=a.K)
            res.update({k: j[k] for k in ('image_id', 'task', 'source', 'dish')}, seconds=round(time.perf_counter() - t, 1))
            log.write(json.dumps(res) + '\n'); log.flush()
            print(f"{n}/{len(jobs)} {j['task']} {j['dish']}: retry used {len(res['retry_steps'])} gen, "
                  f"selected_passed={res['retry_passed']} last_passed={res['retry_last_passed']}  {res['seconds']}s", flush=True)


if __name__ == '__main__':
    main()
