"""CE7454 edit prompts: base prompt, negative prompt and retry ladder per task.

Why this file exists (validation finding, 7 Nov 2026, val_v1 run):
  * SDXL's two CLIP text encoders read at most 77 tokens (incl. start/end). The baseline T2 prompt is 61 tokens, so
    v1's retry suffix (+20) was cut off and every "stronger prompt" retry was the base prompt at higher guidance.
  * CLIP does not understand negation. The baseline T2 prompt says "white rice" three times ("remove the white rice",
    "do not ... leave white rice"), which pulls the output towards white rice: v1 produced grey, washed-out rice.
  * "Keep the plate, table, background ..." spends tokens on regions the mask already protects.
So T2 prompts are short and positive, and what to avoid goes in the negative prompt. The T2 prompt ladder was chosen
by sgedit.prompt_search on the 15 validation (baseline development) rice photos only; rounds and scores are in $SGEDIT_WORK/runs/promptsearch_T2/ and plan/PLAN.md.

T1-B keeps the baseline prompt verbatim (reused, 41 tokens) so the broccoli task stays comparable.
"""
import json
from .paths import BASE_PROMPTS

MAX_TOKENS = 77  # CLIP context length for both SDXL tokenizers, including start and end tokens

_base = json.load(open(BASE_PROMPTS))

# What brown rice must not become (seen on validation): CLIP pulls "brown rice" towards red/purple/wild rice or beans.
_NEG_T2 = 'white rice, red rice, purple rice, black rice, wild rice, beans, sesame, grey, burnt, blurry, cartoon'

# Each ladder entry is (prompt, negative_prompt). Entry 0 is the base prompt used by every arm (single, best-of-K);
# check-and-retry moves to the next entry when the checker says the edit was not done.
LADDERS = {
    'T1-B': {
        src: [
            (_base[f'T1-B_{src}'], None),
            (f'Food photograph. Clearly visible bright green cooked broccoli florets sitting on top of the {src}; '
             f'the {src} remains visible around them.', 'blurry, cartoon, extra plate, bowl, utensils'),
        ] for src in ('rice', 'noodles')
    },
    'T2': {
        # Prompt search on the 15 validation rice photos x 2 seeds (checker "edit done" pass rate; baseline prompt 7 %).
        # Round 1: r1_hawker best (97 %, 1 % red/purple); round 2 refinements all worse (longer negative 83 %,
        # "warm golden" 87 %, guidance 6: 73 %, "steamed, fluffy" 47 %). Retry steps use the next-best wordings.
        'rice': [
            ('Singapore hawker meal photo, plate of cooked brown rice, light brown whole grain rice, beige and tan grains',
             _NEG_T2),                                                                           # r1_hawker, 97 %
            ('Singapore hawker meal photo, plate of cooked brown rice, light brown whole grain rice, warm golden '
             'beige and tan grains', _NEG_T2),                                                   # r2_warm (round-2 wording, original negative)
            ('food photograph, a mound of cooked brown rice, light brown beige grains, unpolished whole grain rice, '
             'soft natural light', _NEG_T2),                                                     # r1_tan, 80 %
        ],
    },
}

# Prompt sets for the factorial design (prompt x arm). 'baseline' is the PlateEdit baseline wording: T2 uses the
# original 61-token instruction with no negative prompt, so "edit not done" retries can only raise guidance.
PROMPT_SETS = {
    'tuned': LADDERS,
    'baseline': {'T1-B': LADDERS['T1-B'], 'T2': {'rice': [(_base['T2_rice'], None)]}},
}


def ladder(task, source, prompt_set='tuned'):
    return PROMPT_SETS[prompt_set][task][source]


def token_lengths(text, tokenizers):
    return [len(t(text).input_ids) for t in tokenizers]


def assert_fits(text, tokenizers, what='prompt'):
    """Fail loudly instead of letting CLIP silently drop the end of a prompt."""
    if text is None:
        return
    n = max(token_lengths(text, tokenizers))
    if n > MAX_TOKENS:
        raise ValueError(f'{what} is {n} tokens (> {MAX_TOKENS}); CLIP would truncate it: {text!r}')


def check_all(tokenizers):
    for name, ladders in PROMPT_SETS.items():
        for task, by_src in ladders.items():
            for src, steps in by_src.items():
                for i, (p, neg) in enumerate(steps):
                    assert_fits(p, tokenizers, f'{name}:{task}/{src} ladder[{i}] prompt')
                    assert_fits(neg, tokenizers, f'{name}:{task}/{src} ladder[{i}] negative')
