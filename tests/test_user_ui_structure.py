from pathlib import Path


def text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_workspace_keeps_two_navigation_layers_and_composer():
    page = text("templates/workspace.html")
    nav = text("templates/partials/studio_nav.html")

    assert 'class="studio-rail"' in nav
    assert 'class="studio-sidebar"' in nav
    assert 'id="composer"' in page
    assert 'class="creation-stream"' in page


def test_asset_detail_does_not_mount_studio_navigation():
    page = text("templates/asset_detail.html")

    assert "partials/studio_nav.html" not in page
    assert 'class="detail-image"' in page
    assert 'class="detail-panel"' in page


def test_prompts_remains_an_iframe_boundary():
    page = text("templates/prompts.html")

    assert "prompts_embed_url" in page
    assert 'class="canvas-frame"' in page


def test_account_pages_use_top_navigation_not_studio_rail():
    for path in ("templates/account.html", "templates/account_api_key.html", "templates/pricing.html"):
        page = text(path)
        assert 'class="simple-nav"' in page
        assert "partials/studio_nav.html" not in page


def test_workspace_exposes_mobile_conversation_drawer_controls():
    nav = text("templates/partials/studio_nav.html")
    script = text("static/js/workspace.js")

    assert "data-conversation-toggle" in nav
    assert 'aria-controls="studio-conversations"' in nav
    assert 'id="studio-conversations"' in nav
    assert 'document.querySelector("[data-conversation-toggle]")' in script
    assert 'document.querySelector("#studio-conversations")' in script


def test_mobile_studio_navigation_keeps_settings_in_the_visible_row():
    nav = text("templates/partials/studio_nav.html")
    css = text("static/css/site.css")

    assert "{% if not hide_studio_sidebar|default(false) %}" in nav
    assert 'grid-template-areas: "logo history nav footer";' in css
    assert 'href="/admin/"' in nav
    assert '<a href="/logout">' in nav


def test_workspace_exposes_existing_task_state_machine_to_the_dom():
    page = text("templates/workspace.html")
    script = text("static/js/workspace.js")

    assert 'data-task-state="running"' in page
    assert 'data-task-state="success"' in page
    assert "card.dataset.taskState" in script


def test_assets_expose_loading_ready_and_error_media_states():
    page = text("templates/assets.html")
    script = text("static/js/assets.js")

    assert "data-asset-media" in page
    assert "data-asset-media-status" in page
    assert 'setState("ready")' in script
    assert 'setState("error")' in script


def test_prompts_iframe_and_regenerate_dialog_expose_status_context():
    prompts = text("templates/prompts.html")
    detail = text("templates/asset_detail.html")

    assert 'data-embed-state="loading"' in prompts
    assert 'class="embed-status"' in prompts
    assert "data-embed-frame" in prompts
    assert 'aria-describedby="regenerate-confirm-description"' in detail
    assert 'id="regenerate-confirm-description"' in detail


def test_account_and_auth_auxiliary_pages_do_not_offer_theme_options():
    paths = (
        "templates/account.html",
        "templates/account_api_key.html",
        "templates/pricing.html",
        "templates/forgot_password.html",
        "templates/verify_email.html",
    )

    for path in paths:
        assert 'partials/theme_options.html' not in text(path)

    studio_nav = text("templates/partials/studio_nav.html")
    assert 'partials/theme_options.html' in studio_nav

    options = text("templates/partials/theme_options.html")
    assert 'data-theme-toggle' in options
    assert 'class="theme-menu"' not in options
    assert 'data-theme-option=' not in options
    assert 'data-theme-current' not in options


def test_auth_auxiliary_feedback_is_announced():
    for path in ("templates/forgot_password.html", "templates/verify_email.html"):
        page = text(path)
        assert 'role="alert"' in page
        assert 'aria-live="polite"' in page


def test_user_ui_static_assets_use_current_cache_version():
    """每个模板都必须给静态资源带上缓存破坏版本号。

    旧测试硬编码了一个跨模板共用的版本字符串，但各模板的样式/脚本本就
    独立演进（版本各不相同），这个前提已不成立。这里改为断言真正的不
    变量：每个模板都带 v='...' 版本参数，而不是断言某个具体日期。
    """
    import re

    for path in (
        "templates/base.html",
        "templates/workspace.html",
        "templates/assets.html",
        "templates/asset_detail.html",
    ):
        page = text(path)
        assert re.search(r"v='[0-9]{8}-[a-z0-9-]+'", page), f"{path} 缺少缓存版本号"
