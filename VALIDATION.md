# Phase 1–4 хэрэгжүүлэлт ба шалгалт — 2026-10-19

Энэ тайлан нь **бодитоор ажиллуулсан шалгалт**, **кодын хэрэгжүүлэлт**, **VPS дээр үлдсэн commissioning**-ийг ялгана. Дэмжигдээгүй зүйлийг ажилласан гэж мэдэгдээгүй.

## Амжилттай ажиллуулсан

| Шалгалт | Үр дүн |
|---|---|
| Python backend suite | **66 passed, 2 skipped** |
| Next.js 16.4.2 production build + TypeScript | Амжилттай; `/` ба SSR `/reports/[id]` |
| npm audit --omit=dev | **0 known vulnerabilities** |
| Python pip-audit | **0 known vulnerabilities** — dependency шинэчлэсний дараа |
| pip check | Broken requirements байхгүй |
| Alembic SQLite upgrade/downgrade | `0001_archive` → `0002_evidence` → `0003_provenance` амжилттай |
| Existing archive migration test | Хуучин article/version/event membership хадгалагдаж, per-version source provenance backfill хийгдсэн |
| PostgreSQL offline migration SQL | DDL үүсгэх амжилттай; native database execution биш |
| Compose JSON Schema | Албан ёсны Compose schema-гаар YAML бүтцийг validate хийсэн |
| Ops scripts | Shell syntax, private setup, preflight, no-overwrite/no-secret-output тестүүд амжилттай |
| Live HTTP integration | FastAPI + SQLite + worker + standalone Next.js + SSR report + publish/correction урсгал амжилттай |

### Backend кейсүүд

- RSS/Atom parsing, invalid XML/entity, bounded CSV/JSON/sitemap, explicit timezone ба unknown timezone handling.
- Canonical URL, SHA-256, lexical similarity, archive versions, metadata-only sitemap → real feed upgrade, first_seen хадгалах, per-version source provenance.
- Stable/merged event IDs, immutable report snapshot, source/evidence links, numeric discrepancy candidates.
- Local Ollama API **contract tests**: strict schema, untrusted-data prompt separation, exact quote/name/value validation, hallucination rejection, timeout/retry, invalid JSON, 1024-dimensional finite embedding validation.
- AI offline fallback, complete pipeline using an explicitly mocked local inference client, grounded entities, embeddings, draft generation; автоматаар publish хийгдээгүй.
- Admin auth, explicit privacy review, snapshot hash conflict, expired draft rejection, publish/withdraw, pending correction privacy, moderated annotation, graph provenance.
- Public PII pattern redaction, request size, pagination/search, rate limit, private/mixed DNS block, credential-bearing URLs, redirected-target robots policy, pinned destination/Host/SNI contract.
- Retention нь current version ба published/withdrawn report evidence-г хамгаална. Native PostgreSQL lock behavior-ийг SQLite test батлахгүй.
- Empty dashboard/API, DB failure, collector success/timeout, internal metrics, worker stale status.

### Live HTTP integration-ийн хамрах хүрээ

`ops/http-e2e.py` нь тусгаарласан temporary SQLite DB, random test-only admin token, `[DEMO]` тэмдэгтэй fixture үүсгэнэ. Production DB/эх сурвалж/тайланд хүрэхгүй. Дараахыг бодитоор HTTP-ээр ажиллуулсан:

1. Alembic head schema + archive fixture → lexical pipeline → draft.
2. Uvicorn API, worker process, standalone Next.js сервер.
3. Next.js `/api` rewrite → FastAPI → бодит test DB.
4. Админ human-review publish → нийтийн source/evidence JSON.
5. `/reports/{id}` server-rendered HTML дотор бодит fixture quote харагдсан; invalid report URL 404.
6. Correction pending текст нийтэд гараагүй → админ accepted review → public annotation.
7. AI disabled үед lexical_fallback; worker heartbeat шинэ.

Дуусахад process ба temporary fixture-үүдийг цэвэрлэсэн. Эдгээр нь жинхэнэ мэдээний статистик биш. UI/browser interaction/visual QA-г HTTP smoke-той андуурахгүй.

## Dependency security шинэчлэлт

Audit-аар илэрсэн хуучин Starlette, pytest, pip-ийг шинэчилсэн. Одоогийн direct pins: FastAPI **0.148.0**, Starlette **1.9.0**, dev pytest **9.1.1**; Docker build pip **26.2.1**. Шинэ хувилбаруудаар suite болон HTTP integration дахин амжилттай.

Audit 0 нь тухайн vulnerability database-ийн мэдэгдэж буй асуудалгүй гэсэн үг; Docker base OS/image scan, penetration test эсвэл цаашдын аюулгүй байдлын баталгаа биш. Нэг upstream TestClient/httpx deprecation warning үлдсэн, failure биш.

## Бодит эх сурвалжийн шалгалт

