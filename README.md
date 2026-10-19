# OpenWatch Mongolia

**Нээлттэй мэдээлэл. Нотолгоонд суурилсан хяналт.**

Монгол хэлтэй нийтийн мэдээллийн архив, RSS/Atom цуглуулалт, нийтлэлийн өөрчлөлт болон ижил агуулгыг харьцуулах систем. **Phase 1 MVP**. AI дүгнэлт, баталгаажсан баримтын тайлан, бодит хүмүүсийн холбооны дүгнэлт гаргахгүй.

## Хэрэгжсэн хүрээ

- Next.js App Router + TypeScript responsive dashboard: хайлт, pagination, нийтлэлийн дэлгэрэнгүй, хувилбарын түүх, үйл явдлын timeline, эх сурвалж, collector төлөв.
- FastAPI + SQLAlchemy 2; PostgreSQL/pgvector image; Alembic `0001_archive` migration.
- RSS 2.0, Atom: гарчиг, 600 тэмдэгт хүртэл товч агуулга, анхны URL, published/updated/first_seen/fetched timestamp тус тус хадгална.
- Canonical URL, tracking query normalization, SHA-256 exact match, token Jaccard near match, connected-component event clustering.
- Хувилбарын архив; эх сурвалжийг устгахын оронд идэвхгүй болгоно.
- Нийтийн унших API; админы mutation bearer authentication; mutation audit log.
- HTTPS-only allowlist, private/reserved IP block, DNS resolution → pinned IP + TLS SNI, redirect бүрийн шалгалт, robots.txt шалгалт, timeout, хэмжээний хязгаар, аюулгүй XML parsing.
- Давхар collector ажиллуулахыг PostgreSQL advisory lock-оор хориглоно. Source бүр тусдаа transaction; нэг feed-ийн алдаа бусдыг зогсоохгүй.
- Caddy reverse proxy, автомат HTTPS тохиргоо; backup болон тусдаа database руу restore шалгах script.

Хуурамч нийтлэл, seed статистик, баталгаажаагүй идэвхтэй feed байхгүй. Тестийн өгөгдөл зөвхөн `backend/tests` дотор байна. Ижил агуулга/цаг нь зохион байгуулалт, ашиг сонирхол эсвэл хууль бус үйлдлийн нотолгоо биш. `events` ID нь одоогийн clustering дахин тооцоход өөрчлөгдөж болно; Phase 3 хүртэл тогтвортой тайлангийн ID гэж ашиглахгүй.

## Ubuntu VPS суулгах

Эхний тохиргоо: 2–4 CPU, 4 GB RAM, 30+ GB диск; энэ нь ачааллын баталгаат хэмжээ биш. AI profile нэмбэл model-оос хамааран илүү RAM/GPU шаардана. Төлбөртэй API ашиглаагүй; VPS, диск, сүлжээ, локал model-ийн зардал тусдаа.

1. Ubuntu 24.04 LTS сервер дээр Docker Engine + Compose plugin-ийг Docker-ийн албан ёсны Ubuntu заавраар суулгана: https://docs.docker.com/engine/install/ubuntu/ . SSH, 80, 443 портыг зөвшөөрнө; DB болон Ollama порт нээхгүй.
2. Git суулгаад кодоо татна:

```sh
sudo apt-get update
sudo apt-get install -y git openssl curl
git clone https://github.com/ssboroo/OPENWATCH-MONGOLIA.git
cd OPENWATCH-MONGOLIA
cp .env.example .env
openssl rand -hex 32
openssl rand -hex 32
```

3. `.env` дотор эхний random утгыг `POSTGRES_PASSWORD`, хоёр дахь утгыг `ADMIN_TOKEN` болгоно. Password-д URL reserved тэмдэг оруулахгүй: hex утга тохиромжтой. `.env`-ийг Git-д оруулахгүй; `chmod 600 .env` ажиллуулна.
4. Домэйн A/AAAA record-ийг VPS руу заагаад `SITE_ADDRESS=watch.example.mn` тохируулна. Домэйнгүй туршихад `:80` ашиглаж болно; админ token-оо нийтийн HTTP сүлжээгээр илгээхгүй, HTTPS эсвэл SSH туннель ашиглана.
5. Дарааллаар ажиллуулна:

