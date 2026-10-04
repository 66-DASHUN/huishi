from __future__ import annotations

from pathlib import Path

import pytest

from app import create_app
from huishi.db import get_db, init_db
from huishi.routes_admin import delete_user_cascade


@pytest.fixture()
def app(tmp_path: Path):
    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "test.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"
    with app.app_context():
        init_db()
    return app


def _create_user(username: str) -> int:
    cursor = get_db().execute(
        """
        INSERT INTO users (username, email, password_hash, role, email_verified, points, created_at)
        VALUES (?, '', 'hash', 'user', 1, 0, 'now')
        """,
        (username,),
    )
    return int(cursor.lastrowid)


def _create_admin(username: str = "admin-user") -> int:
    cursor = get_db().execute(
        """
        INSERT INTO users (username, email, password_hash, role, email_verified, points, created_at)
        VALUES (?, '', 'hash', 'admin', 1, 0, 'now')
        """,
        (username,),
    )
    return int(cursor.lastrowid)


def _login(client, user_id: int) -> None:
    with client.session_transaction() as session:
        session["user_id"] = user_id


def test_delete_user_cascade_cleans_foreign_key_dependents(app):
    with app.app_context():
        target_user_id = _create_user("delete-me")
        other_user_id = _create_user("keep-me")

        conversation_id = get_db().execute(
            """
            INSERT INTO canvas_conversations (user_id, title, archived, created_at, updated_at)
            VALUES (?, 'canvas', 0, 'now', 'now')
            """,
            (target_user_id,),
        ).lastrowid
        get_db().execute(
            """
            INSERT INTO canvas_messages (conversation_id, role, content, tool_calls, created_at)
            VALUES (?, 'user', 'hello', '[]', 'now')
            """,
            (conversation_id,),
        )

        owned_invite_id = get_db().execute(
            """
            INSERT INTO invite_codes
            (code, owner_user_id, reward_points, max_uses, used_count, enabled, created_by_admin_id, created_at, updated_at)
            VALUES ('OWNED', ?, 0, NULL, 0, 1, ?, 'now', 'now')
            """,
            (target_user_id, target_user_id),
        ).lastrowid
        other_invite_id = get_db().execute(
            """
            INSERT INTO invite_codes
            (code, owner_user_id, reward_points, max_uses, used_count, enabled, created_by_admin_id, created_at, updated_at)
            VALUES ('OTHER', ?, 0, NULL, 0, 1, ?, 'now', 'now')
            """,
            (other_user_id, target_user_id),
        ).lastrowid
        get_db().execute(
            """
            INSERT INTO invite_redemptions
            (invite_code_id, inviter_user_id, invitee_user_id, reward_points, created_at)
            VALUES (?, ?, ?, 0, 'now')
            """,
            (owned_invite_id, target_user_id, other_user_id),
        )
        get_db().commit()

        delete_user_cascade(get_db(), target_user_id)
        get_db().commit()

        assert get_db().execute("SELECT id FROM users WHERE id = ?", (target_user_id,)).fetchone() is None
        assert get_db().execute("SELECT id FROM canvas_conversations WHERE user_id = ?", (target_user_id,)).fetchone() is None
        assert get_db().execute("SELECT id FROM canvas_messages WHERE conversation_id = ?", (conversation_id,)).fetchone() is None
        assert get_db().execute("SELECT id FROM invite_codes WHERE id = ?", (owned_invite_id,)).fetchone() is None
        assert get_db().execute("SELECT id FROM invite_redemptions WHERE invite_code_id = ?", (owned_invite_id,)).fetchone() is None

        other_invite = get_db().execute("SELECT owner_user_id, created_by_admin_id FROM invite_codes WHERE id = ?", (other_invite_id,)).fetchone()
        assert other_invite["owner_user_id"] == other_user_id
        assert other_invite["created_by_admin_id"] is None


def test_delete_user_cascade_handles_user_without_records(app):
    with app.app_context():
        target_user_id = _create_user("delete-empty")
        get_db().commit()

        delete_user_cascade(get_db(), target_user_id)
        get_db().commit()

        assert get_db().execute("SELECT id FROM users WHERE id = ?", (target_user_id,)).fetchone() is None


def test_bulk_update_invites_scopes_to_existing_ids(app):
    with app.app_context():
        admin_id = _create_admin()
        owner_id = _create_user("invite-owner")
        first_invite = get_db().execute(
            """
            INSERT INTO invite_codes
            (code, owner_user_id, reward_points, max_uses, used_count, enabled, created_by_admin_id, created_at, updated_at)
            VALUES ('BULK1', ?, 0, NULL, 0, 0, ?, 'now', 'now')
            """,
            (owner_id, admin_id),
        ).lastrowid
        second_invite = get_db().execute(
            """
            INSERT INTO invite_codes
            (code, owner_user_id, reward_points, max_uses, used_count, enabled, created_by_admin_id, created_at, updated_at)
            VALUES ('BULK2', ?, 0, NULL, 0, 0, ?, 'now', 'now')
            """,
            (owner_id, admin_id),
        ).lastrowid
        get_db().commit()

    with app.test_client() as client:
        _login(client, admin_id)
        enable_response = client.post(
            "/admin/invites/bulk",
            data={"action": "enable", "invite_ids[]": [str(first_invite), str(second_invite), "999999"]},
        )
        delete_response = client.post(
            "/admin/invites/bulk",
            data={"action": "delete", "invite_ids[]": [str(second_invite), "999999"]},
        )

    assert enable_response.status_code == 302
    assert delete_response.status_code == 302
    with app.app_context():
        first = get_db().execute("SELECT enabled FROM invite_codes WHERE id = ?", (first_invite,)).fetchone()
        second = get_db().execute("SELECT id FROM invite_codes WHERE id = ?", (second_invite,)).fetchone()
        assert first["enabled"] == 1
        assert second is None


def test_bulk_update_users_preserves_current_and_last_admin(app):
    with app.app_context():
        admin_id = _create_admin()
        other_admin_id = _create_admin("other-admin")
        target_user_id = _create_user("bulk-delete-user")
        get_db().commit()

    with app.test_client() as client:
        _login(client, admin_id)
        current_admin_response = client.post(
            "/admin/users/bulk",
            data={"action": "delete", "user_ids[]": [str(admin_id), str(target_user_id)]},
        )
        delete_user_response = client.post(
            "/admin/users/bulk",
            data={"action": "delete", "user_ids[]": [str(target_user_id), "999999"]},
        )
        other_admin_response = client.post(
            "/admin/users/bulk",
            data={"action": "delete", "user_ids[]": [str(other_admin_id)]},
        )

    assert current_admin_response.status_code == 400
    assert delete_user_response.status_code == 302
    assert other_admin_response.status_code == 302
    with app.app_context():
        assert get_db().execute("SELECT id FROM users WHERE id = ?", (admin_id,)).fetchone() is not None
        assert get_db().execute("SELECT id FROM users WHERE id = ?", (target_user_id,)).fetchone() is None
        assert get_db().execute("SELECT id FROM users WHERE id = ?", (other_admin_id,)).fetchone() is None

