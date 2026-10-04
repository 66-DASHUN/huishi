from __future__ import annotations

import json
import io
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pytest
from werkzeug.security import check_password_hash

from app import create_app
from huishi.db import get_db, init_db


@pytest.fixture()
def app(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("HUISHI_DATABASE", str(tmp_path / "test.sqlite3"))
    monkeypatch.setenv("HUISHI_OUTPUT_DIR", str(tmp_path / "uploads"))
    app = create_app(testing=True)
    with app.app_context():
        init_db()
    return app


def login_as(client, user_id: int, *, csrf_token: str | None = None) -> None:
    with client.session_transaction() as session:
        session["user_id"] = user_id
        if csrf_token is not None:
            session["csrf_token"] = csrf_token


def admin_id(app) -> int:
    with app.app_context():
        return int(get_db().execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1").fetchone()["id"])


def create(client, **overrides):
    data = {
        "username": "new-user",
        "email": "new-user@example.com",
        "password": "secure-123",
        "role": "user",
        "enabled": "on",
        "points": "25",
    }
    data.update(overrides)
    return client.post("/admin/users/create", data=data)


def test_admin_creates_login_ready_user_with_hashed_password_and_initial_ledger(app):
    client = app.test_client()
    login_as(client, admin_id(app))

    response = create(client)

    assert response.status_code == 302
    with app.app_context():
        user = get_db().execute("SELECT * FROM users WHERE email = ?", ("new-user@example.com",)).fetchone()
        ledger = get_db().execute("SELECT delta, reason FROM point_ledger WHERE user_id = ?", (user["id"],)).fetchone()
    assert user["username"] == "new-user"
    assert user["role"] == "user"
    assert user["enabled"] == 1
    assert user["email_verified"] == 1
    assert user["points"] == 25
    assert check_password_hash(user["password_hash"], "secure-123")
    assert (ledger["delta"], ledger["reason"]) == (25, "admin_initial")

    login = app.test_client().post("/login", data={"email": "new-user@example.com", "password": "secure-123"})
    assert login.status_code == 302


def test_admin_can_create_an_admin_account(app):
    client = app.test_client()
    login_as(client, admin_id(app))

    response = create(client, username="second-admin", email="second-admin@example.com", role="admin", points="0")

    assert response.status_code == 302
    with app.app_context():
        user = get_db().execute("SELECT role FROM users WHERE username = ?", ("second-admin",)).fetchone()
    assert user["role"] == "admin"


def test_disabled_created_user_cannot_log_in(app):
    client = app.test_client()
    login_as(client, admin_id(app))

    response = create(client, username="disabled-user", email="disabled@example.com", enabled="")

    assert response.status_code == 302
    login_client = app.test_client()
    login = login_client.post("/login", data={"email": "disabled@example.com", "password": "secure-123"})
    assert login.status_code == 200
    with login_client.session_transaction() as session:
        assert session.get("user_id") is None


def test_create_normalizes_email_and_rejects_case_insensitive_duplicate_email(app):
    client = app.test_client()
    login_as(client, admin_id(app))
    assert create(client).status_code == 302

    response = create(client, email="NEW-USER@EXAMPLE.COM")

    assert response.status_code == 400
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) AS value FROM users WHERE lower(email) = lower(?)", ("new-user@example.com",)).fetchone()["value"] == 1


def test_create_rejects_exact_duplicate_username_using_existing_username_semantics(app):
    client = app.test_client()
    login_as(client, admin_id(app))
    assert create(client).status_code == 302

    response = create(client, email="other-email@example.com", username="new-user")

    assert response.status_code == 400


def test_created_username_uses_existing_case_sensitive_username_login_behavior(app):
    admin_client = app.test_client()
    login_as(admin_client, admin_id(app))
    assert create(
        admin_client,
        username="MixedCaseUser",
        email="mixed-case@example.com",
        password="mixed-case-password",
    ).status_code == 302

    exact_client = app.test_client()
    assert exact_client.post("/login", data={"username": "MixedCaseUser", "password": "mixed-case-password"}).status_code == 302
    insensitive_client = app.test_client()
    assert insensitive_client.post("/login", data={"username": "mixedcaseuser", "password": "mixed-case-password"}).status_code == 200
    with insensitive_client.session_transaction() as session:
        assert session.get("user_id") is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"password": "short"},
        {"points": "-1"},
        {"points": "not-a-number"},
        {"role": "support"},
    ],
)
def test_create_rejects_invalid_values_without_creating_user(app, overrides):
    client = app.test_client()
    login_as(client, admin_id(app))

    response = create(client, **overrides)

    assert response.status_code == 400
    with app.app_context():
        assert get_db().execute("SELECT id FROM users WHERE username = ?", ("new-user",)).fetchone() is None


