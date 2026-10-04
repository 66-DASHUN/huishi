#!/usr/bin/env bash
set -euo pipefail

STAGED_ROOT=${1:?staged project root is required}
PRODUCTION_ROOT=${2:-/opt/huishi}
BACKUP_DIR=/var/backups/huishi/code
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
SOURCE_BACKUP="${BACKUP_DIR}/backend-source-pre-home-performance-${STAMP}.tar.gz"

SOURCE_FILES=(
    ".env.example"
    "app.py"
    "requirements.txt"
    "compose.prod.yml"
    "huishi/config.py"
    "huishi/db.py"
    "huishi/canvas_projects.py"
    "huishi/admin_audit.py"
    "huishi/image_api.py"
    "huishi/providers.py"
    "huishi/user_key.py"
    "huishi/generation_queue.py"
    "huishi/routes_admin.py"
    "huishi/routes_workspace.py"
    "huishi/records.py"
    "huishi/secrets.py"
    "huishi/storage.py"
    "huishi/upload_storage.py"
    "templates/admin/records.html"
    "templates/admin/user_ledger.html"
    "templates/admin/_pagination.html"
    "templates/admin/_config_settings_panels.html"
    "templates/base.html"
    "templates/canvas.html"
    "templates/home.html"
    "static/css/site.css"
    "static/css/home-tailwind.input.css"
    "static/css/home-tailwind.css"
    "static/js/home.js"
    "static/js/home.compiled.js"
    "static/js/admin.js"
    "tailwind.home.config.js"
    "package.json"
    "README.md"
    "docs/product/confirmed-requirements.md"
    "docs/product/performance-security-audit.md"
    "docs/product/technical-architecture.md"
    "docs/product/task-cards/2026-07-08-architecture-roadmap-and-ubuntu-p0.md"
    "tools/db_smoke.py"
    "tools/check_encoding.py"
    "tools/check_asset_budget.py"
    "tools/build_home_js.mjs"
    "tools/run_python.mjs"
    "tools/upload_storage_cli.py"
    "tests/test_admin_audit.py"
    "tests/conftest.py"
    "tests/test_canvas_projects.py"
    "tests/test_canvas_conversations.py"
    "tests/test_admin_console_experience.py"
    "tests/test_admin_pagination.py"
    "tests/test_db_smoke_cli.py"
    "tests/test_check_encoding.py"
    "tests/test_home_build_config.py"
    "tests/test_home_assets.py"
    "tests/test_seo_metadata.py"
    "tests/test_sqlite_production_settings.py"
    "tests/test_asset_budget.py"
    "tests/test_deployment_assets.py"
    "tests/test_deploy_release_scripts.py"
    "tests/test_workspace_generation_flow.py"
    "tests/test_settings_config_status.py"
    "tests/test_requested_regressions.py"
    "tests/test_canvas_embed_mode_contract.py"
    "tests/test_upload_delivery.py"
    "tests/test_upload_storage.py"
    "tests/test_upload_storage_cli.py"
    "tests/test_storage_sweeper.py"
    "deploy/deploy_backend_release.sh"
    "deploy/deploy_canvas_release.sh"
    "deploy/migrate_uploads_to_project_dir.sh"
    "deploy/nginx-huishi.local.conf"
    "deploy/prepare-huishi-agent.sh"
)
EXISTING_SOURCE_FILES=()
NEW_SOURCE_FILES=()

for relative_path in "${SOURCE_FILES[@]}"; do
    test -f "${STAGED_ROOT}/${relative_path}"
    if [ -f "${PRODUCTION_ROOT}/${relative_path}" ]; then
        EXISTING_SOURCE_FILES+=("$relative_path")
    else
        NEW_SOURCE_FILES+=("$relative_path")
    fi
done

mkdir -p "$BACKUP_DIR"
cd "$PRODUCTION_ROOT"
"${PRODUCTION_ROOT}/.venv/bin/python" -c \
    "from pathlib import Path; from tools.code_snapshot import create_snapshot; print(create_snapshot(Path('${PRODUCTION_ROOT}'), Path('${BACKUP_DIR}'), 'pre-home-performance-${STAMP}'))"

tar -czf "$SOURCE_BACKUP" -C "$PRODUCTION_ROOT" "${EXISTING_SOURCE_FILES[@]}"
sha256sum "$SOURCE_BACKUP" >"${SOURCE_BACKUP}.sha256"
printf '%s\n' "${NEW_SOURCE_FILES[@]}" >"${SOURCE_BACKUP}.new-files"

rollback() {
    trap - ERR
    for relative_path in "${NEW_SOURCE_FILES[@]}"; do
        rm -f "${PRODUCTION_ROOT}/${relative_path}"
    done
    tar -xzf "$SOURCE_BACKUP" -C "$PRODUCTION_ROOT"
    systemctl restart huishi.service || true
    systemctl try-restart 'huishi-worker@*.service' || true
}

rollback_on_error() {
    status=$?
    rollback
    exit "$status"
}

trap rollback_on_error ERR

for relative_path in "${SOURCE_FILES[@]}"; do
    mode=0644
    if [[ "$relative_path" == deploy/*.sh ]]; then
        mode=0755
    fi
    install -o root -g root -m "$mode" "${STAGED_ROOT}/${relative_path}" "${PRODUCTION_ROOT}/${relative_path}"
done

"${PRODUCTION_ROOT}/.venv/bin/python" -m pip install --requirement "${PRODUCTION_ROOT}/requirements.txt"

"${PRODUCTION_ROOT}/.venv/bin/python" -m py_compile \
    "${PRODUCTION_ROOT}/huishi/routes_admin.py" \
    "${PRODUCTION_ROOT}/tools/db_smoke.py" \
    "${PRODUCTION_ROOT}/tools/check_encoding.py" \
    "${PRODUCTION_ROOT}/tools/check_asset_budget.py"

systemctl restart huishi.service
systemctl try-restart 'huishi-worker@*.service'
healthy=false
for _ in $(seq 1 45); do
    if [ "$(curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/ || true)" = "200" ]; then
        healthy=true
        break
    fi
    sleep 1
done

if [ "$healthy" != "true" ]; then
    journalctl -u huishi.service -n 80 --no-pager || true
    false
fi

trap - ERR
printf 'release=%s\nsource_backup=%s\n' "$STAMP" "$SOURCE_BACKUP"
