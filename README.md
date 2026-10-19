# OpenWatch Mongolia

**Нээлттэй мэдээлэл. Нотолгоонд суурилсан хяналт.**

Монголын нийтийн мэдээллийн RSS/Atom архив, локал AI шинжилгээ, нотолгооны харьцуулалт, хүний хяналттай тайлангийн платформ. Монгол хэлтэй responsive Next.js dashboard (үндсэн navigation-д MN/EN сонголттой), FastAPI, PostgreSQL/pgvector, Ollama, Docker Compose.

**Phase 1–4-ийн хэрэгжүүлэлт энэ репод байна.** Кодын тест болон бодит VPS дээрх commissioning хоёр тусдаа. Docker-capable VPS, домэйн, model download, эх сурвалжийн эрхийн шалгалт шаардлагатай. Deploy, HTTPS, PostgreSQL live runtime, бодит Ollama model-ийн Монгол хэлний чанарыг энэ орчинд баталгаажуулсан гэж үзэхгүй. Ажиллуулсан шалгалт бүр `VALIDATION.md`-д байна.

## Боломжууд

| Үе шат | Хэрэгжүүлэлт |
|---|---|
| 1 — Архив | RSS/Atom collector, canonical URL, SHA-256, version history, lexical matching, хайлт, dashboard |
| 2 — Локал AI | Ollama schema-тай extraction, 1024-dimensional bge-m3 embedding, pgvector cosine search, semantic matching, topic classification, extractive summary, retry/fallback |
| 3 — Нотолгоо | Immutable evidence spans, entity mention graph, тоо/огнооны зөрүүний нэр дэвшигч, snapshot тайлан, хүний review/publish/withdraw, moderated corrections |
| 4 — Ажиллагаа | HTTPS proxy, non-root application containers, auth, request/rate limits, SSRF guards, audit, worker heartbeat, backup service, isolated restore-check, Prometheus rules, retention, deploy/preflight/smoke scripts |

JSON/CSV нээлттэй өгөгдөл болон sitemap metadata импорт дэмжинэ. Sitemap нь URL ба lastmod л бүртгэнэ; гарчиг зохиохгүй, lastmod-ийг published_at гэж үзэхгүй. Нийтлэлийн URL-ын 404/410 шалгалтыг админ тусад нь ажиллуулж болно; feed-ээс алга болсныг устсан гэж дүгнэхгүй.

### Тайлбарлах зарчим

- Ижил текст, утгын ойролцоо байдал, ойр нийтэлсэн цаг нь зохион байгуулалт, ашиг сонирхол, хууль бус үйлдлийн нотолгоо биш.
- Хамгийн эрт **бүртгэгдсэн** мэдээ нь анхны нийтлэгч гэдгийг батлахгүй.
- `published_at`, `first_seen_at`, `fetched_at`, feed updated цаг тусдаа. Published цаг байхгүй бол first_seen-ээр орлуулахгүй.
- AI entity/claim/summary нь архивын хувилбарын **яг таарсан текстийн хэсэгт** тулгуурлана. Эхэд байхгүй нэр, тоо, ишлэл болон JSON schema алдааг хүлээж авахгүй.
- AI summary нь extractive quotes: шинэ баримт зохиосон чөлөөт дүгнэлт биш. Category нь мэдээний сэдэв; хүний улс төрийн үзэл бодол, намын харьяалал биш.
- Тоо/огнооны ялгааг `different_value_candidate` гэж тэмдэглэнэ. Албан баримтаар автоматаар баталгаажуулсан гэж үзүүлэхгүй. Хүний шалгалтгүй verified finding нийтлэхгүй.
- Тайлан бүр default **draft**. Token-той админ нотолгоо, privacy, хязгаарлалтыг шалгаж, тэмдэглэлтэйгээр publish хийнэ. Corrections мөн хүний review шаарддаг.
- Утас, email, регистрийн хэв шинжийг нийтийн текстэд нуух хамгаалалттай; энэ нь PII илрүүлэх бүрэн баталгаа биш. Тайлангийн explicit privacy review заавал.

## 100 эх сурвалж

`Монголын 100 сайт` цэсэнд нэр/домэйн, чиглэл, HTTP төлөв, feed илэрсэн эсэх, архивын идэвхээр шүүнэ. Энэ нь **хандалтаар батлагдсан Top 100 ranking биш**. ХХЗХ-ны 2020/2021 оны бүртгэл болон хэвлэлийн өөрийн нүүр хуудсаас нэр дэвшигчдийг сонгон шалгасан.

