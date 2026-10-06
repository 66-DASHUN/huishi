import os
import re
from pathlib import Path

from huishi.routes_workspace import _provider_config_status


def test_parse_size_bytes_supports_human_units():
    from huishi.config import parse_size_bytes

    assert parse_size_bytes("512K") == 512 * 1024
    assert parse_size_bytes("5M") == 5 * 1024 * 1024
    assert parse_size_bytes("1.5M") == int(1.5 * 1024 * 1024)
    assert parse_size_bytes("2G") == 2 * 1024 * 1024 * 1024
    assert parse_size_bytes("5242880") == 5_242_880


def test_dotenv_loader_sets_missing_environment_values(tmp_path, monkeypatch):
    from huishi.config import _load_dotenv_file

    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "HUISHI_TEST_DOTENV_VALUE=from-file",
                "HUISHI_TEST_QUOTED_VALUE='quoted file value'",
                "HUISHI_TEST_EXISTING_VALUE=from-file",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("HUISHI_TEST_DOTENV_VALUE", raising=False)
    monkeypatch.delenv("HUISHI_TEST_QUOTED_VALUE", raising=False)
    monkeypatch.setenv("HUISHI_TEST_EXISTING_VALUE", "from-env")

    _load_dotenv_file(env_file)

    assert os.environ["HUISHI_TEST_DOTENV_VALUE"] == "from-file"
    assert os.environ["HUISHI_TEST_QUOTED_VALUE"] == "quoted file value"
    assert os.environ["HUISHI_TEST_EXISTING_VALUE"] == "from-env"


def test_provider_config_status_uses_enabled_provider_key():
    status = _provider_config_status(
        [
            {
                "provider_type": "image",
                "base_url": "https://api.example.com",
                "api_key": "sk-real-secret",
                "enabled": 1,
            }
        ],
        default_base_url="https://default.example.com",
    )

    assert status["has_real_key"] is True
    assert status["key_source"] == "provider"
    assert status["effective_base_url"] == "https://api.example.com"


def test_provider_config_status_ignores_disabled_provider_key():
    status = _provider_config_status(
        [
            {
                "provider_type": "image",
                "base_url": "https://api.example.com",
                "api_key": "sk-real-secret",
                "enabled": 0,
            }
        ],
        default_base_url="https://default.example.com",
    )

    assert status["has_real_key"] is False
    assert status["key_source"] == "missing"
    assert status["effective_base_url"] == "https://default.example.com"


def test_admin_config_settings_page_renders_image_resolution_checkboxes(tmp_path):
    from app import create_app
    from huishi.db import get_db, init_db

    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "test.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"
    with app.app_context():
        init_db()
        admin = get_db().execute("SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1").fetchone()

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = admin["id"]
        response = client.get("/admin/config/settings")

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    # 分辨率不再由服务端渲染 checkbox：渠道与模型关联改由
    # model-management.js 依据迁入页面的目录 JSON 动态生成。
    # 这里断言的是"该能力仍被交付给前端"，而非某种已废弃的 DOM 形态。
    assert 'type="application/json" id="image-provider-catalog"' in body
    assert '"resolutions"' in body
    assert 'name="api_key" type="password"' in body
    # 密码管理器抑制改为 autocomplete="new-password"：
    # data-lpignore 是非标准属性，已随表单重构移除。
    assert 'autocomplete="new-password"' in body
    assert "默认接口协议" in body
    assert 'value="openai"' in body
    assert 'value="gemini"' in body
    assert 'value="grok"' in body
    assert 'value="banana"' in body
    assert 'gemini-3.1-flash-image' in body and 'Nano Banana 2' in body
    assert 'gemini-3-pro-image' in body and 'Nano Banana Pro' in body
    assert 'gemini-3.1-flash-lite-image' not in body
    assert 'gemini-2.5-flash-image' not in body


