from __future__ import annotations

from pathlib import Path

import pytest

from app import create_app
from huishi.db import get_db, init_db, utc_now
from huishi.admin_audit import record_admin_audit
from huishi.invites import create_invite_code
from huishi.pagination import PageQuery


def test_page_query_clamps_values():
    query = PageQuery.from_values("0", "500")
    assert query.page == 1
    assert query.per_page == 100
    assert query.offset == 0


def test_page_query_uses_defaults_for_invalid_values():
    query = PageQuery.from_values("bad", None)
    assert query.page == 1
    assert query.per_page == 20


@pytest.fixture()
def app(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("HUISHI_DATABASE", str(tmp_path / "test.sqlite3"))
    monkeypatch.setenv("HUISHI_OUTPUT_DIR", str(tmp_path / "uploads"))
    app = create_app(testing=True)
    with app.app_context():
        init_db()
        for email, username in (("target@example.com", "target"), ("other@example.com", "other")):
            get_db().execute(
                """
                INSERT INTO users (email, username, password_hash, role, email_verified, points, created_at)
                VALUES (?, ?, 'hash', 'user', 1, 0, ?)
                """,
                (email, username, utc_now()),
            )
        get_db().commit()
    return app


def test_users_page_filters_by_search_and_renders_pagination(app):
    client = app.test_client()
    with app.app_context():
        admin_id = int(get_db().execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1").fetchone()["id"])
    with client.session_transaction() as session:
        session["user_id"] = admin_id

    response = client.get("/admin/users?q=target&page=1&per_page=20")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "target@example.com" in body
    assert "other@example.com" not in body
    assert 'name="q"' in body
    assert "共 1 条" in body


def login_admin(app, client) -> int:
    with app.app_context():
        admin_id = int(get_db().execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1").fetchone()["id"])
    with client.session_transaction() as session:
        session["user_id"] = admin_id
    return admin_id


def test_invites_page_uses_server_side_pagination(app):
    client = app.test_client()
    admin_id = login_admin(app, client)
    with app.app_context():
        for index in range(25):
            create_invite_code(
                owner_user_id=admin_id,
                reward_points=index,
                code=f"PAGE-{index:02d}",
                created_by_admin_id=admin_id,
            )
        get_db().commit()

    body = client.get("/admin/invites?page=2&per_page=10").get_data(as_text=True)

    assert "PAGE-14" in body
    assert "PAGE-24" not in body
    assert "共 25 条" in body


def test_audit_page_filters_by_actor_and_date_range(app):
    client = app.test_client()
    admin_id = login_admin(app, client)
    with app.app_context():
        record_admin_audit(admin_id, "inside.window", "test", "1", summary="inside")
        record_admin_audit(None, "outside.window", "test", "2", summary="outside")
        rows = get_db().execute("SELECT id, action FROM admin_audit_logs ORDER BY id").fetchall()
        for row in rows:
            created_at = "2026-07-10T12:00:00+00:00" if row["action"] == "inside.window" else "2026-06-01T12:00:00+00:00"
            get_db().execute("UPDATE admin_audit_logs SET created_at = ? WHERE id = ?", (created_at, row["id"]))
        get_db().commit()

    body = client.get(
        "/admin/audit?actor=admin&from=2026-07-10&to=2026-07-10"
    ).get_data(as_text=True)

    assert 'data-action="inside.window"' in body
    assert 'data-action="outside.window"' not in body
    assert 'name="actor"' in body
    assert 'name="from"' in body
    assert 'name="to"' in body


def seed_records_and_ledger(app, user_id: int, *, prefix: str, count: int = 25) -> None:
    with app.app_context():
        db = get_db()
        for index in range(count):
            record_id = db.execute(
                """
                INSERT INTO records
                (user_id, prompt, image_path, mode, resolution, actual_size, quality, output_format, count, points_charged, created_at)
                VALUES (?, ?, ?, ?, '2K', '2048x2048', 'auto', 'png', 1, ?, ?)
                """,
                (
                    user_id,
                    f"{prefix}-record-{index:02d}",
                    f"/static/uploads/{prefix}-{index:02d}.png",
                    "image" if index % 2 == 0 else "text",
                    index,
                    f"2026-07-{(index % 20) + 1:02d}T12:00:00+00:00",
                ),
            ).lastrowid
            db.execute(
                """
                INSERT INTO point_ledger (user_id, delta, reason, record_id, admin_note, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    -index,
                    "generation" if index % 2 == 0 else "admin_adjust",
                    record_id,
                    f"{prefix}-ledger-{index:02d}",
                    f"2026-07-{(index % 20) + 1:02d}T12:00:00+00:00",
                ),
            )
        db.commit()


def test_records_page_paginates_and_filters_unified_activity(app):
    client = app.test_client()
    login_admin(app, client)
    with app.app_context():
        target_id = int(get_db().execute("SELECT id FROM users WHERE username = 'target'").fetchone()["id"])
        other_id = int(get_db().execute("SELECT id FROM users WHERE username = 'other'").fetchone()["id"])
    seed_records_and_ledger(app, target_id, prefix="target")
    seed_records_and_ledger(app, other_id, prefix="other", count=3)

    response = client.get(
        "/admin/records?user=target&mode=image&event_type=image_generation&page=1&per_page=10"
    )
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "target-record" in body
    assert "other-record" not in body
    assert 'data-activity-row' in body
    assert 'aria-label="业务流水分页"' in body
    assert "共 13 条" in body


def test_user_ledger_uses_unified_server_side_pagination(app):
    client = app.test_client()
    login_admin(app, client)
    with app.app_context():
        target_id = int(get_db().execute("SELECT id FROM users WHERE username = 'target'").fetchone()["id"])
    seed_records_and_ledger(app, target_id, prefix="target")

    response = client.get(
        f"/admin/users/{target_id}/ledger?q=target&user=other&page=2&per_page=10"
    )
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "target-record" in body
    assert "other-record" not in body
    assert 'data-activity-row' in body
    assert 'aria-label="用户业务流水分页"' in body
    assert "共 25 条" in body
