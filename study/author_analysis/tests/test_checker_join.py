import copy
import hashlib
import json
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from analysis import checker_join as join
from synthetic_fixture import fixture, set_method, make_identical, write_package


def prepared(author_count=1):
    public, private, roster, exports = fixture(author_count)
    private['conditions'] = {c:{'result_sha256':c+'-result','lock_sha256':c+'-lock'} for c in join.CONDITIONS}
    items = {}
    for iid,e in private['items'].items():
        e['source_job_key'] = iid
        for method in join.METHODS:e['selected'][method]['tag'] = 'seed1' if method == 'best_check' else 'retry1'
        items[iid] = {k:e[k] for k in ('condition','photo_id','task','source_job_key')}
        items[iid]['outputs'] = {m:{'output_sha256':e['selected'][m]['sha256'],
            'candidate_tag':e['selected'][m]['tag'],'checker_pass':True,
            'generation_count':4 if m=='best_check' else 2} for m in join.METHODS}
    metadata = {'schema_version':1,'study_version':public['version'],'package_lock_sha256':'package-receipt',
                'source_provenance':{c:{'results_sha256':v['result_sha256'],'lock_sha256':v['lock_sha256']}
                    for c,v in private['conditions'].items()},'items':items}
    return public, private, roster, exports, metadata


def build_raw_run(root, public, private):
    """Synthetic non-image bytes and synthetic checker answers, never real data."""
    policy = {'pass':{'edit':1.5,'preserve':1.5,'realism':3,'extra':.5},
              'weights':{'edit':1,'preserve':.5,'realism':.5,'extra':.5}}
    private['conditions'] = {}
    for condition in join.CONDITIONS:
        directory = root/condition; directory.mkdir()
        rows=[]
        for iid, entry in private['items'].items():
            if entry['condition'] != condition:continue
            entry['source_job_key'] = iid
            folder = directory/'candidates'/iid; folder.mkdir(parents=True)
            for tag in ('seed0','seed1','seed2','seed3','retry1'):
                body = ('SYNTHETIC NON-IMAGE BYTES '+iid+' '+tag).encode()
                sha = hashlib.sha256(body).hexdigest()
                (folder/(tag+'.png')).write_bytes(body)
                passed = tag in ('seed1','retry1')
                scores={'edit':2 if passed else 0,'preserve':2,'realism':5,'extra':0}
                obj = {'sha256':sha,'pass':passed,'score':2.0 if passed else 1.0,
                       'check':{k:{'score':v} for k,v in scores.items()}}
                (folder/(tag+'.json')).write_text(json.dumps(obj),encoding='utf-8')
                method = 'best_check' if tag=='seed1' else 'retry' if tag=='retry1' else None
                if method:
                    entry['selected'][method]={'tag':tag,'sha256':sha}
                    item=next(i for i in public['items'] if i['id']==iid)
                    side=next(s for s in ('A','B') if entry[s]==method)
                    item[side]=sha[:24]+'.png'
            rows.append({'key':iid,'image_id':entry['photo_id'],'task':entry['task'],
                'seed_tags':['seed0','seed1','seed2','seed3'],'retry_steps':['seed0','retry1'],
                'best_check':'seed1','retry':'retry1','retry_passed':True,'retry_last_passed':True})
        results=('\n'.join(json.dumps(r) for r in rows)+'\n').encode(); result_sha=hashlib.sha256(results).hexdigest()
        (directory/'results.jsonl').write_bytes(results)
        lock=json.dumps({'policy':policy}).encode();(directory/'LOCK.json').write_bytes(lock)
        (directory/'COMPLETE.json').write_text(json.dumps({'completed_jobs':34,'results_sha256':result_sha}),encoding='utf-8')
        private['conditions'][condition]={'result_sha256':result_sha,'lock_sha256':hashlib.sha256(lock).hexdigest()}
    return private