def test_admin_config_settings_uses_catalog_selects_and_safe_json_contract(tmp_path):
    from app import create_app
    from huishi.db import get_db, init_db

    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "test.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"
    with app.app_context():
        init_db()
        admin = get_db().execute("SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1").fetchone()

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = admin["id"]
        response = client.get("/admin/config/settings")

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    # 旧的三件套（data-model-select / data-custom-model-toggle / data-model-id）
    # 已随内联表单重构移除，改由 mm-* 表格契约承载。
    assert 'data-mm-connections' in body
    assert 'data-mm-models' in body
    assert 'data-mm-calls' in body
    assert 'type="application/json" id="image-provider-catalog"' in body
    assert 'grok-imagine 2.0' in body
    assert 'grok-imagine-image-2.0' in body
    assert '<datalist id="image-model-options-' not in body


def test_admin_config_settings_loads_its_model_interaction_script_after_catalog(tmp_path):
    from app import create_app
    from huishi.db import get_db, init_db

    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "test.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"
    with app.app_context():
        init_db()
        admin = get_db().execute("SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1").fetchone()

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = admin["id"]
        response = client.get("/admin/config/settings")

    body = response.get_data(as_text=True)
    catalog_index = body.index('id="image-provider-catalog"')
    script_index = body.index('/static/js/settings.js')
    assert catalog_index < script_index
    assert '<script src="/static/js/settings.js' in body
    assert 'defer' in body[script_index - 40: script_index + 120]


def test_provider_status_reports_missing_key_when_config_exists():
    from huishi.routes_workspace import _provider_config_status

    status = _provider_config_status(
        [
            {
                "provider_type": "image",
                "base_url": "https://api.example.com",
                "api_key": "",
                "enabled": 1,
            }
        ]
    )

    assert status["has_real_key"] is False
    assert status["key_source"] == "missing"
    assert status["has_enabled_provider"] is True
    assert status["effective_base_url"] == "https://api.example.com"
    assert status["is_ready"] is False
    assert status["missing_reason"] == "缺少 API Key"


def test_prompt_provider_status_requires_model():
    from huishi.routes_workspace import _provider_config_status

    status = _provider_config_status(
        [
            {
                "provider_type": "prompt",
                "name": "Prompt",
                "base_url": "https://api.example.com",
                "api_key": "sk-real-secret",
                "model": "",
                "enabled": 1,
            }
        ]
    )

    assert status["has_real_key"] is True
    assert status["is_ready"] is False
    assert status["missing_reason"] == "缺少文本模型"


def test_admin_config_settings_page_shows_canvas_config_section(tmp_path):
    from app import create_app
    from huishi.db import get_db, init_db

    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "test.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"
    with app.app_context():
        init_db()
        admin = get_db().execute("SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1").fetchone()

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = admin["id"]
        response = client.get("/admin/config/settings")

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "画布入口" in body
    assert "画布应用地址" in body
    assert "在线 Agent（服务器）" in body
    assert "本地 Agent/MCP（本机）" in body
    assert "本地 Agent/MCP 地址" in body
    assert "本地启动参数" in body
    assert "默认模板" in body
    assert "在线 Agent 不读取这里" in body


def test_admin_config_settings_page_shows_unified_canvas_generation_settings(tmp_path):
    from app import create_app
    from huishi.db import get_db, init_db

    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "test.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"
    with app.app_context():
        init_db()
        admin = get_db().execute("SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1").fetchone()

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = admin["id"]
        response = client.get("/admin/config/settings")

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "画布生成配置" in body
    assert "在线助手" in body
    assert "计费规则" in body
    assert 'href="#settings-image"' in body
    assert 'href="#settings-storage"' in body
    assert 'href="#settings-runtime"' in body


def test_admin_config_settings_page_uses_compact_tables(tmp_path):
    from app import create_app
    from huishi.db import get_db, init_db

    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "test.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"
    with app.app_context():
        init_db()
        admin = get_db().execute("SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1").fetchone()

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = admin["id"]
        response = client.get("/admin/config/settings")

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    # provider-config-table 是已删除的类名；渠道/模型/调用记录三张表
    # 现在统一用 mm-table。
    assert 'class="config-table mm-table"' in body
    assert 'class="config-table storage-config-table"' in body
    assert "settings-health-summary" not in body
    assert "settings-section-nav" not in body
    assert "settings-section-title" not in body


