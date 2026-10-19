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