- 275 домэйн шүүсэн; каталогт 100 домэйн.
- 2026-10-19 snapshot: **96 нүүр хуудас нээгдсэн, 23 нийтлэлийн feed XML parse амжилттай**.
- MONTSAME, Zindaa, Olloo, Bolod-ийн шууд HTTP шалгалт timeout/403. Энэ нь сайт бүх хэрэглэгчид ажиллахгүй гэсэн дүгнэлт биш.
- Research proxy-ийн XML parse нь production pinned-DNS, robots, лицензийн шалгалтыг орлохгүй. Feed-үүд автоматаар идэвхжээгүй.

Хайлт хоёр төрөлтэй:

1. **Веб хайлт** — Google/Bing-ийн `site:` холбоос. Сайт тус бүр эсвэл 10 сайттай 10 бүлэг. Хэрэглэгч гаднын системийн бодит үр дүнг нээнэ; энэ API хайлтын үр дүн зохиохгүй, scrape хийж байгаа мэт дүр эсгэхгүй.
2. **Дотоод архив** — зөвхөн татаж хадгалсан нийтлэл; үгийн, PostgreSQL FTS болон локал embedding хайлт. AI unavailable бол `lexical_fallback` гэж ил тод тэмдэглэнэ.

Provenance: `backend/app/data/mongolia100.v1.json`, `probe-2026-10-19.json`, `probe-all-2026-10-19.json`.

## VPS суулгах

Ubuntu 24.04 LTS, Docker Engine + Compose plugin: https://docs.docker.com/engine/install/ubuntu/ . Эхний CPU-only архивт 4 GB RAM орчмоос эхэлж ачааллаа хэмжинэ; 8B AI model + DB-д **16 GB RAM-аас эхлэхийг тооцоолох** хэрэгтэй. Энэ нь benchmark баталгаа биш. API төлбөргүй; VPS, RAM/GPU, диск, model download-ийн зардал тусдаа.

DNS A/AAAA record-ийг VPS руу заана. SSH, TCP 80/443 болон шаардлагатай бол UDP 443 нээнэ. Database, Ollama, backend, Prometheus порт нийтэд нээхгүй.

```sh
sudo apt-get update
sudo apt-get install -y git python3 curl
git clone https://github.com/ssboroo/OPENWATCH-MONGOLIA.git
cd OPENWATCH-MONGOLIA
python3 ops/setup.py --domain watch.example.mn
# .env-г үүсгэж, random DB password/token-ийг 0600 эрхтэй хадгална.
# Үүссэн secrets stdout-д хэвлэхгүй, байгаа .env-г overwrite хийхгүй.
sh ops/deploy.sh
python3 ops/smoke.py https://watch.example.mn --require-worker
docker compose ps
docker compose logs --tail=100 backend worker proxy backup
```

`watch.example.mn`-г өөрийн домэйноор солино. `ops/deploy.sh`: config preflight → Compose validation → build → DB → Alembic migration → services. Шинэ суулгалтад migration job автоматаар ажиллана. Production schema-г `create_all`-аар удирдахгүй.

Домэйнгүй локал туршилтад `.env.example`-ийг `.env` болгож random hex secrets тохируулаад `SITE_ADDRESS=:80`-оор `docker compose up -d --build` ажиллуулж болно. Production preflight нь HTTP-only тохиргоог хүлээн авахгүй. Нийтийн HTTP сүлжээгээр admin token бүү илгээ.

### Локал AI идэвхжүүлэх

```sh
sh ops/ai-setup.sh
# qwen3:8b ба bge-m3 татна; серверийн диск/RAM хүрэлцэх ёстой.
# .env-д AI_ENABLED=true тохируулсны дараа:
docker compose --profile ai up -d --force-recreate backend worker ollama
```

`bge-m3` embedding нь schema-д **1024 dimension**. Өөр dimension-той model ашиглавал migration болон re-embedding шаардлагатай. Model сольсон үед worker current model/prompt signature-ийг харж дахин боловсруулна. Generation/embedding model-ийн нэрийг snapshot-д хадгална. Ollama нь internal service; prompt дотор tool execution, external fetch байхгүй. Text бол JSON field доторх untrusted data. Prompt instruction-оос гадна exact-span validation ба хүний publish gate хамгаална.

