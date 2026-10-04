# PostgreSQL Smoke Test

Use this when you want to prove that the same PostgreSQL path can run locally and on the Ubuntu server.

## Local Docker PostgreSQL

Start Docker Desktop first, then run:

```powershell
docker run --rm -d --name huishi-pg-smoke `
  -e POSTGRES_PASSWORD=smoke `
  -e POSTGRES_USER=huishi `
  -e POSTGRES_DB=huishi_smoke `
  -p 55432:5432 `
  postgres:16

docker exec huishi-pg-smoke pg_isready -U huishi -d huishi_smoke
```

Run the shared smoke script:

```powershell
$env:DATABASE_URL="postgresql://huishi:smoke@127.0.0.1:55432/huishi_smoke"
$env:HUISHI_OUTPUT_DIR="D:\AI\huishihuabu\data\pg-smoke-uploads"
.\.venv\Scripts\python.exe tools\db_smoke.py
```

Expected output includes:

```text
PASS schema_init
PASS basic_select
PASS transaction_rollback
PASS insert_or_ignore_conflict
PASS user_insert
PASS provider_and_canvas_settings
PASS generation_task_insert
PASS generation_task_to_record
PASS storage_reference_protection
PASS delete_user_cascade
db_smoke=passed
```

Run it twice. The second run must also pass.

Stop the local container when finished:

```powershell
docker stop huishi-pg-smoke
```

## Ubuntu Server Gate

After PostgreSQL is installed and a database/user is created, export the server `DATABASE_URL` and run the same script before starting production traffic:

```bash
cd /opt/huishi
export DATABASE_URL='postgresql://huishi:REPLACE_ME@127.0.0.1:5432/huishi'
export HUISHI_OUTPUT_DIR=/var/lib/huishi/uploads
./.venv/bin/python tools/db_smoke.py
```

Do not put real credentials in logs. The script masks the password when printing `DATABASE_URL`.

## What It Checks

- PostgreSQL schema initialization through the app's normal `init_db()` path
- Basic reads
- User insert
- Provider save/read
- Canvas setting save/read
- Generation task insert and status flow
- Record insert
- Storage referenced-file protection
- Admin user cascade delete
- Cleanup of the smoke user, smoke provider, and temporary files

## Release Rule

PostgreSQL can be used for a new server only after this smoke script passes on that server.

For migrating an existing SQLite database, first run `tools/migrate_sqlite_to_postgres.py` against a staging PostgreSQL database, then run `tools/db_smoke.py` against the migrated database before pointing production traffic at it.
