"""Offline analysis of the categorical author-annotation portal exports.

Matches the live portal format (version ``ce7454-public-categorical-v1-*``):
34 paired items, sides A/B, three questions answered Yes / No / Unsure.
This is NOT the earlier numeric four-field endpoint; use
``study/author_analysis`` for that format only.

Written before any real response existed. Reads exports, never the live
database. Writes aggregates only: no reviewer identities, notes or raw answers.
Authors are non-naive annotators; nothing here is a user study, held-out
performance, nutrition evidence or health evidence.
"""
import argparse
import hashlib
import itertools
import json
import random
import sys
from pathlib import Path

QUESTIONS = ('Change achieved', 'Other food preserved', 'Looks plausible')
CHOICES = ('Yes', 'No', 'Unsure')
METHODS = ('retry', 'best_check')
REPLICATES = 10000
SEED = 7454
JOINT = 'joint'
ENDPOINT = ('Per rater and output: success if all three answers are Yes, failure if any '
            'answer is No, otherwise unknown. Unknown is never imputed.')


def require(test, message):
    if not test:
        raise ValueError(message)


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def load_package(directory):
    directory = Path(directory)
    public = read_json(directory / 'public_manifest.json')
    private = read_json(directory / 'private_map.json')
    validate_design(public, private)
    return public, private


def validate_design(public, private):
    version = public.get('version')
    require(isinstance(version, str) and version and version == private.get('version'),
            'Study versions do not match.')
    require(tuple(public.get('questions', ())) == QUESTIONS, 'Unexpected question set.')
    ids = [item['id'] for item in public['items']]
    require(len(set(ids)) == len(ids) and set(ids) == set(private['items']),
            'Public items and private mapping differ.')
    for row in private['items'].values():
        require({row['A'], row['B']} == set(METHODS), 'Each item must pair retry with best_check.')
        require(set(row['selected']) == set(METHODS), 'Selected outputs missing.')
        same = row['selected']['retry']['sha256'] == row['selected']['best_check']['sha256']
        require(same == bool(row['identical_outputs']), 'Identical-output flag disagrees with hashes.')


def latest_ratings(export, public):
    """Latest submitted rating per item for one reviewer, plus familiarity."""
    require(export.get('version') == public['version'], 'Export uses the wrong study version.')
    items = {item['id'] for item in public['items']}
    latest, familiarity = {}, None
    for event in sorted(export['events'], key=lambda e: e['seq']):
        if event['kind'] == 'familiarity':
            familiarity = event['payload']['prior_familiarity']
        elif event['kind'] == 'rating':
            require(event['item_id'] in items, 'Rating for an unknown item.')
            payload = event['payload']
            require(set(payload) == {'A', 'B'}, 'Malformed rating payload.')
            for side in ('A', 'B'):
                require(all(payload[side].get(q) in CHOICES for q in QUESTIONS),
                        'Malformed or missing answer.')
            previous = latest.get(event['item_id'])
            if previous is None or event['revision'] > previous['revision']:
                latest[event['item_id']] = event
    return {item: event['payload'] for item, event in latest.items()}, familiarity


def load_exports(paths, public):
    seen, reviewers = set(), []
    for path in paths:
        export = read_json(path)
        reviewer = export.get('reviewer_id')
        require(isinstance(reviewer, str) and reviewer not in seen, 'Missing or duplicated reviewer export.')
        seen.add(reviewer)
        ratings, familiarity = latest_ratings(export, public)
        reviewers.append((reviewer, ratings, familiarity))
    reviewers.sort(key=lambda row: row[0])
    return [{'label': f'R{i + 1}', 'ratings': ratings, 'familiarity': familiarity}
            for i, (_, ratings, familiarity) in enumerate(reviewers)]


def joint(answers):
    values = [answers[q] for q in QUESTIONS]
    if 'No' in values:
        return False
    if all(v == 'Yes' for v in values):
        return True
    return None


def outcome(answers, endpoint):
    if endpoint == JOINT:
        return joint(answers)
    return {'Yes': True, 'No': False, 'Unsure': None}[answers[endpoint]]


def coverage(public, reviewers):
    total = len(public['items'])
    rows = []
    for reviewer in reviewers:
        unsure = sum(side[q] == 'Unsure' for payload in reviewer['ratings'].values()
                     for side in (payload['A'], payload['B']) for q in QUESTIONS)
        rows.append({'reviewer': reviewer['label'], 'items_rated': len(reviewer['ratings']),
                     'items_total': total, 'unsure_answers': unsure,
                     'prior_familiarity': reviewer['familiarity']})
    per_item = [sum(item['id'] in r['ratings'] for r in reviewers) for item in public['items']]
    return {'reviewers': rows,
            'items_with_all_reviewers': sum(n == len(reviewers) for n in per_item) if reviewers else 0,
            'items_with_no_reviewer': sum(n == 0 for n in per_item)}


