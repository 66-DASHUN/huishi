# 发布脚本模板

复制到 `releases/<name>/` 使用，把两份脚本里的 `<RELEASE_NAME>` 换成实际版本名。

```bash
REL=my-change-20261007
mkdir -p /opt/huishi/releases/$REL
cp deploy/release_template/{prepare.sh,deploy.sh} /opt/huishi/releases/$REL/
sed -i "s/<RELEASE_NAME>/$REL/g" /opt/huishi/releases/$REL/*.sh
```

## 为什么要有模板

`RELEASES.md` 的对账显示：**20 个历史 release 里没有任何一个同时具备
Dockerfile、prepare+deploy 脚本和 manifest**，其中 2026-10-05 起连续 5 个
只剩两个 compose 文件——那几次发布靠手工命令完成，不可复现、无自动回滚。
根因是"缺一套标准脚本"，不是"缺文档"。

这两份模板把 `DEPLOY.md` §2/§5 记录的三个陷阱**编码成脚本校验**，
而不是留在文档里等人踩。

## `deploy.sh` 拦住的三个陷阱

| 陷阱 | 后果 | 模板的校验 |
|---|---|---|
| 构建服务在基线 compose 里没有 `image:` | 直接 `up -d` 会用历史遗留的 `:latest`，线上代码静默回退数周 | 强制要求 `compose.release.yml` 存在且非 `:latest`；发布前用 `docker compose config` 打印解析后的镜像并逐个断言非空 |
| 不带 `--scale worker=4` | worker 从 4 个被打回 1 个；服务名意外展开为空时 compose 会拉起整个项目 | 显式写服务名 + `--no-deps`；发布后校验副本数必须为 4 |
| 画布 Dockerfile 用 BuildKit 专属 `--mount=type=cache` | 报 "BuildKit is enabled but the buildx component is missing" | 构建前探测 `docker buildx version` 并设置 `DOCKER_BUILDKIT=1` |

另外还会校验**回滚镜像必须已存在**——若 `prepare.sh` 漏跑，`compose.rollback.yml`
指向的 tag 不存在，ERR trap 回滚会二次失败，届时线上处于半发布状态。

## `prepare.sh` 拦住的坑

- **不硬编码容器序号**：`docker inspect huishi-worker-10` 这类写法在 worker
  重启后会取到任意一个历史容器。模板改用 `docker compose ps -q worker`，
  并断言所有副本来自同一镜像（不一致则拒绝继续）。
- **新增文件与覆盖文件分开**：新增文件线上本不存在，参与存在性检查会导致
  `set -e` 下静默失败（本模板的注释里明确区分这两类）。