def test_admin_config_runtime_table_has_semantic_row_groups(tmp_path):
    from app import create_app
    from huishi.db import get_db, init_db

    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "test.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"
    with app.app_context():
        init_db()
        admin = get_db().execute("SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1").fetchone()

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = admin["id"]
        response = client.get("/admin/config/settings")

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'data-runtime-group="billing-canvas"' in body
    assert 'data-runtime-group="agent"' in body
    assert 'data-runtime-group="mail"' in body


def test_admin_config_settings_page_shows_canvas_diagnostics_panel(tmp_path):
    from app import create_app
    from huishi.db import get_db, init_db

    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "test.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"
    with app.app_context():
        init_db()
        admin = get_db().execute("SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1").fetchone()

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = admin["id"]
        response = client.get("/admin/config/settings")

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "本地 Agent 连接" in body
    assert "运行诊断" in body


def test_admin_canvas_diagnostics_action_reports_results(tmp_path):
    from app import create_app
    from huishi.db import get_db, init_db
    from huishi.providers import save_canvas_setting

    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "test.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"
    with app.app_context():
        init_db()
        save_canvas_setting("canvas_app_url", "http://127.0.0.1:3000")
        save_canvas_setting("canvas_agent_url", "http://127.0.0.1:3001")
        get_db().commit()
        admin = get_db().execute("SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1").fetchone()

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = admin["id"]
        response = client.post("/admin/config/settings/diagnostics", data={"csrf_token": "test"}, follow_redirects=True)

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "画布应用地址已配置" in body
    assert "画布生图 Provider" in body
    assert "在线助手文本 Provider" in body


