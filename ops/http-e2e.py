import os,sys,time,json,tempfile,subprocess,urllib.request,urllib.error,secrets
from pathlib import Path
root=Path(__file__).resolve().parent.parent
temp=tempfile.TemporaryDirectory(prefix='ow-e2e-')
token='qa-only-'+secrets.token_hex(24)
os.environ.update(DATABASE_URL='sqlite:///'+temp.name+'/test.db',ADMIN_TOKEN=token,AI_ENABLED='false',BACKEND_URL='http://127.0.0.1:8765')
sys.path.insert(0,str(root/'backend'))
from alembic.config import Config
from alembic import command
os.chdir(root/'backend');command.upgrade(Config('alembic.ini'),'head')
from app.db import Session
from app.models import Source
from app.collector import ingest
from app.pipeline import process_batch
import asyncio
with Session() as db:
 s=Source(name='[DEMO] HTTP integration fixture',endpoint='https://ikon.mn/rss',license='[DEMO] fixture only',permission_note='[DEMO] not production',active=False);db.add(s);db.flush()
 for i,n in enumerate(['400','500']):
  ingest(db,s,[{'url':f'https://ikon.mn/demo-only/{i}','title':'[DEMO] Улсын төсвийн тухай мэдээлэл','excerpt':f'Улсын шинэ төсөв {n} сая төгрөг.','published_at':None,'updated_at':None}])
 db.commit()
asyncio.run(process_batch())
logs=open(temp.name+'/server.log','w')
processes=[]
try:
 processes.append(subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--port','8765'],cwd=root/'backend',env=os.environ,stdout=logs,stderr=logs))
 processes.append(subprocess.Popen([sys.executable,'-m','app.worker'],cwd=root/'backend',env=os.environ,stdout=logs,stderr=logs))
 processes.append(subprocess.Popen(['node','.next/standalone/server.js'],cwd=root/'frontend',env={**os.environ,'PORT':'3765','HOSTNAME':'127.0.0.1'},stdout=logs,stderr=logs))
 def call(path,body=None,auth=False,port=8765,method=None):
  headers={'Content-Type':'application/json'}
  if auth:headers['Authorization']='Bearer '+token
  req=urllib.request.Request(f'http://127.0.0.1:{port}'+path,data=json.dumps(body).encode() if body is not None else None,headers=headers,method=method)
  with urllib.request.urlopen(req,timeout=10) as r:
   raw=r.read().decode()
   return json.loads(raw) if r.headers.get('content-type','').startswith('application/json') else raw
 for _ in range(60):
  try:
   call('/health');call('/',port=3765);break
  except Exception:time.sleep(.25)
 else:raise RuntimeError('Servers did not become healthy')
 assert call('/health',port=3765)['status']=='ok'
 assert 'Админ хяналт' not in call('/',port=3765)
 admin_html=call('/admin',port=3765)
 assert 'noindex' in admin_html and 'Нэвтрэх' in admin_html
 assert call('/api/v1/donation',port=3765)=={'enabled':False}
 try:call('/api/v1/admin/donation',port=3765);raise AssertionError('Admin settings must require authentication')
 except urllib.error.HTTPError as exc:assert exc.code==401
 donation={'enabled':False,'title':'[DEMO] Isolated donation fixture','bank_name':'[DEMO] Test bank','account_holder':'[DEMO] Test holder','account_number':'1234567890','revision':0}
 saved=call('/api/v1/admin/donation',donation,True,method='PUT')
 assert saved['revision']==1 and call('/api/v1/donation')=={'enabled':False}
 donation.update(enabled=True,confirmed=True,revision=1)
 call('/api/v1/admin/donation',donation,True,method='PUT')
 assert call('/api/v1/donation',port=3765)['account_number']=='1234567890'
 donation.update(enabled=False,revision=2)
 call('/api/v1/admin/donation',donation,True,method='PUT')
 assert call('/api/v1/donation',port=3765)=={'enabled':False}
 assert all(p.poll() is None for p in processes),'A service exited unexpectedly'
 assert call('/api/v1/media?limit=100',port=3765)['total']==500
 r=call('/api/v1/admin/reports?state=draft',auth=True)['items'][0]
 assert call('/api/v1/reports')['total']==0
 call(f"/api/v1/admin/reports/{r['id']}/review",{'decision':'publish','privacy_checked':True,'expected_hash':r['body_hash'],'finding':'sources_differ','note':'[DEMO] Explicit human review performed for HTTP integration test.'},True)
 public=call(f"/api/v1/reports/{r['id']}",port=3765)
 assert public['state']=='published' and public['body']['evidence'] and public['body']['discrepancies']
 html=call(f"/reports/{r['id']}",port=3765)
 assert '[DEMO]' in html and '400 сая төгрөг' in html,'SSR report evidence was not rendered'
 try:call('/reports/invalid',port=3765);raise AssertionError('Invalid report route should be 404')
 except urllib.error.HTTPError as exc:assert exc.code==404
 correction=call(f"/api/v1/reports/{r['id']}/corrections",{'text':'[DEMO] Additional evidence for the isolated integration test.','evidence_urls':['https://ikon.mn/demo-only/evidence']})
 assert call(f"/api/v1/reports/{r['id']}")['corrections']==[]
 call(f"/api/v1/admin/corrections/{correction['id']}/review",{'decision':'accepted','privacy_checked':True,'response':'[DEMO] Reviewed isolated test annotation.'},True)
 assert len(call(f"/api/v1/reports/{r['id']}")['corrections'])==1
 rsearch=call('/api/v1/research?q=DEMO',port=3765)
 assert rsearch['total']==2 and all(r['claims'] and r['version_id'] for r in rsearch['items'])
 assert call('/api/v1/semantic-search?q=DEMO')['mode']=='lexical_fallback'
 assert call('/api/v1/system/status')['worker_stale'] is False
 subprocess.run([sys.executable,str(root/'ops/smoke.py'),'http://127.0.0.1:3765','--require-worker'],check=True)
 print('PASS: separate admin login + protected donation draft/publish/unpublish + live HTTP + standalone Next.js rewrite + SSR report + human publish + moderated correction + worker heartbeat + AI-offline fallback; isolated DEMO fixtures only')
finally:
 for p in reversed(processes):
  p.terminate()
  try:p.wait(timeout=10)
  except subprocess.TimeoutExpired:p.kill();p.wait()
 logs.close();temp.cleanup()
