"""Invented E3 locks/ratings only; no real research-data reads."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from analysis import checker_join as join
from synthetic_fixture import fixture
from test_checker_join import build_raw_run


def make_snapshot(root, private):
    folder=root/'tuned';files={};cases=[]
    for name in ('results.jsonl','LOCK.json','COMPLETE.json'):
        files[name]=hashlib.sha256((folder/name).read_bytes()).hexdigest()
    for line in (folder/'results.jsonl').read_text().splitlines():
        row=json.loads(line);records={}
        for tag in sorted(set(row['seed_tags'])|{row['retry']}):
            stem='candidates/'+row['key']+'/'+tag
            for suffix in ('.png','.json'):files[stem+suffix]=hashlib.sha256((folder/(stem+suffix)).read_bytes()).hexdigest()
            records[tag]=json.loads((folder/(stem+'.json')).read_bytes());records[tag]['tag']=tag
        cases.append({'key':row['key'],'photo_id':row['image_id'],'task':row['task'],
            'seed_tags':row['seed_tags'],'best_check':row['best_check'],'retry':row['retry'],'records':records})
    return {'study':'E3','created_utc':'2026-11-09T17:25:29Z',
        'protocol':{'e3':{'condition':'tuned'},'e4':{'checker_thresholds':{'edit':1.5,'preserve':1.5,'realism':3.0,'extra':.5}}},
        'source':{'files':files,'cases':cases}}


class SnapshotTests(unittest.TestCase):
    def setup_files(self,root):
        public,private,roster,exports=fixture()
        run=root/'run';run.mkdir();build_raw_run(run,public,private)
        snapshot=make_snapshot(run,private);path=root/'snapshot.json'
        path.write_text(json.dumps(snapshot));receipt=hashlib.sha256(path.read_bytes()).hexdigest()
        return public,private,roster,exports,snapshot,path,receipt

    def test_recovers_primary_without_fabricating_baseline_or_retry_cost(self):
        with tempfile.TemporaryDirectory() as temp:
            p,m,roster,exports,snapshot,path,receipt=self.setup_files(Path(temp))
            before=copy.deepcopy((p,m,exports))
            data=join.extract_e3_snapshot(path,receipt,p,m,'package')
            self.assertEqual(data['available_conditions'],['tuned'])
            self.assertEqual(len(data['items']),34)
            self.assertEqual(data['source_provenance']['tuned']['verified_embedded_candidate_records'],170)
            report=join.analyze(p,m,roster,exports,data,'package')
            self.assertEqual(report['conditions']['baseline']['status'],'checker_metadata_unavailable')
            costs=report['conditions']['tuned']['methods']['retry']['overall']['generation_calls']
            self.assertIsNone(costs['total']);self.assertIsNone(costs['mean_per_case']);self.assertEqual(costs['unknown_cases'],34)
            self.assertEqual(report['conditions']['tuned']['methods']['best_check']['overall']['generation_calls']['total'],136)
            self.assertEqual((p,m,exports),before)

    def test_rejects_missing_or_changed_external_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            p,m,_,_,_,path,receipt=self.setup_files(Path(temp))
            for bad in (None,'x'*64,'0'*64):
                with self.assertRaisesRegex(ValueError,'receipt'):join.extract_e3_snapshot(path,bad,p,m,'package')
            path.write_text(path.read_text()+' ')
            with self.assertRaisesRegex(ValueError,'receipt'):join.extract_e3_snapshot(path,receipt,p,m,'package')

    def test_rejects_changed_case_hash_score_selector_or_policy(self):
        with tempfile.TemporaryDirectory() as temp:
            p,m,_,_,original,path,_=self.setup_files(Path(temp))
            for kind in ('case','image','score','selector','policy','source','duplicate','record_receipt','wrong_condition'):
                with self.subTest(kind=kind):
                    obj=copy.deepcopy(original);case=obj['source']['cases'][0]
                    if kind=='case':case['photo_id']='wrong'
                    if kind=='image':case['records']['seed1']['sha256']='f'*64
                    if kind=='score':case['records']['seed1']['score']=0
                    if kind=='selector':case['best_check']='seed2'
                    if kind=='policy':obj['protocol']['e4']['checker_thresholds']['edit']=1
                    if kind=='source':obj['source']['files']['results.jsonl']='0'*64
                    if kind=='duplicate':obj['source']['cases'][1]=copy.deepcopy(case)
                    if kind=='record_receipt':del obj['source']['files']['candidates/'+case['key']+'/seed1.json']
                    if kind=='wrong_condition':obj['protocol']['e3']['condition']='baseline'
                    path.write_text(json.dumps(obj));receipt=hashlib.sha256(path.read_bytes()).hexdigest()
                    with self.assertRaises(ValueError):join.extract_e3_snapshot(path,receipt,p,m,'package')

    def test_unknown_panel_stays_unknown_and_partial_record_sets_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            p,m,roster,exports,_,path,receipt=self.setup_files(Path(temp))
            metadata=join.extract_e3_snapshot(path,receipt,p,m,'package')
            report=join.analyze(p,m,roster,[],metadata,'package')
            result=report['conditions']['tuned']['methods']['retry']['overall']
            self.assertIsNone(result['author_joint_success_rate'])
            self.assertEqual(result['author_joint_success_identification_bounds'],[0,1])
            self.assertEqual(result['false_acceptance_identification_bounds'],[0,1])
            bad=copy.deepcopy(metadata);bad['items'].pop(next(iter(bad['items'])))
            with self.assertRaises(ValueError):join.validate_metadata(bad,p,m,'package')
            invented_cost=copy.deepcopy(metadata)
            first=next(iter(invented_cost['items'].values()))
            first['outputs']['retry']['generation_count']=2
            with self.assertRaisesRegex(ValueError,'generation count'):join.validate_metadata(invented_cost,p,m,'package')
            for field in ('e3_snapshot_sha256','snapshot_utc','verified_embedded_candidate_records'):
                bad=copy.deepcopy(metadata);del bad['source_provenance']['tuned'][field]
                with self.assertRaises(ValueError):join.validate_metadata(bad,p,m,'package')


if __name__=='__main__':unittest.main()
