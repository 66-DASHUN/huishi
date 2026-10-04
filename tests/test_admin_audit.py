from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import pytest

from app import create_app
from huishi.db import get_db, init_db
from huishi.db_backend import PostgreSQLConnection


@pytest.fixture()
def app(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("HUISHI_DATABASE", str(tmp_path / "test.sqlite3"))
    monkeypatch.setenv("HUISHI_OUTPUT_DIR", str(tmp_path / "uploads"))
    app = create_app(testing=True)
    with app.app_context():
        init_db()
    return app


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def login_admin(app):
    def login(client):
        with app.app_context():
            admin_id = int(
                get_db().execute("SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1").fetchone()["id"]
            )
        with client.session_transaction() as session:
            session["user_id"] = admin_id
        return admin_id

    return login


@pytest.fixture()
def target_user_id(app):
    with app.app_context():
        cursor = get_db().execute(
            """
            INSERT INTO users (email, username, password_hash, role, email_verified, points, created_at)
            VALUES (?, ?, 'hash', 'user', 1, 20, 'now')
            """,
            ("target@example.com", "target"),
        )
        get_db().commit()
        return int(cursor.lastrowid)


def test_admin_audit_table_is_initialized(app):
    with app.app_context():
        db = get_db()
        if isinstance(db, PostgreSQLConnection):
            columns = db.execute(
                """
                SELECT column_name AS name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'admin_audit_logs'
                ORDER BY ordinal_position
                """
            ).fetchall()
        else:
            columns = db.execute("PRAGMA table_info(admin_audit_logs)").fetchall()

    assert [row["name"] for row in columns] == [
        "id",
        "actor_user_id",
        "action",
        "target_type",
        "target_id",
        "summary",
        "before_json",
        "after_json",
        "result",
        "request_id",
        "created_at",
    ]


def test_redact_audit_values_removes_secret_fields():
    from huishi.admin_audit import redact_audit_values

    assert redact_audit_values(
        {"name": "primary", "api_key": "sk-secret", "smtp_password": "pw", "nested": {"token": "secret"}}
    ) == {
        "name": "primary",
        "api_key": "[redacted]",
        "smtp_password": "[redacted]",
        "nested": {"token": "[redacted]"},
    }


def test_record_admin_audit_stores_safe_json(app):
    from huishi.admin_audit import record_admin_audit

    with app.app_context():
        record_admin_audit(
            1,
            "provider.update",
            "provider",
            "7",
            before={"api_key": "old"},
            after={"api_key": "new", "name": "primary"},
        )
        get_db().commit()
        row = get_db().execute("SELECT * FROM admin_audit_logs").fetchone()

    assert json.loads(row["before_json"]) == {"api_key": "[redacted]"}
    assert json.loads(row["after_json"]) == {"api_key": "[redacted]", "name": "primary"}


def test_request_id_is_preserved_for_valid_input_and_replaced_for_invalid_input(app):
    client = app.test_client()

    accepted = client.get("/", headers={"X-Request-ID": "ops-check_20260711"})
    replaced = client.get("/", headers={"X-Request-ID": "invalid request id with spaces"})

    assert accepted.headers["X-Request-ID"] == "ops-check_20260711"
    assert replaced.headers["X-Request-ID"] != "invalid request id with spaces"
    assert len(replaced.headers["X-Request-ID"]) == 24


@pytest.mark.parametrize(
    ("suffix", "data", "action"),
    [
        ("adjust", {"delta": "100", "admin_note": "support credit"}, "user.points.adjust"),
        ("password", {"password": "new-secret-123"}, "user.password.reset"),
        ("role", {"role": "support"}, "user.role.update"),
    ],
)
def test_admin_mutation_writes_audit(client, login_admin, target_user_id, suffix, data, action, app):
    login_admin(client)

    response = client.post(f"/admin/users/{target_user_id}/{suffix}", data=data)

    assert response.status_code == 302
    with app.app_context():
        row = get_db().execute("SELECT * FROM admin_audit_logs WHERE action = ?", (action,)).fetchone()
    assert row is not None
    assert "new-secret-123" not in row["after_json"]


def audit_actions(app) -> list[str]:
    with app.app_context():
        return [
            str(row["action"])
            for row in get_db().execute("SELECT action FROM admin_audit_logs ORDER BY id").fetchall()
        ]


def test_user_delete_bulk_and_import_write_safe_audits(client, login_admin, target_user_id, app):
    login_admin(client)

    imported = client.post(
        "/admin/users/import",
        data={
            "file": (
                BytesIO(b"email,password,username,role,points,email_verified\nimported@example.com,secret-123,imported,user,12,1\n"),
                "users.csv",
            )
        },
        content_type="multipart/form-data",
    )
    bulk_reset = client.post(
        "/admin/users/bulk",
        data={"action": "reset_login_failures", "user_ids[]": [str(target_user_id)]},
    )
    deleted = client.post(f"/admin/users/{target_user_id}/delete")

    assert imported.status_code == 302
    assert bulk_reset.status_code == 302
    assert deleted.status_code == 302
    assert audit_actions(app)[-3:] == ["user.import", "user.bulk.login_failures.reset", "user.delete"]
    with app.app_context():
        serialized = " ".join(
            str(row["before_json"]) + str(row["after_json"])
            for row in get_db().execute("SELECT before_json, after_json FROM admin_audit_logs").fetchall()
        )
    assert "secret-123" not in serialized


def test_invite_lifecycle_writes_audits(client, login_admin, target_user_id, app):
    login_admin(client)

    created = client.post(
        "/admin/invites",
        data={
            "code": "AUDIT-CODE",
            "owner_user_id": str(target_user_id),
            "reward_points": "8",
            "max_uses": "4",
            "enabled": "on",
        },
    )
    updated = client.post(
        "/admin/invites/AUDIT-CODE",
        data={"reward_points": "10", "max_uses": "5", "enabled": "on"},
    )
    deleted = client.post("/admin/invites/AUDIT-CODE/delete")

    assert created.status_code == 302
    assert updated.status_code == 302
    assert deleted.status_code == 302
    assert audit_actions(app)[-3:] == ["invite.create", "invite.update", "invite.delete"]


def test_billing_and_package_mutations_write_audits(client, login_admin, app):
    login_admin(client)
    with app.app_context():
        rule = get_db().execute("SELECT * FROM pricing_rules ORDER BY id LIMIT 1").fetchone()

    billing = client.post(
        "/admin/config/billing",
        data={
            "mode": rule["mode"],
            "resolution": rule["resolution"],
            "points_per_image": str(int(rule["points_per_image"]) + 1),
            "enabled": "on",
        },
    )
    created = client.post(
        "/admin/config/packages",
        data={"name": "审计套餐", "price": "9.90", "points": "90", "description": "audit", "enabled": "on"},
    )
    with app.app_context():
        package_id = int(get_db().execute("SELECT id FROM packages WHERE name = '审计套餐'").fetchone()["id"])
    updated = client.post(
        f"/admin/packages/{package_id}",
        data={"name": "审计套餐 2", "price": "12.00", "points": "120", "description": "updated", "enabled": "on"},
    )
    deleted = client.post(f"/admin/packages/{package_id}/delete")

    assert billing.status_code == 302
    assert created.status_code == 302
    assert updated.status_code == 302
    assert deleted.status_code == 302
    assert audit_actions(app)[-4:] == [
        "billing.rule.update",
        "package.create",
        "package.update",
        "package.delete",
    ]


def test_billing_config_shows_friendly_name_and_exact_model_id_in_a_table(client, login_admin):
    login_admin(client)

    response = client.get("/admin/config/billing")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "<table" in page
    assert "模型 ID" in page
    assert "Nano Banana Pro" in page
    assert "gemini-3-pro-image" in page


def test_billing_rule_requires_at_least_one_point(client, login_admin, app):
    login_admin(client)
    with app.app_context():
        rule = get_db().execute("SELECT * FROM pricing_rules WHERE points_per_image = 1 ORDER BY id LIMIT 1").fetchone()

    rejected = client.post(
        "/admin/config/billing",
        data={"mode": rule["mode"], "model": rule["model"], "resolution": rule["resolution"], "points_per_image": "0", "enabled": "on"},
    )
    accepted = client.post(
        "/admin/config/billing",
        data={"mode": rule["mode"], "model": rule["model"], "resolution": rule["resolution"], "points_per_image": "1", "enabled": "on"},
    )

    assert rejected.status_code == 400
    assert accepted.status_code == 302


def test_settings_and_provider_audits_redact_secrets(client, login_admin, app):
    login_admin(client)

    settings = client.post(
        "/admin/config/settings",
        data={
            "base_url": "https://image.example.test",
            "api_key": "sk-image-secret",
            "prompt_base_url": "https://prompt.example.test",
            "prompt_api_key": "sk-prompt-secret",
            "prompt_model": "prompt-model",
            "canvas_app_url": "https://canvas.example.test",
            "canvas_agent_url": "http://127.0.0.1:17371",
            "canvas_agent_token": "agent-secret-token",
            "canvas_local_start_cmd": "start-agent",
            "canvas_default_template": "default",
        },
    )
    provider = client.post(
        "/settings/providers",
        data={
            "provider_type": "image",
            "name": "audit provider",
            "base_url": "https://provider.example.test",
            "api_key": "sk-provider-secret",
            "model": "image-model",
            "priority": "10",
            "enabled": "1",
            "resolutions": ["1K", "2K"],
        },
    )

    assert settings.status_code == 302
    assert provider.status_code == 302
    assert audit_actions(app)[-2:] == ["settings.update", "provider.create"]
    with app.app_context():
        serialized = " ".join(
            str(row["before_json"]) + str(row["after_json"])
            for row in get_db().execute(
                "SELECT before_json, after_json FROM admin_audit_logs WHERE action IN ('settings.update', 'provider.create')"
            ).fetchall()
        )
    for secret in ("sk-image-secret", "sk-prompt-secret", "agent-secret-token", "sk-provider-secret"):
        assert secret not in serialized


def test_rejected_password_and_provider_attempts_are_audited_without_secrets(
    client, login_admin, target_user_id, app
):
    login_admin(client)

    password = client.post(
        f"/admin/users/{target_user_id}/password",
        data={"password": "tiny"},
    )
    provider = client.post(
        "/settings/providers",
        data={
            "provider_type": "image",
            "name": "bad provider",
            "base_url": "javascript:alert(1)",
            "api_key": "sk-rejected-secret",
            "model": "image-model",
            "priority": "10",
            "enabled": "1",
        },
    )

    assert password.status_code == 400
    assert provider.status_code == 400
    with app.app_context():
        rows = get_db().execute(
            "SELECT action, result, before_json, after_json FROM admin_audit_logs ORDER BY id"
        ).fetchall()
    assert [(row["action"], row["result"]) for row in rows[-2:]] == [
        ("user.password.reset", "rejected"),
        ("provider.create", "rejected"),
    ]
    serialized = " ".join(str(row["before_json"]) + str(row["after_json"]) for row in rows)
    assert "tiny" not in serialized
    assert "sk-rejected-secret" not in serialized


def test_all_high_risk_admin_write_endpoints_have_rejection_audit_mappings():
    from huishi.admin_audit import ADMIN_WRITE_AUDIT_TARGETS

    assert {
        "admin.config_settings",
        "admin.config_billing",
        "admin.config_packages",
        "admin.users",
        "admin.invites",
        "admin.update_invite_default",
        "admin.update_invite",
        "admin.delete_invite",
        "admin.bulk_update_invites",
        "admin.import_users",
        "admin.adjust_user",
        "admin.bulk_update_users",
        "admin.reset_user_password",
        "admin.reset_user_login_failures",
        "admin.update_user_role",
        "admin.delete_user",
        "admin.update_package",
        "admin.delete_package",
        "workspace.settings",
        "workspace.create_api_provider",
        "workspace.update_api_provider",
        "workspace.delete_api_provider",
        "workspace.test_api_provider",
    }.issubset(ADMIN_WRITE_AUDIT_TARGETS)


def test_high_risk_validation_failures_are_audited_and_rolled_back(
    client, login_admin, target_user_id, app
):
    admin_id = login_admin(client)
    requests = [
        client.post("/admin/config/billing", data={"points_per_image": "bad"}),
        client.post("/admin/config/packages", data={"name": ""}),
        client.post(
            "/admin/invites",
            data={"owner_user_id": "999999", "reward_points": "1", "max_uses": "1"},
        ),
        client.post(f"/admin/users/{target_user_id}/role", data={"role": "invalid"}),
        client.post(f"/admin/users/{admin_id}/delete"),
        client.post("/admin/users/bulk", data={"action": "invalid"}),
        client.post("/admin/invites/bulk", data={"action": "invalid"}),
        client.post(
            "/admin/config/settings",
            data={
                "base_url": "https://valid.example.test",
                "api_key": "sk-must-not-persist",
                "canvas_app_url": "javascript:alert(1)",
                "canvas_agent_token": "agent-secret-must-not-log",
            },
        ),
        client.post("/settings/providers/999999", data={"name": "missing"}),
        client.post("/settings/providers/999999/delete"),
    ]

    assert [response.status_code for response in requests] == [400, 400, 400, 400, 400, 400, 400, 400, 404, 404]
    with app.app_context():
        rows = get_db().execute(
            "SELECT action, target_id, result, before_json, after_json FROM admin_audit_logs ORDER BY id"
        ).fetchall()
        saved_key = get_db().execute(
            "SELECT value FROM app_settings WHERE key = 'image_api_key'"
        ).fetchone()

    assert [(row["action"], row["result"]) for row in rows] == [
        ("billing.rule.update", "rejected"),
        ("package.create", "rejected"),
        ("invite.create", "rejected"),
        ("user.role.update", "rejected"),
        ("user.delete", "rejected"),
        ("user.bulk", "rejected"),
        ("invite.bulk", "rejected"),
        ("settings.update", "rejected"),
        ("provider.update", "rejected"),
        ("provider.delete", "rejected"),
    ]
    assert saved_key is None or saved_key["value"] == ""
    serialized = " ".join(str(row["before_json"]) + str(row["after_json"]) for row in rows)
    assert "sk-must-not-persist" not in serialized
    assert "agent-secret-must-not-log" not in serialized


def test_provider_connectivity_exception_writes_failed_audit(
    client, login_admin, app, monkeypatch
):
    login_admin(client)
    created = client.post(
        "/settings/providers",
        data={
            "provider_type": "image",
            "name": "failing check provider",
            "base_url": "https://provider.example.test",
            "api_key": "sk-provider-secret",
            "model": "image-model",
            "priority": "10",
            "enabled": "1",
            "resolutions": ["1K"],
        },
    )
    assert created.status_code == 302
    with app.app_context():
        provider_id = int(
            get_db().execute(
                "SELECT id FROM api_providers WHERE name = 'failing check provider'"
            ).fetchone()["id"]
        )
        get_db().execute("DELETE FROM admin_audit_logs")
        get_db().commit()

    def fail_check(_provider):
        raise RuntimeError("upstream secret detail")

    monkeypatch.setattr(
        "huishi.routes_workspace.provider_store.check_provider_connectivity",
        fail_check,
    )
    response = client.post(f"/settings/providers/{provider_id}/test")

    assert response.status_code == 302
    with app.app_context():
        row = get_db().execute(
            "SELECT action, result, before_json, after_json FROM admin_audit_logs"
        ).fetchone()
    assert (row["action"], row["result"]) == ("provider.test", "failed")
    assert "upstream secret detail" not in row["before_json"] + row["after_json"]
