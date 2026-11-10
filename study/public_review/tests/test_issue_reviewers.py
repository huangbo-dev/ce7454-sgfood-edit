import contextlib, hashlib, importlib.util, io, json, os, pathlib, stat, tempfile, unittest
from unittest import mock
import issue_reviewers as issuer
NOW=1800000000
PLAN=[{'reviewer_id':'TEST_ONLY_01','email':'synthetic.only.01@e.ntu.edu.sg','expires_at':NOW+3600},{'reviewer_id':'TEST_ONLY_02','email':'synthetic.only.02@e.ntu.edu.sg','expires_at':NOW+7200}]
# Deliberately fake, deterministic, and never usable in an actual app roster.
FAKES=['TEST_ONLY_NOT_A_REAL_ACCESS_CODE_'.ljust(43,'A'),'TEST_ONLY_NOT_A_REAL_ACCESS_CODE_'.ljust(43,'B')]
class Tests(unittest.TestCase):
 def test_hash_only_roster(self):
  roster,delivery=issuer.prepare(PLAN,NOW,iter(FAKES).__next__)
  for row,code in zip(roster,FAKES):
   self.assertEqual(row['code_sha256'],hashlib.sha256(code.encode()).hexdigest())
   self.assertNotIn(code,json.dumps(roster)); self.assertFalse(row['revoked'])
  self.assertEqual(len(delivery),2)
  for plan,code,owner in zip(PLAN,FAKES,delivery):
   self.assertEqual(owner,{**plan,'access_code':code})
   self.assertNotIn(plan['email'],json.dumps(roster))
  for row in roster: self.assertEqual(set(row),{'reviewer_id','expires_at','code_sha256','revoked'})
 def test_invalid_plans(self):
  bad=[[],PLAN*2,[{'reviewer_id':'short','expires_at':NOW+1}],[{'reviewer_id':'TEST_ONLY_01','expires_at':NOW}],[{'reviewer_id':'TEST_ONLY_01','expires_at':NOW+30*86400+1}],[{'reviewer_id':'TEST_ONLY_01','expires_at':float('nan')}],[{'reviewer_id':'TEST_ONLY_01','expires_at':True}],[{'reviewer_id':'TEST_ONLY_01','expires_at':NOW+1,'extra':1}], [PLAN[0],{**PLAN[0],'reviewer_id':'test_only_01'}]]
  for plan in bad:
   with self.subTest(plan=plan),self.assertRaises(ValueError): issuer.validate(plan,NOW)
 def test_invalid_and_duplicate_emails(self):
  for email in ('x@example.com','x@ntu.edu.sg','x@e.ntu.edu.sg.evil','x+y@e.ntu.edu.sg',' x@e.ntu.edu.sg','x@e.ntu.edu.sg\n','.x@e.ntu.edu.sg','x..y@e.ntu.edu.sg','x.@e.ntu.edu.sg','a'*65+'@e.ntu.edu.sg',None):
   with self.subTest(email=email),self.assertRaises(ValueError): issuer.validate([{**PLAN[0],'email':email}],NOW)
  with self.assertRaises(ValueError): issuer.validate([PLAN[0],{**PLAN[1],'email':PLAN[0]['email'].upper()}],NOW)
 def test_expiry_and_id_validation_with_email(self):
  for field,value in [('expires_at',NOW),('expires_at',NOW+30*86400+1),('expires_at',float('inf')),('expires_at',True),('reviewer_id','../escape'),('reviewer_id','short')]:
   with self.subTest(field=field,value=value),self.assertRaises(ValueError): issuer.validate([{**PLAN[0],field:value}],NOW)
 def test_duplicate_token_rejected(self):
  with self.assertRaises(ValueError): issuer.prepare(PLAN,NOW,lambda:FAKES[0])
 def test_invalid_token_rejected(self):
  with self.assertRaises(ValueError): issuer.prepare(PLAN,NOW,lambda:'not a credential')
 def test_synthetic_files_no_stdout_no_overwrite(self):
  with tempfile.TemporaryDirectory() as t:
   dest=pathlib.Path(t)/'synthetic-only'; stdout=io.StringIO()
   # Bypass POSIX gate only for synthetic Windows fixtures. Real CLI remains POSIX-only.
   with mock.patch.object(issuer,'require_posix'),mock.patch.object(issuer,'check_parent_permissions'),contextlib.redirect_stdout(stdout):
    self.assertEqual(issuer.issue(PLAN,dest,NOW,iter(FAKES).__next__),2)
    with self.assertRaises(ValueError): issuer.issue(PLAN,dest,NOW,iter(FAKES).__next__)
   self.assertEqual(stdout.getvalue(),''); self.assertTrue((dest/'COMPLETE.json').exists())
   self.assertEqual(json.loads((dest/'owner_credentials.json').read_text()),[{**row,'access_code':code} for row,code in zip(PLAN,FAKES)])
   self.assertFalse((dest/'deliveries').exists())
   for row in PLAN: self.assertNotIn(row['email'],(dest/'credentials.json').read_text())
   self.assertNotIn(FAKES[0],(dest/'credentials.json').read_text())
   with self.assertRaises(FileExistsError): issuer.exclusive_write(dest/'credentials.json',{})
   if os.name=='posix':
    self.assertEqual(stat.S_IMODE(dest.stat().st_mode),0o700)
    for p in dest.rglob('*'):
     self.assertEqual(stat.S_IMODE(p.stat().st_mode),0o700 if p.is_dir() else 0o600)
 def test_symlinks_rejected(self):
  with mock.patch.object(pathlib.Path,'is_symlink',return_value=True):
   with self.assertRaises(ValueError): issuer.no_links(pathlib.Path('/synthetic'))
 def test_real_platform_gate(self):
  if os.name!='posix':
   with self.assertRaises(ValueError): issuer.require_posix()
  else: issuer.require_posix()
if __name__=='__main__': unittest.main()
