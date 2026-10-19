"""Read-only deployment smoke check. Never publishes reports or changes sources."""
import argparse,json,time,urllib.request
parser=argparse.ArgumentParser()
parser.add_argument('base_url');parser.add_argument('--require-worker',action='store_true')
args=parser.parse_args()
base=args.base_url.rstrip('/')
def get(path):
    with urllib.request.urlopen(base+path,timeout=15) as r:
        if r.status!=200:raise RuntimeError(path+' failed')
        return json.load(r)
assert get('/health')['status']=='ok'
media=get('/api/v1/media?limit=100')
assert media['directory_total']==500 and len(media['items'])==100
search=get('/api/v1/media/search?q=OpenWatch')
assert search['mode']=='external_search_links' and search['total_sites']==500
assert len(search['groups'])==50
assert all(isinstance(v,int) for v in get('/api/v1/statistics').values())
status=get('/api/v1/system/status')
if args.require_worker:assert not status['worker_stale'],'Worker heartbeat is stale'
print('Read-only HTTP smoke passed: API, directory, scoped search, statistics, system status.')
