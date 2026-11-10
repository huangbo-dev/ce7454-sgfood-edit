"""Private offline checker/author calibration, without changing frozen ratings.

Build metadata from the locked run, then join exact selected-output hashes to
exported rubric answers. No network, live database, model calls or portal route.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import sys

try:
    from . import compare
except ImportError:
    import compare

require = compare.require
METHODS = compare.METHODS
CONDITIONS = compare.CONDITIONS


def digest(body):
    return hashlib.sha256(body).hexdigest()


def read_snapshot(path):
    body = Path(path).read_bytes()
    return compare.parse_json_bytes(body), digest(body)


def safe_token(value, name):
    require(isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_-]+', value), 'Unsafe '+name)
    return value


def checked_candidate(path, policy):
    obj, metadata_sha = read_snapshot(path)
    png = path.with_suffix('.png')
    require(png.is_file() and not png.is_symlink(), 'Missing or unsafe candidate image.')
    image_sha = digest(png.read_bytes())
    require(obj.get('sha256') == image_sha, 'Candidate image hash mismatch.')
    scores = {}
    ranges = {'edit': (0, 2), 'preserve': (0, 2), 'realism': (1, 5), 'extra': (0, 1)}
    for field, (lo, hi) in ranges.items():
        value = obj.get('check', {}).get(field, {}).get('score')
        require(type(value) in (int, float) and math.isfinite(value) and lo <= value <= hi, 'Invalid checker score.')
        scores[field] = value
    th, w = policy['pass'], policy['weights']
    for group in (th, w):
        require(set(group) == set(ranges), 'Incomplete checker policy.')
        require(all(type(v) in (int, float) and math.isfinite(v) for v in group.values()), 'Non-finite checker policy.')
    passed = (scores['edit'] >= th['edit'] and scores['preserve'] >= th['preserve']
              and scores['realism'] >= th['realism'] and scores['extra'] <= th['extra'])
    score = (w['edit']*scores['edit']/2 + w['preserve']*scores['preserve']/2
             + w['realism']*(scores['realism']-1)/4 - w['extra']*scores['extra'])
    require(type(obj.get('pass')) is bool and obj['pass'] == passed, 'Candidate checker verdict disagrees with frozen policy.')
    require(type(obj.get('score')) in (int, float) and math.isfinite(obj['score'])
            and math.isclose(obj['score'], score, abs_tol=1e-12), 'Candidate ranking score mismatch.')
    return {'output_sha256': image_sha, 'checker_pass': passed, 'checker_scores': scores,
            'ranking_score': score, 'candidate_metadata_sha256': metadata_sha}


def extract_metadata(run_root, public, private, package_lock_sha):
    """Verify raw run provenance and return 136 selected-output records."""
    compare.validate_design(public, private)
    root = Path(run_root).resolve()
    records = {}; provenance = {}
    for condition in CONDITIONS:
        folder = root/condition
        lock, lock_sha = read_snapshot(folder/'LOCK.json')
        complete, complete_sha = read_snapshot(folder/'COMPLETE.json')
        body = (folder/'results.jsonl').read_bytes(); result_sha = digest(body)
        source = private['conditions'][condition]
        require(source['lock_sha256'] == lock_sha and source['result_sha256'] == result_sha,
                'Run source differs from frozen review package.')
        require(complete.get('results_sha256') == result_sha and complete.get('completed_jobs') == 34,
                'Run is incomplete or results changed.')
        rows = [compare.parse_json_bytes(line) for line in body.splitlines() if line.strip()]
        require(len(rows) == 34, 'Expected exactly 34 cases per condition.')
        keyed = {}
        for row in rows:
            key = safe_token(row.get('key'), 'job key')
            require(key not in keyed, 'Duplicate source job.')
            keyed[key] = row
        items = {iid: e for iid,e in private['items'].items() if e['condition'] == condition}
        require(set(keyed) == {e['source_job_key'] for e in items.values()}, 'Source/review job set mismatch.')
        candidate_count = 0; candidate_metadata_hashes = {}
        for iid, entry in sorted(items.items()):
            key = entry['source_job_key']; row = keyed[key]
            require((row.get('image_id'), row.get('task')) == (entry['photo_id'], entry['task']), 'Source photo/task mismatch.')
            sequences = {'best_check': row.get('seed_tags'), 'retry': row.get('retry_steps')}
            for method, tags in sequences.items():
                require(isinstance(tags, list) and 1 <= len(tags) <= 4 and len(set(tags)) == len(tags), 'Invalid generation sequence.')
                for tag in tags: safe_token(tag, 'candidate tag')
            require(len(sequences['best_check']) == 4, 'Frozen best-of-four budget changed.')
            require(sequences['best_check'][0] == sequences['retry'][0], 'Arms do not share the frozen first candidate.')
            candidates = {}
            for tag in sorted(set(sequences['best_check'] + sequences['retry'])):
                path = folder/'candidates'/key/(tag+'.json')
                require(path.is_file() and not path.is_symlink(), 'Missing or unsafe candidate metadata.')
                candidates[tag] = checked_candidate(path, lock['policy'])
                candidate_metadata_hashes[key+'/'+tag+'.json'] = candidates[tag]['candidate_metadata_sha256']
            candidate_count += len(candidates)
            require(not any(candidates[t]['checker_pass'] for t in sequences['retry'][:-1]), 'Retry continued after a pass.')
            require(len(sequences['retry']) == 4 or candidates[sequences['retry'][-1]]['checker_pass'], 'Retry stopped before pass or budget.')
            outputs = {}
            for method, tags in sequences.items():
                selected = max(tags, key=lambda t: candidates[t]['ranking_score'])
                frozen = entry['selected'][method]
                require(row.get(method) == selected == frozen['tag'], 'Selected candidate or first-maximum tie rule changed.')
                obj = dict(candidates[selected])
                require(obj['output_sha256'] == frozen['sha256'], 'Selected output differs from review pixels.')
                obj.update({'candidate_tag': selected, 'generation_count': len(tags)})
                outputs[method] = obj
            require(type(row.get('retry_passed')) is bool and row['retry_passed'] == outputs['retry']['checker_pass'], 'Retry selected verdict mismatch.')
            require(type(row.get('retry_last_passed')) is bool and row['retry_last_passed'] == candidates[sequences['retry'][-1]]['checker_pass'], 'Retry last verdict mismatch.')
            records[iid] = {'condition': condition, 'photo_id': entry['photo_id'], 'task': entry['task'],
                            'source_job_key': key, 'outputs': outputs}
        provenance[condition] = {'results_sha256': result_sha, 'lock_sha256': lock_sha,
                                 'complete_sha256': complete_sha, 'verified_candidate_count': candidate_count,
                                 'candidate_metadata_sha256': candidate_metadata_hashes,
                                 'candidate_metadata_assurance': 'Snapshot hashed at extraction; no independently preserved historical checker-JSON lock was supplied.'}
    return {'schema_version': 1, 'study_version': public['version'], 'package_lock_sha256': package_lock_sha,
            'source_provenance': provenance, 'items': records,
            'cost_definition': 'Policy generation calls from recorded sequence length. Not physical batch count, checker calls, paid cost or standalone latency.'}


def validate_metadata(metadata, public, private, package_lock_sha):
    require(metadata.get('schema_version') == 1 and metadata.get('study_version') == public['version'], 'Checker metadata schema/version mismatch.')
    require(metadata.get('package_lock_sha256') == package_lock_sha, 'Checker metadata binds a different frozen package.')
    require(set(metadata.get('items', {})) == set(private['items']), 'Checker metadata case set mismatch.')
    for condition in CONDITIONS:
        source = metadata['source_provenance'][condition]
        expected = private['conditions'][condition]
        require(source['results_sha256'] == expected['result_sha256'] and source['lock_sha256'] == expected['lock_sha256'], 'Checker metadata source provenance mismatch.')
    for iid, entry in private['items'].items():
        row = metadata['items'][iid]
        require((row.get('condition'), row.get('photo_id'), row.get('task'), row.get('source_job_key')) ==
                (entry['condition'], entry['photo_id'], entry['task'], entry['source_job_key']), 'Checker join identity mismatch.')
        require(set(row.get('outputs', {})) == set(METHODS), 'Missing or extra checker method.')
        for method in METHODS:
            obj = row['outputs'][method]; selected = entry['selected'][method]
            require(obj.get('output_sha256') == selected['sha256'] and obj.get('candidate_tag') == selected['tag'], 'Checker join output hash/tag mismatch.')
            require(type(obj.get('checker_pass')) is bool, 'Checker verdict must be boolean.')
            require(type(obj.get('generation_count')) is int and 1 <= obj['generation_count'] <= 4, 'Invalid policy generation count.')
            require(method != 'best_check' or obj['generation_count'] == 4, 'Best-of-four count changed.')
    return metadata


def metrics(rows):
    """Fixed author-case denominator; uncertain answers never become failures."""
    counts = Counter(); total = len(rows)
    for checker, human, reason in rows:
        counts['checker_pass' if checker else 'checker_fail'] += 1
        if human is None:
            counts['unknown'] += 1; counts['unknown_'+reason] += 1
            counts['unknown_checker_pass' if checker else 'unknown_checker_fail'] += 1
        else:
            counts['tp' if checker and human else 'fp' if checker else 'fn' if human else 'tn'] += 1
    def ratio(n, d): return n/d if d else None
    cp, unknown = counts['checker_pass'], counts['unknown']
    human_pass = counts['tp'] + counts['fn']
    lo, hi = ratio(human_pass, total), ratio(human_pass+unknown, total)
    all_complete = unknown == 0
    far_complete = counts['unknown_checker_pass'] == 0
    fpr_denom = counts['fp']+counts['tn']
    c_rate = ratio(cp, total)
    return {'fixed_author_output_denominator': total, 'counts': {k:counts[k] for k in
            ('checker_pass','checker_fail','tp','fp','fn','tn','unknown','unknown_missing','unknown_unsure','unknown_checker_pass','unknown_checker_fail')},
        'checker_pass_rate': c_rate,
        'author_joint_success_rate': lo if all_complete else None,
        'author_joint_success_identification_bounds': [lo, hi],
        'false_acceptance_given_checker_pass': ratio(counts['fp'], cp) if far_complete else None,
        'false_acceptance_denominator': cp,
        'false_acceptance_identification_bounds': [ratio(counts['fp'],cp), ratio(counts['fp']+counts['unknown_checker_pass'],cp)],
        'false_positive_given_author_fail': ratio(counts['fp'],fpr_denom) if all_complete else None,
        'false_positive_denominator': fpr_denom if all_complete else None,
        'checker_minus_author_rate': c_rate-lo if all_complete else None,
        'checker_minus_author_identification_bounds': [c_rate-hi,c_rate-lo] if total else [None,None],
        'status': 'complete' if all_complete else 'bounds_only_missing_or_unsure'}


def analyze(public, private, roster, exports, metadata, package_lock_sha):
    compare.validate_design(public, private)
    validate_metadata(metadata, public, private, package_lock_sha)
    authors, answers = compare.validate_exports(exports, public, roster)
    coverage = compare.coverage(public, private, authors, answers)
    report = {'schema_version': 1, 'study_version': public['version'], 'author_count': len(authors),
        'classification': 'Retrospective shared-photo author diagnostic, not independent held-out evaluation.',
        'endpoint': compare.ENDPOINT, 'coverage': coverage, 'conditions': {},
        'definitions': {'false_acceptance_given_checker_pass': 'P(author joint failure | selected checker pass), averaged over the fixed author-case panel.',
                        'false_positive_given_author_fail': 'P(checker pass | author joint failure). This denominator differs from false acceptance.',
                        'bounds': 'Identification bounds: assign every missing/Unsure endpoint to failure or success. These are not confidence intervals or imputations.',
                        'denominator': 'All planned author-case outputs in each arm/task; repeated identical outputs retained, not treated as independent images.'},
        'limitations': ['Authors may know these photos; a checker/author disagreement does not alone establish objective error.',
                       'No population-of-raters claim, significance test, new exclusion, nutrition or health inference.',
                       'Costs are recorded generation calls, not standalone latency or physical batch runtime.',
                       'Run results, selection and pixels match frozen receipts. Candidate checker JSON is an extraction-time snapshot, not independently authenticated historical metadata; confirm a historical checker-JSON lock before stronger provenance claims.',
                       'No new author data were collected by this software.']}
    report['checker_source_provenance'] = metadata['source_provenance']
    for condition in CONDITIONS:
        entries = [(iid,e) for iid,e in sorted(private['items'].items()) if e['condition'] == condition]
        if coverage[condition]['identical_output_joint_conflicts']:
            report['conditions'][condition] = {'status': 'withheld_identical_output_conflict', 'methods': None}
            continue
        result = {}
        for method in METHODS:
            output = {}
            for task in (None, 'T1-B', 'T2'):
                selected = [(iid,e) for iid,e in entries if task is None or e['task'] == task]
                rows = []; calls = []
                for iid,e in selected:
                    checker = metadata['items'][iid]['outputs'][method]
                    calls.append(checker['generation_count'])
                    side = next(s for s in ('A','B') if e[s] == method)
                    for author in authors:
                        answer = answers.get((author,iid))
                        human = None if answer is None else compare.joint_success(answer[side])
                        rows.append((checker['checker_pass'],human,'missing' if answer is None else 'unsure'))
                value = metrics(rows)
                value['case_count'] = len(selected)
                value['photo_count'] = len({e['photo_id'] for _,e in selected})
                value['generation_calls'] = {'total':sum(calls),'mean_per_case':sum(calls)/len(calls),
                                            'not_multiplied_by_authors': True}
                output[task or 'overall'] = value
            result[method] = output
        report['conditions'][condition] = {'status': 'computed_with_explicit_missingness', 'methods': result}
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('extract', 'analyze'))
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--run-root', type=Path)
    parser.add_argument('--metadata', type=Path)
    parser.add_argument('--metadata-sha256', help='SHA256 printed by the earlier extract command; required for analysis.')
    parser.add_argument('--roster', type=Path)
    parser.add_argument('--exports', type=Path, nargs='*', default=[])
    args = parser.parse_args(argv)
    try:
        require(not args.output.exists(), 'Output already exists; reports are never overwritten.')
        public, private, package_sha = compare.load_package(args.data_dir)
        provenance = {'package_lock_sha256':package_sha, 'analysis_sha256':digest(Path(__file__).read_bytes()),
                      'compare_sha256':digest(Path(compare.__file__).read_bytes()),
                      'endpoint_sha256':digest((Path(compare.__file__).parent/'endpoint.py').read_bytes()),
                      'python_version':sys.version.split()[0]}
        if args.command == 'extract':
            require(args.run_root is not None, 'extract requires --run-root.')
            report = extract_metadata(args.run_root, public, private, package_sha)
        else:
            require(args.metadata is not None and args.roster is not None, 'analyze requires --metadata and --roster.')
            metadata, metadata_sha = read_snapshot(args.metadata); roster, roster_sha = read_snapshot(args.roster)
            require(args.metadata_sha256 == metadata_sha, 'Supply the verified extractor receipt with --metadata-sha256; metadata changed or receipt missing.')
            snapshots = [read_snapshot(p) for p in args.exports]
            provenance.update({'checker_metadata_sha256':metadata_sha, 'roster_sha256':roster_sha,
                               'export_sha256':sorted(sha for _,sha in snapshots)})
            report = analyze(public, private, roster, [v for v,_ in snapshots], metadata, package_sha)
        report['reproducibility'] = provenance
        with args.output.open('x',encoding='utf-8',newline='\n') as stream:
            stream.write(json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+'\n')
        print(json.dumps({'status':'written_private_offline', 'report_sha256':digest(args.output.read_bytes())}))
        return 0
    except (ValueError,KeyError,TypeError,OSError,ZeroDivisionError) as exc:
        print('Checker join stopped: '+str(exc),file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
