# 绘世（Huishi）部署与发布手册

本文档描述**当前实际运行**的生产部署形态。生产环境是 Docker Compose，
不是 systemd；发布通过 `releases/` 目录下的版本化覆盖文件进行。

> 历史文档 `docs/db/vm-staging-deploy.md` 描述的是裸机 + systemd 时代
> （`huishi.service`、`/opt/huishi/.venv`、Nginx 直连），**已与现状不符**，
> 不要按它操作。

---

## 1. 生产环境概况

| 项 | 值 |
|---|---|
| 服务器 | `157.254.187.247:7080`（root） |
| 项目根 | `/opt/huishi` |
| 编排 | `docker compose -f compose.prod.yml`，项目名 `huishi` |
| 域名 | https://paintiworld.dashun9527.com |
| 时区 | **Asia/Shanghai (CST, +0800)** —— cron 按本地时间解析 |
| 上传目录 | 宿主机绑定挂载 `/opt/huishi/data/uploads`，容器内 uid:gid = `10001:10001` |

### 服务组成

| 服务 | 镜像 | 端口 | 健康检查 |
|---|---|---|---|
| `postgres` | `postgres:16-alpine` | 仅内部 | `pg_isready` |
| `redis` | `redis:7-alpine` | 仅内部 | `redis-cli ping` |
| `backend` | `huishi-backend:<release>` | `127.0.0.1:18000 → 8000` | HTTP `/` |
| `worker-image` / `worker-video` | `huishi-worker:<release>` | 无 | **无**（见 §5） |
| `canvas` | `huishi-canvas:<release>` | `127.0.0.1:13000 → 3000` | HTTP `/` |
| `canvas-agent` | 构建自 `infinite-canvas/canvas-agent` | 仅内部 `17371` | HTTP `/health` |

`backend` 与两个 worker 服务**共用同一个 Dockerfile**（`deploy/container/backend.Dockerfile`），
仅靠 `command` 区分：backend 跑 gunicorn，worker 跑 `python worker_supervisor.py <image|video>`。

---

## 2. 关键约束（务必先读）

1. **两个 worker 服务各保持 1 个副本，不要 `--scale`。**
   worker 已拆成 `worker-image`（图片/音频）与 `worker-video`（视频）两个服务，
   每个固定 1 个副本。**并发在容器内部**：`worker_supervisor.py` 按配置拉起
   N 个子进程、每个进程内 M 个线程，并发上限 = N × M。

   调并发改环境变量即可，**不要加容器**：
   ```
   HUISHI_GENERATION_IMAGE_PROCESSES=8   HUISHI_GENERATION_IMAGE_THREADS=32
   HUISHI_GENERATION_VIDEO_PROCESSES=2   HUISHI_GENERATION_VIDEO_THREADS=8
   ```
   ⚠️ **给这两个服务 `--scale` 会让并发数翻倍**，进而打爆 Postgres 的
   连接上限（默认 100）。`releases/*/deploy.sh` 因此显式校验"恰好 1 个副本"。

2. **基础 compose 文件里四个构建服务都没有 `image:` 标签。**
   这是**有意的分层设计**：基线 `compose.prod.yml` 只定义「怎么构建」，
   具体镜像 tag 由 `releases/<name>/compose.release.yml` 在发布时叠加。
   所以直接 `docker compose -f compose.prod.yml up -d --build` 会重新构建
   未经版本化的镜像，**破坏回滚能力**。发布一律走 release 目录的 `deploy.sh`。

3. **`POSTGRES_PASSWORD` 缺失时 compose 会直接报错退出**（`${...:?}` 语法），
   这是刻意的防呆设计。

4. **容器内没有 `pg_dump`。** `huishi/backup.py` 调用的 `pg_dump` 只存在于
   `postgres` 容器（版本 16.14）。因此 `flask backup-postgres` 在 backend
   容器里**必然失败**——生产备份走宿主侧的独立脚本（见 §4）。

---

## 3. 发布流程

### 3.1 发布目录结构

每次发布在 `/opt/huishi/releases/<release-name>/` 下创建一个目录，
成熟形态包含：