def test_create_requires_users_create_permission(app):
    with app.app_context():
        user_id = get_db().execute(
            "INSERT INTO users (email, username, password_hash, role, email_verified, points, created_at) VALUES (?, ?, ?, 'user', 1, 0, 'now')",
            ("ordinary@example.com", "ordinary", "hash"),
        ).lastrowid
        get_db().commit()
    client = app.test_client()
    login_as(client, int(user_id))

    response = create(client)

    assert response.status_code == 403


def test_create_requires_csrf_when_csrf_protection_is_enabled(app):
    app.config["CSRF_PROTECT_TESTING"] = True
    client = app.test_client()
    login_as(client, admin_id(app))

    response = create(client)

    assert response.status_code == 403


def test_create_audit_excludes_password_and_hash(app):
    client = app.test_client()
    login_as(client, admin_id(app))

    response = create(client, password="never-log-this-password")

    assert response.status_code == 302
    with app.app_context():
        audit = get_db().execute("SELECT action, before_json, after_json FROM admin_audit_logs WHERE action = 'user.create'").fetchone()
    assert audit["action"] == "user.create"
    after = json.loads(audit["after_json"])
    assert set(after) == {"id", "username", "email", "role", "enabled", "points"}
    assert "never-log-this-password" not in audit["before_json"] + audit["after_json"]
    assert "password_hash" not in audit["before_json"] + audit["after_json"]


def test_create_rolls_back_user_ledger_and_success_audit_when_audit_write_fails(app, monkeypatch):
    client = app.test_client()
    login_as(client, admin_id(app))
    app.config["PROPAGATE_EXCEPTIONS"] = False

    def fail_audit(*_args, **_kwargs):
        raise RuntimeError("audit failure must stay private")

    monkeypatch.setattr("huishi.routes_admin.record_admin_audit", fail_audit)
    response = create(client, username="rollback-user", email="rollback@example.com", password="rollback-secret")

    assert response.status_code == 500
    assert "rollback-secret" not in response.get_data(as_text=True)
    with app.app_context():
        assert get_db().execute("SELECT id FROM users WHERE username = 'rollback-user'").fetchone() is None
        assert get_db().execute("SELECT id FROM point_ledger").fetchone() is None
        success_audit = get_db().execute(
            "SELECT id FROM admin_audit_logs WHERE action = 'user.create' AND result = 'success'"
        ).fetchone()
        audit_rows = get_db().execute("SELECT before_json, after_json FROM admin_audit_logs").fetchall()
    assert success_audit is None
    assert "rollback-secret" not in " ".join(row["before_json"] + row["after_json"] for row in audit_rows)


def test_create_concurrent_unique_conflict_returns_safe_400_and_rolls_back(app, monkeypatch):
    from huishi import routes_admin

    client = app.test_client()
    login_as(client, admin_id(app))

    @contextmanager
    def conflicting_transaction():
        db = get_db()

        class ConflictOnUserInsert:
            def execute(self, sql, params=()):
                if "INSERT INTO users" in sql:
                    raise sqlite3.IntegrityError("unique constraint failed")
                return db.execute(sql, params)

        try:
            yield ConflictOnUserInsert()
        except Exception:
            db.rollback()
            raise
        else:
            db.commit()

    monkeypatch.setattr(routes_admin, "transaction", conflicting_transaction)
    response = create(client, username="racing-user", email="racing@example.com", password="race-secret")

    assert response.status_code == 400
    assert "邮箱或用户名已存在" in response.get_data(as_text=True)
    assert "race-secret" not in response.get_data(as_text=True)
    with app.app_context():
        assert get_db().execute("SELECT id FROM users WHERE username = 'racing-user'").fetchone() is None
        assert get_db().execute("SELECT id FROM point_ledger").fetchone() is None
        audit_rows = get_db().execute("SELECT before_json, after_json FROM admin_audit_logs").fetchall()
    serialized = " ".join(row["before_json"] + row["after_json"] for row in audit_rows)
    assert "race-secret" not in serialized
    assert "password_hash" not in serialized


def test_create_failure_audits_do_not_expose_submitted_password(app):
    client = app.test_client()
    login_as(client, admin_id(app))

    weak = create(client, username="weak-user", email="weak@example.com", password="tiny")
    assert create(client, username="duplicate-user", email="duplicate@example.com", password="first-password").status_code == 302
    duplicate = create(client, username="duplicate-user", email="other@example.com", password="duplicate-secret")

    assert weak.status_code == 400
    assert duplicate.status_code == 400
    with app.app_context():
        audits = get_db().execute("SELECT before_json, after_json FROM admin_audit_logs WHERE action = 'user.create'").fetchall()
    serialized = " ".join(row["before_json"] + row["after_json"] for row in audits)
    for secret in ("tiny", "first-password", "duplicate-secret", "password_hash"):
        assert secret not in serialized


