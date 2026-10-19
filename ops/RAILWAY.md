# Railway deployment

Target project: https://railway.com/project/76d99e18-8f81-42f0-9206-940e355b3912
Repository: `ssboroo/OPENWATCH-MONGOLIA`, branch `main`.

This file is a deployment specification, not a claim that the project is deployed.

## Services

| Service | Source / root | Config path (from repository root) | Public domain |
|---|---|---|---|
| Postgres | `pgvector/pgvector:pg16` image | Persistent volume `/var/lib/postgresql/data` | No |
| backend | GitHub, `/backend` | `/backend/railway.json` | No |
| worker | GitHub, `/backend` | `/backend/railway.worker.json` | No |
| frontend | GitHub, `/frontend` | `/frontend/railway.json` | Generate Railway HTTPS domain |

Keep one worker replica. Do not enable serverless/sleep for the backend or worker. Create a separate empty staging environment if this project already contains other workloads; retain existing services and data.

## Variables

Create a Postgres database named `openwatch`, a dedicated database user and a fresh random password via Railway secrets. Configure `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` on the image. Attach its persistent volume before first deployment. Export a standard private `DATABASE_URL` from that service. The application accepts both `postgres://` and `postgresql://` and selects the installed `psycopg` driver without rewriting the password or query.

Backend and worker:

- `DATABASE_URL`: reference the Postgres service's private URL, using its actual service name and private host/port.
- `ADMIN_TOKEN`: same new random secret of at least 32 characters on both; never put the value in GitHub, build arguments, frontend variables or logs.
- `AI_ENABLED=false` initially; lexical archive/search works without Ollama.
- Backend `PORT=8000`; `BIND_HOST=::` for IPv4/IPv6 private networking.
- Worker `COLLECTION_INTERVAL=900`, `WORKER_TICK_SECONDS=60`.

Frontend:

- `BACKEND_URL=http://backend.railway.internal:8000` if the backend is named `backend`; use the actual private hostname if renamed. Set this **before the build**: the Dockerfile declares it as a build argument because Next.js rewrites are baked into the build.
- `PORT=3000`, `HOSTNAME=0.0.0.0`.
- No database or admin secrets in the frontend.

## Deployment order and checks

1. Deploy pgvector Postgres and verify readiness/persistent storage.
2. Deploy backend. Its pre-deploy `alembic upgrade head` runs using private networking. A failed migration must stop deployment.
3. Deploy worker after the migration succeeds. Do not run concurrent schema migrations from the worker.
4. Build/deploy frontend with `BACKEND_URL` already set. Generate its public domain targeting port 3000.
5. Run `python ops/smoke.py https://<actual-domain> --require-worker` from a network that reaches the domain. Verify the directory contains 500 hosts, API health, worker heartbeat, search and an unauthenticated admin request returns 401.
6. Validate feeds from the deployment environment; record source terms before activation. Never mark all 500 sites as live feeds. Keep the 500-host research snapshot separate from production validation.
7. Configure Railway volume backups and test restoration on a separate database. A volume alone is not an offsite backup.

Optional local AI requires a separate Ollama service, persistent model volume, enough RAM, and successful model/embedding checks before `AI_ENABLED=true`. Do not download or run a large model implicitly on a small deployment.

Reference docs:
- https://docs.railway.com/config-as-code/reference
- https://docs.railway.com/builds/dockerfiles
- https://docs.railway.com/deployments/pre-deploy-command
- https://docs.railway.com/networking/private-networking
