"""Container entrypoint supporting Railway's assigned PORT and private bind host."""
import os
from pathlib import Path
import uvicorn

def main():
    port=int(os.environ.get('PORT','8000'))
    if not 1<=port<=65535:raise ValueError('PORT must be between 1 and 65535')
    uvicorn.run('app.main:app',host=os.environ.get('BIND_HOST','0.0.0.0'),port=port,proxy_headers=True,forwarded_allow_ips='*',log_config=str(Path(__file__).resolve().parents[1]/'logging.json'))

if __name__=='__main__':main()