```
releases/<release-name>/
├── manifest.json            # 基线镜像名 + 逐文件 sha256
├── manifest.sha256          # payload 的完整哈希清单
├── Dockerfile.backend       # FROM <基线镜像> + COPY payload/ /app/
├── Dockerfile.worker        # 同上，针对 worker
├── Dockerfile.canvas        # 可选，仅当改动画布前端
├── compose.release.yml      # 本版镜像 tag（build: null, pull_policy: never）
├── compose.rollback.yml     # 回滚镜像 tag
├── prepare.sh               # 发布前：打回滚 tag + 备份当前源码
├── deploy.sh                # 发布：带 ERR trap 自动回滚
└── payload/                 # 本版改动的文件（保持相对路径）
```

**核心机制是分层镜像**：`Dockerfile.backend` 以「上一版已在运行的镜像」
为 base，只把 `payload/` 覆盖上去。这样：
- 构建快（不需要重新装依赖）
- 镜像本身即版本（`huishi-backend:video-pricing-fix-20261002`）
- 回滚 = 换 tag 重启，秒级完成

### 3.2 标准发布步骤

> **从模板开始**：`deploy/release_template/` 提供了带前置校验的
> `prepare.sh` 与 `deploy.sh`；它们把下面 §5 的三个陷阱编码成了脚本断言，
> 而不是留在文档里。新发布请从模板复制，不要手写。



```bash
cd /opt/huishi

# 1) 发布前：给当前运行镜像打上 rollback tag，并备份将被覆盖的源码
bash releases/<release-name>/prepare.sh

# 2) 发布：构建新镜像 + 只重启受影响的服务（含自动回滚保护）
bash releases/<release-name>/deploy.sh

# 3) 验证（见 §5）
```

`prepare.sh` 做三件事：
- 校验 staging 与生产的文件都存在（`test -f`）
- `docker tag <当前镜像> huishi-*:rollback-<release-name>`
- `tar` 备份将被覆盖的源码到 `.deploy-backups/<release-name>/`

`deploy.sh` 的关键设计：
- `trap rollback_release ERR` —— 任何一步失败自动切回 `compose.rollback.yml`
- `--no-deps` —— **只动目标服务**，不连带重启 postgres/redis
- `--wait` —— 等健康检查通过才算成功
- worker 两个服务各 1 个副本 —— **不要 `--scale`**（并发在进程内部）

### 3.3 回滚

`deploy.sh` 失败会自动回滚。手工回滚：

```bash
cd /opt/huishi
docker compose -f compose.prod.yml -f releases/<release-name>/compose.rollback.yml \
  up -d --no-deps --wait backend
docker compose -f compose.prod.yml -f releases/<release-name>/compose.rollback.yml \
  up -d --no-deps --scale worker=4 worker
```

---

## 4. 备份与恢复

### 4.1 自动备份（已配置）

| 项 | 值 |
|---|---|
| 脚本 | `/usr/local/bin/huishi-db-backup` |
| 调度 | `/etc/cron.d/huishi-db-backup`，`40 10 * * *`（本地 CST） |
| 产出 | 卷 `huishi_backups` 内 `huishi-<UTC>.dump` + `.dump.sha256` |
| 保留 | 最新 14 份 |
| 日志 | `/var/log/huishi-db-backup.log` |

脚本用一次性 `postgres:16-alpine` 容器执行 `pg_dump`，
**版本与生产天然一致**，且不触碰 compose 里的任何服务。

手工触发与查看：

```bash
/usr/local/bin/huishi-db-backup
ls -la /var/lib/docker/volumes/huishi_backups/_data/
```

### 4.2 恢复

```bash
# 恢复到临时库验证（不要直接覆盖生产库）
docker cp <backup.dump> huishi-postgres-1:/tmp/restore.dump
docker exec huishi-postgres-1 psql -U huishi -d postgres -c 'CREATE DATABASE huishi_restore_check'
docker exec huishi-postgres-1 pg_restore --no-owner --no-acl \
  -U huishi -d huishi_restore_check /tmp/restore.dump
```

完整恢复流程见 `docs/product/runbooks/backup-restore.md`。

---

## 5. 发布后验证