def test_create_dialog_is_permission_gated_and_uses_existing_dialog_contract(app):
    with app.app_context():
        viewer_id = get_db().execute(
            "INSERT INTO users (email, username, password_hash, role, email_verified, points, created_at) VALUES (?, ?, ?, 'viewer', 1, 0, 'now')",
            ("viewer@example.com", "viewer", "hash"),
        ).lastrowid
        get_db().commit()

    admin_client = app.test_client()
    login_as(admin_client, admin_id(app))
    admin_page = admin_client.get("/admin/users").get_data(as_text=True)
    viewer_client = app.test_client()
    login_as(viewer_client, int(viewer_id))
    viewer_page = viewer_client.get("/admin/users").get_data(as_text=True)

    assert 'data-dialog-open="admin-user-create"' in admin_page
    assert '<dialog class="settings-dialog" id="admin-user-create"' in admin_page
    assert 'name="csrf_token"' in admin_page
    assert 'name="password" type="password" autocomplete="new-password"' in admin_page
    password_input = re.search(r'<input name="password"[^>]*>', admin_page)
    assert password_input is not None
    assert "value=" not in password_input.group(0)
    assert 'name="role"' in admin_page
    assert 'name="enabled" type="checkbox"' in admin_page
    assert 'name="points" type="number" min="0"' in admin_page
    assert 'admin-user-create' not in viewer_page
    script = Path("static/js/admin.js").read_text(encoding="utf-8")
    assert 'document.querySelectorAll("[data-dialog-open]")' in script
    assert 'dialog.querySelectorAll("[data-dialog-close]")' in script


