"""Check-and-retry editing and the matched-budget comparison arms.

For one (photo, task) job with budget K generations:
  single       the first generation (seed s0, base settings)
  best_clip    best of K seeds at base settings, by CLIP target margin   (picked afterwards by evaluate/clip_select.py)
  best_check   best of K seeds at base settings, by checker score
  retry        sequential: generate, check; stop at the first pass; otherwise change the settings according to the
               failure and try again, up to K generations; return the best-scoring candidate tried
The K seed candidates are generated once and shared by single / best_clip / best_check, and retry reuses the
first one, so every arm sees the same starting point and at most K generations.

POLICY (thresholds, weights, escalation) is fixed on validation photos only and written to the run lock.
Runs in the BrushNet environment; the checker runs as a separate service (sgedit.checker serve) on another GPU.
"""
import json, hashlib, urllib.request
from dataclasses import replace
from pathlib import Path

from .editor import EditSpec
from .prompts import PROMPT_SETS, ladder

POLICY = {
    # v1-val: first validation run (val_v1_20261107). v2-val: prompts, negative prompts and the retry ladder come from
    # sgedit.prompts (v1's T2 retry suffix was silently truncated by CLIP's 77-token limit).
    'version': 'v2-val',            # checker Qwen2.5-VL-7B 4-bit, question set v2
    'pass': {'edit': 1.5, 'preserve': 1.5, 'realism': 3.0, 'extra': 0.5},
    'weights': {'edit': 1.0, 'preserve': 0.5, 'realism': 0.5, 'extra': 0.5},
    'base': {'steps': 20, 'guidance': 7.5, 'mode': 'crop'},
    'escalate_guidance': [10.0, 12.5],
    'prompt_sets': PROMPT_SETS,     # (prompt, negative) per retry step; recorded here so the run lock captures them
    'seeds': [1107, 2207, 3307, 4407, 5507, 6607, 7707, 8807],
}


def score(c, w=None):
    """One number for ranking: edit matters most; preservation, realism and no unrequested additions also count."""
    w = w or POLICY['weights']
    return (w['edit'] * c['edit']['score'] / 2 + w['preserve'] * c['preserve']['score'] / 2
            + w['realism'] * (c['realism']['score'] - 1) / 4 - w['extra'] * c['extra']['score'])


def passes(c, th=None):
    th = th or POLICY['pass']
    return (c['edit']['score'] >= th['edit'] and c['preserve']['score'] >= th['preserve']
            and c['realism']['score'] >= th['realism'] and c['extra']['score'] <= th['extra'])


def failure(c, th=None):
    """The main reason a candidate failed, in priority order."""
    th = th or POLICY['pass']
    if c['edit']['score'] < th['edit']:
        return 'edit'
    if c['extra']['score'] > th['extra']:
        return 'extra'
    if c['realism']['score'] < th['realism']:
        return 'realism'
    if c['preserve']['score'] < th['preserve']:
        return 'preserve'
    return None


def base_spec(task, source, seed, prompt_set='tuned'):
    prompt, neg = ladder(task, source, prompt_set)[0]
    return EditSpec(prompt=prompt, negative_prompt=neg, seed=seed, **POLICY['base'])


def next_spec(spec, task, source, why, n_tried, seeds, prompt_set='tuned'):
    """Change settings according to the failure. Edit not done -> next (prompt, negative) on the task's ladder; once
    the ladder is used up, higher guidance. Unrealistic / unrequested additions / changed surroundings -> new seed
    at base guidance with the current prompt."""
    seed = seeds[n_tried % len(seeds)]
    if why == 'edit':
        steps = ladder(task, source, prompt_set)
        i = next((n for n, (p, neg) in enumerate(steps) if p == spec.prompt and neg == spec.negative_prompt), 0)
        if i + 1 < len(steps):
            prompt, neg = steps[i + 1]
            return replace(spec, prompt=prompt, negative_prompt=neg, seed=seed)
        g_list = [POLICY['base']['guidance']] + POLICY['escalate_guidance']
        return replace(spec, guidance=next((x for x in g_list if x > spec.guidance), g_list[-1]), seed=seed)
    return replace(spec, guidance=POLICY['base']['guidance'], seed=seed)


class CheckerClient:
    def __init__(self, url='http://127.0.0.1:8781'):
        self.url = url

    def check(self, original_path, edited_path, task, source, crop_box):
        body = json.dumps({'original': str(original_path), 'edited': str(edited_path), 'task': task,
                           'source': source, 'crop_box': crop_box}).encode()
        req = urllib.request.Request(self.url, body, {'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=120) as r:
            out = json.loads(r.read())
        if 'error' in out:
            raise RuntimeError(out['error'])
        return out


def job_key(image_id, task):
    return hashlib.sha256(f'{image_id}|{task}'.encode()).hexdigest()[:12]


class Runner:
    """Generates and checks candidates for one job, caching every candidate on disk so runs can resume."""

    def __init__(self, editor, checker, out_dir, check_box_margin=0.25, prompt_set='tuned'):
        self.editor, self.checker, self.out, self.prompt_set = editor, checker, Path(out_dir), prompt_set
        self.margin = check_box_margin

    def candidate(self, job, spec, tag):
        d = self.out / job['key']; d.mkdir(parents=True, exist_ok=True)
        png, meta_p = d / f'{tag}.png', d / f'{tag}.json'
        if meta_p.exists():
            return json.loads(meta_p.read_text())
        img, mask = job['image'], job['mask']
        out, meta = self.editor.edit(img, mask, spec)
        out.save(png)
        from .editor import crop_box
        box = list(crop_box(mask, self.margin, 256, img.size[0]))
        chk = self.checker.check(job['original_path'], png, job['task'], job['source'], box)
        rec = {'tag': tag, 'path': str(png), 'sha256': hashlib.sha256(png.read_bytes()).hexdigest(), 'gen': meta,
               'check': chk, 'score': score(chk), 'pass': passes(chk), 'failure': failure(chk)}
        meta_p.write_text(json.dumps(rec, indent=1))
        return rec

    def run(self, job, K=4):
        base = base_spec(job['task'], job['source'], POLICY['seeds'][0], self.prompt_set)
        seeds = POLICY['seeds']
        seed_cands = [self.candidate(job, replace(base, seed=s), f'seed{i}') for i, s in enumerate(seeds[:K])]
        tried, spec = [seed_cands[0]], base
        while not tried[-1]['pass'] and len(tried) < K:
            spec = next_spec(spec, job['task'], job['source'], tried[-1]['failure'], len(tried), seeds, self.prompt_set)
            tried.append(self.candidate(job, spec, f'retry{len(tried)}'))
        best = lambda cs: max(cs, key=lambda c: c['score'])
        return {'key': job['key'], 'K': K, 'single': seed_cands[0]['tag'], 'best_check': best(seed_cands)['tag'],
                'retry': best(tried)['tag'], 'retry_steps': [c['tag'] for c in tried], 'retry_passed': tried[-1]['pass'],
                'seed_tags': [c['tag'] for c in seed_cands]}
