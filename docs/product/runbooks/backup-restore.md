# 绘世 PostgreSQL 备份恢复手册

> 本文件描述**当前实际运行**的备份机制（2026-10-07 校正）。
> 历史版本描述的 `huishi-backup.timer` + `flask backup-postgres` **均已失效**：
> systemd 单元在 compose 迁移中丢失，而 `flask backup-postgres` 依赖容器内
> 不存在的 `pg_dump`（见下"为什么不用 flask 命令"）。

## 备份机制

| 项 | 值 |
|---|---|
| 脚本 | `/usr/local/bin/huishi-db-backup`（宿主侧，独立于 compose） |
| 调度 | `/etc/cron.d/huishi-db-backup`，`40 10 * * *`（**本地 CST**） |
| 产出 | Docker 卷 `huishi_backups` 内的 `huishi-<UTC>.dump` + `.dump.sha256` |
| 格式 | `pg_dump --format=custom --no-owner --no-acl` |
| 保留 | 最新 14 份 |
| 日志 | `/var/log/huishi-db-backup.log` |

脚本用**一次性 `postgres:16-alpine` 容器**执行 `pg_dump`，因此
**版本与生产天然一致**，且不触碰 compose 里的任何服务。

口令从运行中的 backend 容器环境读取（`docker exec ... printenv POSTGRES_PASSWORD`），
**不落盘**。

### 为什么不用 `flask backup-postgres`

`huishi/backup.py` 调用的是裸 `pg_dump`，而 backend 容器基于
`python:3.12-slim`、只装了 `ffmpeg`，**没有 `pg_dump`**。该命令在容器内
必然失败。生产备份走宿主侧脚本（上表），这是刻意的设计而非临时绕行。

## 日常检查

```bash
# 最近一次备份是否成功
tail -5 /var/log/huishi-db-backup.log          # 期望看到 backup_ok name=...

# 备份产物（大小与时间）
sudo ls -lh /var/lib/docker/volumes/huishi_backups/_data/ | tail -6

# 手动触发一次
/usr/local/bin/huishi-db-backup
```

**判据**：日志里 `backup_ok` 且产物时间是最新的。备份失败**不会**发通知，
所以这是需要人工看一眼的环节。

## 隔离恢复演练（不动生产库）

```bash
# 1) 选一份备份复制进 postgres 容器
BACKUP=$(sudo ls -1t /var/lib/docker/volumes/huishi_backups/_data/huishi-*.dump | head -1)
docker cp "$BACKUP" huishi-postgres-1:/tmp/restore.dump

# 2) 建临时库
docker exec huishi-postgres-1 psql -U huishi -d postgres -c 'CREATE DATABASE huishi_restore_check'

# 3) 恢复
docker exec huishi-postgres-1 pg_restore --no-owner --no-acl -U huishi -d huishi_restore_check /tmp/restore.dump

# 4) 核对表数与行数（与生产对比）
docker exec huishi-postgres-1 psql -U huishi -d huishi_restore_check -tAc \
  "select count(*) from pg_tables where schemaname='public';"

# 5) 清理
docker exec huishi-postgres-1 psql -U huishi -d postgres -c 'DROP DATABASE huishi_restore_check'
docker exec huishi-postgres-1 rm -f /tmp/restore.dump
```

## 校验和

每份备份都带 `.dump.sha256`。校验：

```bash
docker run --rm -v huishi_backups:/backup postgres:16-alpine \
  sh -c 'cd /backup && sha256sum -c huishi-<stamp>.dump.sha256'
```

## 注意事项

- 不得把 `.env`、真实密钥或用户上传文件写入代码快照。
- 备份**只覆盖 PostgreSQL**。用户上传的图片/视频在宿主目录
  `/opt/huishi/data/uploads`，需另行备份（不在本手册范围）。
- 恢复演练**永远建临时库**，不要直接覆盖 `huishi_prod`。
