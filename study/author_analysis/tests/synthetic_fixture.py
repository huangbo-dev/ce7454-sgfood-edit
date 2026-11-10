"""Invented ratings and invented image bytes only. Never research evidence."""
import copy
import hashlib
import json
from pathlib import Path


def sha(text): return hashlib.sha256(text.encode()).hexdigest()


def fixture(author_count=1):
    version='synthetic-only-v2'; items=[]; mapping={}
    for condition in ('tuned','baseline'):
        for i in range(20):
            photo=f'synthetic-photo-{i:02d}'
            qa='accept' if i<12 or i==14 else 'needs-review'
            for task in (('T1-B','T2') if i<14 else ('T1-B',)):
                iid=sha(f'{condition}|{photo}|{task}')[:20]
                sides=('retry','best_check') if i%2 else ('best_check','retry')
                selected={m:{'sha256':sha(f'{iid}|{m}')} for m in sides}
                items.append({'id':iid,'section':'Round 1' if condition=='tuned' else 'Round 2','task_text':'SYNTHETIC TEST ONLY',
                    'original':sha(photo)[:24]+'.png','A':selected[sides[0]]['sha256'][:24]+'.png','B':selected[sides[1]]['sha256'][:24]+'.png'})
                mapping[iid]={'condition':condition,'photo_id':photo,'task':task,'prior_mask_qa':qa,
                    'A':sides[0],'B':sides[1],'selected':selected,'identical_outputs':False}
    public={'version':version,'items':items}
    private={'version':version,'rubric_schema':'sgfood-judge-v1-author-portal-v2',
        'joint_success':'edit=2 AND preserve=2 AND realism>=3 AND extra=0','items':mapping}
    roster={'schema_version':1,'study_version':version,'locked_before_collection':True,'locked_utc':'2026-11-01T00:00:00Z',
        'authors':[{'id':f'synthetic-author-{i}','role':'author','prior_exposure':'Invented fixture, no real photos or author.'} for i in range(author_count)]}
    exports=[]
    for author in roster['authors']:
        rows={}
        for item in items:
            iid=item['id'];rating=dict(edit=2,preserve=2,realism=5,extra=0)
            rows[iid]={'version':version,'item_id':iid,'submission_id':sha(author['id']+iid),
                'base_revision':0,'revision':1,'created_utc':'2026-11-02T00:00:00Z',
                'A':dict(rating),'B':dict(rating),'preference':'tie','certainty':'uncertain','note':'SYNTHETIC SOFTWARE TEST ONLY'}
        exports.append({'rater':author['id'],'version':version,'responses':rows})
    return public,private,roster,exports


def set_method(private, export, iid, method, success):
    side=next(s for s in ('A','B') if private['items'][iid][s]==method)
    export['responses'][iid][side]=dict(edit=2 if success else 0,preserve=2,realism=5,extra=0)


def make_identical(public, private, iid):
    entry=private['items'][iid]
    digest=entry['selected']['retry']['sha256']
    entry['selected']['best_check']['sha256']=digest;entry['identical_outputs']=True
    item=next(x for x in public['items'] if x['id']==iid)
    item['A']=item['B']=digest[:24]+'.png'


def write_package(root,public,private):
    root=Path(root);data=root/'data';(data/'media').mkdir(parents=True)
    # Content hashes and names are made self-consistent for CLI tests, without
    # including any real photos or pretending these bytes are renderable images.
    public=copy.deepcopy(public);private=copy.deepcopy(private)
    for item in public['items']:
        entry=private['items'][item['id']]
        for key in ('original','A','B'):
            label=entry['photo_id'] if key=='original' else item['id']+entry[key]
            if key!='original' and entry['identical_outputs']:label=item['id']+'identical'
            content=('SYNTHETIC NON-IMAGE BYTES: '+label).encode()
            digest=hashlib.sha256(content).hexdigest();name=digest[:24]+'.png'
            (data/'media'/name).write_bytes(content);item[key]=name
            if key!='original':entry['selected'][entry[key]]['sha256']=digest
    for name,obj in (('public_manifest.json',public),('private_map.json',private)):
        (data/name).write_text(json.dumps(obj),encoding='utf-8')
    files={str(p.relative_to(data)).replace('\\','/'):{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in data.rglob('*') if p.is_file()}
    (data/'PACKAGE_LOCK.json').write_text(json.dumps({'version':public['version'],'files':files}),encoding='utf-8')
    return data