```sh
docker compose config --quiet
docker compose build
docker compose up -d db
docker compose run --rm migrate
docker compose up -d
# Домэйнээр HTTPS тохируулсан бол:
curl --fail https://watch.example.mn/health
docker compose ps
docker compose logs --tail=100 backend worker proxy
```

`migrate` service бүх шинэчлэлтэд Alembic ажиллуулна. Production-д `create_all` ашиглахгүй. Caddy сертификат авахын тулд зөв DNS ба 80/443 нээлттэй байх ёстой. Compose зөвхөн proxy портуудыг нийтэд нээнэ.

## Эх сурвалж нэмэх

Анх **0 эх сурвалж** байна. URL, feed-ийн хүчинтэй байдал болон нийтлэгчийн нөхцөлийг шалгалгүй идэвхжүүлэхгүй. Зөвхөн нийтэд нээлттэй, зөвшөөрөлтэй RSS/Atom endpoint ашиглана; login/paywall тойрохгүй. Эх сурвалжийн Terms, лиценз, excerpt ашиглах эрхийг оператор шалгаж бүртгэнэ. robots.txt нь ашиглах лицензийг орлохгүй.

1. `.env`-д `ALLOWED_HOSTS=news.example.mn` нэмнэ. Redirect эсвэл robots.txt өөр hostname ашиглавал зөвхөн шалгасан hostname-ийг таслалаар нэмж болно. Wildcard байхгүй.
2. `docker compose up -d --force-recreate backend worker`.
3. Аюулгүй админ терминалд token оруулна. Frontend-д token хадгалахгүй:

```sh
read -rs ADMIN_TOKEN
export ADMIN_TOKEN
export BASE_URL=https://watch.example.mn
curl --fail "$BASE_URL/api/v1/sources" \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H 'Content-Type: application/json' \
  -d '{"name":"Шалгасан нийтлэгч","endpoint":"https://news.example.mn/rss","publisher":"Нийтлэгч","license":"Бодитоор шалгасан лиценз/нөхцөлийн URL","permission_note":"Зөвшөөрөгдсөн ашиглалтын хүрээ, шалгасан огноо"}'
# Буцаасан ID-г ашиглана (жишээнд 1):
curl --fail -X POST "$BASE_URL/api/v1/sources/1/validate" -H "Authorization: Bearer $ADMIN_TOKEN"
# valid:true болсны дараа:
curl --fail -X PATCH "$BASE_URL/api/v1/sources/1" \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H 'Content-Type: application/json' -d '{"active":true}'
curl --fail -X POST "$BASE_URL/api/v1/collect/run" -H "Authorization: Bearer $ADMIN_TOKEN"
curl --fail "$BASE_URL/api/v1/collector/status"
unset ADMIN_TOKEN
```

Дээрх `news.example.mn` нь **жишээ домэйн** бөгөөд ажиллаж буй feed гэж батлаагүй. Баталгаажуулалт нь дахин татаж XML/feed болон robots шалгана; activation-ийг оператор тусад нь хийнэ. Операторын оруулсан эрхийн тайлбарыг систем хууль зүйн дүгнэлтээр автоматаар баталгаажуулахгүй. Source алдаа, checked_at, success_at-ийг API харуулна.

## API

`GET /health` нь DB холболт шалгана. Endpoint жагсаалт ба schema-г backend дотор `/docs`-оор үзэж болно; proxy үүнийг нийтэд гаргаагүй.

| Нийтийн GET | Үүрэг |
|---|---|
| `/api/v1/sources`, `/sources/{id}` | Source бүртгэл |
| `/api/v1/articles`, `/search` | `q`, `source_id`, `offset`, `limit` (1–100) |
| `/api/v1/articles/{id}` | Нийтлэл ба анхны URL |
| `/api/v1/articles/{id}/versions` | Хувилбарын түүх, pagination |
| `/api/v1/events`, `/clusters` | Lexical event бүлэг, pagination |
| `/api/v1/events/{id}` | Ижил төстэй холбоос, оноо, арга |
| `/api/v1/events/{id}/timeline`, `/sources` | Цагийн дараалал, нийтлэгчид |
| `/api/v1/statistics` | DB-аас бодит тоонууд |
| `/api/v1/collector/status` | Сүүлийн ажил, алдаа |
| `/api/v1/reports` | Phase 3 идэвхжээгүй, хоосон жагсаалт |

