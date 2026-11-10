"""Cookie-free, fail-closed review server. Never deploy without separate security review."""
import argparse, contextlib, os, stat, collections, hashlib, hmac, http.server, json, pathlib, re, secrets, socket, socketserver, sqlite3, threading, time
from urllib.parse import urlsplit
QUESTIONS=('Change achieved','Other food preserved','Looks plausible')
CHOICES=('Yes','No','Unsure')
MAX_BODY=16384
class Reject(Exception):
 def __init__(self,status=400): self.status=status

def read_json(p,limit=2000000):
 b=p.read_bytes()
 if len(b)>limit: raise ValueError('file too large')
 return json.loads(b)
def verify_package(root):
 data=root/'data'; lock=read_json(data/'PACKAGE_LOCK.json'); manifest=read_json(data/'public_manifest.json')
 if lock['version']!=manifest['version']: raise ValueError('version')
 for n,v in lock['files'].items():
  p=data/n
  if not p.resolve().is_relative_to(data.resolve()) or p.is_symlink(): raise ValueError('path')
  b=p.read_bytes()
  if len(b)!=v['bytes'] or hashlib.sha256(b).hexdigest()!=v['sha256']: raise ValueError('integrity')
 required={'public_manifest.json','private_map.json'}|{'media/'+i[k] for i in manifest['items'] for k in ('original','A','B')}
 if set(lock['files'])!=required: raise ValueError('lock coverage')
 return manifest
