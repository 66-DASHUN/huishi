# 宿主侧定时任务（绘世）

这些脚本装在**宿主机**（不是容器）的 `/usr/local/bin/`，
由 `/etc/cron.d/` 里的条目调用。放在仓库里是为了可复现——
此前 `STORAGE_ORPHAN_RETENTION_DAYS` 之类的保留策略因为**没有任何东西在执行**
而空转了很久，问题就在于这些脚本只存在于服务器上、没有版本管理。

## 两个任务

| 脚本 | cron | 作用 |
|---|---|---|
| `huishi-storage-sweep` | `17 4 * * *` | 删 uploads 里无人引用的孤儿文件（保留策略此前空转） |
| `huishi-disk-cleanup` | `23 5 * * *` | 清悬空镜像 + 过期构建缓存 |

时间刻意错开：数据库备份在 10:40，uploads 清理 04:17，磁盘清理 05:23。

**日志必须写进共享卷**（宿主是 `/var/lib/docker/volumes/huishi_logs/_data`，
容器内是 `/var/log/huishi`）。原因：运行总览的清理探针跑在 backend 容器里，
读不到宿主 `/etc/cron.d`；日志放共享卷它才观测得到，否则那条探针永远报
warning（常报警的探针等于没有探针）。

## 安装

```bash
install -m 0755 huishi-storage-sweep /usr/local/bin/
install -m 0755 huishi-disk-cleanup  /usr/local/bin/
cat > /etc/cron.d/huishi-storage-sweep <<'EOF'
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
17 4 * * * root /usr/local/bin/huishi-storage-sweep >> /var/log/huishi/huishi-storage-sweep.log 2>&1
EOF
cat > /etc/cron.d/huishi-disk-cleanup <<'EOF'
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
23 5 * * * root /usr/local/bin/huishi-disk-cleanup >> /var/log/huishi/huishi-disk-cleanup.log 2>&1
EOF
chmod 0644 /etc/cron.d/huishi-*
```

## 安全性（这两件事都做过实测核验）

**uploads 清理不会删用户作品。** 它调用 `storage.upload_reference_names`，
保护所有仍被 `records` / `generation_tasks` / `canvas_project_assets`
引用的文件。2026-10-11 首次真删后核验：19 条扣费记录、10 条画布记录的文件
**全部完好**，删掉的 32 个是孤儿（测试产物、无引用的旧上传）。

**磁盘清理只动 huishi 命名空间。** 这台服务器同时跑着
sub2api / gpt-image-playground / grok-stack 等其它服务，所以脚本：
- 悬空镜像：只删无 tag 的中间层（不可能是回滚目标）
- 容器：只删名字以 `huishi-` 开头的已停止容器
- 构建缓存：`--filter until=168h`，只清一周以上未使用的部分

**不删**带 tag 的镜像与 `rollback-*`（回滚要用，由发布流程管理）。

## 干跑

```bash
DRY_RUN=1 bash /usr/local/bin/huishi-disk-cleanup
docker exec huishi-backend-1 python -m flask storage-sweep   # 不加 --delete 即干跑
```

## 磁盘水位

脚本会在使用率 ≥80% 时记 WARN、≥90% 时记 ALERT（并返回退出码 2）。
日志：`/var/log/huishi/huishi-disk-cleanup.log`。