```bash
cd /opt/huishi

# 服务状态（全部应为 healthy）
docker compose -f compose.prod.yml ps --format 'table {{.Service}}\t{{.State}}\t{{.Health}}'

# worker 副本数必须为 4
docker compose -f compose.prod.yml ps -q worker | wc -l

# 三个端点
curl -fsS -o /dev/null -w 'backend=%{http_code}\n' http://127.0.0.1:18000/
curl -fsS -o /dev/null -w 'canvas=%{http_code}\n'  http://127.0.0.1:13000/
curl -kfsS -o /dev/null -w 'public=%{http_code}\n' https://paintiworld.dashun9527.com/

# 关键模块可导入
docker compose -f compose.prod.yml exec -T backend python -c \
  "import huishi.network, huishi.providers, huishi.image_api, huishi.video_api; print('imports ok')"
```

### 部署时的三个真实陷阱（都踩过）

1. **构建服务必须带 `image:` tag 运行，否则会静默回退到 `:latest`。**
   基线 `compose.prod.yml` 里四个构建服务都没有 `image:`，如果直接
   `docker compose up -d`（不带 release 覆盖文件、不带 `--build`），
   compose 会使用本地已存在的 `huishi-backend:latest` / `huishi-worker:latest`
   ——那是**任意一个历史遗留的旧镜像**，会让线上代码静默回退数周。
   永远使用 release 目录的 `compose.release.yml` 覆盖。

2. **`docker compose up -d` 不带 `--scale worker=4` 会把 worker 打回 1 个。**
   而且如果命令里服务名意外为空（例如误写 `$(...)` 展开为空），
   compose 会**拉起整个项目**，连带重置 backend/worker 到 `:latest`。
   只操作目标服务时必须显式写服务名 + `--no-deps`。

3. **画布 Dockerfile 用了 BuildKit 专属的 `--mount=type=cache`。**
   宿主需要 `docker-buildx` 插件（`apt-get install -y docker-buildx`），
   并以 `DOCKER_BUILDKIT=1` 构建；否则报
   "BuildKit is enabled but the buildx component is missing"。
   legacy builder 无法解析该指令。

### 已知监控盲区

- **`worker` 没有健康检查。** `restart: unless-stopped` 只在进程退出时触发；
  进程活着但卡死属于静默失败。发布后应额外确认任务队列在流动：
  ```bash
  docker compose -f compose.prod.yml exec -T backend \
    python -c "from redis import Redis; import os; r=Redis.from_url(os.environ['HUISHI_REDIS_URL']); print('queued', r.llen('rq:queue:huishi-generation'))"
  ```
- 画布构建缓存未挂载，每次重建画布镜像耗时较长。

---

## 6. 测试

```bash
# 在容器内跑（环境完整，是权威结果）
cd /opt/huishi
docker compose -f compose.prod.yml exec -T backend python -m pytest tests/ -q
```

**注意**：测试套件默认用临时 SQLite，不会碰生产库。
`HUISHI_TEST_DATABASE_URL` 若被设置，`tests/conftest.py` 会强制要求库名
含 `test`/`pytest`/`rehearsal`，否则拒绝启动——这是防误连生产的设计。

测试**不是**发布门禁：`deploy.sh` 只构建和重启，不跑测试。
发布前请手工执行。

---

## 7. 历史遗留（已于 2026-10-07 清理）

systemd / 裸机时代的文件已全部删除。原本存在的风险是：`deploy/` 里那些
脚本看起来仍可用，实际在 compose 架构下**第一步就失败**（依赖
`/opt/huishi/.venv` 与 `systemctl`，且文件清单含仓库中不存在的条目）。

删除的清单与每项的失效原因，以及其中**仍有参考价值**的内容
（Nginx 安全头、反向代理转发头、日志脱敏的正则注意点），
已归档到 `docs/legacy-baremetal-notes.md`。

**`deploy/` 现在只包含三样东西**：

| 路径 | 用途 |
|---|---|
| `deploy/container/backend.Dockerfile` | **现役**构建入口（`compose.prod.yml` 的 backend 与 worker 都引用它） |
| `deploy/release_template/` | 新发布用的 `prepare.sh` / `deploy.sh` 模板（含前置校验） |
| `deploy/release_index.py` | 生成服务器侧 `releases/index.json` 的脚本 |

发布历史清单见仓库根的 `RELEASES.md`。
