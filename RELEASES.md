# 绘世（Huishi）发布索引

本文件是**发布版本清单**——记录每个 release 的用途、状态与回滚目标。
发布机制详见 `DEPLOY.md`。

> **为什么需要这份清单**：发布产物本身不入库（`.gitignore` 忽略
> `releases/`），历史版本的"哪个版本在跑、回滚到哪个 tag"此前只能靠
> `docker image ls` 的创建时间和目录 mtime 反推。本清单把它固化下来。

## 当前状态（2026-10-07）

| 服务 | 运行镜像 |
|---|---|
| `backend` | `huishi-backend:channel-health-20261006` |
| `worker` | `huishi-backend:channel-health-20261006`（4 副本，与 backend 共用镜像，仅 command 不同） |
| `canvas` | `huishi-canvas:token-fragment-20261005` |
| `canvas-agent` | `huishi-canvas-agent:latest` |
| `postgres` | `postgres:16-alpine` |
| `redis` | `redis:7-alpine` |

**当前回滚目标**：`huishi-backend:rollback-channel-health-20261006`

## 版本类型约定

清单里每个 release 标注 `kind`：

| kind | 含义 | 目录完备度要求 |
|---|---|---|
| `正式` | 面向生产的功能/修复发布 | 必须自包含：`Dockerfile.*` + `compose.release.yml` + `compose.rollback.yml` + `prepare.sh` + `deploy.sh` + `payload/` |
| `测试` | 灰度/预演，通过隔离库验证后再转正式 | 额外含 `smoke.sh` 或 `rehearse` 脚本 |
| `回退` | 仅回滚用，不用于前进 | 至少含 `compose.rollback.yml` |

**命名约定**：`kebab-case-描述-YYYYMMDD[-HHMM]`。同一发布若含多个服务，
用统一的日期后缀（例：`token-fragment-20261005`）。

## Release 清单

按时间倒序。`文件数` 指 release 目录内的条目数——**数字越小说明目录越不完整**。

| release | 日期 | 文件数 | 目标镜像 | kind | 状态 | 备注 |
|---|---|---|---|---|---|---|
| `channel-health-20261006` | 2026-10-06 | 7 | `huishi-backend:channel-health-20261006` | 正式 | **在跑** | 渠道健康度 + 队列生图修复 + gemini 回退。含 Dockerfile×2、prepare/deploy、payload |
| `payloads-20261005` | 2026-10-05 | 2 | `huishi-backend:payloads-20261005` | 正式 | 已被取代 | ⚠️ **目录不完整**：只有两个 compose，无 Dockerfile/脚本 |
| `sanitize-secrets-20261005` | 2026-10-05 | 2 | `huishi-backend:sanitize-secrets-20261005` | 正式 | 已被取代 | ⚠️ 同上 |
| `extract-image-sizes-20261005` | 2026-10-05 | 2 | `huishi-backend:extract-image-sizes-20261005` | 正式 | 已被取代 | ⚠️ 同上 |
| `token-fragment-20261005` | 2026-10-05 | 2 | `huishi-backend/worker/canvas:token-fragment-20261005` | 正式 | canvas 部分**在跑** | ⚠️ 同上 |
| `canvas-token-fragment-20261005` | 2026-10-05 | 2 | `huishi-canvas:token-fragment-20261005` | 正式 | 与上条重复 | ⚠️ 同一批发布拆成了两个目录 |
| `subject-reference-20261004` | 2026-10-04 | 7 | `huishi-worker:subject-reference-20261004` | 正式 | 已被取代 | 含 Dockerfile.worker、prepare/deploy、payload |
| `video-pricing-fix-20261002` | 2026-10-02 | 9 | `huishi-backend/worker:video-pricing-fix-20261002` | 正式 | 已被取代 | ✅ **脚本与 Dockerfile 最齐全**，可作模板（含 payload-worker、tests）；**缺 manifest** |
| `duration-range-20260923-1916` | 2026-09-23 | 12 | `huishi-backend/worker/canvas:duration-range-20260923-1916` | 正式 | 已被取代 | 文件数最多，含 `manifest.sha256`/`smoke.sh`/`verify_*.py`，但**缺 prepare.sh 与 deploy.sh** |
| `task-status-20260923-050336` | 2026-09-23 | 5 | `huishi-backend:task-status-20260923-050336` | 正式 | 已被取代 | ⚠️ compose 里的 worker 指向 `huishi-worker:asset-upload-20260923-013600`（与自身名字不符） |
| `task-status-20260923-045510` | 2026-09-23 | 5 | `huishi-backend:task-status-20260923-045510` | 正式 | 已被取代 | ⚠️ 同上 |
| `subject-chip-20260923-041855` | 2026-09-23 | 7 | `huishi-backend/worker:subject-chip-20260923-041855` | 正式 | 已被取代 | 含 before.tgz 与 containers.before.txt |
| `asset-upload-20260923-013600` | 2026-09-23 | 9 | `huishi-backend/worker:asset-upload-20260923-013600` | 正式 | 已被取代 | 含 migrate/rollback SQL 与 verify 脚本 |
| `seedance-direct-20260923-001229` | 2026-09-23 | 10 | `huishi-backend/worker:seedance-direct-20260923-001229` | 正式 | 已被取代 | 含数据库迁移与回滚 |
| `subject-picker-20260922-180727` | 2026-09-22 | 4 | （无 image tag） | 正式 | 已被取代 | ⚠️ 无 compose.release.yml 的镜像声明 |
| `task-repair-20260922-164347` | 2026-09-22 | 5 | `huishi-backend/worker:task-repair-20260922-164347` | 正式 | 已被取代 | 含 manifest.json 与 before.tgz |
| `task-repair-20260922-163651` | 2026-09-22 | 5 | 同上形式 | 正式 | 已被取代 | |
| `task-repair-20260922-154826` | 2026-09-22 | 5 | 同上形式 | 正式 | 已被取代 | |
| `task-repair-20260922-135605` | 2026-09-22 | 5 | 同上形式 | 正式 | 已被取代 | |
| `task-repair-20260922-135146` | 2026-09-22 | 5 | 同上形式 | 正式 | 已被取代 | 该系列最早一个 |