def test_storage_settings_are_encrypted_masked_and_audited(tmp_path, monkeypatch):
    from cryptography.fernet import Fernet

    from app import create_app
    from huishi.db import get_db, init_db
    from huishi.providers import get_app_settings

    monkeypatch.setenv("HUISHI_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "test.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"
    with app.app_context():
        init_db()
        admin = get_db().execute("SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1").fetchone()

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = admin["id"]
        response = client.post(
            "/admin/config/settings",
            data={
                "csrf_token": "test",
                "storage_fields_submitted": "1",
                "storage_mode": "r2",
                "storage_bucket": "assets",
                "storage_access_key_id": "storage-access-id",
                "storage_secret_access_key": "sk-storage-secret",
                "storage_endpoint_url": "https://account.r2.cloudflarestorage.com",
                "storage_prefix": "huishi",
            },
            follow_redirects=True,
        )

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "sk-storage-secret" not in body
    assert "storage-access-id" not in body
    assert "已保存" in body
    with app.app_context():
        settings = get_app_settings("storage_access_key_id", "storage_secret_access_key")
        raw_rows = get_db().execute(
            "SELECT key, value FROM app_settings WHERE key IN (?, ?)",
            ("storage_access_key_id", "storage_secret_access_key"),
        ).fetchall()
        audit = get_db().execute(
            "SELECT before_json, after_json FROM admin_audit_logs WHERE action = 'settings.update' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert settings == {
        "storage_access_key_id": "storage-access-id",
        "storage_secret_access_key": "sk-storage-secret",
    }
    assert all(str(row["value"]).startswith("enc:v1:") for row in raw_rows)
    assert "sk-storage-secret" not in str(audit["after_json"])
    assert "storage-access-id" not in str(audit["after_json"])


def test_remote_storage_settings_require_bucket_credentials_and_endpoint(tmp_path):
    from app import create_app
    from huishi.db import get_db, init_db

    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "test.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"
    with app.app_context():
        init_db()
        admin = get_db().execute("SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1").fetchone()

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = admin["id"]
        response = client.post(
            "/admin/config/settings",
            data={
                "csrf_token": "test",
                "storage_fields_submitted": "1",
                "storage_mode": "r2",
                "storage_bucket": "",
                "storage_endpoint_url": "not-a-url",
            },
        )

    assert response.status_code == 400


def test_local_storage_connectivity_action_records_success(tmp_path):
    from app import create_app
    from huishi.db import get_db, init_db
    from huishi.providers import get_app_settings

    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "test.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"
    with app.app_context():
        init_db()
        admin = get_db().execute("SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1").fetchone()

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = admin["id"]
        response = client.post(
            "/admin/config/settings/storage/test",
            data={"csrf_token": "test"},
            follow_redirects=True,
        )

    assert response.status_code == 200
    assert "存储连接正常" in response.get_data(as_text=True)
    with app.app_context():
        assert get_app_settings("storage_last_health")["storage_last_health"].startswith("ok:")


def test_legacy_settings_route_redirects_to_admin_config(tmp_path):
    from app import create_app
    from huishi.db import get_db, init_db

    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "test.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"
    with app.app_context():
        init_db()
        admin = get_db().execute("SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1").fetchone()

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = admin["id"]
        response = client.get("/settings", follow_redirects=False)

    assert response.status_code == 302
    assert "/admin/config/settings" in response.headers["Location"]


def test_canvas_route_uses_default_canvas_app_url(tmp_path, monkeypatch):
    from app import create_app
    from huishi.db import get_db, init_db

    monkeypatch.setenv("HUISHI_CANVAS_APP_URL", "http://127.0.0.1:3000")
    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "test.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"
    with app.app_context():
        init_db()
        admin = get_db().execute("SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1").fetchone()

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = admin["id"]
        response = client.get("/canvas")

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "http://127.0.0.1:3000/canvas" in body


def test_production_csp_allows_configured_canvas_frame_origin():
    from app import production_content_security_policy

    csp = production_content_security_policy("https://canvas.huishi.local/canvas")

    assert "frame-src 'self' https://canvas.huishi.local" in csp
    assert "frame-ancestors 'self'" in csp


def test_admin_layout_has_config_center_entry():
    from pathlib import Path

    template = Path("templates/admin/layout.html").read_text(encoding="utf-8")

    assert "配置中心" in template
    assert 'href="/admin/config/settings"' in template
    assert "配置总览" not in template
    assert 'href="/admin/pricing"' not in template
    assert 'href="/admin/packages"' not in template


def test_admin_config_center_redirects_to_system_settings(tmp_path):
    from app import create_app
    from huishi.db import get_db, init_db

    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "test.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"
    with app.app_context():
        init_db()
        admin = get_db().execute("SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1").fetchone()

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = admin["id"]
        response = client.get("/admin/config", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/config/settings")


def test_admin_config_billing_page_renders(tmp_path):
    from app import create_app
    from huishi.db import get_db, init_db

    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "test.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"
    with app.app_context():
        init_db()
        admin = get_db().execute("SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1").fetchone()

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = admin["id"]
        response = client.get("/admin/config/billing")

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "计费规则" in body
    assert "工作台与画布共用模型级定价" in body
    assert "config-editor-list" in body
    assert "视频模型定价" in body
    assert "config-overview-strip" not in body


def test_legacy_admin_pricing_and_packages_redirect_to_config_center(tmp_path):
    from app import create_app
    from huishi.db import get_db, init_db

    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "test.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"
    with app.app_context():
        init_db()
        admin = get_db().execute("SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1").fetchone()

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = admin["id"]
        pricing_response = client.get("/admin/pricing", follow_redirects=False)
        packages_response = client.get("/admin/packages", follow_redirects=False)

    assert pricing_response.status_code == 302
    assert "/admin/config/billing" in pricing_response.headers["Location"]
    assert packages_response.status_code == 302
    assert "/admin/config/packages" in packages_response.headers["Location"]


def test_canvas_app_url_rejects_non_http_value(tmp_path):
    from app import create_app
    from huishi.db import get_db, init_db

    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "test.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"
    with app.app_context():
        init_db()
        admin = get_db().execute("SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1").fetchone()

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = admin["id"]
        response = client.post(
            "/admin/config/settings",
            data={"csrf_token": "test", "canvas_app_url": "api.deepseek.com"},
        )

    assert response.status_code == 400


def test_admin_config_pages_render_shared_sidebar(tmp_path):
    from app import create_app
    from huishi.db import get_db, init_db

    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "test.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"
    with app.app_context():
        init_db()
        admin = get_db().execute("SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1").fetchone()

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = admin["id"]
        settings_response = client.get("/admin/config/settings")
        billing_response = client.get("/admin/config/billing")
        packages_response = client.get("/admin/config/packages")

    for response in (settings_response, billing_response, packages_response):
        body = response.get_data(as_text=True)
        assert response.status_code == 200
        assert "配置总览" not in body
        assert "/admin/config/settings" in body
        assert "/admin/config/billing" in body
        assert "/admin/config/packages" in body


def test_admin_config_packages_page_uses_console_editor_layout(tmp_path):
    from app import create_app
    from huishi.db import get_db, init_db

    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "test.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"
    with app.app_context():
        init_db()
        admin = get_db().execute("SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1").fetchone()

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = admin["id"]
        response = client.get("/admin/config/packages")

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "套餐说明" in body
    assert "config-package-create" in body
    assert "package-editor-list" in body


def test_admin_config_billing_marks_active_sidebar_item(tmp_path):
    from app import create_app
    from huishi.db import get_db, init_db

    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "test.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"
    with app.app_context():
        init_db()
        admin = get_db().execute("SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1").fetchone()

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = admin["id"]
        response = client.get("/admin/config/billing")

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'href="/admin/config/billing"' in body
    assert 'data-config-nav-active="billing"' in body


def test_admin_config_pages_have_scoped_layout_repairs():
    css = Path("static/css/site.css").read_text(encoding="utf-8")
    repair = css.split("/* Admin configuration repair", 1)[1]

    for selector in (
        ".admin-console-page .config-shell",
        ".admin-console-page .settings-table-section",
        ".admin-console-page .config-table",
        ".admin-console-page .settings-dialog",
        ".admin-console-page .config-overview-strip",
        ".admin-console-page .config-package-fields",
    ):
        assert selector in css
    # 作用域约束：这些配置选择器必须带 .admin-console-page 前缀，否则会外溢到用户侧。
    # 注意其中一部分规则定义在 repair 段之外（更早的 admin 区块），因此对整个
    # 样式表断言，而不是只对 repair 段断言。
    for rule in (".config-shell", ".config-content", ".config-table", ".settings-dialog"):
        assert f".admin-console-page {rule}" in css, rule
    # repair 段自身不得出现行首无作用域限定的裸配置选择器。
    for bare in (".config-shell", ".config-content", ".config-table"):
        assert re.search(rf"(?m)^{re.escape(bare)}\s*[,{{]", repair) is None, bare


def test_admin_settings_content_uses_available_desktop_width():
    css = Path("static/css/site.css").read_text(encoding="utf-8")
    repair = css.split("/* Admin configuration repair", 1)[1]
    selector = """.admin-console-page .config-content > .settings-console-form,
.admin-console-page .config-content > .settings-flash {"""

    assert selector in repair
    rule = repair.split(selector, 1)[1].split("}", 1)[0]
    assert "width: 100%;" in rule
    assert "max-width: none;" in rule


def test_admin_settings_root_form_stays_flat_under_theme_overrides():
    css = Path("static/css/site.css").read_text(encoding="utf-8")
    compact = css.split("/* Compact system settings tables */", 1)[1]
    selector = ".admin-console-page .settings-console-form {"

    assert selector in compact
    rule = compact.split(selector, 1)[1].split("}", 1)[0]
    for declaration in (
        "background: transparent !important;",
        "border: 0 !important;",
        "border-radius: 0 !important;",
        "box-shadow: none !important;",
        "overflow: visible !important;",
    ):
        assert declaration in rule


def test_admin_settings_submit_drops_legacy_outer_margin():
    css = Path("static/css/site.css").read_text(encoding="utf-8")
    compact = css.split("/* Compact system settings tables */", 1)[1]
    selector = ".admin-console-page .settings-submit {"

    assert selector in compact
    rule = compact.split(selector, 1)[1].split("}", 1)[0]
    assert "margin: 0;" in rule


def test_settings_tables_stack_without_horizontal_page_overflow():
    css = Path("static/css/site.css").read_text(encoding="utf-8")

    assert ".admin-console-page .config-table td::before" in css
    assert 'content: attr(data-label);' in css
    assert ".admin-console-page .config-table-scroll" in css
    assert "overflow-x: auto;" in css
