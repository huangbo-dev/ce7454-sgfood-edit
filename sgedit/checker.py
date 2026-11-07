"""Edit checker: Qwen2.5-VL (default 7B-Instruct, 4-bit; chosen over 3B on validation, see calib/) scores one edited output against its original.

Each criterion is one question whose answer is a single digit; the score is the expectation over the model's
next-token probabilities for the allowed digits (deterministic, continuous, so it can rank candidates).
  edit      0-2  requested change done?           (crops around the edit region, original vs edited)
  preserve  0-2  rest of the meal unchanged?      (full images)
  realism   1-5  realistic food photograph?       (edited crop)
  extra     0-1  anything added that was not asked? (crops)
This model selects candidates; it is deliberately NOT the evaluator (GPT-5.5 judge and people are).

Runs in the CE7454 main environment (sgedit.paths.MAIN_PY), fp16 on a V100.
  python -m sgedit.checker serve --port 8781     # JSON over HTTP on 127.0.0.1
"""
import argparse, json, time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import threading
import torch
from PIL import Image

MODEL = 'Qwen/Qwen2.5-VL-7B-Instruct'
GOALS = {
    'T1-B': 'ADD a few cooked broccoli florets on top of the existing {src}. The {src} must stay visible and recognisable.',
    'T2': 'REPLACE the white rice with cooked whole-grain brown rice: darker, visible bran-coloured grains, no white rice left, '
          'not merely tinted or seasoned white rice.',
}
QUESTIONS = {
    'edit': ('crop', ['0', '1', '2'],
             'Image 1 is the ORIGINAL close-up, image 2 is the EDITED close-up. Requested edit: {goal}\n'
             'Was the requested edit done in image 2? 0 = not done or a different change, 1 = partly done or ambiguous, '
             '2 = clearly and completely done. Answer with one digit.'),
    'preserve': ('full', ['0', '1', '2'],
                 'Image 1 is the ORIGINAL meal photo, image 2 is the EDITED photo. Only the {src} was supposed to change. '
                 'Ignore grey padding bars. Is everything else (other food, plate, table, background) unchanged in image 2? '
                 '0 = major change, 1 = minor change, 2 = unchanged. Answer with one digit.'),
    'realism': ('crop_edited', ['1', '2', '3', '4', '5'],
                'This is a close-up of an edited food photo. How realistic is it as a real food photograph? '
                '1 = clearly fake or broken, 3 = plausible with artefacts, 5 = indistinguishable from a real photo. Answer with one digit.'),
    'extra': ('crop', ['0', '1'],
              'Image 1 is the ORIGINAL close-up, image 2 is the EDITED close-up. Requested edit: {goal}\n'
              'Does image 2 contain anything added that was NOT requested (garnish, other food, utensils, text, a new plate or bowl)? '
              '0 = no, 1 = yes. Answer with one digit.'),
}


# Question set v2: direct perception questions, answered with one letter. Each maps letter probabilities to a score.
# Combination rules: T1 edit = P(broccoli) * (1 + P(staple visible)) on 0-2; T2 edit = 2 P(brown) + P(mix).
QUESTIONS_V2 = {
    'broccoli': ('crop_edited', 'AB', 'Are there cooked broccoli florets on the {src} in this close-up? A = yes, B = no. Answer with one letter.'),
    'staple': ('crop_edited', 'AB', 'Is the {src} still clearly visible in this close-up? A = yes, B = no. Answer with one letter.'),
    'rice_type': ('crop_edited', 'ABCD', 'What kind of rice is shown in this close-up? A = white rice, B = brown whole-grain rice, '
                  'C = a mix of white and brown rice, D = no rice visible. Answer with one letter.'),
    'pasted': ('crop_edited', 'AB', 'Does this close-up contain something that looks pasted in, such as a separate bowl or plate, a rectangular '
               'patch, or text? A = yes, B = no. Answer with one letter.'),
    'real': ('crop_edited', 'AB', 'Does this look like a real, natural food photograph (A), or fake, smeared or broken (B)? Answer with one letter.'),
}


