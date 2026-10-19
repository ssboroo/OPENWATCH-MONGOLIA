"""Deployment preflight. Reads a restricted dotenv grammar without shell evaluation."""
import re
from pathlib import Path
root=Path(__file__).resolve().parent.parent
p=root/'.env'
if not p.exists():raise SystemExit('Create .env using ops/setup.py first')
values={}
for line in p.read_text().splitlines():
    if not line.strip() or line.lstrip().startswith('#'):continue
    key,sep,value=line.partition('=')
    if not sep or not re.fullmatch('[A-Z_]+',key):raise SystemExit('Invalid .env syntax')
    values[key]=value.strip()
for key in ['POSTGRES_PASSWORD','ADMIN_TOKEN']:
    value=values.get(key,'')
    if len(value)<32 or 'CHANGE_ME' in value:raise SystemExit(key+' must contain a fresh random secret')
if not re.fullmatch('[0-9A-Fa-f]{32,}',values['POSTGRES_PASSWORD']):raise SystemExit('Use a hex PostgreSQL password for safe DATABASE_URL composition')
if values.get('SITE_ADDRESS',':80').startswith(':'):raise SystemExit('Production deployment requires SITE_ADDRESS=your.public.domain')
if p.stat().st_mode & 0o077:raise SystemExit('Restrict .env permissions: chmod 600 .env')
print('Configuration preflight passed; no secrets printed.')
