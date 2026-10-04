from pathlib import Path


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_admin_layout_uses_shared_theme_and_navigation():
    layout = read("templates/admin/layout.html")

    assert "console-page admin-console-page" not in layout
    assert "{% block body_class %}admin-console-page{% endblock %}" in layout
    assert 'class="admin-theme-control" data-theme-toggle' not in layout
    assert 'include "partials/theme_options.html"' not in layout
    assert "运行总览" in layout
    assert "业务流水" in layout


def test_admin_css_uses_semantic_surfaces_instead_of_split_theme():
    css = read("static/css/site.css")

    assert "--admin-surface: var(--color-surface);" in css
    assert "--admin-canvas: var(--color-bg);" in css
    assert ".admin-console-sidebar" in css
    assert "background: var(--admin-surface);" in css
    assert 'font-family: var(--font-ui);' in css
    admin_css = css.split('/* Admin operations console:', 1)[1]
    content_rule = admin_css.split('\n.admin-console-content {', 1)[1].split('}', 1)[0]
    assert 'min-width: 0;' in content_rule
    assert 'max-width: 100%;' in content_rule
    assert '.admin-metric-strip strong {' in css
    metric_rule = css.split('.admin-metric-strip strong {', 1)[1].split('}', 1)[0]
    assert 'font-family: var(--font-ui);' in metric_rule
    admin_css = css[css.index(".admin-console-page {") :]
    assert "Instrument Serif" not in admin_css
    assert "var(--c-" not in admin_css
    assert "border-left: 2px solid var(--color-primary)" not in admin_css
    assert '.admin-console-page :where(input, textarea)::placeholder {' in admin_css
    assert '.admin-console-page :where(button, input, select, textarea):disabled {' in admin_css
    assert 'color: var(--admin-muted);\n  opacity: 1;' in admin_css
    assert '.admin-console-page .admin-console-sidebar nav a[aria-current="page"]' in admin_css
    mobile_css = admin_css.split('@media (max-width: 760px)', 1)[1]
    mobile_sidebar = mobile_css.split('.admin-console-sidebar {', 1)[1].split('}', 1)[0]
    mobile_topbar = mobile_css.split('.admin-console-topbar {', 1)[1].split('}', 1)[0]
    assert 'height: 64px;' in mobile_sidebar
    assert 'position: sticky;' in mobile_topbar
    assert 'top: 64px;' in mobile_topbar


def test_activity_page_is_one_table_with_one_pagination_contract():
    records = read("templates/admin/records.html")
    table = read("templates/admin/_activity_table.html")

    assert "生成记录" not in records
    assert "积分流水" not in records
    assert "业务流水" in records
    assert 'name="event_type"' in records
    assert 'data-activity-row' in table


def test_dashboard_and_users_follow_unified_operations_contract():
    dashboard = read("templates/admin/dashboard.html")
    users = read("templates/admin/users.html")

    assert "近期业务" in dashboard
    assert "最近生成" not in dashboard
    assert 'data-health-label' in dashboard
    assert '"error":"异常"' in dashboard
    assert 'data-admin-file-input' in users
    assert 'class="admin-user-identity"' in users


def test_settings_provider_table_reserves_an_actions_column_and_js_rebuilds_models():
    css = read("static/css/site.css")
    script = read("static/js/settings.js")

    assert ".admin-console-page .provider-config-table th:nth-child(9)" in css
    assert "min-width" in css.split(".admin-console-page .provider-config-table th:nth-child(9)", 1)[1].split("}", 1)[0]
    assert "replaceChildren" in script
    assert "data-restore-default-url" in script
    assert "data-provider-new-card" not in script


def test_settings_dialog_close_and_submit_controls_meet_touch_and_motion_contracts():
    css = read("static/css/site.css")

    close_rule = css.split(
        ".admin-console-page .settings-dialog [data-dialog-close][aria-label] {", 1
    )[1].split("}", 1)[0]
    assert "width: 44px;" in close_rule
    assert "min-width: 44px;" in close_rule

    submit_rule = css.split(".admin-console-page .settings-submit {", 1)[1].split("}", 1)[0]
    assert "transform: none !important;" in submit_rule
    assert "transition: none !important;" in submit_rule
    assert "box-shadow: none !important;" in submit_rule


def test_settings_protocol_catalog_exposes_jiasuapi_everywhere():
    template = read("templates/admin/_model_management.html")
    model_script = read("static/js/model-management.js")
    settings_script = read("static/js/settings.js")

    assert template.count('value="jiasuapi"') == 1
    assert "jiasuapi" in model_script
    assert "jiasuapi" in settings_script


def test_jiasuapi_connection_editor_exposes_manual_backup_address():
    template = read("templates/admin/_model_management.html")
    model_script = read("static/js/model-management.js")

    assert 'name="backup_base_url"' in template
    assert "backup_base_url" in model_script
    assert "备用地址仅供管理员手动切换" in template
