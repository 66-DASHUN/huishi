# 本地到 Ubuntu 的 PostgreSQL 同一路线

目标：本地先用 PostgreSQL + Redis/RQ 跑通，服务器上线时继续使用同一组后端类型和同一个验证门槛，避免本地 SQLite、服务器 PostgreSQL 两套语义漂移。

注意：这是一条 PG-first 验证路线，不是“已经生产可用”的证明。服务器上的 `db_smoke`、全量 pytest、应用 smoke 和必要的迁移彩排全部通过后，才能放生产流量。

## 当前结论

- fresh deploy 可以走 PG-first 路线。
- 存量 SQLite 数据迁移不能直接上线，必须先做 staging 迁移彩排和数据一致性校验。
- 本地通过不等于服务器通过；上线前必须在 Ubuntu 服务器重复 `db_smoke -> pytest -> application smoke`。

## 本地依赖

启动本地 PostgreSQL 16 和 Redis 7：

```powershell
docker compose -f compose.local-postgres.yml up -d
docker exec huishi-local-postgres pg_isready -U huishi -d huishi_smoke
docker exec huishi-local-redis redis-cli ping
```

使用本地 PG profile：

```powershell
Copy-Item .env.local-postgres.example .env
```

如果 `.env` 里已有真实 key，不要覆盖；只把下面这些变量合并进去：

```env
DATABASE_URL=postgresql://huishi:smoke@127.0.0.1:55432/huishi_smoke
HUISHI_REQUIRE_POSTGRES=1
HUISHI_REDIS_URL=redis://127.0.0.1:56379/0
HUISHI_GENERATION_QUEUE_BACKEND=rq
HUISHI_REQUIRE_REDIS_LIMITS=1
```

## 本地验证门槛

先跑数据库 smoke，建议连续跑两次：

```powershell
$env:DATABASE_URL="postgresql://huishi:smoke@127.0.0.1:55432/huishi_smoke"
$env:HUISHI_OUTPUT_DIR="D:\AI\huishihuabu\data\pg-smoke-uploads"
.\.venv\Scripts\python.exe tools\db_smoke.py
.\.venv\Scripts\python.exe tools\db_smoke.py
```

必须看到：

```text
db_smoke=passed
```

再跑关键测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_db_backend.py tests/test_sqlite_to_postgres_migration.py tests/test_database_access_boundary.py tests/test_db_helpers.py tests/test_admin_delete_user_cascade.py tests/test_storage_sweeper.py tests/test_sqlite_production_settings.py
```

上线前还要在 PostgreSQL 环境下跑全量测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## 本地应用启动

Web：

```powershell
.\.venv\Scripts\python.exe app.py
```

RQ worker：

```powershell
.\.venv\Scripts\python.exe worker.py
```

本地应用 smoke 至少走一遍：

- 管理员登录
- 后台配置 image provider 和 agent/text provider
- 普通用户提交一次生图
- 画布页提交一次生图
- 邀请码创建/兑换
- 积分流水变化正确
- `flask --app wsgi:app storage-sweep` dry-run 正常

## Ubuntu 服务器

安装依赖：

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nginx postgresql postgresql-contrib redis-server
sudo systemctl enable --now postgresql redis-server
```

创建 PostgreSQL 用户和库：

```bash
sudo -u postgres createuser huishi
sudo -u postgres createdb -O huishi huishi
sudo -u postgres psql -c "ALTER USER huishi WITH PASSWORD 'REPLACE_WITH_STRONG_PASSWORD';"
```

服务器 `.env` 必须显式使用 PostgreSQL：

```env
HUISHI_ENV=production
HUISHI_SECRET_KEY=replace-with-a-long-random-secret
HUISHI_ADMIN_PASSWORD=replace-with-a-strong-admin-password
HUISHI_ENCRYPTION_KEY=replace-with-fernet-key

DATABASE_URL=postgresql://huishi:REPLACE_WITH_STRONG_PASSWORD@127.0.0.1:5432/huishi
HUISHI_REQUIRE_POSTGRES=1
HUISHI_OUTPUT_DIR=/var/lib/huishi/uploads
HUISHI_LOG_DIR=/var/log/huishi

HUISHI_GENERATION_QUEUE_BACKEND=rq
HUISHI_REDIS_URL=redis://127.0.0.1:6379/0
HUISHI_REQUIRE_REDIS_LIMITS=1
HUISHI_RQ_JOB_TIMEOUT_SECONDS=1200
```

生成 `HUISHI_ENCRYPTION_KEY`：

```bash
./.venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

服务器放行前必须执行：

```bash
cd /opt/huishi
export DATABASE_URL='postgresql://huishi:REPLACE_WITH_STRONG_PASSWORD@127.0.0.1:5432/huishi'
export HUISHI_OUTPUT_DIR=/var/lib/huishi/uploads
./.venv/bin/python tools/db_smoke.py
./.venv/bin/python -m pytest -q
```

然后启动 `gunicorn` 和 `worker.py`，再做一次完整应用 smoke。

## 上线阻断条件

以下任一项未通过，都不能声明 PostgreSQL 生产可用：

- `HUISHI_REQUIRE_POSTGRES=1` 下应用能正常启动，漏配 `DATABASE_URL` 会失败。
- 本地 `tools/db_smoke.py` 连续两次输出 `db_smoke=passed`。
- Ubuntu 服务器 `tools/db_smoke.py` 输出 `db_smoke=passed`。
- 全量 pytest 在 PostgreSQL 环境通过，关键 skipped 用例原因已确认。
- 账单、邀请、限流、生成任务状态流在 PostgreSQL 下验证通过。
- 存量数据场景完成 SQLite -> PostgreSQL staging 迁移彩排，并校验行数和关键业务数据。

## 连接数检查

上线前估算 PostgreSQL 连接数：

```text
预计连接数 = gunicorn worker 数 + RQ worker 数 + 管理/维护连接余量
```

默认 PostgreSQL `max_connections` 常见为 `100`。如果计划开很多 RQ worker，先降低 worker 数或调整 PostgreSQL 连接容量，避免上线后连接耗尽。
