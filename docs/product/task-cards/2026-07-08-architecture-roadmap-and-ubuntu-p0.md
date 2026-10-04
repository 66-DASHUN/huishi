# Task Card: Architecture Roadmap and Ubuntu P0

## Metadata

- Task ID: ARCH-2026-07-08-P0
- Task Name: Architecture roadmap and Ubuntu-ready deployment baseline
- Current Stage: Production Verification Complete
- Current Status: PostgreSQL + Redis/RQ production active; full isolated PostgreSQL test profile, backup verification, restore rehearsal, and application smoke passed
- Priority: High
- Owner: Codex
- Advisory Reviewer: Claude

## Background

The user wants Codex and Claude to collaborate on architecture decisions and optimize the project for a production-ready path involving PostgreSQL, Redis, and queues. The user also confirmed the deployment target is Ubuntu.

## Goal

Create an incremental architecture route and make the current Flask + SQLite application safer to deploy on Ubuntu before beginning PostgreSQL/Redis migration work.

## Scope

- Record confirmed architecture requirements.
- Record the Claude/Codex collaboration protocol.
- Record the phased technical architecture route.
- Harden the current SQLite deployment baseline.
- Add a Gunicorn WSGI entry point.
- Update Ubuntu deployment documentation.
- Fix regressions revealed by enabling SQLite foreign keys.

## Non-goals

- Do not migrate to PostgreSQL in P0.
- Do not introduce Redis in P0.
- Do not replace the in-process generation executor in P0.
- Do not commit, push, or deploy unless the user explicitly requests it.

## Acceptance Criteria

- Architecture docs exist under `docs/product/`.
- `DEPLOY.md` explains Ubuntu deployment through Gunicorn, systemd, and Nginx.
- SQLite production PRAGMAs are applied per connection.
- Foreign-key related delete flows pass tests.
- Full Python test suite passes.
- Claude has reviewed the architecture or implementation diff, and any `BLOCKER` findings are fixed or explicitly tracked.

## Role Notes

- Product: prioritize incremental stability over broad migration.
- Backend: keep P0 small; defer PostgreSQL/Redis until P1/P2/P3.
- Release/Ops: Ubuntu deployment must be explicit and reproducible.
- QA: foreign-key behavior, WSGI import, and full regression tests are required.
- Claude: advisory review found a delete-user cascade issue; Codex fixed it and added tests.

## Decision Log

- P0 deploys with `gunicorn -w 1 -k gthread --threads 4` because generation execution is currently in-process.
- Multi-worker Gunicorn requires both shared auth/rate-limit state and an external generation queue; this is split across P3 and P4.
- PostgreSQL migration begins only after SQL inventory and access-boundary work.
- Redis begins as infrastructure for locks/rate limits before becoming a queue dependency.

## Current Verification

- `python -m py_compile wsgi.py huishi/db.py huishi/records.py huishi/routes_admin.py app.py`
- `pytest -q`
- P1 boundary checks: `tests/test_database_access_boundary.py`
- P1 helper checks: `tests/test_db_helpers.py`

Latest observed result:

- 2026-07-12 production gate: SQLite/default profile `295 passed, 41 skipped`; isolated PostgreSQL profile `313 passed, 41 skipped`; PostgreSQL restore `db_smoke=passed`; frontend `24 passed`; all eight services active.

- `python -m py_compile app.py worker.py wsgi.py huishi/storage.py huishi/generation_queue.py huishi/generation_limits.py huishi/config.py`
- Target queue/limit/storage/settings/canvas tests: `40 passed, 28 skipped`
- Full suite: `163 passed, 37 skipped`
- Latest focused checks after shared Redis auth limits and blocking upstream wait:
  - `HUISHI_CANVAS_PROJECT_DIR=D:\AI\huishihuabu\infinite-canvas .venv\Scripts\python.exe -m pytest -q tests/test_canvas_embed_mode_contract.py tests/test_settings_config_status.py tests/test_generation_rate_limits.py tests/test_shared_rate_limits.py tests/test_sqlite_production_settings.py` -> `62 passed`
  - `.venv\Scripts\python.exe -m pytest -q` -> `188 passed, 41 skipped`
  - `cd infinite-canvas\web && bun run typecheck` -> passed
  - `cmd /c restart-dev.bat`; main `http://127.0.0.1:8000/` -> `200`, canvas `http://127.0.0.1:3000/` -> `200`
  - Claude produced JSON UI guidance and one implementation review. A second review attempt timed out through both MCP bridge and direct Claude CLI after the risk fixes.
- Latest Claude architecture review found four production-readiness risks: RQ timeout below wait+API timeout, HTTPS being documented as optional despite Secure Cookie, Redis active counter leakage after killed workers, and stale task windows below the limiter wait window. Codex fixed these in config, limiter implementation, worker state flow, and deployment docs.

## P1 Progress