def case_rows(public, private, reviewers, endpoint):
    """One row per item: mean known outcome per method across raters."""
    rows = []
    for item in public['items']:
        mapping = private['items'][item['id']]
        known = {method: [] for method in METHODS}
        unknown = {method: 0 for method in METHODS}
        for reviewer in reviewers:
            payload = reviewer['ratings'].get(item['id'])
            if payload is None:
                continue
            for side in ('A', 'B'):
                value = outcome(payload[side], endpoint)
                if value is None:
                    unknown[mapping[side]] += 1
                else:
                    known[mapping[side]].append(1.0 if value else 0.0)
        means = {m: (sum(v) / len(v) if v else None) for m, v in known.items()}
        diff = (means['retry'] - means['best_check']
                if None not in means.values() else None)
        rows.append({'item': item['id'], 'photo': mapping['photo_id'], 'task': mapping['task'],
                     'identical': bool(mapping['identical_outputs']), 'means': means,
                     'known': {m: len(v) for m, v in known.items()}, 'successes': {m: sum(v) for m, v in known.items()},
                     'unknown': unknown, 'difference': diff})
    return rows


def mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def percentile(values, q):
    values = sorted(values)
    if not values:
        return None
    position = (len(values) - 1) * q
    low = int(position)
    high = min(low + 1, len(values) - 1)
    return values[low] + (values[high] - values[low]) * (position - low)


def cluster_interval(rows, replicates=REPLICATES, seed=SEED):
    """95% percentile interval for the mean paired difference, resampling photos."""
    by_photo = {}
    for row in rows:
        if row['difference'] is not None:
            by_photo.setdefault(row['photo'], []).append(row['difference'])
    photos = sorted(by_photo)
    if len(photos) < 2:
        return None
    rng = random.Random(seed)
    draws = []
    for _ in range(replicates):
        sample = [d for _ in photos for d in by_photo[rng.choice(photos)]]
        draws.append(sum(sample) / len(sample))
    return [percentile(draws, .025), percentile(draws, .975)]


def summarize(rows):
    differences = [r['difference'] for r in rows if r['difference'] is not None]
    summary = {'cases': len(rows), 'cases_with_paired_difference': len(differences),
               'photo_clusters': len({r['photo'] for r in rows if r['difference'] is not None}),
               'mean_rate': {m: mean(r['means'][m] for r in rows) for m in METHODS},
               'mean_paired_difference_retry_minus_best_check': mean(differences),
               'interval_95_photo_cluster': cluster_interval(rows),
               'cases_retry_higher': sum(d > 0 for d in differences),
               'cases_best_check_higher': sum(d < 0 for d in differences),
               'cases_equal': sum(d == 0 for d in differences)}
    return summary


def bounds(rows):
    """Pooled rater-output success range if every unknown were a failure or a success."""
    result = {}
    for method in METHODS:
        success = sum(r['successes'][method] for r in rows)
        known = sum(r['known'][method] for r in rows)
        unknown = sum(r['unknown'][method] for r in rows)
        total = known + unknown
        result[method] = {'known_ratings': known, 'unknown_ratings': unknown,
                          'lower': success / total if total else None,
                          'upper': (success + unknown) / total if total else None}
    return result


def krippendorff_nominal(units):
    """Nominal alpha over units (lists of category labels); needs >= 2 labels per unit."""
    coincidence = {}
    for labels in units:
        if len(labels) < 2:
            continue
        for a, b in itertools.permutations(range(len(labels)), 2):
            key = (labels[a], labels[b])
            coincidence[key] = coincidence.get(key, 0) + 1 / (len(labels) - 1)
    totals = {}
    for (a, _), weight in coincidence.items():
        totals[a] = totals.get(a, 0) + weight
    n = sum(totals.values())
    if n <= 1:
        return None
    observed = sum(w for (a, b), w in coincidence.items() if a != b) / n
    expected = sum(totals[a] * totals[b] for a in totals for b in totals if a != b) / (n * (n - 1))
    return None if expected == 0 else 1 - observed / expected


def agreement(public, reviewers):
    result = {}
    for question in QUESTIONS:
        units, agree, pairs = [], 0, 0
        for item in public['items']:
            for side in ('A', 'B'):
                labels = [r['ratings'][item['id']][side][question]
                          for r in reviewers if item['id'] in r['ratings']]
                units.append(labels)
                for a, b in itertools.combinations(labels, 2):
                    pairs += 1
                    agree += a == b
        result[question] = {'krippendorff_alpha_nominal': krippendorff_nominal(units),
                            'mean_pairwise_agreement': agree / pairs if pairs else None,
                            'rater_pairs_compared': pairs}
    return result


