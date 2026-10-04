from __future__ import annotations

from pathlib import Path

import pytest

from app import create_app
from huishi.admin_audit import record_admin_audit
from huishi.db import get_db, init_db


@pytest.fixture()
def app(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("HUISHI_DATABASE", str(tmp_path / "test.sqlite3"))
    monkeypatch.setenv("HUISHI_OUTPUT_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("HUISHI_BACKUP_DIR", str(tmp_path / "backups"))
    app = create_app(testing=True)
    with app.app_context():
        init_db()
        admin = get_db().execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1").fetchone()
        record_admin_audit(int(admin["id"]), "user.points.adjust", "user", "2", summary="测试调整")
        get_db().commit()
    return app


def login_admin(app, client):
    with app.app_context():
        admin_id = int(get_db().execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1").fetchone()["id"])
    with client.session_transaction() as session:
        session["user_id"] = admin_id


def test_admin_layout_has_primary_navigation_and_current_page(app):
    client = app.test_client()
    login_admin(app, client)

    response = client.get("/admin/audit")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'aria-label="管理导航"' in body
    assert 'aria-current="page"' in body
    assert "css/site.css?v=20260913-multi-model-1" in body
    assert 'name="q"' in body
    assert "审计日志" in body
    assert "user.points.adjust" in body


def test_dashboard_renders_actionable_operations_health(app):
    client = app.test_client()
    login_admin(app, client)

    body = client.get("/admin/").get_data(as_text=True)

    assert "运行状态" in body
    assert "数据库" in body
    assert "备份" in body
    assert 'data-health-status="' in body
    assert "近期业务" in body
    assert "最近生成" not in body
    assert "积分流水" not in body


def test_admin_console_assets_cover_shell_health_and_responsive_layout():
    css = Path("static/css/site.css").read_text(encoding="utf-8")
    layout = Path("templates/admin/layout.html").read_text(encoding="utf-8")

    assert ".admin-console-shell" in css
    assert "console-page admin-console-page" not in layout
    assert "{% block body_class %}admin-console-page{% endblock %}" in layout
    assert "background: var(--admin-canvas);" in css
    assert ".admin-health-table" in css
    assert '[data-health-status="healthy"]' in css
    assert ".admin-audit-drawer" in css
    assert "@media (max-width: 760px)" in css
    assert ".admin-console-sidebar nav::-webkit-scrollbar" in css
    assert "scrollbar-width: none;" in css


def test_admin_audit_drawer_script_supports_keyboard_and_focus_restore():
    script = Path("static/js/admin.js").read_text(encoding="utf-8")

    assert "data-audit-open" in script
    assert 'event.key === "Escape"' in script
    assert "auditDrawer.focus()" in script
    assert "auditDrawerTrigger.focus()" in script


def test_records_and_user_ledger_share_dense_accessible_activity_table():
    records_template = Path("templates/admin/records.html").read_text(encoding="utf-8")
    ledger_template = Path("templates/admin/user_ledger.html").read_text(encoding="utf-8")
    activity_template = Path("templates/admin/_activity_table.html").read_text(encoding="utf-8")
    css = Path("static/css/site.css").read_text(encoding="utf-8")

    assert records_template.count('_activity_table.html') == 1
    assert ledger_template.count('_activity_table.html') == 1
    assert 'class="admin-data-table admin-activity-table"' in activity_template
    assert 'data-activity-row' in activity_template
    assert 'class="table-list"' not in records_template
    assert 'class="table-list"' not in ledger_template
    assert ".sr-only {" in css
    assert ".admin-record-prompt" in css


def test_activity_drawer_uses_safe_json_and_text_content():
    template = Path("templates/admin/_activity_table.html").read_text(encoding="utf-8")
    script = Path("static/js/admin.js").read_text(encoding="utf-8")

    assert "event|tojson|forceescape" in template
    assert "JSON.parse(row.dataset.activity" in script
    assert "target.textContent" in script
    assert "data-activity-open" in script


def test_users_table_handles_long_values_and_named_csv_file_control():
    template = Path("templates/admin/users.html").read_text(encoding="utf-8")
    script = Path("static/js/admin.js").read_text(encoding="utf-8")

    assert 'class="admin-user-identity"' in template
    assert 'title="{{ user[' in template
    assert 'data-admin-file-input' in template
    assert 'data-admin-file-name' in template
    assert 'file.name' in script
