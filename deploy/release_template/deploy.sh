#!/usr/bin/env bash
# 标准发布脚本模板（绘世）。
#
# 用法：复制到 releases/<name>/deploy.sh，把 <RELEASE_NAME> 替换为实际版本名。
#
# 设计要点——**把 DEPLOY.md 里那三个"不读文档必炸"的陷阱编码成前置校验**，
# 而不是留在文档里等人踩：
#   1. 四个构建服务在 compose.prod.yml 里都没有 image:，直接 up -d 会回退到
#      历史遗留的 :latest，让线上代码静默回退数周。→ 强制叠加 compose.release.yml
#   2. 服务名意外展开为空时 compose 会拉起整个项目。
#      → 显式写服务名并校验副本数
#      注：worker 已拆成 worker-image / worker-video，两者都**必须恰好 1 个副本**
#      ——并发在进程内部（worker_supervisor.py 起 N 进程 × M 线程），
#      多副本会让并发数翻倍并打爆 Postgres 连接数。
#   3. 画布 Dockerfile 用了 BuildKit 专属的 --mount=type=cache，需要
#      docker-buildx 且 DOCKER_BUILDKIT=1。→ 构建前探测
set -euo pipefail

RELEASE_NAME="<RELEASE_NAME>"

root=/opt/huishi
base="$root/compose.prod.yml"
release="$root/releases/$RELEASE_NAME"
release_compose="$release/compose.release.yml"
rollback_compose="$release/compose.rollback.yml"

services=(backend worker-image worker-video)

fail() { echo "[deploy] $*" >&2; exit 1; }

# ---------- 前置校验 ----------
[ -d "$release" ] || fail "release 目录不存在: $release"
[ -f "$release_compose" ] || fail "缺少 compose.release.yml —— 直接 up -d 会让线上回退到 :latest"
[ -f "$rollback_compose" ] || fail "缺少 compose.rollback.yml —— 没有回滚目标，拒绝发布"
[ -f "$release/Dockerfile.backend" ] || fail "缺少 Dockerfile.backend"

# 陷阱 1：compose.release.yml 必须为本版服务显式声明镜像 tag。
for svc in "${services[@]}"; do
  if ! grep -Eq "^  ${svc}:" "$release_compose"; then
    fail "compose.release.yml 未声明服务 $svc"
  fi
done
if grep -Eq '^\s+image:\s*\S+:latest\s*$' "$release_compose"; then
  fail "compose.release.yml 指向 :latest —— 这不是版本化镜像"
fi

# 陷阱 2：基线 compose 里构建服务没有 image:；若 release 覆盖未生效，
# compose 会去构建未版本化镜像。显式确认解析结果。
# 用独立 python 文件而不是 -c 内联：内联脚本要嵌在单引号 shell 串里，
# 内部再用引号就得层层转义，极易写错（f-string 里转义引号会直接 SyntaxError）。
config_json=$(mktemp)
resolved_helper=$(mktemp)
resolved=$(mktemp)
trap 'rm -f "$config_json" "$resolved_helper" "$resolved"' EXIT
if ! docker compose -f "$base" -f "$release_compose" config --format json > "$config_json" 2>/dev/null; then
  fail "compose 配置解析失败（叠加 $release_compose 后）"
fi
cat > "$resolved_helper" <<'PYHELPER'
import json, sys
data = json.load(sys.stdin)
for name, svc in sorted(data["services"].items()):
    print("%s=%s" % (name, svc.get("image")))
PYHELPER
python3 "$resolved_helper" < "$config_json" > "$resolved"
for svc in "${services[@]}"; do
  # 读文件内容。上面的 python3 把结果重定向到了 $resolved 这个**文件**，
  # 早先写成 printf 直接打印该变量，等于把路径当内容，grep 必然无匹配；
  # set -e 加 pipefail 下会静默退出（退出码 1、无任何输出），极难排查。
  img=$(grep "^${svc}=" "$resolved" | cut -d= -f2-)
  [ -n "$img" ] && [ "$img" != "None" ] || fail "服务 $svc 解析后没有镜像 tag（会回退到 :latest）"
  printf '[deploy] %s -> %s\n' "$svc" "$img"
done

# 陷阱 3：画布镜像需要 BuildKit + buildx。
if [ -f "$release/Dockerfile.canvas" ]; then
  docker buildx version >/dev/null 2>&1 || fail "缺少 docker-buildx（apt-get install -y docker-buildx）"
  export DOCKER_BUILDKIT=1
fi

# 回滚 tag 必须已存在（由 prepare.sh 打上）。
for svc in "${services[@]}"; do
  tag=$(grep -A2 "^  ${svc}:" "$rollback_compose" | grep -oP '(?<=image: ).*' | head -1)
  if [ -n "$tag" ] && ! docker image inspect "$tag" >/dev/null 2>&1; then
    fail "回滚镜像 $tag 不存在 —— prepare.sh 是否漏跑？"
  fi
done

rollback_release() {
  status=$?
  trap - ERR
  printf '[deploy] 失败(status %s)，执行回滚\n' "$status" >&2
  docker compose -f "$base" -f "$rollback_compose" up -d --no-deps --wait backend || true
  docker compose -f "$base" -f "$rollback_compose" up -d --no-deps worker-image || true
  docker compose -f "$base" -f "$rollback_compose" up -d --no-deps worker-video || true
  exit "$status"
}
trap rollback_release ERR

# ---------- 构建与发布 ----------
docker build -f "$release/Dockerfile.backend" -t "huishi-backend:${RELEASE_NAME}" "$release"

# 陷阱 2：显式写服务名 + --no-deps（不连带重启 postgres/redis）。
# 注意：worker 两个服务都**不加 --scale**——并发在进程内部，多副本会翻倍。
docker compose -f "$base" -f "$release_compose" up -d --no-deps --wait backend
docker compose -f "$base" -f "$release_compose" up -d --no-deps worker-image
docker compose -f "$base" -f "$release_compose" up -d --no-deps worker-video

# 校验每个 worker 服务恰好 1 个副本（多于 1 会让并发数翻倍、打爆连接数）。
for svc in worker-image worker-video; do
  copies=$(docker compose -f "$base" -f "$release_compose" ps -q "$svc" | wc -l)
  [ "$copies" -eq 1 ] || fail "$svc 副本数为 $copies，期望 1"
done

trap - ERR
docker compose -f "$base" -f "$release_compose" ps backend worker-image worker-video

# ---------- 收尾提醒 ----------
cat <<'EOF'

发布后请完成（脚本不代劳，因为会改工作区）：
  1) 同步磁盘源码：把 payload/ 下的运行时文件 cp 到 /opt/huishi
     （否则磁盘与镜像产生差异，下次基线比对会出现大量假差异）
  2) 跑测试：docker compose -f compose.prod.yml exec -T backend python -m pytest tests/ -q
  3) 更新 RELEASES.md 并在服务器运行 python3 /opt/huishi/releases/_index.py
EOF