Админ: `POST /sources`, `POST /sources/{id}/validate`, `PATCH /sources/{id}` (active), `POST /collect/run`, бүгд `/api/v1` prefix-тэй. Тодорхойгүй ID 404, schema 422, DB failure 503. Rate limit нь API process бүрд client IP тутамд 120 хүсэлт/мин; proxy hop дээр client IP ашиглах тохиргоог доорх хязгаарлалтаас уншина уу.

## Database, migration

`0001_archive` нь sources, articles, article_versions, events, event_articles, similarity_matches, collection_runs, audit_logs гэсэн 8 хүснэгт үүсгэнэ. Foreign key, unique URL, unique article/version, timestamp/index-үүд; PostgreSQL-д vector extension, JSONB GIN ба `simple` full-text GIN index үүсгэнэ. Монгол хэлний stemming гэж батлаагүй. Одоогийн хайлт нь substring ILIKE; FTS index-ийг ranked search-д ашиглах нь дараагийн ажил.

Phase 2/3-ийн entities, mentions, embeddings, claims, comparisons, evidence, reports, corrections хүснэгтүүдийг одоогоор үүсгээгүй. Хэрэгжээгүй хүснэгт, хоосон AI дүгнэлтийг бодит боломж мэт харуулахгүй.

## Backup, restore, update

```sh
sh ops/backup.sh
sh ops/restore-test.sh backups/openwatch-YYYYMMDDTHHMMSSZ.dump
```

Backup нь 14 хоног хадгална; production DB-г солихгүй тусдаа `openwatch_restore_check` DB-д сэргээн SQL шалгана. Production restore хийхийн өмнө backup болон зогсолтын төлөвлөгөө шаардлагатай. Нөөцийг encrypted offsite хадгалалт руу хуулж, restore-test тогтмол хийнэ. Cron (`/opt/OPENWATCH-MONGOLIA`-г бодит замаар солино):

```cron
15 2 * * * cd /opt/OPENWATCH-MONGOLIA && sh ops/backup.sh >> /var/log/openwatch-backup.log 2>&1
```

Disk monitoring: `df -h`, `docker system df`, `du -sh backups`; лог: `docker compose logs --since=1h worker`. Feed error status API-г гаднын монитор хянах боломжтой; alert илгээх integration хийгээгүй.

Шинэчлэх:

```sh
git rev-parse HEAD  # өмнөх commit-ийг хадгал
sh ops/backup.sh
git pull --ff-only
docker compose build
docker compose run --rm migrate
docker compose up -d
```

Rollback: шинэ migration backward-compatible эсэхийг шалгаад өмнөх commit-ийг checkout хийж build/up ажиллуулна. DB-г сохроор downgrade хийхгүй; migration downgrade өгөгдөл устгаж болно. Migration rollback-ийг disposable DB дээр эхэлж шалгана.

## Локал хөгжүүлэлт ба шалгалт

Python 3.12+, Node 22+. Frontend build үед гаднын font татах шаардлагагүй (CSS font холболт runtime-д fallback-тай).

```sh
python -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
cd backend
../.venv/bin/python -m pytest -q
# SQLite зөвхөн локал туршилт; PostgreSQL deployment-ийг орлохгүй.
DATABASE_URL=sqlite:////tmp/openwatch-dev.db ../.venv/bin/alembic upgrade head
DATABASE_URL=sqlite:////tmp/openwatch-dev.db ../.venv/bin/uvicorn app.main:app --port 8000
# өөр терминалд repository root-оос:
cd frontend
npm ci
BACKEND_URL=http://127.0.0.1:8000 npm run build
BACKEND_URL=http://127.0.0.1:8000 npm start
```

Тестийн хураангуй: `VALIDATION.md`.

## Хязгаарлалт ба дараагийн үе шат

