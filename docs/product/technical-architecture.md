# Technical Architecture Roadmap

## Current State

- Backend: Flask monolith.
- Database: PostgreSQL in production through `DATABASE_URL`; Python `sqlite3` remains the local/test fallback through the same `huishi/db.py` boundary.
- Default local database path: `data/huishi.sqlite3` via `HUISHI_DATABASE`.
- Task execution: configurable generation backend in `huishi/generation_queue.py`.
  - Local/dev fallback: in-process `ThreadPoolExecutor`.
  - Ubuntu production path: `Redis + RQ` with `worker.py`.
- Deployment docs now describe `gunicorn + wsgi.py + systemd + Nginx + Redis + RQ`.
- Redis is integrated for generation queue and upstream generation limits. Generation concurrency uses expiring per-task slot tokens, not a single long-lived counter, so killed workers do not permanently consume capacity.
- PostgreSQL is live on the Ubuntu VM with startup enforcement, SQL translation, fresh-schema conversion, production smoke, backup/restore rehearsal, and a full isolated PostgreSQL pytest profile.
- Celery and SQLAlchemy are not currently integrated.
- Local upload storage has a `storage-sweep` CLI for orphan cleanup and capacity reporting.

## Target State

The long-term target is a production architecture that can run on an Ubuntu server and later scale beyond one process:

- Flask app served by Gunicorn behind Nginx or Caddy.
- Database configurable through a stable app-level database layer.
- PostgreSQL for production once SQL compatibility and migrations are ready.
- Redis for rate limits, short-lived locks, generation state cache, and later queue coordination.
- External queue such as RQ + Redis for image generation and agent tasks.
- Explicit deployment, backup, rollback, and smoke-test documentation.

## Phase P0: Ubuntu-Ready Current Stack

Purpose: make the current app deployable safely before broader architecture changes.

Status: completed as the historical baseline; production has advanced through P2, P3, and P4.

Scope:

- Add `wsgi.py` for Gunicorn.
- Add `gunicorn` dependency.
- Harden SQLite connections with `timeout`, `busy_timeout`, `journal_mode=WAL`, `synchronous=NORMAL`, and `foreign_keys=ON`.
- Update Ubuntu deployment docs with venv, environment variables, systemd, Nginx, and smoke tests.
- Keep Gunicorn conservative while generation execution is in-process; with `HUISHI_GENERATION_QUEUE_BACKEND=rq`, production can run multiple Gunicorn workers because image generation is externalized.
- Fix foreign-key regressions exposed by enabling SQLite constraints.

Acceptance:

- `python -m py_compile` passes for changed Python entry points.
- Full pytest suite passes.
- `wsgi.py` imports with a temporary database.
- Deployment docs include Ubuntu service, reverse proxy, environment, data directory, and SQLite WAL checks.
- Claude review has no unresolved `BLOCKER`.

Risks:

- SQLite still permits only one writer at a time.
- In-process generation queue prevents safe multi-worker or multi-host scaling.
- WAL requires local disk and correct backup handling for `*.sqlite3`, `*.sqlite3-wal`, and `*.sqlite3-shm`.

## Phase P1: Database Access Boundary

Purpose: prepare for PostgreSQL without changing the database engine yet.

Scope:

- Inventory all SQL statements and SQLite-specific constructs.
- Centralize connection creation, transaction helpers, and row conversion.
- Add tests around destructive operations, billing updates, generation task transitions, and invite/canvas foreign-key paths.
- Document SQL compatibility risks: `AUTOINCREMENT`, partial indexes, `INSERT OR IGNORE`, `PRAGMA`, `lastrowid`, `?` placeholders, and date handling.

Acceptance:

- A SQL inventory exists.
- High-risk write paths have tests.
- No route performs hidden connection setup outside the shared database module.

## Phase P2: PostgreSQL Compatibility

Purpose: make PostgreSQL a supported deployment target.

Status: implemented for fresh PostgreSQL production deployments. `DATABASE_URL`, psycopg, placeholder translation, fresh schema conversion, startup enforcement, server smoke, full isolated PostgreSQL pytest, application smoke, automated backups, checksum verification, and isolated restore rehearsal have passed. Importing an unrelated legacy SQLite dataset still requires a dedicated migration rehearsal before that dataset is cut over.

Scope:

- Add `DATABASE_URL` while keeping SQLite for local tests.
- Choose migration tooling, likely Alembic or a lightweight explicit migration runner.
- Convert schema and SQL incompatible with PostgreSQL.
- Add a PostgreSQL test profile for critical paths.
- Provide SQLite-to-PostgreSQL migration and rollback instructions.

Acceptance:

- Critical tests pass against PostgreSQL.
- Fresh PostgreSQL database can initialize from migrations.
- Existing SQLite data has a documented export/import path.
- Production cutover has backup, restore, and smoke-test steps.

## Phase P3: Redis Foundation

Purpose: add shared infrastructure without moving generation execution yet.

Status: implemented for generation limits and auth/email short-window limits. Redis is used when `HUISHI_REDIS_URL` is configured; local/test mode keeps an in-memory fallback.

Scope:

- Add Redis configuration with optional local/off behavior.
- Move generation upstream limits, login lockout state, email-code send limits, and password-reset attempt limits into Redis.
- Keep durable records in the database.
- Add timeout, retry, and fallback behavior when Redis is unavailable.
- Use expiring per-task upstream concurrency slots so a killed worker only holds capacity until its slot TTL.

Acceptance:

- App boots without Redis in local/test mode.
- Production mode clearly fails or degrades according to documented configuration.
- Redis-backed generation and auth/email rate limits have tests.

## Phase P4: External Task Queue

Purpose: support multiple app workers and reliable background work.

Status: implemented for image generation through `Redis + RQ`.

Scope:

- Move image generation and canvas/agent long tasks from in-process `ThreadPoolExecutor` to RQ + Redis or Celery.
- Store durable task state in the database.
- Make worker startup a separate systemd service.
- Add retry, timeout, cleanup, and stuck-task recovery.
- Workers wait for shared upstream capacity before calling the provider, so normal queue pressure does not immediately fail user tasks.

Acceptance:

- Gunicorn can safely use multiple workers only after both conditions are true: P3 has moved login/email rate limits and lockout state to shared storage, and P4 has moved generation execution to an external queue.
- A worker restart does not lose queued tasks.
- Generation polling works regardless of which app worker handles the request.
- Deployment docs include app service, worker service, Redis, and rollback.
- RQ job timeout is configured above the upstream wait window plus image API timeout; task stale detection is also configured above that combined window.

## Current Decision

The current Ubuntu production deployment uses PostgreSQL + Redis/RQ with `HUISHI_REQUIRE_POSTGRES=1` and `HUISHI_REQUIRE_REDIS_LIMITS=1`. Fresh deploys must pass `tools/db_smoke.py`, the isolated PostgreSQL pytest profile, application smoke, backup verification, and restore rehearsal. Existing third-party or legacy SQLite data still requires a staging migration rehearsal before importing it into production.

## Multi-Worker Safety Notes

With `HUISHI_GENERATION_QUEUE_BACKEND=rq` and `HUISHI_REDIS_URL`, generation execution, upstream generation limits, login failure lockout, email-code send limits, and password-reset attempt limits use shared Redis state. For a single Ubuntu host, `gunicorn -w 2 -k gthread --threads 4` is the documented production starting point. Multi-host deployment should still receive a real staging smoke test with the same Redis, database, upload storage, and reverse-proxy topology as production.
