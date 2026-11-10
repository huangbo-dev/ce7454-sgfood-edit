"""Offline, protocol-aligned CE7454 author analysis. Never served by the portal.

Consumes exported answers, a pre-collection author roster, and the private frozen
mapping. It never contacts a network, reads the live database, or changes answers.
Only the explicit offline analysis command reveals methods in a new report.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import itertools
import json
from pathlib import Path
import random
import re
import sys

try:
    from .endpoint import joint_success, NUMERIC_SCALES
except ImportError:
    from endpoint import joint_success, NUMERIC_SCALES

SCHEMA = 'sgfood-judge-v1-author-portal-v2'
METHODS = ('best_check', 'retry')
CONDITIONS = ('tuned', 'baseline')
REPLICATES = 10000
SEED = 20261108
ENDPOINT = 'edit=2 AND preserve=2 AND realism>=3 AND extra=0'


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def require(test, message):
    if not test:
        raise ValueError(message)


def utc(text):
    require(isinstance(text, str), 'A timezone-aware ISO timestamp is required.')
    try:
        value = datetime.fromisoformat(text.replace('Z', '+00:00'))
    except ValueError as exc:
        raise ValueError('Invalid ISO timestamp.') from exc
    require(value.tzinfo is not None and value.utcoffset() is not None, 'Timestamp lacks timezone.')
    return value


def validate_design(public, private):
    require(isinstance(public, dict) and isinstance(private, dict), 'Malformed study manifests.')
    version = public.get('version')
    require(isinstance(version, str) and bool(version) and version == private.get('version'), 'Study versions do not match.')
    require(private.get('rubric_schema') == SCHEMA, 'Wrong rubric schema. Do not analyze old three-level ratings.')
    require(ENDPOINT in private.get('joint_success', ''), 'Primary endpoint metadata does not match frozen protocol.')
    items = public.get('items')
    mapping = private.get('items')
    require(isinstance(items, list) and isinstance(mapping, dict), 'Missing item manifests.')
    require(len(items) == 68 and len(mapping) == 68, 'This frozen study requires all 68 pairs.')
    ids = [x.get('id') for x in items]
    require(all(isinstance(x, str) for x in ids) and len(set(ids)) == 68 and set(ids) == set(mapping), 'Missing, duplicated or extra item identifiers.')
    public_by_id = {x['id']: x for x in items}
    cases = set(); photos = defaultdict(set); qa = {}; originals = {}
    for iid, entry in mapping.items():
        require(isinstance(entry, dict), 'Malformed private item.')
        c, photo, task = entry.get('condition'), entry.get('photo_id'), entry.get('task')
        require(c in CONDITIONS and isinstance(photo, str) and bool(photo) and task in ('T1-B', 'T2'), 'Invalid case metadata.')
        require((c, photo, task) not in cases, 'Duplicate condition/photo/task case.')
        cases.add((c, photo, task)); photos[c].add(photo)
        require({entry.get('A'), entry.get('B')} == set(METHODS), 'A/B method assignment is invalid.')
        label = entry.get('prior_mask_qa')
        require(label in ('accept', 'needs-review'), 'Unknown prior mask stratum.')
        require(photo not in qa or qa[photo] == label, 'A photo has conflicting prior QA strata.')
        qa[photo] = label
        row = public_by_id[iid]
        for name in ('original', 'A', 'B'):
            require(isinstance(row.get(name), str) and re.fullmatch(r'[a-f0-9]{24}\.png', row[name]), 'Invalid opaque media identifier.')
        require(photo not in originals or originals[photo] == row['original'], 'A photo has conflicting originals.')
        originals[photo] = row['original']
        selected = entry.get('selected', {})
        hashes = {}
        for side in ('A', 'B'):
            method = entry[side]
            digest = selected.get(method, {}).get('sha256')
            require(isinstance(digest, str) and re.fullmatch(r'[a-f0-9]{64}', digest), 'Missing selected-output content hash.')
            require(row[side] == digest[:24]+'.png', 'Selected-output hash does not match frozen A/B media.')
            hashes[method] = digest
        require(type(entry.get('identical_outputs')) is bool and entry['identical_outputs'] == (hashes['retry'] == hashes['best_check']), 'Identical-output marker is inconsistent.')
    require(photos['tuned'] == photos['baseline'] and len(photos['tuned']) == 20, 'Both conditions must retain the same 20 photos.')
    for c in CONDITIONS:
        for task, count in (('T1-B', 20), ('T2', 14)):
            subset = {photo for condition, photo, name in cases if condition == c and name == task}
            require(len(subset) == count, 'Frozen task cohort count changed.')
            if c == 'baseline':
                require(subset == {p for condition, p, name in cases if condition == 'tuned' and name == task}, 'Task cohorts differ between prompt conditions.')
    require(Counter(qa.values()) == {'accept': 13, 'needs-review': 7}, 'Prior-QA cohort changed; retain all flagged cases.')
    rice = {p for c,p,t in cases if c == 'tuned' and t == 'T2'}
    require(Counter(qa[p] for p in rice) == {'accept': 12, 'needs-review': 2}, 'Frozen rice/mask strata changed.')
    return public_by_id


def validate_roster(roster, version):
    require(isinstance(roster, dict) and roster.get('schema_version') == 1 and roster.get('study_version') == version, 'Author roster schema/version mismatch.')
    require(roster.get('locked_before_collection') is True, 'A pre-collection fixed author roster is required.')
    locked = utc(roster.get('locked_utc'))
    authors = roster.get('authors')
    require(isinstance(authors, list) and len(authors) > 0, 'Author roster is empty.')
    ids = []
    for author in authors:
        require(isinstance(author, dict) and isinstance(author.get('id'), str) and bool(author['id']), 'Invalid author identifier.')
        require(author.get('role') == 'author', 'This portal supports the fixed author-only study, not outside participants.')
        require(isinstance(author.get('prior_exposure'), str) and bool(author['prior_exposure'].strip()), 'Each author must disclose prior exposure.')
        ids.append(author['id'])
    require(len(set(ids)) == len(ids), 'Duplicate author identifiers in roster.')
    return sorted(ids), locked


def validate_exports(exports, public, roster):
    authors, locked = validate_roster(roster, public['version'])
    item_ids = {i['id'] for i in public['items']}
    answers = {}; seen = set()
    for export in exports:
        require(isinstance(export, dict), 'Malformed author export.')
        author = export.get('rater')
        require(author in authors and author not in seen, 'Unknown author or duplicate author export. Supply one latest export per author.')
        require(export.get('version') == public['version'], 'Export uses the wrong study version.')
        seen.add(author)
        rows = export.get('responses')
        require(isinstance(rows, dict) and set(rows) <= item_ids, 'Export has invalid or unknown items.')
        submissions = set()
        for iid, row in rows.items():
            require(isinstance(row, dict) and row.get('item_id') == iid and row.get('version') == public['version'], 'Answer identity/version mismatch.')
            for side in ('A', 'B'):
                joint_success(row.get(side))  # validates all four values, including explicit Unsure
            require(row.get('preference') in (None, 'A', 'B', 'tie', 'neither'), 'Invalid separate preference.')
            require(row.get('certainty') in (None, 'certain', 'uncertain'), 'Invalid certainty.')
            require(isinstance(row.get('note', ''), str) and len(row.get('note','')) <= 1000, 'Invalid note.')
            rev, base = row.get('revision'), row.get('base_revision')
            require(type(rev) is int and rev >= 1 and type(base) is int and base == rev-1, 'Invalid saved revision; use the latest server export.')
            sid = row.get('submission_id')
            require(isinstance(sid, str) and re.fullmatch(r'[A-Za-z0-9_-]{16,80}',sid) and sid not in submissions, 'Invalid or reused submission identifier.')
            submissions.add(sid)
            require(utc(row.get('created_utc')) >= locked, 'Roster was not locked before these saved answers.')
            answers[(author, iid)] = row
    return authors, answers


def coverage(public, private, authors, answers):
    result = {}
    for condition in CONDITIONS:
        items = sorted(i for i,e in private['items'].items() if e['condition'] == condition)
        saved = complete = 0; unknown_by_field = Counter(); incomplete = []; identical_conflicts = []
        for iid in items:
            missing_authors = []; unknown_authors = []
            for author in authors:
                row = answers.get((author, iid))
                if row is None:
                    missing_authors.append(author); continue
                saved += 1
                if all(joint_success(row[s]) is not None for s in ('A','B')):
                    complete += 1
                    if private['items'][iid]['identical_outputs'] and joint_success(row['A']) != joint_success(row['B']):
                        identical_conflicts.append({'item_id':iid,'author':author})
                else:
                    unknown_authors.append(author)
                for side in ('A','B'):
                    for field in NUMERIC_SCALES:
                        if row[side][field] == 'unclear': unknown_by_field[field] += 1
            if missing_authors or unknown_authors:
                incomplete.append({'item_id':iid,'missing_authors':missing_authors,'authors_with_unsure':unknown_authors})
        result[condition] = {'expected_cases':len(items),'expected_paired_author_ratings':len(items)*len(authors),
            'saved_paired_author_ratings':saved,'complete_numeric_paired_author_ratings':complete,
            'missing_paired_author_ratings':len(items)*len(authors)-saved,
            'paired_author_ratings_with_unsure':saved-complete,
            'unsure_criterion_counts':{f:unknown_by_field[f] for f in NUMERIC_SCALES},
            'complete_cases':len(items)-len(incomplete),'incomplete_cases':incomplete,
            'identical_output_joint_conflicts':identical_conflicts,
            'ready_for_comparative_analysis':not incomplete and not identical_conflicts}
    return result


def estimate_rows(condition, private, authors, answers):
    """Require complete paired roster; means within case, then equally across cases."""
    result = []
    for iid, entry in sorted(private['items'].items()):
        if entry['condition'] != condition: continue
        scores = {m:[] for m in METHODS}
        dimensions = {m:{f:[] for f in NUMERIC_SCALES} for m in METHODS}
        for author in authors:
            row = answers.get((author, iid))
            require(row is not None, 'Incomplete case cannot enter comparative analysis.')
            for side in ('A','B'):
                value = joint_success(row[side])
                require(value is not None, 'Unsure cannot be imputed or dropped.')
                method = entry[side]; scores[method].append(int(value))
                for field in NUMERIC_SCALES: dimensions[method][field].append(row[side][field])
        means = {m:sum(values)/len(values) for m,values in scores.items()}
        result.append({'item_id':iid,'photo_id':entry['photo_id'],'task':entry['task'],'prior_mask_qa':entry['prior_mask_qa'],
            'condition':condition,'author_count':len(authors),'joint_success':means,'paired_difference':means['retry']-means['best_check'],
            'dimension_means':{m:{f:sum(values)/len(values) for f,values in fields.items()} for m,fields in dimensions.items()},
            'identical_outputs':entry['identical_outputs']})
    return result


def percentile(values, q):
    """Linear interpolation, position (n-1)*q; defined here for reproducibility."""
    require(bool(values) and 0 <= q <= 1, 'Invalid percentile request.')
    ordered = sorted(values); pos=(len(ordered)-1)*q; lo=int(pos); hi=min(lo+1,len(ordered)-1)
    return ordered[lo]+(ordered[hi]-ordered[lo])*(pos-lo)


def cluster_draws(photos, replicates=REPLICATES, seed=SEED):
    """One shared sequence for all contrasts, never independent task/arm draws."""
    photos=sorted(set(photos)); require(len(photos)>0,'No photo clusters.')
    rng=random.Random(seed)
    for _ in range(replicates):
        yield Counter(photos[rng.randrange(len(photos))] for _ in photos)


def weighted_case_mean(rows, multiplicities, key='paired_difference'):
    denominator=sum(multiplicities.get(r['photo_id'],0) for r in rows)
    require(denominator>0,'Bootstrap draw has no eligible cases.')
    return sum(r[key]*multiplicities.get(r['photo_id'],0) for r in rows)/denominator


def summaries(rows):
    def mean(group):
        return {'cases':len(group),'photos':len({r['photo_id'] for r in group}),
            'joint_success':{m:sum(r['joint_success'][m] for r in group)/len(group) for m in METHODS},
            'retry_minus_best':sum(r['paired_difference'] for r in group)/len(group),
            'dimension_means':{m:{f:sum(r['dimension_means'][m][f] for r in group)/len(group) for f in NUMERIC_SCALES} for m in METHODS}}
    return {'overall':mean(rows),
        'per_task':{t:mean([r for r in rows if r['task']==t]) for t in ('T1-B','T2')},
        'prior_mask_strata_descriptive_only':{q:mean([r for r in rows if r['prior_mask_qa']==q]) for q in ('accept','needs-review')}}


def diagnostics(condition, private, authors, answers):
    preferences=Counter(); certainty=Counter(); dimensions={m:{f:Counter() for f in NUMERIC_SCALES} for m in METHODS}
    identical={'cases':0,'paired_author_ratings':0,'any_dimension_disagreement':0,'joint_disagreement':0,'directional_preferences':0}
    agreement={'author_count':len(authors),'status':'not_estimable_single_author' if len(authors)==1 else 'descriptive_fixed_panel',
        'known_joint_author_pairs':0,'joint_agreements':0,'unknown_joint_author_pairs':0}
    for iid,entry in sorted(private['items'].items()):
        if entry['condition']!=condition:continue
        if entry['identical_outputs']:identical['cases']+=1
        for author in authors:
            row=answers.get((author,iid))
            if row is None:continue
            preference=row.get('preference'); preferences[entry[preference] if preference in ('A','B') else preference or 'missing']+=1
            certainty[row.get('certainty') or 'missing']+=1
            for side in ('A','B'):
                for field in NUMERIC_SCALES:dimensions[entry[side]][field][str(row[side][field])]+=1
            if entry['identical_outputs']:
                identical['paired_author_ratings']+=1
                identical['any_dimension_disagreement']+=row['A']!=row['B']
                a,b=joint_success(row['A']),joint_success(row['B'])
                identical['joint_disagreement']+=a is not None and b is not None and a!=b
                identical['directional_preferences']+=preference in ('A','B')
        for a,b in itertools.combinations(authors,2):
            ra,rb=answers.get((a,iid)),answers.get((b,iid))
            for side in ('A','B'):
                ja=joint_success(ra[side]) if ra else None; jb=joint_success(rb[side]) if rb else None
                if ja is None or jb is None:agreement['unknown_joint_author_pairs']+=1
                else:
                    agreement['known_joint_author_pairs']+=1;agreement['joint_agreements']+=ja==jb
    agreement['joint_agreement_fraction']=(agreement['joint_agreements']/agreement['known_joint_author_pairs'] if agreement['known_joint_author_pairs'] else None)
    return {'preference_votes':{p:preferences[p] for p in ('retry','best_check','tie','neither','missing')},
        'certainty':{c:certainty[c] for c in ('certain','uncertain','missing')},
        'rubric_histograms':{m:{f:dict(sorted(counts.items())) for f,counts in fields.items()} for m,fields in dimensions.items()},
        'identical_output_consistency':identical,'author_agreement':agreement,
        'policy':'Raw explicit votes only, no plurality/majority conversion. Identical pairs retained; inconsistencies flagged, never corrected or excluded. Directional votes on identical pixels are not evidence of visual improvement.'}


def prompt_integrity(private, authors, answers):
    """Flag cross-condition repeat-image conflicts without invalidating primary."""
    cases={(e['condition'],e['photo_id'],e['task']):(iid,e) for iid,e in private['items'].items()}
    conflicts={m:[] for m in METHODS}
    for (condition,photo,task),(new_id,new) in sorted(cases.items()):
        if condition!='tuned':continue
        old_id,old=cases[('baseline',photo,task)]
        for author in authors:
            a,b=answers.get((author,new_id)),answers.get((author,old_id))
            if not a or not b:continue
            for ns,os in itertools.product(('A','B'),repeat=2):
                nm,om=new[ns],old[os]
                if new['selected'][nm]['sha256']!=old['selected'][om]['sha256']:continue
                x,y=joint_success(a[ns]),joint_success(b[os])
                if x is not None and y is not None and x!=y:
                    record={'author':author,'photo_id':photo,'task':task,'revised_item':new_id,'original_item':old_id,
                            'revised_method':nm,'original_method':om}
                    for method in sorted({nm,om}):conflicts[method].append(record)
    return conflicts


def analyze(public, private, roster, exports, coverage_only=False):
    validate_design(public,private)
    authors,answers=validate_exports(exports,public,roster)
    cov=coverage(public,private,authors,answers)
    report={'schema_version':1,'study_version':public['version'],'status':'coverage_only',
        'endpoint':ENDPOINT,'unknown_policy':'Any Unsure leaves joint success unknown. No imputation or complete-case filtering.',
        'author_count':len(authors),'fixed_roster':roster,'coverage':cov,
        'classification':'Retrospective shared-photo author review; not independent held-out or external-participant evidence.',
        'limitations':['Fixed author panel, with declared prior photo/mask exposure; single-author ratings are not independent replication.',
            'Photo-cluster interval describes this fixed panel and small photo cohort, not a population of reviewers or powered hypothesis test.',
            'Rice contributes two equally weighted edit cases, noodles one; per-task results are required.',
            'Prior mask strata are descriptive and confounded with rice/noodle composition.',
            'No nutritional, behavioural, awareness, older-adult or health-effect claim follows.'],
        'analysis_not_included':['Single-shot or CLIP comparisons were not collected by this pairwise portal.',
            'Checker false acceptance and generation costs need separately verified selected-output checker/cost metadata; not inferred from ratings.',
            'No inferential p-values or new reviewer/case exclusion rules are applied.',
            'Latest-only exports cannot prove original first-submission times; preserve the roster hash before collection separately.'],
        'identical_output_policy':'Pre-collection integrity gate: conflicting known joint endpoints for one author on byte-identical A/B outputs suppress the affected contrast pending explicit review. Preserve both raw ratings; never recode, omit, or force a tie. Dimension-only disagreement with equal endpoints remains a diagnostic.'}
    if coverage_only:return report
    if not cov['tuned']['ready_for_comparative_analysis']:
        report['status']='incomplete_primary_no_comparative_estimates'
        return report
    rows={c:estimate_rows(c,private,authors,answers) for c in CONDITIONS if cov[c]['ready_for_comparative_analysis']}
    report['status']='primary_complete_secondary_complete' if 'baseline' in rows else 'primary_complete_secondary_incomplete'
    report['contrasts']={c:dict(summaries(values),diagnostics=diagnostics(c,private,authors,answers)) for c,values in rows.items()}
    report['case_estimates']=rows  # private offline audit trace, never a web route
    bootstrap={c:[] for c in rows}; prompt_rows={}; prompt_conflicts={}
    if 'baseline' in rows:
        prompt_conflicts=prompt_integrity(private,authors,answers)
        report['prompt_integrity_conflicts']=prompt_conflicts
        if any(prompt_conflicts.values()):
            report['status']='primary_complete_secondary_prompt_withheld'
        original={(r['photo_id'],r['task']):r for r in rows['baseline']}
        for method in METHODS:
            if prompt_conflicts[method]:continue
            prompt_rows[method]=[{'photo_id':r['photo_id'],'paired_difference':r['joint_success'][method]-original[(r['photo_id'],r['task'])]['joint_success'][method]} for r in rows['tuned']]
            bootstrap['prompt_'+method]=[]
        if not any(prompt_conflicts.values()):
            prompt_rows['interaction']=[{'photo_id':r['photo_id'],'paired_difference':r['paired_difference']-original[(r['photo_id'],r['task'])]['paired_difference']} for r in rows['tuned']]
            bootstrap['interaction']=[]
    for draw in cluster_draws({r['photo_id'] for r in rows['tuned']}):
        for c,values in rows.items():bootstrap[c].append(weighted_case_mean(values,draw))
        for method,values in prompt_rows.items():bootstrap['interaction' if method=='interaction' else 'prompt_'+method].append(weighted_case_mean(values,draw))
    def interval(values):return [percentile(values,.025),percentile(values,.975)]
    for c in rows:report['contrasts'][c]['retry_minus_best_percentile_95_ci']=interval(bootstrap[c])
    if 'baseline' in rows:
        report['prompt_comparisons_secondary']={m:{'status':'complete','revised_minus_original':sum(r['paired_difference'] for r in rr)/len(rr),
            'percentile_95_ci':interval(bootstrap['interaction' if m=='interaction' else 'prompt_'+m])} for m,rr in prompt_rows.items()}
        for method in (*METHODS,'interaction'):
            if method not in prompt_rows:
                report['prompt_comparisons_secondary'][method]={'status':'withheld_identical_output_rating_conflict','estimate':None,'percentile_95_ci':None}
        report['prompt_comparisons_secondary']['interaction']['meaning']='Change in retry-minus-best between revised and original prompts; does not establish causality outside this frozen system.'
    report['bootstrap']={'replicates':REPLICATES,'seed':SEED,'clusters':20,'sampling':'Uniformly sample 20 sorted photo IDs with replacement; preserve multiplicity and all their tasks, conditions, arms and author ratings; same draws for every contrast.',
        'estimand':'Mean paired difference over edit cases, after fixed-author averaging per case; not mean of per-photo averages.',
        'percentile':'Linear interpolation at (n-1)*q, q=.025 and .975. No task-level independence, author resampling or p-value.',
        'replicate_series_sha256':hashlib.sha256(canonical(bootstrap).encode()).hexdigest()}
    return report


def parse_json_bytes(body):
    def pairs(values):
        out={}
        for key,value in values:
            require(key not in out,'Duplicate JSON object key; ambiguous data rejected.')
            out[key]=value
        return out
    return json.loads(body.decode('utf-8'),object_pairs_hook=pairs,
                      parse_constant=lambda _:(_ for _ in ()).throw(ValueError('Non-finite JSON is invalid.')))


def read_json(path):
    return parse_json_bytes(Path(path).read_bytes())


def load_package(directory):
    root=Path(directory).resolve();lockpath=root/'PACKAGE_LOCK.json';lockbytes=lockpath.read_bytes();lock=parse_json_bytes(lockbytes)
    bodies={}
    for name,info in lock['files'].items():
        require(name in ('public_manifest.json','private_map.json') or re.fullmatch(r'media/[a-f0-9]{24}\.png',name),'Unexpected or ambiguous package file.')
        path=(root/name).resolve()
        require(root in path.parents and path.is_file() and not (root/name).is_symlink(),'Unsafe package path.')
        body=path.read_bytes()
        require(len(body)==info['bytes'] and hashlib.sha256(body).hexdigest()==info['sha256'],'Frozen review package hash mismatch.')
        if name in ('public_manifest.json','private_map.json'):bodies[name]=body
    require({'public_manifest.json','private_map.json'}<=set(lock['files']),'Manifests are not locked.')
    public=parse_json_bytes(bodies['public_manifest.json']);private=parse_json_bytes(bodies['private_map.json'])
    require(lock.get('version')==public.get('version')==private.get('version'),'Package-lock version mismatch.')
    validate_design(public,private)
    referenced={'media/'+item[field] for item in public['items'] for field in ('original','A','B')}
    require(set(lock['files'])==referenced|{'public_manifest.json','private_map.json'},'Every referenced image must be locked exactly; missing or extra media rejected.')
    for item in public['items']:
        entry=private['items'][item['id']]
        for side in ('A','B'):
            require(entry['selected'][entry[side]]['sha256']==lock['files']['media/'+item[side]]['sha256'],
                    'Full selected-output hash disagrees with locked media content.')
    return public,private,hashlib.sha256(lockbytes).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-dir',type=Path,required=True)
    p.add_argument('--roster',type=Path,required=True)
    p.add_argument('--exports',type=Path,nargs='*',default=[])
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--coverage-only',action='store_true',help='No method outcomes; report only missingness before unblinding.')
    a=p.parse_args()
    try:
        require(not a.output.exists(),'Output already exists. Choose a new path; no reports are overwritten.')
        public,private,lock_sha=load_package(a.data_dir)
        roster_bytes=a.roster.read_bytes();export_bytes=[x.read_bytes() for x in a.exports]
        sources={'roster_sha256':hashlib.sha256(roster_bytes).hexdigest(),
            'export_sha256':sorted(hashlib.sha256(x).hexdigest() for x in export_bytes),
            'package_lock_sha256':lock_sha,
            'analysis_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'endpoint_sha256':hashlib.sha256((Path(__file__).parent/'endpoint.py').read_bytes()).hexdigest(),
            'python_version':sys.version.split()[0]}
        report=analyze(public,private,parse_json_bytes(roster_bytes),[parse_json_bytes(x) for x in export_bytes],a.coverage_only)
        report['reproducibility']=sources
        with a.output.open('x',encoding='utf-8',newline='\n') as f:f.write(json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+'\n')
        print(json.dumps({'status':report['status'],'report_sha256':hashlib.sha256(a.output.read_bytes()).hexdigest(),'private_offline_report':True}))
        return 2 if report['status']=='incomplete_primary_no_comparative_estimates' else 0
    except (ValueError,KeyError,TypeError,OSError) as exc:
        print('Analysis stopped: '+str(exc),file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
