from pathlib import Path


def test_home_auth_modal_has_password_visibility_toggle():
    source = Path("static/js/home.js").read_text(encoding="utf-8")

    assert 'className="password-toggle"' in source
    assert 'aria-label={visible ? "隐藏密码" : "显示密码"}' in source
    assert 'autoComplete="current-password"' in source
    assert 'autoComplete="new-password"' in source
    assert source.count("<PasswordField") == 2


def test_home_injects_configured_canvas_url(monkeypatch, tmp_path):
    monkeypatch.setenv("HUISHI_DATABASE", str(tmp_path / "home.sqlite3"))

    from app import create_app
    from huishi.db import get_db, init_db
    from huishi.providers import save_canvas_setting

    app = create_app(testing=True)
    with app.app_context():
        init_db()
        save_canvas_setting("canvas_app_url", "http://127.0.0.1:3000/")
        get_db().commit()

    with app.test_client() as client:
        response = client.get("/")

    assert response.status_code == 200
    assert b'window.__HUISHI_CANVAS_URL__ = "http://127.0.0.1:3000";' in response.data


def test_home_hero_source_has_authenticated_quick_cards():
    source = Path("static/js/home.js").read_text(encoding="utf-8")

    assert 'const CANVAS_URL = window.__HUISHI_CANVAS_URL__ || "";' in source
    assert "function CanvasIcon()" in source
    assert "function PromptsIcon()" in source
    assert "function MaterialsIcon()" in source
    assert 'href="/prompts"' in source
    assert 'value="画布" label="我的画布"' in source
    assert 'value="词库" label="提示词库"' in source
    assert 'value="素材" label="我的素材"' in source
