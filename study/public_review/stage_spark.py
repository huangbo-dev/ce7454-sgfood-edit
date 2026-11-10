"""Offline Spark staging helper. No server/start/network/access changes. Never auto-executed."""
import argparse,hashlib,json,os,pathlib,re,shutil
def reject_symlinks(path):
 for p in (path,*path.parents):
  if p.is_symlink(): raise ValueError('Symlink refused')
def stage(bundle,source,dest):
 bundle=pathlib.Path(bundle); source=pathlib.Path(source); dest=pathlib.Path(dest)
 for p in (bundle,source,dest): reject_symlinks(p)
 if dest.exists(): raise ValueError('Destination collision')
 lock_path=bundle/'data/PACKAGE_LOCK.json'; reject_symlinks(lock_path)
 lock=json.loads(lock_path.read_text()); expected=lock['files']; copies=[]
 for name,meta in expected.items():
  if name in ('public_manifest.json','private_map.json'): p=bundle/'data'/name
  elif re.fullmatch(r'media/[a-f0-9]{24}\.png',name): p=source/name[6:]
  else: raise ValueError('Unexpected data name')
  reject_symlinks(p)
  if not p.is_file() or p.stat().st_size>10000000: raise ValueError('Invalid file')
  b=p.read_bytes()
  if len(b)!=meta['bytes'] or hashlib.sha256(b).hexdigest()!=meta['sha256']: raise ValueError('Source content mismatch')
  copies.append((p,pathlib.Path('data')/name))
 for folder in ('backend','frontend','tests','evidence'):
  for p in (bundle/folder).iterdir():
   if p.is_dir() or p.suffix not in ('.py','.js','.css','.html','.json','.md'): continue
   reject_symlinks(p); copies.append((p,pathlib.Path(folder)/p.name))
 for n in ('README.md','stage_spark.py'):
  p=bundle/n; reject_symlinks(p); copies.append((p,pathlib.Path(n)))
 os.umask(0o077); dest.mkdir(mode=0o700)
 for p,rel in copies:
  out=dest/rel; out.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(p,out)
 (dest/'private').mkdir(mode=0o700)
 shutil.copyfile(lock_path,dest/'data/PACKAGE_LOCK.json')
 for name,meta in expected.items():
  b=(dest/'data'/name).read_bytes()
  if len(b)!=meta['bytes'] or hashlib.sha256(b).hexdigest()!=meta['sha256']: raise ValueError('Copy verification failed')
 print('Staged and verified. No credentials, responses, listener, or exposure created.')
def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--bundle',type=pathlib.Path,required=True)
 p.add_argument('--source',type=pathlib.Path,required=True,help='Approved source media directory')
 p.add_argument('--dest',type=pathlib.Path,required=True,help='New isolated staging directory')
 args=p.parse_args(argv)
 stage(args.bundle,args.source,args.dest)
if __name__=='__main__': main()