## 目录完备度实况（由 `releases/_index.py` 生成）

`/opt/huishi/releases/index.json` 会逐项报告每个 release 是否具备
`Dockerfile`、`prepare.sh`+`deploy.sh`、`manifest`。**当前 20 个 release 中，
同时具备三者的一个都没有**：

| 能力 | 具备的 release 数 |
|---|---|
| 有 Dockerfile | 17 / 20 |
| 有 prepare.sh + deploy.sh | 3 / 20（`channel-health-20261006`、`subject-reference-20261004`、`video-pricing-fix-20261002`） |
| 有 manifest | 14 / 20 |
| **三者齐全** | **0 / 20** |

最接近的是 `subject-reference-20261004`（有 Dockerfile、脚本、manifest.json，
但缺 `payload-worker` 与验证脚本）。

> 生成方式：`python3 /opt/huishi/releases/_index.py` —— 每次发布后跑一次，
> 它会重写 `index.json` 并列出不完整的 release。该脚本随本清单一起纳入版本控制
> （位于 `deploy/release_index.py`）。

## 已知问题（待收敛）

1. **2026-10-05 起连续 5 个 release 目录退化**：只剩 `compose.release.yml` +
   `compose.rollback.yml`，缺 Dockerfile 与 prepare/deploy 脚本——那几次发布
   靠手工命令完成，**不可复现、无自动回滚保护**。
2. **`task-status-*` 两个 release 的 worker 镜像指向别的发布**
   （`asset-upload-20260923-013600`），回滚时可能取到非预期镜像。
3. **`subject-picker-20260922-180727` 没有镜像声明**，无法仅凭目录完成回滚。
4. **回滚 tag 命名不统一**：有 `rollback-<name>`、`rollback-<date>-<name>`
   两种形态（例：`rollback-20261005-token-fragment` 与
   `rollback-channel-health-20261006`）。
5. **`huishi-canvas-agent` 用 `:latest`**，没有版本化——画布 Agent 的变更
   无法从镜像 tag 追溯。

## 新增发布的流程要求

每个新 release 目录**必须自包含**（对齐 `video-pricing-fix-20261002`
的形态）：

```
releases/<kebab-name-YYYYMMDD[-HHMM]>/
├── Dockerfile.backend      # FROM <基线镜像> + COPY payload/ /app/
├── Dockerfile.worker       # 同 backend（共用镜像，仅 command 不同）
├── compose.release.yml     # 本版镜像 tag
├── compose.rollback.yml    # 回滚镜像 tag
├── manifest.json           # 基线镜像 + 逐文件 sha256
├── prepare.sh              # 打回滚 tag + 备份待覆盖源码
├── deploy.sh               # 构建 + 只重启目标服务（含 ERR trap 自动回滚）
└── payload/                # 本版改动的文件（保持相对路径）
```

发布完成后**回到本文件补一行**，记录 `kind` 与状态。这是让清单不腐化的唯一办法。