class App:
 def __init__(self,root,origin):
  self.root=pathlib.Path(root); self.origin=origin; u=urlsplit(origin)
  if u.scheme not in ('https','http') or u.path or u.query or u.fragment or u.username or (u.scheme=='http' and u.hostname!='127.0.0.1'): raise ValueError('origin')
  self.host=u.netloc; self.manifest=verify_package(self.root); self.items={i['id']:i for i in self.manifest['items']}; self.media={i[k] for i in self.items.values() for k in ('original','A','B')}
  self.roster_path=self.root/'private/credentials.json'; self.check_private(); self.roster() # fail before creating any database
  self.sessions={}; self.login_global=collections.deque(); self.buckets=collections.OrderedDict(); self.mutex=threading.RLock()
  self.db_path=self.root/'private/ratings.sqlite3'
  with self.db() as c:
   c.execute('CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY, reviewer TEXT NOT NULL, kind TEXT NOT NULL, item TEXT NOT NULL, revision INTEGER NOT NULL, submission TEXT NOT NULL, request TEXT NOT NULL, payload TEXT NOT NULL, created REAL NOT NULL, UNIQUE(reviewer,submission))')
   c.execute("CREATE TRIGGER IF NOT EXISTS immutable_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'append only'); END")
   c.execute("CREATE TRIGGER IF NOT EXISTS immutable_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'append only'); END")
 def check_private(self):
  private=self.root/'private'
  for p in (self.root,private,self.roster_path,private/'ratings.sqlite3'):
   if p.is_symlink(): raise ValueError('symlink')
  if os.name=='posix':
   if stat.S_IMODE(private.stat().st_mode)!=0o700: raise ValueError('private directory permissions')
   for p in (self.roster_path,private/'ratings.sqlite3'):
    if p.exists() and stat.S_IMODE(p.stat().st_mode)!=0o600: raise ValueError('private file permissions')
 def roster(self):
  rows=read_json(self.roster_path,262144)
  if not isinstance(rows,list) or not 1<=len(rows)<=100: raise ValueError('roster')
  hashes=set(); ids=set()
  for r in rows:
   if set(r)!={'reviewer_id','code_sha256','expires_at','revoked'} or not re.fullmatch(r'[A-Za-z0-9_-]{8,64}',r['reviewer_id']) or not re.fullmatch('[a-f0-9]{64}',r['code_sha256']) or type(r['expires_at']) not in (int,float) or type(r['revoked'])!=bool: raise ValueError('roster')
   if r['reviewer_id'] in ids or r['code_sha256'] in hashes: raise ValueError('duplicate')
   ids.add(r['reviewer_id']); hashes.add(r['code_sha256'])
  return rows
 @contextlib.contextmanager
 def db(self):
  if self.db_path.exists() and self.db_path.stat().st_size>50000000: raise Reject(503)
  c=sqlite3.connect(self.db_path,timeout=2)
  try:
   with c: yield c
  finally: c.close()
 def login(self,obj):
  now=time.time()
  with self.mutex:
   while self.login_global and now-self.login_global[0]>60: self.login_global.popleft()
   if len(self.login_global)>=30: raise Reject(429)
   self.login_global.append(now)
   if set(obj)!={'code'} or not isinstance(obj['code'],str) or not re.fullmatch(r'[A-Za-z0-9_-]{40,128}',obj['code']): raise Reject(401)
   key=hashlib.sha256(obj['code'].encode()).hexdigest()
   bucket=self.buckets.setdefault(key,collections.deque()); self.buckets.move_to_end(key)
   while len(self.buckets)>256: self.buckets.popitem(last=False)
   while bucket and now-bucket[0]>900: bucket.popleft()
   if len(bucket)>=5: raise Reject(429)
   bucket.append(now)
   match=None
   for r in self.roster():
    if hmac.compare_digest(r['code_sha256'],key) and not r['revoked'] and r['expires_at']>now: match=r
   if not match: raise Reject(401)
   self.sessions={k:v for k,v in self.sessions.items() if v['expires_at']>now and v['reviewer_id']!=match['reviewer_id']}
   if len(self.sessions)>=100: raise Reject(503)
   token=secrets.token_urlsafe(32); exp=min(now+900,match['expires_at']); self.sessions[hashlib.sha256(token.encode()).hexdigest()]={'reviewer_id':match['reviewer_id'],'expires_at':exp,'code_sha256':key}
   return {'token':token,'expires_at':exp}
 def auth(self,header):
  if not header or not re.fullmatch(r'Bearer [A-Za-z0-9_-]{43}',header): raise Reject(401)
  key=hashlib.sha256(header[7:].encode()).hexdigest()
  with self.mutex:
   s=self.sessions.get(key); now=time.time()
   if not s or s['expires_at']<=now: self.sessions.pop(key,None); raise Reject(401)
   if not any(r['reviewer_id']==s['reviewer_id'] and r['code_sha256']==s['code_sha256'] and not r['revoked'] and r['expires_at']>now for r in self.roster()): self.sessions.pop(key,None); raise Reject(401)
   return s['reviewer_id'],key
 def history(self,who):
  with self.db() as c:
   return [{'seq':r[0],'kind':r[1],'item_id':r[2],'revision':r[3],'submission_id':r[4],'payload':json.loads(r[5]),'created_at':r[6]} for r in c.execute('SELECT seq,kind,item,revision,submission,payload,created FROM events WHERE reviewer=? ORDER BY seq',(who,))]
 def event(self,who,kind,o):
  fields={'submission_id','payload'} if kind=='familiarity' else ({'submission_id','item_id'} if kind=='exposure' else {'submission_id','item_id','base_revision','payload'})
  if set(o)!=fields or not isinstance(o['submission_id'],str) or not re.fullmatch(r'[a-f0-9-]{36}',o['submission_id']): raise Reject()
  item=o.get('item_id',''); payload=o.get('payload',{})
  if kind!='familiarity' and item not in self.items: raise Reject()
  if kind=='familiarity':
   if not isinstance(payload,dict) or set(payload)!={'prior_familiarity','note'} or payload['prior_familiarity'] not in CHOICES or not isinstance(payload['note'],str) or len(payload['note'])>1000: raise Reject()
  if kind=='rating':
   if type(o['base_revision'])!=int or o['base_revision']<0 or not isinstance(payload,dict) or set(payload)!={'A','B'}: raise Reject()
   for side in ('A','B'):
    p=payload[side]
    if not isinstance(p,dict) or set(p)!=set(QUESTIONS)|{'note'} or any(p[q] not in CHOICES for q in QUESTIONS) or not isinstance(p['note'],str) or len(p['note'])>1000: raise Reject()
  request=json.dumps(o,sort_keys=True,separators=(',',':'))
  with self.mutex,self.db() as c:
   c.execute('BEGIN IMMEDIATE'); old=c.execute('SELECT request,revision,kind FROM events WHERE reviewer=? AND submission=?',(who,o['submission_id'])).fetchone()
   if old:
    if old[0]!=request or old[2]!=kind: raise Reject(409)
    return {'revision':old[1],'duplicate':True}
   if c.execute('SELECT COUNT(*) FROM events WHERE reviewer=?',(who,)).fetchone()[0]>=10000: raise Reject(429)
   if kind!='familiarity' and not c.execute("SELECT 1 FROM events WHERE reviewer=? AND kind='familiarity'",(who,)).fetchone(): raise Reject(409)
   if kind=='rating' and not c.execute("SELECT 1 FROM events WHERE reviewer=? AND kind='exposure' AND item=?",(who,item)).fetchone(): raise Reject(409)
   rev=c.execute('SELECT COALESCE(MAX(revision),0) FROM events WHERE reviewer=? AND kind=? AND item=?',(who,kind,item)).fetchone()[0]
   if kind=='rating' and rev!=o['base_revision']: raise Reject(409)
   c.execute('INSERT INTO events(reviewer,kind,item,revision,submission,request,payload,created) VALUES(?,?,?,?,?,?,?,?)',(who,kind,item,rev+1,o['submission_id'],request,json.dumps(payload),time.time()))
   return {'revision':rev+1,'duplicate':False}
 def dispatch(self,path,obj,auth):
  if path=='/api/login': return self.login(obj)
  who,key=self.auth(auth)
  if path=='/api/logout':
   if obj: raise Reject()
   with self.mutex: self.sessions.pop(key,None)
   return {'ok':True}
  if path=='/api/media':
   if set(obj)!={'name'} or obj['name'] not in self.media: raise Reject(404)
   with self.mutex,self.db() as c:
    if not c.execute("SELECT 1 FROM events WHERE reviewer=? AND kind='familiarity'",(who,)).fetchone(): raise Reject(409)
    if c.execute('SELECT COUNT(*) FROM events WHERE reviewer=?',(who,)).fetchone()[0]>=10000: raise Reject(429)
    c.execute('INSERT INTO events(reviewer,kind,item,revision,submission,request,payload,created) VALUES(?,?,?,?,?,?,?,?)',(who,'media_request',obj['name'],0,secrets.token_hex(18),'{}',json.dumps({'meaning':'Authenticated image request; not proof of human viewing'}),time.time()))
   return (self.root/'data/media'/obj['name']).read_bytes()
  if path in ('/api/rating','/api/familiarity','/api/exposure'): return self.event(who,path[5:],obj)
  if obj: raise Reject()
  if path=='/api/manifest': return self.manifest
  history=self.history(who)
  if path=='/api/export': return {'version':self.manifest['version'],'reviewer_id':who,'events':history}
  if path=='/api/state':
   latest={}; fam=None
   for e in history:
    if e['kind']=='rating': latest[e['item_id']]=e
    elif e['kind']=='familiarity': fam=e['payload']
   return {'ratings':list(latest.values()),'familiarity':fam}
  raise Reject(404)

