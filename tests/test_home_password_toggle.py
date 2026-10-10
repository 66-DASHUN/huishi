from pathlib import Path


def test_home_auth_modal_has_password_visibility_toggle():
    source = Path("static/js/home.js").read_text(encoding="utf-8")

    assert 'className="password-toggle"' in source
    assert 'aria-label={visible ? "隐藏密码" : "显示密码"}' in source
    assert 'autoComplete="current-password"' in source
    assert 'autoComplete="new-password"' in source
    assert source.count("<PasswordField") == 2


def test_home_no_longer_injects_the_canvas_app_url(monkeypatch, tmp_path):
    """首页不得再把画布应用地址交给前端。

    这条钉的是一个"看起来像嵌进来"的回归：首页「画布」卡片曾经 href 指向
    canvas_app_url，也就是画布应用的落地页（另一个域名+端口）。用户点一下
    就整页离开了绘世，观感上像外挂。现在卡片指向主站 /canvas，用 iframe
    内嵌，地址栏始终不变。

    所以这里反过来断言：即便后台配了画布地址，首页也不再注入它。
    """
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
    assert b"__HUISHI_CANVAS_URL__" not in response.data
    assert b"127.0.0.1:3000" not in response.data


def test_home_hero_source_has_authenticated_quick_cards():
    source = Path("static/js/home.js").read_text(encoding="utf-8")

    # 画布卡片必须指向主站路由，而不是画布应用地址（见上一条测试的说明）
    assert 'href="/canvas"' in source
    assert "CANVAS_URL" not in source
    assert "function CanvasIcon()" in source
    assert "function PromptsIcon()" in source
    assert "function MaterialsIcon()" in source
    assert 'href="/prompts"' in source
    assert 'value="画布" label="我的画布"' in source
    assert 'value="词库" label="提示词库"' in source
    assert 'value="素材" label="我的素材"' in source
