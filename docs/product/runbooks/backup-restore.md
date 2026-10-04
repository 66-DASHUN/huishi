# 绘世 PostgreSQL 备份恢复手册

## 备份产物

`huishi-backup.timer` 每天调用 `flask --app wsgi:app backup-postgres`，生成：

- `huishi-YYYYMMDDTHHMMSSZ.dump`
- 同名 `.sha256`
- `status.json`

备份使用 PostgreSQL custom format、原子改名、SHA-256 校验和 14 份保留策略。失败时 `status.json` 记录失败类型但不记录数据库密码。

## 日常检查

```bash
systemctl list-timers huishi-backup.timer
sudo systemctl show huishi-backup.service -p Result -p ExecMainStatus
sudo ls -lh /var/backups/huishi/postgres
sudo cat /var/backups/huishi/postgres/status.json
```

不得把 `.env`、真实密钥或用户上传文件写入代码快照。

## 隔离恢复演练

下面的命令不会修改生产数据库：

```bash
sudo -u postgres dropdb --if-exists huishi_restore_rehearsal
sudo -u postgres createdb huishi_restore_rehearsal

sudo cp /var/backups/huishi/postgres/huishi-YYYYMMDDTHHMMSSZ.dump /tmp/huishi-restore.dump
sudo chown postgres:postgres /tmp/huishi-restore.dump
sudo chmod 0600 /tmp/huishi-restore.dump
sudo -u postgres pg_restore \
  --clean --if-exists --no-owner \
  --dbname=huishi_restore_rehearsal \
  /tmp/huishi-restore.dump

sudo install -d -o postgres -g postgres -m 0700 /tmp/huishi-restore-smoke
cd /opt/huishi
sudo -u postgres env \
  DATABASE_URL='postgresql:///huishi_restore_rehearsal?host=/var/run/postgresql' \
  HUISHI_OUTPUT_DIR=/tmp/huishi-restore-smoke \
  .venv/bin/python tools/db_smoke.py
```

必须看到 `db_smoke=passed`。完成后清理：

```bash
sudo -u postgres dropdb huishi_restore_rehearsal
sudo rm -rf /tmp/huishi-restore-smoke /tmp/huishi-restore.dump
```

## 生产恢复

仅在确认生产数据库损坏或误操作后执行：

1. 停止 `huishi.service` 和所有 `huishi-worker@*.service`。
2. 对当前数据库再做一次故障现场 dump，禁止直接覆盖唯一证据。
3. 将目标备份恢复到临时数据库并运行 `tools/db_smoke.py`。
4. 记录恢复点、操作者、原因和校验和。
5. 重建生产数据库并执行 `pg_restore --clean --if-exists --no-owner`。
6. 启动 Flask，检查登录、Provider、积分、生成记录和画布会话。
7. 启动 worker，提交一条受控测试任务。
8. 验收后再删除临时数据库。

`HUISHI_ENCRYPTION_KEY` 必须与目标备份对应。密钥错误或丢失时，即使数据库恢复成功，已加密的 Provider、SMTP、用户 Key 和 Agent Token 仍无法使用。
