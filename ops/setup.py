"""Create a fresh private .env without revealing secrets. Never overwrites."""
import argparse,os,re,secrets
from pathlib import Path
parser=argparse.ArgumentParser()
parser.add_argument('--domain',required=True)
args=parser.parse_args()
if not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?',args.domain) or '.' not in args.domain:raise SystemExit('Pass a public DNS hostname')
root=Path(__file__).resolve().parent.parent
content=(root/'.env.example').read_text().replace('CHANGE_ME_LONG_RANDOM_PASSWORD',secrets.token_hex(32)).replace('CHANGE_ME_AT_LEAST_32_RANDOM_CHARACTERS',secrets.token_hex(32)).replace('SITE_ADDRESS=:80','SITE_ADDRESS='+args.domain)
fd=os.open(root/'.env',os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
with os.fdopen(fd,'w') as f:f.write(content)
print('Created private .env. Secrets were not printed.')