- 275 домэйн шүүж, 100 домэйн сонгосон; хандалтын баталгаатай Top 100 ranking гэж нэрлээгүй.
- Versioned research snapshot: **96 нүүр нээгдсэн, 23 нийтлэлийн feed XML parse амжилттай**.
- Комментийн feed, placeholder болон зориулалт нь өөрчлөгдсөн сайтуудыг ялгасан.
- MONTSAME, Zindaa, Olloo, Bolod-ийн шууд шалгалт timeout/403. Сайт бүх хэрэглэгчид ажиллахгүй гэсэн дүгнэлт биш.
- Судалгааны HTTP proxy нь production pinned DNS + robots + license validation-ийг орлохгүй. Энэ хөгжүүлэлтийн орчинд direct DNS хязгаарлагдсан.
- Production collector-д шинээр автоматаар идэвхжүүлсэн feed **0**. VPS дээр каталог sync → эрхийн тайлбар → activation гэсэн бодит алхам шаардлагатай. Research XML parse-ийг live collector validation гэж тайлагнаагүй.

## Код бэлэн, native/live шалгалт үлдсэн

- **2 skipped тест**: dedicated PostgreSQL/pgvector URL өгөөгүй. Native migration/JSONB/HNSW/cosine болон advisory lock-ийн тестүүд `backend/tests/test_postgres.py`-д байна. SQLite эсвэл offline SQL нь тэдгээрийг орлохгүй.
- Docker/Compose daemon энэ орчинд байхгүй. Docker build/up, image ownership, healthcheck, backup service, real restore check, Caddy HTTPS/ACME certificate-ийг бодитоор ажиллуулаагүй. Schema, shell, Python setup/preflight л шалгасан.
- Бодит Ollama server/model татаж inference ажиллуулаагүй. Contract, schema, fallback, storage/matching flow тесттэй; Монгол хэлний accuracy/embedding benchmark, model latency/RAM/GPU хэмжээг батлаагүй.
- Playwright package байсан ч browser executable байгаагүй; Chromium download амжилтгүй. Browser visual/mobile interaction QA хийгдээгүй. Build/SSR/HTTP шалгалт үүнийг орлохгүй.
- VPS/domain/SSH холболт өгөөгүй тул production deploy, TLS, offsite backup, restore rehearsal, resource/load/security test, notification routing хийсэн гэж мэдэгдээгүй.
- MN үндсэн UI; navigation болон нийтлэг үндсэн labels-д EN сонголт бий. Нийтлэл, нотолгоо, админы бүх тайлбарыг автоматаар бүрэн орчуулах үйлчилгээ биш.

## VPS дээр дуусгах дараалал

1. `python3 ops/setup.py --domain YOUR_DOMAIN` → `sh ops/deploy.sh`.
2. `python3 ops/smoke.py https://YOUR_DOMAIN --require-worker`.
3. Models: `sh ops/ai-setup.sh`, AI_ENABLED=true, AI profile recreate; Admin-аас model reachable шалгах.
4. Эх сурвалж discovery/validation → Terms/лиценз → activation → collect → analyze.
5. Бодит Монгол мэдээний validation corpus дээр extractive/semantic чанар, threshold, false-positive-ийг хэмжих.
6. Draft → хүний review → publish → source links, correction, withdraw урсгалыг бодит орчинд шалгах.
7. Backup dump → isolated restore-check → encrypted offsite хадгалалт.
8. Monitoring profile, alerts, disk, volume permissions, firewall, resource/load/penetration checklist.

Эцсийн production commissioning нь дээрх серверийн бодит орчинд гүйцэтгэгдэх ёстой. Репод Phase 1–4-ийн код, migration, UI, тест, operational scripts орсон нь сервер дээр үйлчилгээг ажиллуулсан гэсэн утга биш.


## 500 хаяг + хайлт + лого шинэчлэл — 2026-10-20 (Улаанбаатар)

- Каталог: 500 давхардалгүй hostname, 326 хэвлэл/мэдээллийн лавлах + 174 албан эх сурвалж; 500 ажилладаг RSS гэсэн баталгаа биш.
- Python: 66 passed, 2 PostgreSQL integration skipped; native PostgreSQL тестийн URL шаардлагатай.
- Next.js production build + TypeScript амжилттай.
- Шинэ кейсүүд: UTC+8 өдрийн эхлэх/дуусах зааг, нийтэлсэн огноогүй нийтлэл, хосолсон domain/category/date шүүлт, wildcard literal, дараалал, AI fallback-ийн хүрээ, Google date URL, Bing огнооны хамгаалалт, бүх сайтын сонголт.
- Publisher favicon + monogram fallback хэрэгжсэн; бүх publisher-ийн дүрс байгаа гэж батлаагүй. Browser screenshot шалгалт хийгдээгүй.
- Өмнөх security/dependency audit үр дүн нь тухайн үеийн snapshot; энэ өөрчлөлт dependency нэмээгүй.

