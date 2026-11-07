"""Result metadata for the existing score-based selection policy.

Schema 2 ties retry_passed to the selected retry image. Historical unversioned
rows instead used the last attempted candidate; do not rewrite those records.
This module has no model, network, or filesystem dependencies.
"""

RESULT_SCHEMA_VERSION = 2


def summarize_result(key, K, seed_cands, tried):
    """Select by score (first wins ties), then describe the selected output.

    Stopping status is separate: the last attempt may pass even when an earlier,
    higher-scoring failed candidate is selected. This is not a pass-first policy.
    """
    best_seed = max(seed_cands, key=lambda c: c['score'])
    selected = max(tried, key=lambda c: c['score'])
    return {
        'result_schema_version': RESULT_SCHEMA_VERSION,
        'key': key,
        'K': K,
        'single': seed_cands[0]['tag'],
        'best_check': best_seed['tag'],
        'retry': selected['tag'],
        'retry_steps': [c['tag'] for c in tried],
        'retry_passed': selected['pass'],
        'retry_last_passed': tried[-1]['pass'],
        'seed_tags': [c['tag'] for c in seed_cands],
    }
