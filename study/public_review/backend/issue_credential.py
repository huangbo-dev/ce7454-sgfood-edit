"""Offline issuance utility. DO NOT RUN until individual reviewer issuance is approved."""
import argparse,hashlib,json,os,pathlib,re,secrets,time

def main():
 p=argparse.ArgumentParser(); p.add_argument('--reviewer-id',required=True); p.add_argument('--expires-utc-epoch',type=int,required=True); p.add_argument('--output',type=pathlib.Path,required=True); p.add_argument('--approved-issuance',action='store_true',required=True); a=p.parse_args()
 if not re.fullmatch(r'[A-Za-z0-9_-]{8,64}',a.reviewer_id) or not time.time()<a.expires_utc_epoch<time.time()+30*86400: raise SystemExit('Invalid reviewer or expiry')
 if a.output.exists() or a.output.is_symlink() or a.output.parent.is_symlink(): raise SystemExit('Refusing overwrite or symlink')
 os.umask(0o077); code=secrets.token_urlsafe(32)
 with a.output.open('x',encoding='utf-8') as f: json.dump([{'reviewer_id':a.reviewer_id,'code_sha256':hashlib.sha256(code.encode()).hexdigest(),'expires_at':a.expires_utc_epoch,'revoked':False}],f,indent=2)
 print('One-time display; securely deliver only to the approved reviewer:'); print(code)
if __name__=='__main__': main()