class Checker:
    def __init__(self, device='cuda', max_side=640, qset='v2', model=MODEL, quant4=True):
        from transformers import Qwen2_5_VLForConditionalGeneration, AutoProcessor, BitsAndBytesConfig
        kw = {'torch_dtype': torch.float16, 'attn_implementation': 'sdpa'}
        if quant4:  # 7B in 4-bit NF4 fits a 16 GB V100 next to nothing else (~6 GB)
            kw['quantization_config'] = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type='nf4',
                                                           bnb_4bit_compute_dtype=torch.float16)
            kw['device_map'] = {'': 0}
            self.model = Qwen2_5_VLForConditionalGeneration.from_pretrained(model, **kw).eval()
        else:
            self.model = Qwen2_5_VLForConditionalGeneration.from_pretrained(model, **kw).to(device).eval()
        self.proc = AutoProcessor.from_pretrained(model)
        self.model_name, self.quant4 = model, quant4
        self.device, self.max_side = device, max_side
        tok = self.proc.tokenizer
        self.digit_ids = {d: tok.convert_tokens_to_ids(d) for d in '012345ABCD'}
        self.qset = qset
        self.lock = threading.Lock()

    def _fit(self, im):
        im = im.convert('RGB')
        s = self.max_side / max(im.size)
        return im.resize((max(28, round(im.width * s)), max(28, round(im.height * s))), Image.BICUBIC) if s < 1 else im

    @torch.inference_mode()
    def _ask(self, images, text, allowed):
        content = [{'type': 'image'} for _ in images] + [{'type': 'text', 'text': text}]
        msgs = [{'role': 'user', 'content': content}]
        prompt = self.proc.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        inp = self.proc(text=[prompt], images=[self._fit(i) for i in images], return_tensors='pt').to(self.device)
        logits = self.model(**inp).logits[0, -1].float()
        ids = [self.digit_ids[a] for a in allowed]
        p = torch.softmax(logits[ids], 0)
        if not torch.isfinite(p).all():
            raise FloatingPointError('non-finite checker logits')
        mass = torch.softmax(logits, 0)[ids].sum().item()   # how much probability went to valid answers
        return {'score': float(sum(int(a) * q for a, q in zip(allowed, p.tolist()))) if allowed[0].isdigit() else None,
                'probs': dict(zip(allowed, [round(x, 4) for x in p.tolist()])), 'valid_mass': round(mass, 4)}

    def check(self, original, edited, task, source='rice', crop_box=None):
        """original, edited: PIL images of the same canvas; crop_box: (x0, y0, x1, y1) around the edit region."""
        goal = GOALS[task].format(src=source)
        oc, ec = (original.crop(crop_box), edited.crop(crop_box)) if crop_box else (original, edited)
        views = {'crop': [oc, ec], 'full': [original, edited], 'crop_edited': [ec]}
        out, t = {}, time.perf_counter()
        with self.lock:
            if self.qset == 'v1':
                for k, (view, allowed, q) in QUESTIONS.items():
                    out[k] = self._ask(views[view], q.format(goal=goal, src=source), allowed)
            else:
                names = (['broccoli', 'staple'] if task == 'T1-B' else ['rice_type']) + ['pasted', 'real']
                raw = {n: self._ask(views[QUESTIONS_V2[n][0]], QUESTIONS_V2[n][2].format(src=source), QUESTIONS_V2[n][1])
                       for n in names}
                P = {n: r['probs'] for n, r in raw.items()}
                edit = (P['broccoli']['A'] * (1 + P['staple']['A']) if task == 'T1-B'
                        else 2 * P['rice_type']['B'] + P['rice_type']['C'])
                pv = QUESTIONS['preserve']
                out['preserve'] = self._ask(views[pv[0]], pv[2].format(goal=goal, src=source), pv[1])
                out['edit'] = {'score': edit}
                out['extra'] = {'score': P['pasted']['A']}
                out['realism'] = {'score': 1 + 4 * P['real']['A']}
                out['raw'] = raw
                for k in ('edit', 'extra', 'realism'):
                    out[k]['valid_mass'] = min(r['valid_mass'] for r in raw.values())
        out['seconds'] = round(time.perf_counter() - t, 2)
        out['qset'] = self.qset
        out['model'] = self.model_name + (' (4-bit)' if self.quant4 else '')
        return out


def serve(port, model, quant4):
    ck = Checker(model=model, quant4=quant4)
    print(f'checker ready on 127.0.0.1:{port}', flush=True)

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            n = int(self.headers.get('Content-Length') or 0)
            d = json.loads(self.rfile.read(n))
            try:
                r = ck.check(Image.open(d['original']), Image.open(d['edited']), d['task'], d.get('source', 'rice'),
                             tuple(d['crop_box']) if d.get('crop_box') else None)
                body, code = json.dumps(r).encode(), 200
            except Exception as e:  # report, don't crash the service
                body, code = json.dumps({'error': f'{type(e).__name__}: {e}'}).encode(), 500
            self.send_response(code); self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)

    ThreadingHTTPServer(('127.0.0.1', port), H).serve_forever()


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('serve'); s.add_argument('--port', type=int, default=8781)
    s.add_argument('--model', default=MODEL); s.add_argument('--no-quant4', action='store_true')
    a = ap.parse_args()
    serve(a.port, a.model, not a.no_quant4)