- **Phase 1**: Feed archive + lexical анализ. Clustering бүх архивын хосыг харьцуулдаг O(n²); том архивт incremental/indexed matching нэмэхээс өмнө ачааллын тест шаардлагатай. Cluster ID одоогоор дахин тооцогдоно.
- **Phase 2**: Ollama schema-тай JSON, Монгол embedding чанарын үнэлгээ, pgvector similarity, grounded summary/entity/claim extraction, timeout/retry/prompt injection хамгаалалт хараахан хэрэгжээгүй. Ollama profile зөвхөн тусгаарласан service бэлтгэнэ. `docker compose --profile ai up -d ollama`; model татах жишээ: `docker compose exec ollama ollama pull qwen3:8b`. Pipeline хараахан холбогдоогүй. AI байхгүй үед Phase 1 бүрэн хамааралгүй ажиллана.
- **Phase 3**: Evidence graph, claim discrepancy, хүний хяналттай public report, correction workflow, тогтвортой report/event identity нэмнэ. Тайлан нийтэлж байгаа мэт товч байхгүй. Одоогийн нийтлэлийн эх сурвалжийг шууд нээж болно.
- **Phase 4**: VPS deployment, бодит HTTPS/backup-restore баталгаа, ачаалал/SSRF penetration test, мониторинг/alert, config hardening шаардлагатай. Энэ repository өөрөө VPS-д deploy хийгдээгүй.
- Нийтлэл устсан/404 болсон эсэхийг тусад нь crawl хийдэггүй. Feed-ээс алга болсныг устсан гэж тэмдэглэхгүй. Retention автомат purge хараахан хэрэгжээгүй; `retention_days` нь одоогоор ашиглагдахгүй. Зөвшөөрөл, архив хадгалах бодлогоо тогтоохоос өмнө production feed-ийг идэвхжүүлэхгүй.
- JSON API, sitemap, CSV import болон bilingual English UI дараагийн ажил. RSS/Atom л одоогоор дэмжинэ.
- Admin UI байхгүй; хамгаалагдсан API ашиглана. Authentication нь single-admin bearer token; multi-user/role management байхгүй.
- API IP limit нь proxy ард бүх хүсэлт нэг IP болж харагдаж болзошгүй: одоогийн uvicorn `--no-proxy-headers` нь хуурамч forwarded header-д итгэхгүй. Олон нийтийн ачаалалд proxy талын client IP rate limiting эсвэл итгэмжлэгдсэн proxy тохиргоо нэмнэ.
- AI-ийн timeout/JSON болон public report correction тестүүд нь тэдгээр функц хэрэгжээгүй тул ажиллуулаагүй. Үүнийг Phase 1-ийн тесттэй андуурахгүй.

## Монголын 100 эх сурвалжийн лавлах, нэгдсэн хайлтын холбоос

`Монголын 100 сайт` цэсэнд нэр/домэйн, чиглэл, HTTP шалгалтын төлөв, feed илэрсэн эсэх, архивын идэвхээр шүүнэ. Энэ нь **хандалтын статистикаар батлагдсан Top 100 ranking биш**: ХХЗХ-ны 2020/2021 оны бүртгэл болон хэвлэлийн өөрийн нүүр хуудсаас сонгосон 100 домэйн. Нэг сайт нээгдсэн нь түүний агуулга үнэн, feed шинэ, ашиглах эрх зөвшөөрөгдсөн гэсэн баталгаа биш.

Хоёр хайлт тусдаа ажиллана:

- **Веб хайлт**: түлхүүр үгээр Google/Bing-ийн `site:` операторыг ашиглана. 100 сайтыг 10 бүлэг болгон хайх холбоос, сайт тус бүрээр хайх холбоос гаргана. Хэрэглэгч холбоос дээр дарж гаднын хайлтын системийн үр дүнг нээнэ. Хайлтын үр дүнг API-д татаж байгаа, 100 сайтаас realtime мэдээ scrape хийж байгаа мэт харуулахгүй. Хайлтын системийн индексийн хамрах хүрээ, site оператор нь төгс баталгаа биш.
- **Архивын хайлт**: сайт сонгоод `Архиваас хайх` дарвал `articles?domain=...&q=...` API-аар зөвхөн татаж хадгалсан нийтлэлийг хайна. Татагдаагүй сайтад хоосон үр дүн гарна.

