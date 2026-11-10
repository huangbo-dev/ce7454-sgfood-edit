"""Offline per-output endpoint from the unchanged CE7454 pre-test protocol.

No aggregation, exclusions, missing-value imputation, or inference is performed.
This module never reads the private method mapping or author response database.
"""

NUMERIC_SCALES = {
    'edit': {0, 1, 2},
    'preserve': {0, 1, 2},
    'realism': {1, 2, 3, 4, 5},
    'extra': {0, 1},
}


def joint_success(rating):
    """Return bool for complete ratings; None if any explicit Unsure occurs.

Missing/malformed fields are errors, not inferred scores. This preserves the
distinction between incomplete collection and a visible-quality failure.
    """
    if not isinstance(rating, dict) or set(rating) != set(NUMERIC_SCALES):
        raise ValueError('All four per-output rubric fields are required.')
    for field, scale in NUMERIC_SCALES.items():
        value = rating[field]
        if value == 'unclear':
            continue
        if type(value) is not int or value not in scale:
            raise ValueError(f'Invalid {field} rating.')
    if 'unclear' in rating.values():
        return None
    return (rating['edit'] == 2 and rating['preserve'] == 2
            and rating['realism'] >= 3 and rating['extra'] == 0)