AI unavailable, timeout, schema/evidence invalid үед архив, lexical search, lexical claims, draft report үргэлжилнэ. Retry/backoff ба durable next_analysis_at хэрэглэнэ. AI-г ассан гэж дүр эсгэхгүй; System status, Admin → Ажиллагаа → Ollama/model төлөв харуулна.

## Эх сурвалж холбох

Админ цэсээр `.env`-ийн ADMIN_TOKEN-г өөрийн аюулгүй төхөөрөмжөөс оруулна. Token зөвхөн цонхны санах ойд; localStorage, cookie, URL-д хадгалахгүй. Single-admin bearer authentication; байгууллагын олон хэрэглэгчтэй SSO/RBAC систем биш.

1. **Админ → Ажиллагаа → Feed илрүүлэх**: домэйн эсвэл бүх 100 сайт. Background scan эхэлж, хүчинтэй feed Source үүсгэнэ. Идэвхгүй хэвээр.
2. **Админ → Эх сурвалж**: URL/robots/feed validation ажиллуулна.
3. Нийтлэгчийн Terms/лиценз, excerpt ашиглах зөвшөөрлийг бодитоор шалгаж license болон permission_note бөглөнө.
4. Идэвхжүүлсний дараа collector тогтмол татна. Шаардлагатай бол Ажиллагаа → Цуглуулалт эхлүүлэх.
5. Worker lexical/AI шинжилж event, evidence, draft үүсгэнэ. Тайланг тусад нь хүний хяналтаар нийтэлнэ.

CLI хувилбар:

```sh
docker compose exec backend python -m app.catalog_sync --domain mnb.mn
# Эсвэл бүх 100:
docker compose exec backend python -m app.catalog_sync
```

Каталогийн домэйн ба www хувилбарууд explicit allowlist-д багтсан. Өөр host нэмэх бол `.env`-ийн `ALLOWED_HOSTS`-д exact нэрээр оруулж backend/worker-ийг recreate хийнэ. DNS public эсэх, redirect бүр, IP pinning, TLS SNI, timeout, response size, XML entity хамгаалалт ашиглана. Нэвтрэх хязгаарлалт, paywall, login тойрохгүй. robots.txt нь лицензийг орлохгүй.

Нээлттэй JSON/CSV endpoint-ийн schema:

```json
{"items":[{"title":"Бодит эхийн гарчиг","url":"https://publisher.example/article/1","summary":"Зөвшөөрөгдсөн богино хэсэг","published_at":"2026-10-19T12:00:00+08:00","updated_at":null}]}
```

CSV columns: `title,url,summary,published_at,updated_at`. JSON raw array мөн болно. Timestamp өгвөл explicit timezone шаардлагатай. Импорт 500 хүртэл record, response 2 MB, excerpt 600 тэмдэгт. Sitemap index бол child sitemap-уудыг тусад нь бүртгэнэ. Sitemap-ээс нийтлэлийн бүтэн агуулга татахгүй.

## Тайлан, залруулга

- Event ID-г устгаж дахин үүсгэхгүй. Merge болсон хуучин ID canonical event руу resolve хийнэ. Matching нь bounded token candidates, exact hash, valid current embeddings ашиглана.
- Evidence span нь article_version_id, source URL, offsets, exact quote, method, observed time-тай.
- Report snapshot нь scope, source links, timeline, matches, claims/discrepancy candidates, model/prompt provenance, limitations, privacy flags, checksum агуулна.
- Draft өөрчлөхийн оронд шинэ revision үүсгэнэ. Review нь expected_hash шалгана. Архивын хувилбар нь retention-д арилсан draft-ийг publish хийхгүй, дахин build шаарддаг.
- Publish нь privacy_checked + хяналтын тэмдэглэл шаарддаг. Нийтийн байнгын URL: `/reports/{id}`; JSON татаж болно.
- Withdraw нь шалтгаан/time/hash бүхий tombstone үлдээнэ, body-г нийтээс нууна.
- Corrections pending текстийг нийтэд гаргахгүй. Хүн accepted/rejected шийдвэр, үндэслэл өгнө; accepted annotation-г нийтийн тайланд хавсаргана. Хувийн холбоо барих мэдээлэл цуглуулахгүй.
- Graph нь publisher → article → event candidate болон article → mentions entity холбоос. Бодит хамтын ажиллагаа, улс төрийн байр суурийг таамаглахгүй.

