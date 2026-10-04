from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_backup_service_is_sandboxed_and_uses_production_environment():
    text = read("deploy/huishi-backup.service")
    assert "Type=oneshot" in text
    assert "User=huishi" in text
    assert "EnvironmentFile=/opt/huishi/.env" in text
    assert "backup-postgres" in text
    assert "PrivateTmp=true" in text
    assert "NoNewPrivileges=true" in text


def test_backup_timer_is_persistent_and_daily():
    text = read("deploy/huishi-backup.timer")
    assert "OnCalendar=*-*-* 02:40:00" in text
    assert "RandomizedDelaySec=10m" in text
    assert "Persistent=true" in text


def test_canvas_agent_uses_dedicated_home_and_systemd_sandbox():
    text = read("deploy/huishi-canvas-agent.service")
    assert "User=huishi-agent" in text
    assert "Group=huishi-agent" in text
    assert "Environment=HOME=/var/lib/huishi-agent" in text
    assert "ProtectSystem=strict" in text
    assert "ProtectHome=true" in text
    assert "PrivateTmp=true" in text
    assert "NoNewPrivileges=true" in text
    assert "PrivateDevices=true" in text
    assert "ReadWritePaths=/var/lib/huishi-agent" in text


def test_canvas_proxy_has_security_headers():
    text = read("deploy/nginx-huishi.local.conf")
    for header in (
        "Strict-Transport-Security",
        "X-Content-Type-Options",
        "Referrer-Policy",
        "Permissions-Policy",
    ):
        assert header in text
    assert "proxy_hide_header X-Powered-By" in text
    assert 'Content-Security-Policy "frame-ancestors https://huishi.local"' in text
    assert 'Referrer-Policy "no-referrer"' in text


def test_nginx_uses_current_http2_directive():
    text = read("deploy/nginx-huishi.local.conf")

    assert "listen 443 ssl http2;" not in text
    assert text.count("http2 on;") == 2


def test_canvas_service_accepts_sigterm_as_success():
    text = read("deploy/huishi-canvas.service")
    assert "SuccessExitStatus=143 SIGTERM" in text
    assert "TimeoutStopSec=30" in text


def test_nextjs_disables_powered_by_header_and_build_error_bypass():
    text = read("infinite-canvas/web/next.config.ts")
    assert "poweredByHeader: false" in text
    assert "ignoreBuildErrors: true" not in text


def test_bootstrap_installs_backup_and_agent_units_without_recursive_source_chown():
    text = read("deploy/vm-staging-bootstrap.sh")
    assert "huishi-backup.service" in text
    assert "huishi-backup.timer" in text
    assert "huishi-canvas-agent.service" in text
    assert 'chown -R root:root "${APP_DIR}"' in text
    assert text.rfind('chown -R root:root "${APP_DIR}"') > text.rfind(
        'chown -R "${APP_USER}:${APP_GROUP}" "${APP_DIR}"'
    )


def test_bootstrap_grants_nginx_read_access_to_generated_uploads():
    text = read("deploy/vm-staging-bootstrap.sh")

    assert "acl" in text
    assert "setfacl -m u:www-data:--x /var/lib/huishi" in text
    assert "setfacl -m u:www-data:r-x /var/lib/huishi/uploads" in text


def test_agent_runtime_is_copied_out_of_personal_home_without_copying_download_cache():
    text = read("deploy/prepare-huishi-agent.sh")
    assert 'RUNTIME_DIR="${AGENT_RUNTIME_DIR:-/usr/local/lib/huishi-agent}"' in text
    assert '"${RUNTIME_DIR}/claude"' in text
    assert '${RUNTIME_DIR}/node_modules/@openai/codex/bin/codex.js' in text
    assert "--exclude=downloads/" in text
    assert 'chown -R "${AGENT_USER}:${AGENT_GROUP}" "${AGENT_HOME}"' in text


def test_storage_sweep_is_observation_only_until_canvas_assets_are_server_tracked():
    text = read("deploy/huishi-storage-sweep.service")

    assert "storage-sweep" in text
    assert "storage-sweep --delete" not in text
    assert "Canvas projects currently persist in browser storage" in text


def test_compose_uses_project_owned_upload_directory():
    compose = read("compose.prod.yml")

    assert "./data/uploads:/var/lib/huishi/uploads" in compose
    assert "\n      - uploads:/var/lib/huishi/uploads" not in compose
