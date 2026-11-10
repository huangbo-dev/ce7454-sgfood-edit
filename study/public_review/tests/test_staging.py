import hashlib,importlib.util,json,pathlib,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('stage',ROOT/'stage_spark.py'); stage=importlib.util.module_from_spec(spec); spec.loader.exec_module(stage)
class StageTests(unittest.TestCase):
 def test_verified_copy_and_collision(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=pathlib.Path(tmp); bundle=p/'bundle'; media=p/'media'; bundle.mkdir(); media.mkdir()
   for name in ('data','backend','frontend','tests','evidence'): (bundle/name).mkdir()
   for name in ('README.md','stage_spark.py'): (bundle/name).write_text('fixture')
   image='a'*24+'.png'; (media/image).write_bytes(b'fixture')
   files={'media/'+image:{'bytes':7,'sha256':hashlib.sha256(b'fixture').hexdigest()}}
   for name in ('public_manifest.json','private_map.json'):
    (bundle/'data'/name).write_text('{}'); files[name]={'bytes':2,'sha256':hashlib.sha256(b'{}').hexdigest()}
   (bundle/'data/PACKAGE_LOCK.json').write_bytes(json.dumps({'version':'fixture','files':files},indent=2).replace('\n','\r\n').encode())
   code_lock={'data/PACKAGE_LOCK.json':hashlib.sha256((bundle/'data/PACKAGE_LOCK.json').read_bytes()).hexdigest(),'stage_spark.py':hashlib.sha256((bundle/'stage_spark.py').read_bytes()).hexdigest()}
   (bundle/'evidence/CANDIDATE_CODE_LOCK.json').write_text(json.dumps(code_lock))
   stage.stage(bundle,media,p/'dest'); self.assertEqual((p/'dest/data/media'/image).read_bytes(),b'fixture'); self.assertEqual(list((p/'dest/private').iterdir()),[])
   self.assertEqual((p/'dest/data/PACKAGE_LOCK.json').read_bytes(),(bundle/'data/PACKAGE_LOCK.json').read_bytes())
   for name,digest in json.loads((p/'dest/evidence/CANDIDATE_CODE_LOCK.json').read_text()).items(): self.assertEqual(hashlib.sha256((p/'dest'/name).read_bytes()).hexdigest(),digest)
   with self.assertRaises(ValueError): stage.stage(bundle,media,p/'dest')
   (media/image).write_bytes(b'altered')
   with self.assertRaises(ValueError): stage.stage(bundle,media,p/'bad')
   self.assertFalse((p/'bad').exists())