class LimitedReader:
 def __init__(self,raw): self.raw=raw; self.left=16384
 def readline(self,size=-1):
  line=self.raw.readline(min(size if size>=0 else self.left+1,self.left+1)); self.left-=len(line)
  if self.left<0: raise ValueError('headers too large')
  return line
 def __getattr__(self,n): return getattr(self.raw,n)
class Handler(http.server.BaseHTTPRequestHandler):
 protocol_version='HTTP/1.0'
 def setup(self):
  self.request.settimeout(5); super().setup(); self.rfile=LimitedReader(self.rfile)
  self.deadline=threading.Timer(10,self.abort_request); self.deadline.daemon=True; self.deadline.start()
 def abort_request(self):
  try: self.connection.shutdown(socket.SHUT_RDWR)
  except OSError: pass
 def finish(self):
  self.deadline.cancel()
  super().finish()
 def log_message(self,*a): pass
 def version_string(self): return 'Review'
 def send_error(self,code,message=None,explain=None): self.reply(code,{'error':'Request unavailable'})
 def reply(self,status,body,ctype='application/json'):
  if not isinstance(body,bytes): body=json.dumps(body).encode()
  self.send_response(status); self.send_header('Content-Type',ctype); self.send_header('Content-Length',str(len(body)))
  for k,v in {'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','X-Frame-Options':'DENY','Referrer-Policy':'no-referrer','Content-Security-Policy':"default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'; object-src 'none'",'Connection':'close'}.items(): self.send_header(k,v)
  self.end_headers()
  if self.command!='HEAD': self.wfile.write(body)
  self.close_connection=True
 def handle_one_request(self):
  try: super().handle_one_request()
  except (ValueError,OSError): self.close_connection=True
 def check(self,post=False):
  a=self.server.app
  if self.headers.get_all('Host')!=[a.host] or len(self.path)>200 or '?' in self.path or '#' in self.path: raise Reject(400)
  if self.headers.get('Transfer-Encoding') or self.headers.get('Expect'): raise Reject(400)
  origins=self.headers.get_all('Origin',[])
  if post and origins!=[a.origin]: raise Reject(403)
  if post and self.headers.get('Sec-Fetch-Site') not in (None,'same-origin','none'): raise Reject(403)
  if len(self.headers.get_all('Authorization',[]))>1: raise Reject()
 def do_GET(self):
  try:
   self.check(); routes={'/':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8'),'/style.css':('style.css','text/css; charset=utf-8')}
   if self.path not in routes: raise Reject(404)
   name,ct=routes[self.path]; self.reply(200,(self.server.app.root/'frontend'/name).read_bytes(),ct)
  except Reject as e: self.send_error(e.status)
  except Exception: self.send_error(503)
 def do_POST(self):
  try:
   self.check(True)
   if self.headers.get_all('Content-Type')!=['application/json'] or len(self.headers.get_all('Content-Length',[]))!=1: raise Reject(415)
   length=self.headers['Content-Length']
   if not re.fullmatch(r'[0-9]{1,5}',length) or not 2<=int(length)<=MAX_BODY: raise Reject(413)
   raw=self.rfile.read(int(length))
   if len(raw)!=int(length): raise Reject()
   obj=json.loads(raw)
   if not isinstance(obj,dict): raise Reject()
   result=self.server.app.dispatch(self.path,obj,self.headers.get('Authorization'))
   self.reply(200,result,'image/png' if isinstance(result,bytes) else 'application/json')
  except Reject as e: self.send_error(e.status)
  except (ValueError,TypeError,KeyError): self.send_error(400)
  except Exception: self.send_error(503)
 def do_HEAD(self): self.send_error(405)
 do_OPTIONS=do_HEAD; do_PUT=do_HEAD; do_DELETE=do_HEAD; do_PATCH=do_HEAD; do_TRACE=do_HEAD; do_CONNECT=do_HEAD
class Server(socketserver.ThreadingMixIn,http.server.HTTPServer):
 daemon_threads=True; request_queue_size=16
 def __init__(self,address,app):
  if address[0]!='127.0.0.1': raise ValueError('loopback only')
  self.app=app; self.slots=threading.BoundedSemaphore(16); super().__init__(address,Handler)
 def process_request(self,request,address):
  if not self.slots.acquire(False): self.shutdown_request(request); return
  try: super().process_request(request,address)
  except Exception: self.slots.release(); raise
 def process_request_thread(self,request,address):
  try: super().process_request_thread(request,address)
  finally: self.slots.release()
def public_origin(value):
 try:
  u=urlsplit(value); port=u.port
 except ValueError as exc:
  raise argparse.ArgumentTypeError('Use an explicitly approved HTTPS origin.') from exc
 if u.scheme!='https' or not u.hostname or u.username is not None or u.password is not None or u.path or u.query or u.fragment or any(c.isspace() for c in value):
  raise argparse.ArgumentTypeError('Use an explicitly approved HTTPS origin without a path or credentials.')
 return value

def main(argv=None):
 p=argparse.ArgumentParser(); p.add_argument('--root',type=pathlib.Path,required=True); p.add_argument('--origin',type=public_origin,required=True); args=p.parse_args(argv)
 os.umask(0o077)
 app=App(args.root,args.origin)
 with Server(('127.0.0.1',8792),app) as server: server.serve_forever()
if __name__=='__main__': main()
