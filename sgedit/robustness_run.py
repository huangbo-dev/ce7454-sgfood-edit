"""Fixed shared-photo robustness experiment. Not a primary held-out test."""
import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path
import sys
import time

PURPOSE = 'shared_photo_robustness_not_primary_heldout'


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def validate_inputs(path, work, expected_photos=20, expected_jobs=34):
    work = Path(work).resolve()
    data = json.loads(Path(path).read_text())
    if data.get('study_type') != PURPOSE:
        raise ValueError('Explicit shared-photo/non-held-out classification required')
    photos = data.get('photos', [])
    if len(photos) != expected_photos or len({p['image_id'] for p in photos}) != expected_photos:
        raise ValueError('Photo cohort count/identity changed')
    jobs = []
    for p in photos:
        if p.get('source') not in ('rice', 'noodles') or p.get('mask_qa') not in ('accept', 'needs-review'):
            raise ValueError('Missing source or prior mask QA status')
        resolved = {}
        for key, hash_key in [('original_path', 'image_sha256'), ('mask_path', 'mask_sha256')]:
            rel = Path(p[key])
            if rel.is_absolute() or '..' in rel.parts:
                raise ValueError('Input path must stay within work directory')
            target = (work / rel).resolve()
            if work not in target.parents or digest(target) != p[hash_key]:
                raise ValueError('Input hash/path mismatch: ' + p['image_id'])
            resolved[key] = str(target)
        for task in (['T1-B', 'T2'] if p['source'] == 'rice' else ['T1-B']):
            jobs.append(dict(image_id=p['image_id'], dish=p['dish'], source=p['source'],
                             task=task, mask_qa=p['mask_qa'], **resolved))
    if len(jobs) != expected_jobs:
        raise ValueError('Edit-case count changed')
    return data, jobs


def validate_geometry(image_size, mask_size, values):
    if tuple(image_size) != (1024, 1024) or tuple(mask_size) != (1024, 1024):
        raise ValueError('Original and mask must be matching 1024-square canvases')
    values = set(values)
    if values not in ({0, 255}, {0, 1}):
        raise ValueError('Mask must be binary, nonempty, and not the entire canvas')


def write_new_json(path, value):
    with Path(path).open('x') as f:
        json.dump(value, f, indent=2)
        f.write('\n')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--manifest', type=Path, required=True)
    ap.add_argument('--model-audit', type=Path, required=True)
    ap.add_argument('--run', required=True)
    ap.add_argument('--preflight-only', action='store_true')
    a = ap.parse_args()
    from .paths import WORK, RUNS, REPO
    data, jobs = validate_inputs(a.manifest, WORK)
    qa = {q: sum(p['mask_qa'] == q for p in data['photos']) for q in ('accept', 'needs-review')}
    if qa != {'accept': 13, 'needs-review': 7}:
        raise ValueError('Keep all 20 and the original 13/7 QA split')
    import numpy as np
    from PIL import Image
    for j in jobs:
        with Image.open(j['original_path']) as im, Image.open(j['mask_path']) as ma:
            mask = np.asarray(ma)
            if mask.ndim == 3:
                if mask.shape[2] not in (3, 4) or not np.all(mask[..., :3] == mask[..., :1]):
                    raise ValueError('Mask has nonbinary color channels')
                mask = mask[..., 0]
            validate_geometry(im.size, ma.size, np.unique(mask).tolist())
    model_audit = json.loads(a.model_audit.read_text())
    if not model_audit.get('files'):
        raise ValueError('Model/runtime audit is empty')
    for item in model_audit['files']:
        if digest(item['path']) != item['sha256']:
            raise ValueError('Model file hash changed')
    if a.preflight_only:
        print(json.dumps({'study_type': PURPOSE, 'photos': 20, 'jobs': len(jobs), 'mask_qa': qa,
                          'model_files_verified': len(model_audit['files']), 'generation_started': False}, indent=2))
        return
    if not a.run or Path(a.run).name != a.run or a.run in ('.', '..'):
        raise ValueError('Run name must be a simple new directory name')
    required_env = {'CUDA_VISIBLE_DEVICES': '0', 'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1'}
    if any(os.environ.get(k) != v for k, v in required_env.items()):
        raise ValueError('Launch requires GPU 0 and offline cached-model mode')
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=REPO, text=True).strip():
        raise ValueError('Commit and review the code before freezing this run')
    git_commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip()
    from .loop import Runner, CheckerClient, POLICY, job_key
    from .prompts import ladder
    root = RUNS / a.run
    root.mkdir(exist_ok=False)
    protocol = REPO / 'plan' / 'SHARED_PHOTO_ROBUSTNESS_20261108.md'
    code = {p.name: digest(p) for p in sorted((REPO / 'sgedit').glob('*.py'))}
    # Freeze BOTH prompt conditions before any generated output is observed.
    for prompt_set in ('baseline', 'tuned'):
        run = root / prompt_set
        run.mkdir()
        write_new_json(run / 'LOCK.json', dict(study_type=PURPOSE, K=4, prompt_set=prompt_set,
            locked_at=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), policy=POLICY,
            manifest_sha256=digest(a.manifest), model_audit_sha256=digest(a.model_audit),
            protocol_sha256=digest(protocol), code_sha256=code, git_commit=git_commit, jobs=jobs,
            python=sys.executable, cuda_visible_devices=os.environ.get('CUDA_VISIBLE_DEVICES'),
            checker='http://127.0.0.1:8781', prior_mask_qa=qa))
    from .editor import Editor
    editor = Editor()
    for prompt_set in ('baseline', 'tuned'):
        run = root / prompt_set
        runner = Runner(editor, CheckerClient('http://127.0.0.1:8781'), run / 'candidates', prompt_set=prompt_set)
        with (run / 'results.jsonl').open('x') as log:
            for i, source_job in enumerate(jobs, 1):
                j = dict(source_job)
                j['key'] = job_key(j['image_id'], j['task'])
                j['prompt'] = ladder(j['task'], j['source'], prompt_set)[0][0]
                j['image'] = Image.open(j['original_path']).convert('RGB')
                mask = np.asarray(Image.open(j['mask_path']))
                j['mask'] = (mask[..., 0] if mask.ndim == 3 else mask) > 0
                t = time.perf_counter()
                try:
                    result = runner.run(j, K=4)
                except Exception as exc:
                    write_new_json(run / 'FAILURE.json', dict(key=j['key'], error=repr(exc),
                        seconds=round(time.perf_counter()-t, 1), finished_jobs=i-1,
                        note='Incomplete run; preserve all inputs and partial outputs. No automatic retry or exclusions.'))
                    raise
                result.update(source_job, study_type=PURPOSE, seconds=round(time.perf_counter()-t, 1))
                log.write(json.dumps(result) + '\n'); log.flush()
                print(f"{prompt_set} {i}/{len(jobs)} {j['key']} qa={j['mask_qa']} selected_pass={result['retry_passed']} last_pass={result['retry_last_passed']} seconds={result['seconds']}", flush=True)
        write_new_json(run / 'COMPLETE.json', dict(completed_jobs=len(jobs), results_sha256=digest(run / 'results.jsonl')))
    write_new_json(root / 'COMPLETE.json', dict(conditions=['baseline', 'tuned'], jobs_per_condition=len(jobs), study_type=PURPOSE))


if __name__ == '__main__':
    main()