def test_enabled_schema_migration_keeps_existing_sqlite_users_enabled():
    from huishi.db import migrate_users_table

    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            created_at TEXT NOT NULL
        )
        """
    )
    db.execute("INSERT INTO users (username, password_hash, role, created_at) VALUES ('legacy', 'hash', 'user', 'now')")

    migrate_users_table(db)

    assert db.execute("SELECT enabled FROM users WHERE username = 'legacy'").fetchone()["enabled"] == 1


def test_enabled_schema_migration_is_included_for_postgresql():
    from huishi.db import migrate_postgres_schema_columns
    from huishi.db_backend import PostgreSQLConnection

    class Cursor:
        def fetchone(self):
            return None

    class RawPostgres:
        def __init__(self):
            self.executed: list[str] = []

        def execute(self, sql, _params=()):
            self.executed.append(sql)
            return Cursor()

        def commit(self):
            pass

        def rollback(self):
            pass

        def close(self):
            pass

    raw = RawPostgres()
    migrate_postgres_schema_columns(PostgreSQLConnection(raw))

    assert any("ALTER TABLE users ADD COLUMN IF NOT EXISTS enabled" in sql for sql in raw.executed)


def test_disabled_existing_web_session_is_cleared_before_protected_view(app):
    from werkzeug.security import generate_password_hash

    with app.app_context():
        user_id = get_db().execute(
            """
            INSERT INTO users (email, username, password_hash, role, email_verified, enabled, points, created_at)
            VALUES ('session-user@example.com', 'session-user', ?, 'user', 1, 1, 0, 'now')
            """,
            (generate_password_hash("session-password"),),
        ).lastrowid
        get_db().commit()
    client = app.test_client()
    login_as(client, int(user_id))
    assert client.get("/account").status_code == 200

    with app.app_context():
        get_db().execute("UPDATE users SET enabled = 0 WHERE id = ?", (user_id,))
        get_db().commit()

    response = client.get("/account")

    assert response.status_code == 200
    with client.session_transaction() as session:
        assert session.get("user_id") is None


def test_enabled_existing_web_session_remains_authenticated(app):
    with app.app_context():
        user_id = get_db().execute(
            "INSERT INTO users (email, username, password_hash, role, email_verified, enabled, points, created_at) VALUES ('enabled-session@example.com', 'enabled-session', 'hash', 'user', 1, 1, 0, 'now')"
        ).lastrowid
        get_db().commit()
    client = app.test_client()
    login_as(client, int(user_id))

    response = client.get("/account")

    assert response.status_code == 200
    with client.session_transaction() as session:
        assert session.get("user_id") == int(user_id)


def test_admin_can_toggle_existing_user_status_and_audit(app):
    client = app.test_client()
    admin = admin_id(app)
    login_as(client, admin)
    with app.app_context():
        user_id = get_db().execute(
            "INSERT INTO users (email, username, password_hash, role, email_verified, enabled, points, created_at) VALUES (?, ?, 'hash', 'user', 1, 1, 0, 'now')",
            ("status-user@example.com", "status-user"),
        ).lastrowid
        get_db().commit()

    response = client.post(f"/admin/users/{user_id}/status", data={"enabled": "0"})

    assert response.status_code == 302
    with app.app_context():
        user = get_db().execute("SELECT enabled FROM users WHERE id = ?", (user_id,)).fetchone()
        audit = get_db().execute(
            "SELECT action, before_json, after_json FROM admin_audit_logs WHERE action = 'user.status.update' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert user["enabled"] == 0
    assert audit["action"] == "user.status.update"
    assert '"enabled": true' in audit["before_json"]
    assert '"enabled": false' in audit["after_json"]


def test_status_update_uses_immediate_transaction_for_last_admin_guard(app, monkeypatch):
    from huishi import routes_admin

    client = app.test_client()
    admin = admin_id(app)
    login_as(client, admin)
    with app.app_context():
        second_admin = get_db().execute(
            "INSERT INTO users (email, username, password_hash, role, email_verified, enabled, points, created_at) VALUES ('transaction-admin@example.com', 'transaction-admin', 'hash', 'admin', 1, 1, 0, 'now')"
        ).lastrowid
        get_db().commit()

    entered = []

    @contextmanager
    def tracked_immediate_transaction():
        entered.append(True)
        db = get_db()
        try:
            yield db
        except Exception:
            db.rollback()
            raise
        else:
            db.commit()

    monkeypatch.setattr(routes_admin, "immediate_transaction", tracked_immediate_transaction, raising=False)

    response = client.post(f"/admin/users/{second_admin}/status", data={"enabled": "0"})

    assert response.status_code == 302
    assert entered == [True]


def test_status_update_is_admin_only_and_cannot_disable_current_or_last_enabled_admin(app):
    with app.app_context():
        admin = get_db().execute("SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1").fetchone()
        second_admin = get_db().execute(
            "INSERT INTO users (email, username, password_hash, role, email_verified, enabled, points, created_at) VALUES ('second-status-admin@example.com', 'second-status-admin', 'hash', 'admin', 1, 1, 0, 'now')"
        ).lastrowid
        user_id = get_db().execute(
            "INSERT INTO users (email, username, password_hash, role, email_verified, enabled, points, created_at) VALUES ('status-user-2@example.com', 'status-user-2', 'hash', 'user', 1, 1, 0, 'now')"
        ).lastrowid
        get_db().commit()
    client = app.test_client()
    login_as(client, int(admin["id"]))
    assert client.post(f"/admin/users/{admin['id']}/status", data={"enabled": "0"}).status_code == 400
    assert client.post(f"/admin/users/{second_admin}/status", data={"enabled": "0"}).status_code == 302
    assert client.post(f"/admin/users/{admin['id']}/status", data={"enabled": "0"}).status_code == 400

    ordinary = app.test_client()
    login_as(ordinary, int(user_id))
    assert ordinary.post(f"/admin/users/{admin['id']}/status", data={"enabled": "0"}).status_code == 403


def test_users_csv_status_round_trip_includes_enabled(app):
    client = app.test_client()
    login_as(client, admin_id(app))
    with app.app_context():
        user_id = get_db().execute(
            "INSERT INTO users (email, username, password_hash, role, email_verified, enabled, points, created_at) VALUES ('csv-disabled@example.com', 'csv-disabled', 'hash', 'user', 1, 0, 7, 'now')"
        ).lastrowid
        get_db().commit()

    exported = client.get("/admin/users/export")
    csv_text = exported.get_data(as_text=True)
    assert "enabled" in csv_text.splitlines()[0]
    assert "csv-disabled@example.com" in csv_text
    assert ",0," in csv_text

    imported = client.post(
        "/admin/users/import",
        data={"file": (io.BytesIO(b"email,password,username,role,points,email_verified,enabled\nroundtrip@example.com,secret-123,roundtrip,user,9,1,0\n"), "users.csv")},
        content_type="multipart/form-data",
    )
    assert imported.status_code == 302
    with app.app_context():
        imported_user = get_db().execute("SELECT id, enabled, points FROM users WHERE email = 'roundtrip@example.com'").fetchone()
        ledger = get_db().execute(
            "SELECT delta, reason FROM point_ledger WHERE user_id = ?",
            (imported_user["id"],),
        ).fetchone()
    assert imported_user["enabled"] == 0
    assert imported_user["points"] == 9
    assert (ledger["delta"], ledger["reason"]) == (9, "admin_initial")
