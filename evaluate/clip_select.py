"""Best-of-K by CLIP margin: the cheap-selector arm.

For every job of a run, scores the K seed candidates with CLIP ViT-L/14 on a crop around the mask and picks the one
with the largest margin = sim(target text) - max sim(confuser texts). Text banks (labels x prompt templates, averaged)
are the baseline's frozen banks, $SGEDIT_BASELINE/experiment/config/text_banks/<task>_<source>_main.json, so the
selector is fixed before any CE7454 run. Writes $SGEDIT_WORK/runs/<run>/clip_select.jsonl, read by judge_arms.py.

  CUDA_VISIBLE_DEVICES=0 python evaluate/clip_select.py --run <run>      # checker environment
"""
import argparse, json, sys
from pathlib import Path
import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sgedit.paths import RUNS, PLATEEDIT  # noqa: E402
from sgedit.editor import crop_box  # noqa: E402  (same view as the checker)

MODEL = 'openai/clip-vit-large-patch14'
BANKS = PLATEEDIT / 'experiment/config/text_banks'


class Clip:
    def __init__(self, device='cuda'):
        from transformers import CLIPModel, CLIPProcessor
        snaps = sorted((PLATEEDIT / 'work/cache/hf/models--openai--clip-vit-large-patch14/snapshots').glob('*'))
        src = str(snaps[-1]) if snaps else MODEL     # the baseline's local copy, else the Hugging Face id
        self.model = CLIPModel.from_pretrained(src).float().to(device).eval()
        self.proc = CLIPProcessor.from_pretrained(src)
        self.device, self.size, self.text = device, self.model.config.vision_config.image_size, {}

    @torch.inference_mode()
    def bank(self, task, source):
        k = (task, source)
        if k not in self.text:
            b = json.load(open(BANKS / f'{task}_{source}_main.json'))
            inp = self.proc.tokenizer(b['strings'], padding=True, return_tensors='pt').to(self.device)
            t = F.normalize(self.model.get_text_features(**inp), dim=-1)
            t = F.normalize(t.reshape(len(b['labels']), -1, t.shape[-1]).mean(1), dim=-1)
            self.text[k] = (t, b['labels'])
        return self.text[k]

    @torch.inference_mode()
    def margin(self, img, box, task, source):
        im = img.convert('RGB').crop(box)
        s = max(im.size); sq = Image.new('RGB', (s, s), (127, 127, 127)); sq.paste(im, ((s - im.width) // 2, (s - im.height) // 2))
        px = self.proc.image_processor(images=sq.resize((self.size, self.size), Image.BICUBIC), do_resize=False,
                                       do_center_crop=False, return_tensors='pt').pixel_values.to(self.device)
        f = F.normalize(self.model.get_image_features(pixel_values=px), dim=-1)
        t, _ = self.bank(task, source)
        v = (f @ t.T)[0].tolist()
        return v[0] - max(v[1:])


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--run', required=True)
    a = ap.parse_args()
    R = RUNS / a.run
    jobs = {j['key']: j for j in json.loads((R / 'jobs.json').read_text())}
    res = [json.loads(l) for f in sorted(R.glob('results_shard*.jsonl')) for l in open(f)]
    clip = Clip()
    with open(R / 'clip_select.jsonl', 'w') as out:
        for r in res:
            j = jobs[r['key']]
            m = np.asarray(Image.open(j['mask_path'])) > 0
            m = m[..., 0] if m.ndim == 3 else m
            box = crop_box(m, 0.25, 256, m.shape[0])
            margins = {}
            for tag in r['seed_tags']:
                c = json.loads((R / 'candidates' / r['key'] / f'{tag}.json').read_text())
                margins[tag] = round(clip.margin(Image.open(c['path']), box, r['task'], r['source']), 5)
            out.write(json.dumps({'key': r['key'], 'best_clip': max(margins, key=margins.get), 'margins': margins}) + '\n')
    print(f'{len(res)} jobs scored -> {R / "clip_select.jsonl"}')


if __name__ == '__main__':
    main()