Өргөтгөсөн HTTP судалгаа: 500/500 хаяг оролдсон; 247 нүүр хуудас нээгдсэн, 250 нь энэ орчинд холбогдоогүй/timeout, 2 нь хязгаарлалт/placeholder, 1 нь HTML биш. 180 өөрийн домэйн дээрх icon холбоос, 63 explicit feed candidate илэрсэн. Энэ 63 нь XML parse хийгдсэн RSS гэсэн үг биш. `production_validated=false`; collector идэвхжээгүй. Live HTTP integration-ийг энэ шинэчлэлтэй дахин ажиллуулж PASS авсан.


## Railway deployment бэлтгэл — 2026-10-20

Backend/worker/frontend тусдаа Railway config, backend pre-deploy Alembic, PORT/BIND_HOST, Railway Postgres URL → psycopg 3, Docker build-time BACKEND_URL, frontend `/health` rewrite, Railway дээр үйлчлэх security headers бэлдсэн. CSP нь publisher-ийн HTTPS icon-уудыг зөвшөөрнө. 70 backend tests passed, 2 native PostgreSQL tests skipped; Next.js production build амжилттай. Энэ нь Railway дээр deployment ажилласан гэсэн баталгаа биш; actual service/domain/log validation дараа хийгдэнэ.


## Бодит RSS цуглуулалт — 2026-10-20

Railway production дээр нийтэд нээлттэй 23 RSS endpoint-ийг pinned DNS, robots болон XML parser-аар шалгав. 22 valid feed-ийг гарчиг, анхны холбоос, feed-д нийтэлсэн 600 тэмдэгт хүртэл тоймын хүрээнд идэвхжүүлсэн; бүтэн текстийн лиценз/нийтлэгчийн тусгай зөвшөөрөл гэж мэдэгдээгүй. dailynews.mn-ийн robots шалгалт амжилтгүй тул идэвхгүй хэвээр. Collector production DB-д бодит нийтлэл хадгалж эхэлснийг нийтийн `/articles`, `/statistics`, `/sources` API-аар шалгасан. Картын live feed health, last-success, article-count нь түүхэн homepage snapshot-оос тусдаа; алдаа гарсан ч хадгалсан мэдээ хэвээр үлдэнэ. Backend 71 passed, 2 skipped; Next.js build амжилттай.


## 500 хаягийн сэргээж үргэлжлүүлэх commissioning

HTML headline-only адаптер, publisher-declared news sitemap title, 12 хүртэл зэрэгцээ deadline-тай scan, DB progress/resume, advisory lock, supervised daily scan болон эх сурвалж тус бүрийн хязгаартай зэрэгцээ collector нэмсэн. Навигаци/өөр домэйн/duplicate link-ийг news болгон авахгүй гэсэн кейсүүд, мэдээний provenance, scan resume, нэг host-ийн алдаа бусдыг зогсоохгүй гэсэн кейсүүд нэмэгдсэн. 75 тест passed, 2 native PostgreSQL skipped. 500 хаягийн live scan-ийн тоо нь `/media` ба `/system/status`-ийн бодит progress; код deploy хийсэн нь 500 сайт бүгд ажилласан гэсэн баталгаа биш.


Adapter v2: plain publisher article-ID links (including iKon `/n/...`) нэмсэн. Бодит татсан iKon homepage-оос гарчиг задлах шалгалт амжилттай; өмнөх `no_public_stream` төлөвтэй хаягуудыг шинэ адаптераар нэг удаа дахин шалгана, ажилласан урсгалыг зогсоохгүй. Backend 76 passed, 2 skipped; Next.js build амжилттай. Нийтэлсэн огноо тодорхойгүй гарчгийн цагийг `Илрүүлсэн` гэж ялгаж харуулна.

## Topic evidence research

Read-only `/api/v1/research` searches all query terms in current archived versions, with category/domain and inclusive Ulaanbaatar date filters. Returns exact title/excerpt quotes (PII redaction marked), version IDs, SHA-256, original links, known publication and discovery timestamps, and unverified numeric statement candidates. Headline-only scope is explicit. Graph tab includes a search workspace refreshing every 60 seconds while open. No independent corroboration, truth score, full-text access or AI inference is asserted. Backend: 79 passed, 2 PostgreSQL tests skipped locally. Frontend production build passed.

Isolated real HTTP integration also passed through standalone Next rewrite: research returned both DEMO version-grounded results and numeric candidates; existing human review, SSR reports, moderated correction, worker heartbeat and AI-offline fallback passed. No production fixture writes.

## Local AI analysis and connection candidates

Qwen3 extraction and BGE-M3 embeddings run in a private Ollama service with persistent models. Hosted production uses qwen3:4b within Railway's 8 GB service memory ceiling. An installed-model heartbeat is distinct from successful inference. Worker analysis and collection run independently; AI batches are capped at four and divide capacity between newest news and oldest backfill. Headline-only articles now receive grounded AI extraction and embeddings, retaining explicit scope. Public analysis exposes only current-version quotes, unverified claims, named entities and source-cited shared-name/semantic candidates. Entity names are mentions, not resolved identity or proof of actual relationships. Published reports still require human review. Local checks: 82 passed, 2 PostgreSQL tests skipped; frontend production build and isolated real HTTP integration passed. Live model/inference verification must be checked separately after deploy.