API:

```text
GET /api/v1/media?q=ikon&category=news&availability=reachable&limit=20&offset=0
GET /api/v1/media/search?q=Оюутолгой&engine=google
GET /api/v1/media/search?q=төсөв&domain=ikon.mn&engine=bing
GET /api/v1/articles?q=төсөв&domain=ikon.mn
```

`media/search` нь **external_search_links**, мэдээний үр дүнгийн массив биш. Нэрээр шүүх `media?q` болон мэдээний агуулгаар хайх `articles?q`-г ялгана.

Сонголт ба HTTP шалгалтын evidence:

- `backend/app/data/mongolia100.v1.json`: хувилбарласан 100 домэйн, provenance, төрөл.
- `backend/app/data/probe-2026-10-19.json`: сонгосон 100 домэйны нүүр/feed шалгалтын бодит үр дүн.
- `backend/app/data/probe-all-2026-10-19.json`: 275 нэр дэвшигчийн шалгалтын тайлан, timeout/403/503, өөр зориулалттай болсон шалтгаан. Энэ нь буруутгал, найдвартай байдлын үнэлгээ биш.

Feed snapshot нь тухайн хөгжүүлэлтийн орчны HTTP proxy-оор хийсэн XML parse шалгалт. Production-ийн robots, pinned DNS, лицензийн шалгалтыг орлохгүй. Нүүр HTTP 200 болсныг feed баталгаажсан гэж тооцоогүй; comments feed-ийг тусад нь хассан. Шалгалт амжилтгүй гэдэг нь сайт бүх хэрэглэгчид ажиллахгүй гэсэн дүгнэлт биш.

### VPS дээр feed-үүдийг бодитоор холбох

```sh
# Одоогийн 100 домэйн болон www хувилбарууд security allowlist-д багтсан.
# Шинэчлэх, migration:
docker compose build
docker compose run --rm migrate
docker compose up -d
# Бүх лавлах сайтаас explicit RSS/Atom feed нээж, robots ба XML шалгана:
docker compose exec backend python -m app.catalog_sync
# Эсвэл нэг сайт:
docker compose exec backend python -m app.catalog_sync --domain mnb.mn
```

Sync нь feed хүчинтэй бол Source-г idempotent үүсгэн validated_at хадгалж, **шинэ эх сурвалжийг идэвхгүй** үлдээнэ. Лиценз/ашиглалтын тайлбарыг бодитоор бүртгэж байж админ идэвхжүүлнэ. `POST /sources` нь name, endpoint, publisher, license, permission_note талбаруудтай; Source байгаа бол доорх PATCH-ээр эдгээр тайлбарыг шинэчилж болно. Robots болон лицензийн шалгалтыг тойрч бүх эх сурвалжийг сохроор идэвхжүүлэхгүй. Хэвлэлийн бүрэн агуулгыг дахин нийтлэхгүй.

Feed snapshot-аас зөвхөн URL/probe metadata дамжсан; бодит нийтлэлийн архивт судалгааны fixture эсвэл зохиомол мэдээ оруулаагүй. Сайтын нэр, домэйн бүр Google/Bing хайлттай шууд ажиллах бөгөөд архив нь баталгаажуулж идэвхжүүлсэн feed-ээс бүрдэнэ.

Импортолсон feed-ийн бодит эрхийн тайлбарыг оруулах жишээ (placeholder-ийг шалгасан утгаар солино):

```sh
curl --fail -X PATCH "$BASE_URL/api/v1/sources/1" \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H 'Content-Type: application/json' \
  -d '{"license":"Шалгасан нөхцөлийн URL","permission_note":"Зөвшөөрөгдсөн metadata/excerpt ашиглалтын хүрээ","active":true}'
```

2026-10-19-ний snapshot: 100 сонгосон домэйнээс 96 нүүр хуудас нээгдсэн, 23 feed XML parse амжилттай. Тухайн орчинд timeout/403 болсон нь сайт бүх хэрэглэгчид ажиллахгүй гэсэн баталгаа биш. Шалгалтын дэлгэрэнгүй `VALIDATION.md` болон JSON файлуудад байна.
