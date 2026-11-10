import os,hashlib,http.client,importlib.util,json,pathlib,secrets,sqlite3,tempfile,threading,time,unittest,uuid
ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('server',ROOT/'backend/server.py'); s=importlib.util.module_from_spec(spec); spec.loader.exec_module(s)
class Tests(unittest.TestCase):
 def setUp(self):
  os.umask(0o077); self.tmp=tempfile.TemporaryDirectory(); self.root=pathlib.Path(self.tmp.name)
  for n in ('data/media','private','frontend'): (self.root/n).mkdir(parents=True)
  for n in ('index.html','app.js','style.css'): (self.root/'frontend'/n).write_text('fixture')
  (self.root/'data/media/fixture.png').write_bytes(b'fixture')
  (self.root/'data/private_map.json').write_text('{}')
  (self.root/'data/public_manifest.json').write_text(json.dumps({'version':'fixture','items':[{'id':'case','original':'fixture.png','A':'fixture.png','B':'fixture.png'}]}))
  files={p.relative_to(self.root/'data').as_posix():{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in (self.root/'data').rglob('*') if p.is_file()}
  (self.root/'data/PACKAGE_LOCK.json').write_text(json.dumps({'version':'fixture','files':files}))
  self.code=secrets.token_urlsafe(32); self.other=secrets.token_urlsafe(32)
  self.rows=[{'reviewer_id':name,'code_sha256':hashlib.sha256(code.encode()).hexdigest(),'expires_at':time.time()+3600,'revoked':False} for name,code in [('reviewer1',self.code),('reviewer2',self.other)]]; self.write_roster()
  self.app=s.App(self.root,'http://127.0.0.1:8792'); self.http=s.Server(('127.0.0.1',0),self.app); self.thread=threading.Thread(target=self.http.serve_forever,daemon=True); self.thread.start()
 def tearDown(self): self.http.shutdown(); self.http.server_close(); self.thread.join(); self.tmp.cleanup()
 def write_roster(self): (self.root/'private/credentials.json').write_text(json.dumps(self.rows))
 def call(self,path,obj=None,token=None,method='POST',extra=None):
  c=http.client.HTTPConnection('127.0.0.1',self.http.server_port,timeout=3); headers={'Host':self.app.host,'Origin':self.app.origin,'Content-Type':'application/json'}
  if token: headers['Authorization']='Bearer '+token
  if extra: headers.update(extra)
  c.request(method,path,None if obj is None else json.dumps(obj),headers); r=c.getresponse(); body=r.read(); h=dict(r.getheaders()); c.close(); self.assertNotIn('Set-Cookie',h); self.assertEqual(h['Cache-Control'],'no-store'); return r.status,body,h
 def login(self,code=None):
  status,b,_=self.call('/api/login',{'code':code or self.code}); self.assertEqual(status,200); return json.loads(b)['token']
 def event(self,kind,token,**kw): return self.call('/api/'+kind,{'submission_id':str(uuid.uuid4()),**kw},token)
 def ready(self):
  t=self.login(); self.assertEqual(self.event('familiarity',t,payload={'prior_familiarity':'Unsure','note':''})[0],200); self.assertEqual(self.event('exposure',t,item_id='case')[0],200); return t
 def payload(self): return {a:{**{q:'Unsure' for q in s.QUESTIONS},'note':''} for a in ('A','B')}
 def test_protection_and_methods(self):
  for p in ('/api/manifest','/api/media','/api/export','/api/state'): self.assertEqual(self.call(p,{'name':'fixture.png'} if p.endswith('media') else {})[0],401)
  for p in ('/private/credentials.json','/data/private_map.json','/data/media/fixture.png','/../backend/server.py','/api/manifest'): self.assertEqual(self.call(p,method='GET')[0],404)
  self.assertEqual(self.call('/',method='GET',extra={'Cookie':'tutorial=unrelated'})[0],200)
  self.assertEqual(self.call('/api/state',{},extra={'Cookie':'session=anything'})[0],401)
  for method in ('HEAD','OPTIONS','TRACE','PUT','DELETE'): self.assertEqual(self.call('/',method=method)[0],405)
 def test_external_link_public_navigation(self):
  headers={'Origin':'https://external.example','Sec-Fetch-Site':'cross-site'}
  for path in ('/','/app.js','/style.css'):
   status,body,response_headers=self.call(path,method='GET',extra=headers)
   self.assertEqual(status,200); self.assertNotIn('Access-Control-Allow-Origin',response_headers)
  self.assertEqual(self.call('/api/login',{'code':self.code},extra=headers)[0],403)
  self.assertEqual(self.call('/api/manifest',method='GET',extra=headers)[0],404)
 def test_origin_host_cookie_and_json(self):
  for headers,status in [({'Origin':'https://evil.test'},403),({'Host':'evil.test'},400),({'Content-Type':'text/plain'},415),({'Sec-Fetch-Site':'cross-site'},403)]: self.assertEqual(self.call('/api/login',{'code':self.code},extra=headers)[0],status)
  self.assertEqual(self.call('/api/login',{'code':'x'*17000})[0],413)
 def test_familiarity_media_audit(self):
  t=self.login(); self.assertEqual(self.call('/api/media',{'name':'fixture.png'},t)[0],409)
  self.event('familiarity',t,payload={'prior_familiarity':'Yes','note':'fixture'})
  self.assertEqual(self.call('/api/media',{'name':'fixture.png'},t)[0],200)
  self.assertEqual(self.call('/api/media',{'name':'../private_map.json'},t)[0],404)
  h=json.loads(self.call('/api/export',{},t)[1])['events']; self.assertEqual([x['kind'] for x in h],['familiarity','media_request'])
 def test_revision_idempotency_and_isolation(self):
  t=self.ready(); obj={'submission_id':str(uuid.uuid4()),'item_id':'case','base_revision':0,'payload':self.payload()}
  self.assertEqual(self.call('/api/rating',obj,t)[0],200); self.assertTrue(json.loads(self.call('/api/rating',obj,t)[1])['duplicate'])
  obj['submission_id']=str(uuid.uuid4()); self.assertEqual(self.call('/api/rating',obj,t)[0],409)
  obj['base_revision']=1; self.assertEqual(self.call('/api/rating',obj,t)[0],200)
  state=json.loads(self.call('/api/state',{},t)[1]); self.assertEqual(state['ratings'][0]['revision'],2)
  t2=self.login(self.other); self.assertEqual(json.loads(self.call('/api/export',{},t2)[1])['events'],[])
  with self.app.db() as c:
   with self.assertRaises(sqlite3.IntegrityError): c.execute('DELETE FROM events')
 def test_numeric_rubric_rejected(self):
  t=self.ready(); p=self.payload(); p['A']['Change achieved']=2
  self.assertEqual(self.event('rating',t,item_id='case',base_revision=0,payload=p)[0],400)
 def test_expiry_revocation_logout(self):
  t=self.login(); self.rows[0]['revoked']=True; self.write_roster(); self.assertEqual(self.call('/api/state',{},t)[0],401)
  self.rows[0]['revoked']=False; self.write_roster(); t=self.login(); self.assertEqual(self.call('/api/logout',{},t)[0],200); self.assertEqual(self.call('/api/state',{},t)[0],401)
  t=self.login(); self.app.sessions[hashlib.sha256(t.encode()).hexdigest()]['expires_at']=0; self.assertEqual(self.call('/api/state',{},t)[0],401)
 def test_login_limit_and_no_credential_storage(self):
  for _ in range(5): self.assertEqual(self.call('/api/login',{'code':'x'*43})[0],401)
  self.assertEqual(self.call('/api/login',{'code':'x'*43})[0],429)
  self.assertNotIn(self.code,(self.root/'private/credentials.json').read_text())
 def test_global_malformed_login_limit(self):
  for _ in range(30): self.assertEqual(self.call('/api/login',{'code':'bad'})[0],401)
  self.assertEqual(self.call('/api/login',{'code':self.code})[0],429)
 def test_missing_roster_never_creates_database(self):
  (self.root/'private/credentials.json').unlink(); (self.root/'private/ratings.sqlite3').unlink()
  with self.assertRaises(FileNotFoundError): s.App(self.root,self.app.origin)
  self.assertFalse((self.root/'private/ratings.sqlite3').exists())
 def test_fail_closed(self):
  (self.root/'data/media/fixture.png').write_bytes(b'changed')
  with self.assertRaises(ValueError): s.App(self.root,self.app.origin)
  (self.root/'data/media/fixture.png').write_bytes(b'fixture'); (self.root/'private/credentials.json').unlink()
  with self.assertRaises(FileNotFoundError): s.App(self.root,self.app.origin)
 def test_concurrent_idempotency(self):
  t=self.ready(); o={'submission_id':str(uuid.uuid4()),'item_id':'case','base_revision':0,'payload':self.payload()}; results=[]
  threads=[threading.Thread(target=lambda:results.append(self.call('/api/rating',o,t)[0])) for _ in range(6)]
  [x.start() for x in threads]; [x.join() for x in threads]; self.assertEqual(results,[200]*6); self.assertEqual(len([x for x in self.app.history('reviewer1') if x['kind']=='rating']),1)
if __name__=='__main__': unittest.main()