def identical_consistency(public, private, reviewers):
    """On identical-pixel pairs, how often a rater gave both sides the same answer."""
    same = total = 0
    for item in public['items']:
        if not private['items'][item['id']]['identical_outputs']:
            continue
        for reviewer in reviewers:
            payload = reviewer['ratings'].get(item['id'])
            if payload is None:
                continue
            for question in QUESTIONS:
                total += 1
                same += payload['A'][question] == payload['B'][question]
    return {'answers_compared': total, 'same_answer_both_sides': same,
            'share': same / total if total else None,
            'policy': 'Diagnostic only. Identical pairs stay in every estimate; nothing is corrected or dropped.'}


def checker_flags(metadata):
    """Collect {output sha256: checker_pass} from any nested checker metadata JSON."""
    flags = {}

    def walk(node):
        if isinstance(node, dict):
            if 'output_sha256' in node and isinstance(node.get('checker_pass'), bool):
                sha = node['output_sha256']
                require(flags.get(sha, node['checker_pass']) == node['checker_pass'],
                        'Conflicting checker verdicts for one output.')
                flags[sha] = node['checker_pass']
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(metadata)
    return flags


def checker_join(public, private, reviewers, flags):
    """Author joint outcomes per unique output, split by the checker verdict."""
    per_output = {}
    for item in public['items']:
        mapping = private['items'][item['id']]
        for reviewer in reviewers:
            payload = reviewer['ratings'].get(item['id'])
            if payload is None:
                continue
            for side in ('A', 'B'):
                sha = mapping['selected'][mapping[side]]['sha256']
                value = joint(payload[side])
                if value is not None:
                    per_output.setdefault(sha, []).append(1.0 if value else 0.0)
    groups = {}
    for verdict in (True, False):
        rates = [sum(v) / len(v) for sha, v in per_output.items() if flags.get(sha) is verdict]
        groups['checker_pass' if verdict else 'checker_fail'] = {
            'unique_outputs_with_known_author_ratings': len(rates),
            'mean_author_joint_success': mean(rates),
            'outputs_no_author_success': sum(r == 0 for r in rates),
            'outputs_all_authors_success': sum(r == 1 for r in rates)}
    groups['outputs_without_checker_verdict'] = sum(sha not in flags for sha in per_output)
    groups['note'] = ('Share of checker-passed outputs that authors failed is a false-acceptance '
                      'measure among checker passes, not a false-positive rate among author failures.')
    return groups


def analyze(public, private, reviewers, coverage_only=False, flags=None):
    report = {'schema_version': 1, 'study_version': public['version'],
              'reviewers': len(reviewers), 'coverage': coverage(public, reviewers)}
    if coverage_only:
        report['status'] = 'coverage_only'
        return report
    report['status'] = 'analyzed'
    report['endpoint'] = ENDPOINT
    report['bootstrap'] = {'replicates': REPLICATES, 'seed': SEED,
                           'unit': 'photo, resampled with replacement with all its cases'}
    report['estimates'] = {}
    for endpoint in (JOINT,) + QUESTIONS:
        rows = case_rows(public, private, reviewers, endpoint)
        block = {'all_cases': summarize(rows),
                 'excluding_identical_outputs': summarize([r for r in rows if not r['identical']]),
                 'by_task': {task: summarize([r for r in rows if r['task'] == task])
                             for task in sorted({r['task'] for r in rows})},
                 'unknown_bounds': bounds(rows)}
        report['estimates'][endpoint] = block
    report['agreement'] = agreement(public, reviewers)
    report['identical_pair_consistency'] = identical_consistency(public, private, reviewers)
    if flags is not None:
        report['checker_vs_authors'] = checker_join(public, private, reviewers, flags)
    report['limits'] = ('Blinded annotation by the non-naive authors on 20 retrospectively shared '
                        'photos. Exploratory intervals. Not a user study, held-out result, or '
                        'nutrition or health evidence.')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--exports', type=Path, nargs='+', required=True)
    parser.add_argument('--checker-metadata', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--coverage-only', action='store_true',
                        help='Report missingness only; no method outcomes before collection ends.')
    args = parser.parse_args(argv)
    require(not args.output.exists(), 'Output exists; choose a new path.')
    public, private = load_package(args.data_dir)
    reviewers = load_exports(args.exports, public)
    flags = checker_flags(read_json(args.checker_metadata)) if args.checker_metadata else None
    report = analyze(public, private, reviewers, args.coverage_only, flags)
    body = json.dumps(report, indent=1, sort_keys=True)
    args.output.write_text(body, encoding='utf-8')
    print(json.dumps({'status': report['status'], 'report_sha256': hashlib.sha256(body.encode()).hexdigest()}))


if __name__ == '__main__':
    try:
        main()
    except ValueError as error:
        sys.exit(f'Refused: {error}')