- Added SQL inventory under `docs/db/sql-inventory.md`.
- Added database access boundary tests.
- Added `sql_placeholders(...)` and `transaction()` helpers in `huishi/db.py`.
- Applied `sql_placeholders(...)` to `delete_user_cascade(...)` after covering the relevant delete-user paths.
- Added invite redemption transaction tests and moved registration + invite redemption to `transaction()`.
- Added generation task creation rollback coverage and moved `/generate` task creation to `immediate_transaction()`.
- Added final generation rollback coverage and moved `_finalize_generation(...)` record creation + billing deduction to `transaction()`.
- Moved app-setting key reads and workspace bulk asset `IN (...)` queries to `sql_placeholders(...)`, with boundary and behavior tests.
- Moved admin bulk invite/user `IN (...)` and `NOT IN (...)` queries to `sql_placeholders(...)`, with route-level regression tests.
- Added generation worker rollback coverage and wrapped final record creation, billing, and task success marking in one `transaction()`, including generated-output cleanup on rollback.
- Moved password reset and email verification writes in `huishi.auth` to `transaction()`, with verification-link regression coverage.

## P3/P4 Progress

- Added `redis==5.2.1` and `rq==2.1.0`.
- Added `worker.py` for RQ workers.
- Added `HUISHI_GENERATION_QUEUE_BACKEND=rq`, `HUISHI_REDIS_URL`, `HUISHI_RQ_QUEUE_NAME`, and RQ timeout/TTL settings.
- Added Redis-backed upstream limiter with defaults aligned to the user's upstream capacity: `HUISHI_UPSTREAM_MAX_CONCURRENCY=240` and `HUISHI_UPSTREAM_RPM_LIMIT=300`.
- Kept in-memory limiter as local fallback when Redis is not configured.
- Added queue and limiter tests.
- Added shared Redis auth/email limits for login lockout, registration email-code sends, password-reset email-code sends, and password-reset attempts, with in-memory local fallback.
- Changed generation workers to wait for shared upstream capacity before calling providers instead of immediately failing queued tasks during normal concurrency/RPM pressure.
- Added `HUISHI_GENERATION_LIMIT_WAIT_TIMEOUT_SECONDS` and `HUISHI_GENERATION_LIMIT_WAIT_SLEEP_SECONDS`.
- Changed `HUISHI_RQ_JOB_TIMEOUT_SECONDS` default to `1200`, and made RQ enqueue use a safe floor above limiter wait + image API timeout.
- Changed `HUISHI_GENERATION_TASK_STALE_SECONDS` default to cover limiter wait + image API timeout.
- Production startup now requires `HUISHI_REDIS_URL` by default through `HUISHI_REQUIRE_REDIS_LIMITS=1`, so auth/email limits do not silently degrade to per-process memory state on multi-worker Ubuntu deployments.
- Redis RPM rejection now clamps the minute key to the configured RPM with a TTL instead of decrementing, avoiding negative counters and no-TTL windows.
- Redis upstream concurrency now uses expiring per-task ZSET slot tokens instead of a single active counter, so a killed worker does not permanently consume an upstream slot.

## Storage Progress

- Added `huishi/storage.py` with `sweep_local_uploads(...)`.
- Added `flask storage-sweep`, defaulting to dry-run; `--delete` is required to remove files.
- Storage sweep preserves visible asset references and active task references, deletes old orphan files, and reports capacity pressure without deleting referenced data.
- Added storage sweeper tests.

## UI Progress

- Claude produced a JSON style reference for non-home UI.
- Added scoped `--nx-*` homepage-video-inspired styling for `.auth-page`, `.console-page`, and dark `.workspace-page`.
- Did not add `.home-page` or `.hero-*` selectors in the UI patch.
- Changed new workspace sessions to default to dark theme while preserving saved user theme choices.

## PostgreSQL Production Status

- PostgreSQL compatibility (P2) is implemented for the current fresh production deployment.
- Added `DATABASE_URL=postgresql://...`, psycopg dependency, SQL placeholder translation, `INSERT OR IGNORE` rewrite, fresh schema conversion, and fake PG initialization tests.
- Local Docker PostgreSQL 16 smoke passed against `postgresql://huishi:smoke@127.0.0.1:55432/huishi_smoke`: schema initialization, basic select, transaction rollback, `INSERT OR IGNORE` conflict handling, user insert, Provider save/read, canvas setting save/read, generation task status flow, record insert, storage referenced-file protection, and admin user cascade delete.
- Added `tools/db_smoke.py` and `docs/db/postgres-smoke.md` so the same smoke gate can run locally and on the Ubuntu server from `DATABASE_URL`.
- Added `HUISHI_REQUIRE_POSTGRES`, `.env.local-postgres.example`, `compose.local-postgres.yml`, and `docs/db/local-to-ubuntu-postgres.md` so fresh deploys can test locally with the same PostgreSQL/Redis shape intended for Ubuntu.
- The Ubuntu deployment now runs PostgreSQL on the server with Redis/RQ generation, startup guards, daily custom-format backups, SHA-256 verification, and an isolated restore rehearsal.
- A dedicated PostgreSQL pytest profile resets an explicitly named test/rehearsal schema before every test; the full profile passed without touching the production database.
- Importing a separate legacy SQLite dataset remains a distinct migration project and still requires a real-data rehearsal before that dataset is imported.
