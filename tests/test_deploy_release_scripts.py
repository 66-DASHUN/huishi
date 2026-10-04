from pathlib import Path


def test_canvas_release_creates_parent_directories_for_new_source_files():
    source = Path("deploy/deploy_canvas_release.sh").read_text(encoding="utf-8")

    assert 'mkdir -p "$(dirname "${PRODUCTION_WEB}/${relative_path}")"' in source


def test_canvas_release_deploys_production_verification_configuration():
    source = Path("deploy/deploy_canvas_release.sh").read_text(encoding="utf-8")

    assert '".prettierignore"' in source
    assert '"scripts/production-verification.test.ts"' in source


def test_canvas_release_deploys_canvas_project_persistence_sources():
    source = Path("deploy/deploy_canvas_release.sh").read_text(encoding="utf-8")

    assert '"src/app/(user)/canvas/page.tsx"' in source
    assert '"src/app/(user)/canvas/lib/host-canvas-session.ts"' in source
    assert '"src/app/(user)/canvas/lib/host-canvas-session.test.ts"' in source
    assert '"src/app/(user)/canvas/stores/use-canvas-store.ts"' in source
    assert '"src/app/(user)/canvas/hooks/use-canvas-project-cloud-sync.ts"' in source
    assert '"src/services/api/canvas-projects.ts"' in source
    assert '"src/services/api/canvas-projects.test.ts"' in source


def test_backend_release_deploys_agent_runtime_audit_contract():
    source = Path("deploy/deploy_backend_release.sh").read_text(encoding="utf-8")

    assert '"deploy/prepare-huishi-agent.sh"' in source
    assert '"deploy/deploy_canvas_release.sh"' in source
    assert '"tests/test_deployment_assets.py"' in source
    assert '"tests/test_deploy_release_scripts.py"' in source


def test_backend_release_deploys_canvas_embed_regression():
    source = Path("deploy/deploy_backend_release.sh").read_text(encoding="utf-8")

    assert '"templates/canvas.html"' in source
    assert '"tests/test_workspace_generation_flow.py"' in source


def test_backend_release_deploys_upload_storage_and_migration_tools():
    source = Path("deploy/deploy_backend_release.sh").read_text(encoding="utf-8")

    for required in (
        '"app.py"',
        '"huishi/upload_storage.py"',
        '"tools/upload_storage_cli.py"',
        '"deploy/migrate_uploads_to_project_dir.sh"',
        '"tests/test_upload_delivery.py"',
        '"tests/test_upload_storage.py"',
        '"tests/test_upload_storage_cli.py"',
        '"requirements.txt"',
        '"compose.prod.yml"',
    ):
        assert required in source


def test_backend_release_deploys_settings_and_storage_configuration_sources():
    source = Path("deploy/deploy_backend_release.sh").read_text(encoding="utf-8")

    for required in (
        '".env.example"',
        '"huishi/image_api.py"',
        '"templates/admin/_config_settings_panels.html"',
        '"static/js/admin.js"',
        '"tests/test_settings_config_status.py"',
        '"tests/test_requested_regressions.py"',
    ):
        assert required in source


def test_release_scripts_deploy_provider_protocol_sources():
    backend = Path("deploy/deploy_backend_release.sh").read_text(encoding="utf-8")
    canvas = Path("deploy/deploy_canvas_release.sh").read_text(encoding="utf-8")

    for required in (
        '"huishi/providers.py"',
        '"huishi/user_key.py"',
        '"huishi/generation_queue.py"',
    ):
        assert required in backend
    assert '"src/components/layout/app-config-modal.tsx"' in canvas


def test_canvas_release_deploys_generation_count_sources():
    source = Path("deploy/deploy_canvas_release.sh").read_text(encoding="utf-8")

    for required in (
        '"src/lib/image-generation-count.ts"',
        '"src/stores/use-config-store.ts"',
        '"src/components/image-settings-panel.tsx"',
        '"src/services/api/image.ts"',
        '"src/services/api/host-image.ts"',
        '"src/app/(user)/canvas/components/canvas-config-node-panel.tsx"',
        '"src/app/(user)/canvas/components/canvas-node-prompt-panel.tsx"',
    ):
        assert required in source


def test_upload_migration_script_preserves_source_volume_and_owns_project_data():
    source = Path("deploy/migrate_uploads_to_project_dir.sh").read_text(encoding="utf-8")

    assert "/var/lib/docker/volumes/huishi_uploads/_data" in source
    assert "/opt/huishi/data/uploads" in source
    assert "upload_storage_cli.py\" migrate-local" in source
    assert 'chown -R "${UPLOAD_UID}:${UPLOAD_GID}" "${TARGET_DIR}"' in source
    assert "rm -rf" not in source
    assert "docker volume rm" not in source


def test_backend_release_deploys_home_performance_sources_and_tests():
    source = Path("deploy/deploy_backend_release.sh").read_text(encoding="utf-8")

    assert '"static/js/home.js"' in source
    assert '"static/js/home.compiled.js"' in source
    assert '"tests/test_home_assets.py"' in source
    assert '"tests/test_seo_metadata.py"' in source


def test_backend_release_deploys_current_performance_audit():
    source = Path("deploy/deploy_backend_release.sh").read_text(encoding="utf-8")

    assert '"tests/conftest.py"' in source
    assert '"docs/product/performance-security-audit.md"' in source
    assert '"docs/product/confirmed-requirements.md"' in source
    assert '"docs/product/technical-architecture.md"' in source
    assert '"docs/product/task-cards/2026-07-08-architecture-roadmap-and-ubuntu-p0.md"' in source


def test_backend_release_deploys_postgres_profile_fixes():
    source = Path("deploy/deploy_backend_release.sh").read_text(encoding="utf-8")

    assert '"huishi/config.py"' in source
    assert '"huishi/db.py"' in source
    assert '"tests/test_admin_audit.py"' in source
    assert '"tests/test_canvas_conversations.py"' in source
    assert '"tests/test_sqlite_production_settings.py"' in source
    assert '"deploy/nginx-huishi.local.conf"' in source


def test_backend_release_installs_dependencies_and_restarts_active_workers():
    source = Path("deploy/deploy_backend_release.sh").read_text(encoding="utf-8")

    assert '"${PRODUCTION_ROOT}/.venv/bin/python" -m pip install --requirement "${PRODUCTION_ROOT}/requirements.txt"' in source
    assert "systemctl try-restart 'huishi-worker@*.service'" in source


def test_vm_staging_example_allows_frontend_generation_limit():
    source = Path("deploy/env.vm-staging.example").read_text(encoding="utf-8")

    assert "HUISHI_MAX_GENERATION_COUNT=10" in source
    assert "HUISHI_MAX_GENERATION_COUNT=8" not in source
