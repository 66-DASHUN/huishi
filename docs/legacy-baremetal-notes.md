# 裸机 / systemd 时代的遗留说明（已归档）

本文件保存 **compose 迁移之前**（裸机 + systemd + Nginx 直连）部署形态中
仍有参考价值的信息。原来的部署脚本与单元文件已于 2026-10-07 删除。

> 想看**当前**的部署与发布方式，请看 `DEPLOY.md`。本文件描述的历史形态
> **已不适用**，仅为避免丢失其中的运维经验而保留。

## 为什么删除

迁移到 Docker Compose 后，`deploy/` 下遗留的以下文件已无法工作：

| 已删除文件 | 失效原因 |
|---|---|
| `deploy/deploy_backend_release.sh` | 依赖 `/opt/huishi/.venv/bin/python` 与 `systemctl restart huishi.service`；且其 74 项文件清单含 4 个仓库中不存在的文件，`set -e` + `test -f` 下**第一步就失败** |
| `deploy/deploy_canvas_release.sh` | 依赖 `systemctl stop/start huishi-canvas.service` 与 `.next.new-<stamp>` 双目录切换 |
| `deploy/huishi.service`、`huishi-worker@.service`、`huishi-canvas.service`、`huishi-canvas-agent.service` | 生产上**已不存在任何 huishi systemd 单元**（`systemctl list-unit-files \| grep huishi` 为空）；服务现由 compose 管理 |
| `deploy/huishi-backup.service`、`huishi-backup.timer` | 备份已改为宿主侧 `/usr/local/bin/huishi-db-backup` + `/etc/cron.d/huishi-db-backup`（每天 10:40 本地时间）。**注意**：这两个文件是死文件，从未在迁移后运行过 |
| `deploy/huishi-storage-sweep.service`、`.timer` | 存储清理现由 compose 侧调度 |
| `deploy/nginx-huishi.local.conf` | 域名 `huishi.local` 已过时，现用 `paintiworld.dashun9527.com` |
| `deploy/deploy-vm-staging.ps1`、`vm-staging-bootstrap.sh`、`env.vm-staging.example` | VM staging 流程已废弃 |
| `deploy/prepare-huishi-agent.sh` | Canvas Agent 已容器化 |
| `deploy/migrate_uploads_to_project_dir.sh` | 上传目录迁移已完成 |
| `deploy/huishi-banana-20260831.tar.gz` | 一次性热修包 |

**保留**：`deploy/container/backend.Dockerfile` —— 这是**现役**构建入口，
`compose.prod.yml` 的 backend 与 worker 都引用它。

## 仍有价值的经验：Nginx 安全头

原 `nginx-huishi.local.conf` 里的安全头配置仍然值得沿用到生产 Nginx：

```nginx
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
add_header X-Content-Type-Options "nosniff" always;
add_header Referrer-Policy "no-referrer" always;
add_header Content-Security-Policy "frame-ancestors <画布域名>" always;
add_header Permissions-Policy "camera=(), microphone=(), geolocation=(), payment=()" always;

# 静态资源
location ^~ /_next/static/ {
    add_header Cache-Control "public, max-age=31536000, immutable";
}
```

反向代理转发头（画布与工作台都要）：

```nginx
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto https;
proxy_read_timeout 240s;   # 生成接口耗时长（实测可达 45s+）
```

`Content-Security-Policy` 里的 `frame-ancestors` 必须与画布实际域名一致，
否则画布内嵌会被浏览器拦截。

## 另注：日志脱敏

迁移后新增的 Nginx 脱敏配置见 `/etc/nginx/conf.d/05-redact-sensitive-query.conf`
（用 `map` + `log_format` 抹掉查询串里的会话令牌）。注意 `map` 的正则模式
**必须带 `~` 前缀**，否则会被当作字面量比较、脱敏静默失效。
