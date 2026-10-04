#!/usr/bin/env bash
set -euo pipefail

STAGED_WEB=${1:?staged canvas web directory is required}
PRODUCTION_WEB=${2:-/opt/huishi/infinite-canvas/web}
PRODUCTION_ROOT=$(dirname "$(dirname "$PRODUCTION_WEB")")
BACKUP_DIR=/var/backups/huishi/code
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
NEW_BUILD="${PRODUCTION_WEB}/.next.new-${STAMP}"
PREVIOUS_BUILD="${PRODUCTION_WEB}/.next.previous-${STAMP}"
NEXT_BACKUP="${BACKUP_DIR}/canvas-next-pre-performance-${STAMP}.tar.gz"
SOURCE_BACKUP="${BACKUP_DIR}/canvas-source-pre-performance-${STAMP}.tar.gz"

SOURCE_FILES=(
    ".prettierignore"
    ".prettierrc.json"
    "package.json"
    "tsconfig.json"
    "scripts/report-bundle.mjs"
    "scripts/report-bundle.test.ts"
    "scripts/prepare-standalone.mjs"
    "scripts/prepare-standalone.test.ts"
    "scripts/production-verification.test.ts"
    "src/lib/image-generation-count.ts"
    "src/stores/use-config-store.ts"
    "src/stores/use-theme-store.ts"
    "src/components/image-settings-panel.tsx"
    "src/components/layout/app-config-modal.tsx"
    "src/components/prompts/prompt-card.tsx"
    "src/components/prompts/prompt-detail-dialog.tsx"
    "src/app/(user)/canvas/hooks/use-canvas-viewport.ts"
    "src/app/(user)/canvas/hooks/use-canvas-viewport.test.ts"
    "src/app/(user)/canvas/hooks/use-canvas-agent-lifecycle.ts"
    "src/app/(user)/canvas/hooks/use-canvas-agent-lifecycle.test.ts"
    "src/app/(user)/canvas/utils/canvas-agent-motion.ts"
    "src/app/(user)/canvas/utils/canvas-lazy-surfaces.test.ts"
    "src/app/(user)/canvas/utils/canvas-asset-insertion.ts"
    "src/app/(user)/canvas/utils/canvas-asset-insertion.test.ts"
    "src/app/(user)/canvas/stores/use-canvas-host-session-store.ts"
    "src/app/(user)/canvas/stores/use-canvas-store.ts"
    "src/app/(user)/canvas/lib/host-canvas-session.ts"
    "src/app/(user)/canvas/lib/host-canvas-session.test.ts"
    "src/app/(user)/canvas/hooks/use-canvas-project-cloud-sync.ts"
    "src/app/(user)/canvas/components/canvas-assistant-panel.tsx"
    "src/app/(user)/canvas/components/canvas-config-node-panel.tsx"
    "src/app/(user)/canvas/components/canvas-node-prompt-panel.tsx"
    "src/app/(user)/canvas/components/canvas-node-angle-dialog.tsx"
    "src/app/(user)/canvas/components/canvas-node-crop-dialog.tsx"
    "src/app/(user)/canvas/components/canvas-node-split-dialog.tsx"
    "src/app/(user)/canvas/components/canvas-node-upscale-dialog.tsx"
    "src/app/(user)/canvas/components/canvas-node.tsx"
    "src/app/(user)/canvas/components/canvas-status-screen.tsx"
    "src/app/(user)/canvas/components/canvas-status-screen.test.ts"
    "src/app/(user)/canvas/components/canvas-host-session-guard.tsx"
    "src/app/(user)/canvas/page.tsx"
    "src/app/(user)/canvas/[id]/page.tsx"
    "src/app/(user)/canvas/[id]/canvas-client-page.tsx"
    "src/services/api/image.ts"
    "src/services/api/host-image.ts"
    "src/services/api/canvas-projects.ts"
    "src/services/api/canvas-projects.test.ts"
)
EXISTING_SOURCE_FILES=()
NEW_SOURCE_FILES=()

