"""GPT judge for blinded pairwise comparisons of edits (the evaluator; never used for selection).

An items folder holds items.json (original + outputs A/B per item), rubric.json and media/. Folders are built by
evaluate/judge_arms.py (comparison arms of a run) and calib/build_items.py (checker calibration).
Every item is judged twice, with the two outputs in both orders, to measure and cancel position bias.
Answers are cached in <items>/judge_out/<model>/<item>_<order>.json, so the script can be stopped and resumed.

Key: OPENAI_API_KEY, or the first line of $SGEDIT_OPENAI_KEYFILE [~/.config/plateedit/openai.key] (chmod 600).

  python evaluate/judge.py --list-models
  python evaluate/judge.py --items-dir <folder> --model <id> --limit 2   # pilot on 2 items (4 calls)
  python evaluate/judge.py --items-dir <folder> --model <id>
"""
import argparse, base64, json, os, sys, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

KEYFILE = Path(os.environ.get('SGEDIT_OPENAI_KEYFILE', Path.home() / '.config/plateedit/openai.key'))
DIR, ITEMS, RUBRIC, SYSTEM = None, None, None, None   # set by load()

SIDE = {
    'type': 'object', 'additionalProperties': False,
    'required': ['observations', 'edit', 'preserve', 'realism', 'extra'],
    'properties': {
        'observations': {'type': 'string', 'description': 'One or two sentences on what changed versus the original.'},
        'edit': {'type': 'integer', 'enum': [0, 1, 2]},
        'preserve': {'type': 'integer', 'enum': [0, 1, 2]},
        'realism': {'type': 'integer', 'enum': [1, 2, 3, 4, 5]},
        'extra': {'type': 'integer', 'enum': [0, 1]},
    },
}
SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'required': ['output_1', 'output_2', 'preference'],
    'properties': {'output_1': SIDE, 'output_2': SIDE, 'preference': {'type': 'string', 'enum': ['1', '2', 'tie']}},
}


def load(items_dir):
    global DIR, ITEMS, RUBRIC, SYSTEM
    DIR = Path(items_dir)
    ITEMS = json.load(open(DIR / 'items.json'))
    RUBRIC = json.load(open(DIR / 'rubric.json'))
    SYSTEM = rubric_text()


def rubric_text():
    lines = ['You are a careful, strict rater of food-image edits. You will see an ORIGINAL meal photo and two EDITED outputs.',
             'Rate each output independently on the four criteria, then give an overall preference.', '', 'Criteria:']
    for k, spec in RUBRIC['per_output'].items():
        lines.append(f'- {k}: {spec["question"]}')
        lines += [f'    {v}: {d}' for v, d in spec['scale'].items()]
    lines.append(f'- preference: {RUBRIC["preference"]["question"]} Answer "1", "2" or "tie".')
    lines += ['', 'Rules:'] + [f'- {r}' for r in RUBRIC['rules']]
    lines.append('- Compare each output against the ORIGINAL, region by region, before scoring.')
    return '\n'.join(lines)



def img(name):
    b = base64.b64encode((DIR / 'media' / name).read_bytes()).decode()
    return {'type': 'image_url', 'image_url': {'url': f'data:image/jpeg;base64,{b}', 'detail': 'high'}}


def messages(item, order):
    first, second = (item['A'], item['B']) if order == 'AB' else (item['B'], item['A'])
    user = [
        {'type': 'text', 'text': f'Task goal: {RUBRIC["task_goals"][item["task"]]}\n'
                                 + (f'Instruction given to the editor: {item["instruction"]}\n' if item.get('instruction') else '')
                                 + '\nORIGINAL:'},
        img(item['original']),
        {'type': 'text', 'text': 'OUTPUT 1:'}, img(first),
        {'type': 'text', 'text': 'OUTPUT 2:'}, img(second),
        {'type': 'text', 'text': 'Return the JSON rating.'},
    ]
    return [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': user}]


def to_canonical(ans, order):
    """Map 'output_1/2' answers back to the blinded A/B labels used by human raters."""
    one, two = ('A', 'B') if order == 'AB' else ('B', 'A')
    pref = {'1': one, '2': two, 'tie': 'tie'}[ans['preference']]
    return {one: ans['output_1'], two: ans['output_2'], 'preference': pref}


def client():
    from openai import OpenAI
    key = os.environ.get('OPENAI_API_KEY') or (KEYFILE.read_text().split()[0] if KEYFILE.exists() else None)
    if not key:
        sys.exit(f'No API key: set OPENAI_API_KEY or write it to {KEYFILE} (chmod 600).')
    return OpenAI(api_key=key, max_retries=5, timeout=180)


def judge_one(c, model, item, order, outdir, lock, usage):
    out = outdir / f'{item["id"]}_{order}.json'
    if out.exists():
        return 'cached'
    t = time.time()
    kw = dict(model=model, messages=messages(item, order),
              response_format={'type': 'json_schema', 'json_schema': {'name': 'rating', 'strict': True, 'schema': SCHEMA}})
    sampling = {'temperature': 0, 'seed': 20261106}
    try:
        r = c.chat.completions.create(**kw, **sampling)
    except Exception as e:  # reasoning models only accept the default temperature
        if 'temperature' not in str(e):
            raise
        sampling = {'temperature': 'default'}
        r = c.chat.completions.create(**kw)
    raw = json.loads(r.choices[0].message.content)
    rec = {'item': item['id'], 'order': order, 'model': model, 'model_returned': r.model, 'sampling': sampling,
           'rubric_sha256': ITEMS['rubric_sha256'], 'raw': raw, 'canonical': to_canonical(raw, order),
           'usage': {'prompt': r.usage.prompt_tokens, 'completion': r.usage.completion_tokens},
           'seconds': round(time.time() - t, 2), 'ts': time.time()}
    out.write_text(json.dumps(rec, indent=1))
    with lock:
        usage[0] += r.usage.prompt_tokens
        usage[1] += r.usage.completion_tokens
    return 'new'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--items-dir', help='folder with items.json, rubric.json and media/')
    ap.add_argument('--model')
    ap.add_argument('--limit', type=int, default=0, help='only the first N items (pilot)')
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--list-models', action='store_true')
    a = ap.parse_args()
    c = client()
    if a.list_models:
        for m in sorted(m.id for m in c.models.list().data):
            print(m)
        return
    if not (a.model and a.items_dir):
        sys.exit('--items-dir and --model are required (see --list-models)')
    load(a.items_dir)
    outdir = DIR / 'judge_out' / a.model.replace('/', '_')
    outdir.mkdir(parents=True, exist_ok=True)
    items = ITEMS['items'][:a.limit] if a.limit else ITEMS['items']
    jobs = [(i, o) for i in items for o in ('AB', 'BA')]
    lock, usage, stats = threading.Lock(), [0, 0], {'new': 0, 'cached': 0, 'error': 0}
    with ThreadPoolExecutor(a.workers) as ex:
        fut = {ex.submit(judge_one, c, a.model, i, o, outdir, lock, usage): (i['id'], o) for i, o in jobs}
        for k, f in enumerate(as_completed(fut), 1):
            try:
                stats[f.result()] += 1
            except Exception as e:
                stats['error'] += 1
                print(f'  error {fut[f]}: {type(e).__name__}: {str(e)[:200]}', flush=True)
            if k % 10 == 0 or k == len(jobs):
                print(f'  {k}/{len(jobs)} {stats} tokens in/out {usage[0]}/{usage[1]}', flush=True)
    print(f'done: {stats}; output in {outdir}')


if __name__ == '__main__':
    main()
