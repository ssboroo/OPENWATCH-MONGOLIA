# Phase 1 шалгалтын тайлан — 2026-10-19

## Амжилттай ажиллуулсан

- Python 3.12: `cd backend && ../.venv/bin/python -m pytest -q` — **18 passed**. RSS/Atom, invalid XML/entity, canonical URL, hash/lexical similarity, article version, event clustering, empty API, auth, pagination/search, rate limit, SSRF/private DNS, robots denial, collector success/timeout, DB failure, activation validation, Alembic upgrade/downgrade.
- Next.js **16.4.2** production build ба TypeScript шалгалт амжилттай. Эхний 15.x хувилбарыг npm audit-ийн зөвлөмжөөр шинэчилсэн.
- `npm audit --omit=dev` — **0 vulnerabilities** (тухайн шалгасан registry-ийн тайлан; цаашдын аюулгүй байдлын баталгаа биш).
- Alembic upgrade → downgrade disposable SQLite дээр амжилттай; PostgreSQL offline SQL үүсгэх шалгалт амжилттай. Migration-ийн JSONB Text reference алдааг илрүүлж зассан.
- Production standalone frontend → Next.js API rewrite → бодит FastAPI process → Alembic-аар үүсгэсэн SQLite DB гэсэн HTTP smoke шалгалт амжилттай: нүүр 200, statistics бодит 0, archive хоосон жагсаалт.

## Ажиллуулаагүй / баталгаажаагүй

- Энэ орчинд Docker болон PostgreSQL server binary байхгүй: Docker image build, Compose up, pgvector/JSONB runtime, advisory lock concurrency, live PostgreSQL migration шалгаагүй.
- Playwright package байсан ч Chromium executable байхгүй: browser visual/mobile interaction тестийг ажиллуулах боломжгүй байсан. HTTP smoke ба production build нь visual QA-г орлохгүй.
- Бодит RSS endpoint **0 баталгаажуулсан**; идэвхтэй эх сурвалж 0. Test fixture нь нийтэд харуулах мэдээлэл биш.
- VPS deploy, домэйн, HTTPS сертификат, backup cron, бодит restore test, alerting: сервер дээр ажиллуулаагүй. Script/config бэлтгэсэн.
- Ollama model болон AI pipeline ажиллуулаагүй; Phase 2 implementation хараахан хийгдээгүй. AI offline/timeout/invalid JSON кейсийг хэрэгжсэн мэт тестлээгүй.
- Evidence graph, claim verification, public report source links, correction workflow: Phase 3. Нийтлэлийн source URL-ын API тест нь public report тест биш.
- Ачаалал, том архив, redirect/TLS SNI end-to-end, DNS rebinding penetration тест хийгээгүй. DNS private/mixed-address block unit тесттэй.

Төгс production систем гэж батлаагүй. Phase 1-ийн бодит код, тест, ажиллуулах тохиргоо бөгөөд Phase 2–4 болон deployment баталгаажуулалт үлдсэн. Тестээс нэг upstream AnyIO/Starlette deprecation warning гарсан, failure биш.

## 100 эх сурвалжийн шинэчлэлт — 2026-10-19

- 275 домэйнд HTTP судалгаа хийж, зориулалт өөрчлөгдсөн, placeholder болон комментийн feed-ийг ялгасан. 100 домэйн сонгосон; **96 нүүр хуудас нээгдсэн, 23 нийтлэлийн feed XML parse амжилттай**. MONTSAME, Zindaa, Olloo, Bolod-ийн шууд HTTP шалгалт timeout/403 хэвээр; хайлтын холбоосыг ашиглаж болно. Хандалтын Top 100 эрэмбэ гэж батлаагүй.
- Research proxy-ийн шалгалт нь production pinned-DNS, robots, license validation-ийг орлохгүй. Live collector-ийн баталгаажсан шинэ source **0**, автоматаар идэвхжүүлсэн source **0**; VPS дээр `catalog_sync` + эрхийн бүртгэл + activation шаардлагатай.
- `pytest`: **30 passed**. Нэмэлт кейсүүд: 100 unique domain, provenance, directory/search pagination/filter, Google/Bing query encoding, 10 бүлгийн 100 домэйны бүрэн хамралт, мэдээний үр дүн зохиохгүй external link contract, invalid domain/engine, domain archive filtering, импортолсон source-ийн эрх шинэчлэх, feed sync idempotence ба auto-activation хориг.
- Next.js production build/TypeScript: шинэ media directory component-той амжилттай.
- Шинэ UI-д site search, category/status filter, Google/Bing external links, archive domain filter холбогдсон. Гаднын хайлтын системийн үр дүнг дотоод агрегат үр дүн мэт харуулаагүй.
- Өмнөх Docker/PostgreSQL/VPS/browser executable хязгаарлалтууд хэвээр. Feed parse нь XML формат шалгасан болохоос нийтлэлийн үнэн зөв, шинэ байдал эсвэл лицензийн зөвшөөрлийг батлаагүй.