for relative_path in "${SOURCE_FILES[@]}"; do
    test -f "${STAGED_WEB}/${relative_path}"
    if [ -f "${PRODUCTION_WEB}/${relative_path}" ]; then
        EXISTING_SOURCE_FILES+=("$relative_path")
    else
        NEW_SOURCE_FILES+=("$relative_path")
    fi
done
test -f "${STAGED_WEB}/.next/standalone/server.js"
test -d "${STAGED_WEB}/.next/standalone/.next/static"
test -f "${PRODUCTION_WEB}/.next/standalone/server.js"

mkdir -p "$BACKUP_DIR"
cd "$PRODUCTION_ROOT"
"${PRODUCTION_ROOT}/.venv/bin/python" -c \
    "from pathlib import Path; from tools.code_snapshot import create_snapshot; print(create_snapshot(Path('${PRODUCTION_ROOT}'), Path('${BACKUP_DIR}'), 'pre-canvas-performance-${STAMP}'))"

tar -czf "$NEXT_BACKUP" -C "$PRODUCTION_WEB" .next
sha256sum "$NEXT_BACKUP" >"${NEXT_BACKUP}.sha256"
tar -czf "$SOURCE_BACKUP" -C "$PRODUCTION_WEB" "${EXISTING_SOURCE_FILES[@]}"
sha256sum "$SOURCE_BACKUP" >"${SOURCE_BACKUP}.sha256"
printf '%s\n' "${NEW_SOURCE_FILES[@]}" >"${SOURCE_BACKUP}.new-files"

rm -rf "$NEW_BUILD"
cp -a "${STAGED_WEB}/.next" "$NEW_BUILD"
rm -rf "${NEW_BUILD}/standalone/.next/cache"
ln -s /var/lib/huishi/canvas-cache "${NEW_BUILD}/standalone/.next/cache"
chown -R root:root "$NEW_BUILD"
chmod -R u=rwX,go=rX "$NEW_BUILD"

rollback() {
    trap - ERR
    systemctl stop huishi-canvas.service || true
    if [ -d "$PREVIOUS_BUILD" ]; then
        rm -rf "${PRODUCTION_WEB}/.next"
        mv "$PREVIOUS_BUILD" "${PRODUCTION_WEB}/.next"
    fi
    rm -rf "$NEW_BUILD"
    for relative_path in "${NEW_SOURCE_FILES[@]}"; do
        rm -f "${PRODUCTION_WEB}/${relative_path}"
    done
    if [ -f "$SOURCE_BACKUP" ]; then
        tar -xzf "$SOURCE_BACKUP" -C "$PRODUCTION_WEB"
    fi
    systemctl start huishi-canvas.service || true
}

rollback_on_error() {
    status=$?
    rollback
    exit "$status"
}

trap rollback_on_error ERR

for relative_path in "${SOURCE_FILES[@]}"; do
    mkdir -p "$(dirname "${PRODUCTION_WEB}/${relative_path}")"
    install -o root -g root -m 0644 "${STAGED_WEB}/${relative_path}" "${PRODUCTION_WEB}/${relative_path}"
done

systemctl stop huishi-canvas.service
mv "${PRODUCTION_WEB}/.next" "$PREVIOUS_BUILD"
mv "$NEW_BUILD" "${PRODUCTION_WEB}/.next"
systemctl start huishi-canvas.service

healthy=false
for _ in $(seq 1 45); do
    if [ "$(curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:3000/canvas || true)" = "200" ]; then
        healthy=true
        break
    fi
    sleep 1
done

if [ "$healthy" != "true" ]; then
    journalctl -u huishi-canvas.service -n 80 --no-pager || true
    false
fi

trap - ERR

BUILD_ID=$(cat "${PRODUCTION_WEB}/.next/BUILD_ID")
printf 'release=%s\nbuild_id=%s\nprevious_build=%s\nnext_backup=%s\nsource_backup=%s\n' \
    "$STAMP" "$BUILD_ID" "$PREVIOUS_BUILD" "$NEXT_BACKUP" "$SOURCE_BACKUP"