class JoinTests(unittest.TestCase):
    def test_confusion_matrix_denominators_are_not_interchanged(self):
        m=join.metrics([(True,False,''),(True,True,''),(False,False,''),(False,False,'')])
        self.assertEqual(m['false_acceptance_given_checker_pass'],.5)
        self.assertEqual(m['false_positive_given_author_fail'],1/3)
        self.assertEqual(m['author_joint_success_rate'],.25)
        self.assertEqual(m['checker_minus_author_rate'],.25)

    def test_unknown_bounds_preserve_all_planned_outputs(self):
        m=join.metrics([(True,False,''),(True,None,'unsure'),(False,None,'missing'),(False,True,'')])
        self.assertIsNone(m['false_acceptance_given_checker_pass'])
        self.assertIsNone(m['author_joint_success_rate'])
        self.assertIsNone(m['false_positive_given_author_fail'])
        self.assertEqual(m['false_acceptance_identification_bounds'],[.5,1])
        self.assertEqual(m['author_joint_success_identification_bounds'],[.25,.75])
        self.assertEqual(m['checker_minus_author_identification_bounds'],[-.25,.25])
        self.assertEqual(m['counts']['unknown_missing'],1)
        self.assertEqual(m['counts']['unknown_unsure'],1)

    def test_no_checker_accepts_is_undefined_not_zero_false_acceptance(self):
        m=join.metrics([(False,False,''),(False,True,'')])
        self.assertIsNone(m['false_acceptance_given_checker_pass'])
        self.assertEqual(m['false_acceptance_identification_bounds'],[None,None])
        self.assertEqual(m['false_positive_given_author_fail'],0)

    def test_false_acceptance_known_if_only_checker_rejects_are_unknown(self):
        m=join.metrics([(True,False,''),(False,None,'unsure')])
        self.assertEqual(m['false_acceptance_given_checker_pass'],1)
        self.assertIsNone(m['false_positive_given_author_fail'])

    def test_fixed_author_panel_thresholds_individually(self):
        public,private,roster,exports,metadata=prepared(2)
        for iid in private['items']:set_method(private,exports[1],iid,'retry',False)
        r=join.analyze(public,private,roster,exports,metadata,'package-receipt')
        m=r['conditions']['tuned']['methods']['retry']['overall']
        self.assertEqual(m['author_joint_success_rate'],.5)
        self.assertEqual(m['false_acceptance_given_checker_pass'],.5)
        self.assertEqual(m['fixed_author_output_denominator'],68)
        self.assertEqual(m['generation_calls']['total'],68)
        self.assertEqual(m['photo_count'],20)

    def test_case_weighting_is_not_equal_photo_weighting(self):
        public,private,roster,exports,metadata=prepared()
        for iid,e in private['items'].items():
            set_method(private,exports[0],iid,'retry',int(e['photo_id'].rsplit('-',1)[1])<14)
        r=join.analyze(public,private,roster,exports,metadata,'package-receipt')
        self.assertEqual(r['conditions']['tuned']['methods']['retry']['overall']['author_joint_success_rate'],28/34)

    def test_missing_export_and_unsure_widen_bounds_not_drop_rater(self):
        public,private,roster,exports,metadata=prepared(2)
        exports.pop()
        r=join.analyze(public,private,roster,exports,metadata,'package-receipt')
        m=r['conditions']['tuned']['methods']['retry']['overall']
        self.assertEqual(m['author_joint_success_identification_bounds'],[.5,1])
        self.assertEqual(m['counts']['unknown_missing'],34)
        side=next(s for s in ('A','B') if next(iter(private['items'].values()))[s]=='retry')
        iid=next(iter(private['items']));exports[0]['responses'][iid][side]['realism']='unclear'
        r=join.analyze(public,private,roster,exports,metadata,'package-receipt')
        self.assertEqual(r['conditions']['tuned']['methods']['retry']['overall']['counts']['unknown_unsure'],1)

    def test_identical_conflict_withholds_not_recodes(self):
        public,private,roster,exports,metadata=prepared()
        iid=next(i for i,e in private['items'].items() if e['condition']=='tuned')
        make_identical(public,private,iid)
        metadata['items'][iid]['outputs']['best_check']['output_sha256']=private['items'][iid]['selected']['best_check']['sha256']
        set_method(private,exports[0],iid,'retry',False)
        before=copy.deepcopy(exports)
        r=join.analyze(public,private,roster,exports,metadata,'package-receipt')
        self.assertEqual(r['conditions']['tuned']['status'],'withheld_identical_output_conflict')
        self.assertIsNone(r['conditions']['tuned']['methods'])
        self.assertIsNotNone(r['conditions']['baseline']['methods'])
        self.assertEqual(exports,before)

    def test_ab_permutation_is_invariant(self):
        public,private,roster,exports,metadata=prepared()
        for iid in private['items']:set_method(private,exports[0],iid,'retry',False)
        a=join.analyze(public,private,roster,exports,metadata,'package-receipt')
        for item in public['items']:
            iid=item['id'];e=private['items'][iid]
            item['A'],item['B']=item['B'],item['A'];e['A'],e['B']=e['B'],e['A']
            row=exports[0]['responses'][iid];row['A'],row['B']=row['B'],row['A']
        b=join.analyze(public,private,roster,exports,metadata,'package-receipt')
        self.assertEqual(a,b)

    def test_metadata_identity_hash_budget_receipt_and_bool_validation(self):
        for kind in ('hash','case','source','version','budget','boolean','receipt','missing'):
            with self.subTest(kind=kind):
                public,private,roster,exports,metadata=prepared();iid=next(iter(metadata['items']))
                row=metadata['items'][iid];out=row['outputs']['retry']
                if kind=='hash':out['output_sha256']='f'*64
                if kind=='case':row['task']='T2' if row['task']=='T1-B' else 'T1-B'
                if kind=='source':metadata['source_provenance']['tuned']['lock_sha256']='wrong'
                if kind=='version':metadata['study_version']='wrong'
                if kind=='budget':out['generation_count']=0
                if kind=='boolean':out['checker_pass']=1
                if kind=='receipt':metadata['package_lock_sha256']='wrong'
                if kind=='missing':del metadata['items'][iid]
                with self.assertRaises(ValueError):join.analyze(public,private,roster,exports,metadata,'package-receipt')

    def test_real_extractor_on_full_synthetic_run(self):
        public,private,roster,exports=fixture()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);build_raw_run(root,public,private)
            metadata=join.extract_metadata(root,public,private,'receipt')
            self.assertEqual(len(metadata['items']),68)
            self.assertEqual(metadata['source_provenance']['tuned']['verified_candidate_count'],170)
            r=join.analyze(public,private,roster,exports,metadata,'receipt')
            self.assertEqual(r['conditions']['tuned']['methods']['retry']['overall']['generation_calls']['total'],68)

    def test_extractor_rejects_corrupt_candidate_bytes(self):
        public,private,_,_=fixture()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);build_raw_run(root,public,private)
            next(root.rglob('seed0.png')).write_bytes(b'CORRUPTED')
            with self.assertRaisesRegex(ValueError,'hash mismatch'):join.extract_metadata(root,public,private,'receipt')

    def test_extractor_recomputes_checker_verdict_and_score(self):
        for field,value in (('pass',False),('score',1.9)):
            public,private,_,_=fixture()
            with tempfile.TemporaryDirectory() as temp:
                root=Path(temp);build_raw_run(root,public,private)
                path=next(root.rglob('seed1.json'));obj=json.loads(path.read_text());obj[field]=value;path.write_text(json.dumps(obj))
                with self.assertRaises(ValueError):join.extract_metadata(root,public,private,'receipt')

    def test_extractor_rejects_modified_results(self):
        public,private,_,_=fixture()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);build_raw_run(root,public,private)
            path=root/'tuned'/'results.jsonl';path.write_bytes(path.read_bytes()+b'\n')
            with self.assertRaisesRegex(ValueError,'differs'):join.extract_metadata(root,public,private,'receipt')

    def test_consistent_score_edit_is_snapshot_not_historical_verification(self):
        public,private,_,_=fixture()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);build_raw_run(root,public,private)
            before=join.extract_metadata(root,public,private,'receipt')
            path=next((root/'tuned').rglob('seed1.json'));obj=json.loads(path.read_text())
            obj['check']['realism']['score']=4.8;obj['score']=1.975
            path.write_text(json.dumps(obj))
            after=join.extract_metadata(root,public,private,'receipt')
            self.assertNotEqual(before['source_provenance']['tuned']['candidate_metadata_sha256'],after['source_provenance']['tuned']['candidate_metadata_sha256'])
            self.assertIn('no independently preserved historical',after['source_provenance']['tuned']['candidate_metadata_assurance'])

    def test_first_maximum_tie_and_retry_shared_start_rules(self):
        public,private,_,_=fixture()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);build_raw_run(root,public,private)
            path=next((root/'tuned').rglob('seed2.json'));obj=json.loads(path.read_text())
            obj['check']['edit']['score']=2;obj['pass']=True;obj['score']=2.0;path.write_text(json.dumps(obj))
            after=join.extract_metadata(root,public,private,'receipt')
            self.assertEqual(after['items'][path.parent.name]['outputs']['best_check']['candidate_tag'],'seed1')
            results=root/'tuned'/'results.jsonl';rows=[json.loads(x) for x in results.read_text().splitlines()]
            rows[0]['retry_steps']=['seed2','retry1']
            body=('\n'.join(json.dumps(x) for x in rows)+'\n').encode();results.write_bytes(body)
            sha=hashlib.sha256(body).hexdigest();private['conditions']['tuned']['result_sha256']=sha
            (root/'tuned'/'COMPLETE.json').write_text(json.dumps({'completed_jobs':34,'results_sha256':sha}))
            with self.assertRaisesRegex(ValueError,'first candidate'):join.extract_metadata(root,public,private,'receipt')

    def test_selected_failure_and_last_pass_are_distinct(self):
        public,private,_,_=fixture()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);build_raw_run(root,public,private)
            iid=next(i for i,e in private['items'].items() if e['condition']=='tuned')
            folder=root/'tuned'/'candidates'/iid
            values={'seed0':({'edit':1.4,'preserve':2,'realism':5,'extra':0},False,1.7),
                    'retry1':({'edit':1.5,'preserve':1.5,'realism':3,'extra':.5},True,1.125)}
            for tag,(scores,passed,score) in values.items():
                path=folder/(tag+'.json');obj=json.loads(path.read_text())
                obj.update({'check':{k:{'score':v} for k,v in scores.items()},'pass':passed,'score':score})
                path.write_text(json.dumps(obj))
            entry=private['items'][iid];sha=hashlib.sha256((folder/'seed0.png').read_bytes()).hexdigest()
            entry['selected']['retry']={'tag':'seed0','sha256':sha}
            item=next(i for i in public['items'] if i['id']==iid)
            side=next(s for s in ('A','B') if entry[s]=='retry');item[side]=sha[:24]+'.png'
            results=root/'tuned'/'results.jsonl';rows=[json.loads(x) for x in results.read_text().splitlines()]
            row=next(r for r in rows if r['key']==iid);row.update({'retry':'seed0','retry_passed':False})
            body=('\n'.join(json.dumps(x) for x in rows)+'\n').encode();results.write_bytes(body)
            rsha=hashlib.sha256(body).hexdigest();private['conditions']['tuned']['result_sha256']=rsha
            (root/'tuned'/'COMPLETE.json').write_text(json.dumps({'completed_jobs':34,'results_sha256':rsha}))
            out=join.extract_metadata(root,public,private,'receipt')['items'][iid]['outputs']['retry']
            self.assertFalse(out['checker_pass']);self.assertEqual(out['candidate_tag'],'seed0')

    def test_successful_cli_round_trip_and_endpoint_hash_receipt(self):
        public,private,roster,exports=fixture()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);run=root/'run';run.mkdir();build_raw_run(run,public,private)
            data=root/'data';(data/'media').mkdir(parents=True)
            for item in public['items']:
                e=private['items'][item['id']]
                (data/'media'/item['original']).write_bytes(('SYNTHETIC ORIGINAL '+e['photo_id']).encode())
                for side in ('A','B'):
                    method=e[side];src=run/e['condition']/'candidates'/e['source_job_key']/(e['selected'][method]['tag']+'.png')
                    shutil.copyfile(src,data/'media'/item[side])
            for name,obj in (('public_manifest.json',public),('private_map.json',private)):(data/name).write_text(json.dumps(obj))
            files={str(p.relative_to(data)).replace('\\','/'):{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in data.rglob('*') if p.is_file()}
            (data/'PACKAGE_LOCK.json').write_text(json.dumps({'version':public['version'],'files':files}))
            metadata=root/'metadata.json';report=root/'report.json';rp=root/'roster.json';ep=root/'export.json'
            rp.write_text(json.dumps(roster));ep.write_text(json.dumps(exports[0]))
            self.assertEqual(join.main(['extract','--data-dir',str(data),'--run-root',str(run),'--output',str(metadata)]),0)
            receipt=hashlib.sha256(metadata.read_bytes()).hexdigest()
            self.assertEqual(join.main(['analyze','--data-dir',str(data),'--metadata',str(metadata),'--metadata-sha256',receipt,'--roster',str(rp),'--exports',str(ep),'--output',str(report)]),0)
            result=json.loads(report.read_text())
            expected=hashlib.sha256((Path(join.compare.__file__).parent/'endpoint.py').read_bytes()).hexdigest()
            self.assertEqual(result['reproducibility']['endpoint_sha256'],expected)
            self.assertEqual(result['conditions']['tuned']['methods']['retry']['overall']['false_acceptance_given_checker_pass'],0)

    def test_cli_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)/'keep.json';out.write_bytes(b'KEEP')
            code=join.main(['extract','--data-dir',temp,'--run-root',temp,'--output',str(out)])
            self.assertEqual(code,1);self.assertEqual(out.read_bytes(),b'KEEP')

    def test_cli_rejects_missing_or_mismatched_metadata_receipt(self):
        public,private,roster,exports,metadata=prepared()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);mp=root/'metadata.json';rp=root/'roster.json';out=root/'result.json'
            mp.write_text(json.dumps(metadata));rp.write_text(json.dumps(roster))
            with mock.patch.object(join.compare,'load_package',return_value=(public,private,'package-receipt')):
                for receipt in ([],['--metadata-sha256','wrong']):
                    self.assertEqual(join.main(['analyze','--data-dir',temp,'--metadata',str(mp),'--roster',str(rp),'--output',str(out)]+receipt),1)
                    self.assertFalse(out.exists())


if __name__ == '__main__':unittest.main()
