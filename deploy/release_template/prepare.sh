#!/usr/bin/env bash
# 发布前准备模板（绘世）。复制到 releases/<name>/prepare.sh 并改 <RELEASE_NAME>。
#
# 做三件事，**只读取与打标签，不改动任何运行中的服务**：
#   1. 校验 payload 里的文件都能在暂存区找到
#   2. 备份将被覆盖的线上源码
#   3. 给当前运行镜像打回滚 tag（deploy.sh 会依赖它）
set -euo pipefail

RELEASE_NAME="<RELEASE_NAME>"

root=/opt/huishi
release="$root/releases/$RELEASE_NAME"
backup="$root/.deploy-backups/$RELEASE_NAME"

# 本版覆盖的既有文件（按需增删，保持相对路径）
overwrite_files=(
  # huishi/example.py
  # templates/admin/example.html
)

# 本版新增的文件（线上尚不存在，不参与存在性检查与备份）
new_files=(
  # huishi/new_module.py
)

[ -d "$release/payload" ] || { echo "缺少 payload/ 目录" >&2; exit 1; }

for file in "${new_files[@]}" "${overwrite_files[@]}"; do
  test -f "$release/payload/$file" || { echo "payload 缺少 $file" >&2; exit 1; }
done
for file in "${overwrite_files[@]}"; do
  test -f "$root/$file" || { echo "线上不存在待覆盖文件 $file（路径写错？）" >&2; exit 1; }
done

mkdir -p "$backup"
if [ "${#overwrite_files[@]}" -gt 0 ]; then
  tar -czf "$backup/source.tar.gz" -C "$root" "${overwrite_files[@]}"
  printf '%s\n' "${overwrite_files[@]}" > "$backup/backed-up-files.txt"
fi
printf '%s\n' "${new_files[@]}" > "$backup/new-files.txt"

# 回滚 tag：用 compose 查询当前项目容器，不要硬编码容器序号。
backend_image=$(docker compose -f "$root/compose.prod.yml" ps -q backend \
  | head -1 | xargs -r docker inspect --format '{{.Image}}')
test -n "$backend_image" || { echo "找不到运行中的 backend 容器" >&2; exit 1; }

# backend 与两个 worker 服务共用同一个镜像；必须确认它们来自同一镜像，
# 否则回滚 tag 会指向一个不是当前运行版本的镜像。
#
# 注意服务名：worker 已拆成 worker-image / worker-video（并发在进程内部，
# 每个服务固定 1 个副本）。继续查旧的 `worker` 服务名会拿到空值，
# 被下面的 count 判断误报成"镜像不一致"而中止发布。
worker_images=$(
  for svc in worker-image worker-video; do
    docker compose -f "$root/compose.prod.yml" ps -q "$svc" \
      | xargs -r docker inspect --format '{{.Image}}'
  done | sort -u
)
worker_count=$(printf '%s\n' "$worker_images" | grep -c . || true)
if [ "$worker_count" -ne 1 ]; then
  echo "worker 服务的镜像不一致（$worker_count 种），请先确认线上状态" >&2
  printf '%s\n' "$worker_images" >&2
  exit 1
fi
worker_image=$(printf '%s\n' "$worker_images" | head -1)

docker tag "$backend_image" "huishi-backend:rollback-${RELEASE_NAME}"
docker tag "$worker_image"  "huishi-worker:rollback-${RELEASE_NAME}"

printf 'release=%s\nbackup=%s\noverwrite=%s\nnew=%s\nbackend_rollback=%s\nworker_rollback=%s\n' \
  "$RELEASE_NAME" "$backup/source.tar.gz" "${#overwrite_files[@]}" "${#new_files[@]}" \
  "huishi-backend:rollback-${RELEASE_NAME}" "huishi-worker:rollback-${RELEASE_NAME}"