## Backup, restore, retention

Compose-ийн **backup service** 24 цаг тутам custom-format dump хийж, archive listing шалгаад 14 хоног хадгална. Named volume `backup_data` дотор байна. Автомат backup healthcheck 25 цагаас хуучирвал unhealthy.

```sh
docker compose exec backup ls -l /backups
# Нэрийг бодитоор үүссэн dump-аар солино:
docker compose exec backup sh /ops/restore-check.sh /backups/openwatch-YYYYMMDDTHHMMSSZ.dump
```

Restore-check нь тусдаа `ow_restore_*` database үүсгэж сэргээн SQL шалгаад устгана; production database-г солихгүй. Backup volume нь VPS дискнээс тусдаа offsite backup биш. Dumps-ийг encrypted offsite хадгалалт руу хуулж, бодит restore test тогтмол ажиллуулах шаардлагатай. Хуучин manual `sh ops/backup.sh`, `sh ops/restore-test.sh backups/file.dump` хувилбар мөн бий.

Retention: Admin → Ажиллагаа → dry-run; админ API `POST /api/v1/admin/maintenance/retention` body `{"dry_run":false}` нь noncurrent, хуучин, нийтэлсэн/withdrawn тайланд ишлэгдээгүй хувилбаруудыг л цэвэрлэнэ. Current version болон reviewed report evidence хамгаалагдана. Report snapshot-ийн хууль зүйн retention/takedown нь тусдаа хүний бодлого; database backup-д хуучин агуулга үлдэж болохыг тооцно. Автоматаар production дээр устгах job идэвхжүүлээгүй.

## Мониторинг, аюулгүй ажиллагаа

```sh
docker compose --profile monitoring up -d prometheus
# Нийтийн порт нээхгүй. SSH/Docker exec ашиглан дотоод alerts шалгана:
docker compose exec prometheus wget -qO- http://localhost:9090/api/v1/alerts
docker compose logs --since=1h worker backup
df -h
docker system df
```

System status нь heartbeat, AI config/status, диск, pending corrections харуулна. Prometheus `/metrics` internal endpoint-ийг scrape хийнэ. Worker stale, backend unreachable, disk <15%, active source errors дүрэмтэй. Alert notification-г Slack/email рүү автоматаар илгээхгүй; receiver/notification routing сервер дээр тусад нь тохируулна.

DB/Ollama/backend/metrics public port-гүй. Caddy нь HTTPS, headers, CSP, HSTS тохиргоотой; Next.js inline script/style-д `unsafe-inline` шаардлагатай baseline CSP бөгөөд nonce-based хатуу CSP гэж батлаагүй. API нь process/IP тутам 120 хүсэлт/мин, correction 5/цаг, mutation body 64 KiB хязгаартай. Multi-replica үед shared rate-limit store шаардлагатай.

Docker-ийн backend зөвхөн дотоод сүлжээнд, Caddy forwarded IP-д итгэхээр тохируулсан. Backend порт public болгож болохгүй. DB bootstrap role нь official image-ийн database owner; хэрэглэгч олонтой production-д тусдаа least-privilege runtime/migration/backup role тогтоох, TLS/access hardening хийхийг commissioning-д шалгана.

## Update, rollback

```sh
git rev-parse HEAD  # өмнөх commit-ийг хадгал
sh ops/backup.sh
git pull --ff-only
sh ops/deploy.sh
python3 ops/smoke.py https://watch.example.mn --require-worker
```

Rollback хийхдээ өмнөх commit-ийг checkout → build/up. Шинэ migration backward-compatible эсэхийг эхлээд шалгана; database-г сохроор downgrade хийхгүй. `0002_evidence` downgrade нь AI/evidence/report хүснэгтүүдийг устгадаг тул production rollback-д backup + тусдаа сэргээх rehearsal шаардлагатай. `ops/restore-check.sh` live restore биш.

## API тойм

Нийтийн endpoints:

- `/health`, `/api/v1/system/status`
- `/api/v1/media`, `/media/search`
- `/api/v1/articles`, `/search`: q, domain, source_id, mode=lexical|fts, offset, limit
- `/api/v1/semantic-search`: q, domain, offset, limit; semantic эсвэл ил тод lexical_fallback
- `/api/v1/articles/{id}`, `/versions`, `/analysis`, `/observations`
- `/api/v1/events`, `/clusters`, `/events/{id}`, `/timeline`, `/sources`, `/graph`
- `/api/v1/statistics`, `/collector/status`
- `/api/v1/reports`, `/reports/{id}`, `POST /reports/{id}/corrections`

Admin bearer endpoints:

- `POST /api/v1/sources`, `PATCH /sources/{id}`, `POST /sources/{id}/validate`
- `POST /api/v1/collect/run`, `/admin/analysis/run`, `/admin/catalog/sync`
- `GET /api/v1/admin/reports`, `POST /admin/reports/build`, `/admin/reports/{id}/review`
- `GET /api/v1/admin/corrections`, `POST /admin/corrections/{id}/review`
- `GET /api/v1/admin/audit`, `/admin/ai/status`
- `POST /api/v1/admin/articles/{id}/check`, `/admin/maintenance/retention`

Backend `/docs` ба `/openapi.json` нь internal; public proxy тэдгээрийг нийтэд гаргаагүй. Pagination 1–100. 401 auth, 404 not found, 409 stale/conflict, 413 body size, 422 schema/review guard, 429 rate, 503 DB failure.

## Хөгжүүлэлт ба тест

```sh
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements-dev.txt
cd backend
../.venv/bin/python -m pytest -q
DATABASE_URL=sqlite:////tmp/openwatch-dev.db ../.venv/bin/alembic upgrade head
DATABASE_URL=sqlite:////tmp/openwatch-dev.db ../.venv/bin/uvicorn app.main:app --port 8000
# Өөр терминалд:
cd frontend
npm ci
BACKEND_URL=http://127.0.0.1:8000 npm run dev
```

SQLite нь local tests/dev fallback; pgvector SQL distance, HNSW, PostgreSQL advisory/row locks-ийг орлохгүй. Production нь PostgreSQL. `backend/migrations/versions/0001_archive.py`, `0002_evidence.py`, `0003_version_provenance.py` explicit migration; 19 application tables. API stat бүх тоо DB-аас; source research тоо хувилбарласан probe snapshot-оос.

```sh
cd frontend
npm run build
npm audit --omit=dev
# Репогийн root-оос, dependency-тэй CI environment:
sh ops/ci.sh
```

Тест/үлдсэн commissioning шалгалтууд: **[VALIDATION.md](VALIDATION.md)**. Ollama API contract: https://docs.ollama.com/api/embed ; structured output: https://docs.ollama.com/capabilities/structured-outputs ; pgvector SQLAlchemy: https://github.com/pgvector/pgvector-python . Model-ийн Монгол хэлний чанарыг өөрийн бодит validation dataset дээр хэмжиж threshold, review policy-г тохируулна.

### Native PostgreSQL integration test

Dedicated **test database**-ийн URL-ийг environment-д `OPENWATCH_TEST_POSTGRES_URL` болгож өгөөд `pytest` ажиллуулбал тусгаарласан `ow_test_*` schema дотор migration, JSONB, HNSW/cosine query болон advisory lock-ийн native тестүүд ажиллана. Schema-г эцэст нь цэвэрлэнэ. Production URL өгч болохгүй. Энэ environment variable байхгүй бол тэр хоёр тестийг skipped гэж ил тод тайлагнана.

### Хуучин container volume-ийн ownership

Өмнөх root Caddy/Ollama image ашигласан persistent volume-оо non-root image руу шилжүүлэх үед ownership-ийг нэг удаа тохируулах шаардлагатай байж болно. Файлыг устгахгүй. Compose-ийн default project name `openwatch` үед:

```sh
# Үйлчилгээг update хийхийн өмнө backup авна.
docker run --rm --user 0 --entrypoint sh \
  -v openwatch_caddy_data:/data -v openwatch_caddy_config:/config \
  caddy:2-alpine -c 'chown -R 10001:10001 /data /config'
docker run --rm --user 0 --entrypoint sh \
  -v openwatch_ollama:/models \
  alpine:3 -c 'chown -R 10001:10001 /models'
```

Шинэ суулгалтад image-ийн directory ownership бэлэн. Ollama model cache нь хуучин volume-ийн `models/` бүтэцтэй нийцнэ. Custom Compose project name ашигласан бол volume нэрээ эхэлж `docker volume ls`-ээр шалгаж тохируулна.
