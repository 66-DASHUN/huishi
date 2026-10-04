from __future__ import annotations

from pathlib import Path

import pytest

from app import create_app
from huishi.db import get_db, init_db
from huishi.invites import create_invite_code, redeem_invite


@pytest.fixture()
def app(tmp_path: Path):
    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "test.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"
    with app.app_context():
        init_db()
    return app


def _create_user(username: str, *, points: int = 0) -> int:
    cursor = get_db().execute(
        """
        INSERT INTO users (username, email, password_hash, role, email_verified, points, created_at)
        VALUES (?, '', 'hash', 'user', 1, ?, 'now')
        """,
        (username, points),
    )
    return int(cursor.lastrowid)


def test_redeem_invite_rewards_both_users_and_records_redemption(app):
    with app.app_context():
        inviter_id = _create_user("inviter")
        invitee_id = _create_user("invitee")
        code = create_invite_code(owner_user_id=inviter_id, reward_points=7, code="WELCOME7")
        invite = get_db().execute("SELECT * FROM invite_codes WHERE code = ?", (code,)).fetchone()

        redeem_invite(invite["id"], invitee_id)
        get_db().commit()

        inviter = get_db().execute("SELECT points FROM users WHERE id = ?", (inviter_id,)).fetchone()
        invitee = get_db().execute("SELECT points FROM users WHERE id = ?", (invitee_id,)).fetchone()
        updated_invite = get_db().execute("SELECT used_count FROM invite_codes WHERE id = ?", (invite["id"],)).fetchone()
        redemption = get_db().execute("SELECT reward_points FROM invite_redemptions WHERE invitee_user_id = ?", (invitee_id,)).fetchone()

    assert inviter["points"] == 7
    assert invitee["points"] == 7
    assert updated_invite["used_count"] == 1
    assert redemption["reward_points"] == 7


def test_registration_style_invite_failure_rolls_back_user_and_invite_changes(app):
    with app.app_context():
        inviter_id = _create_user("inviter")
        code = create_invite_code(owner_user_id=inviter_id, reward_points=5, code="LIMITED1", max_uses=1)
        invite = get_db().execute("SELECT * FROM invite_codes WHERE code = ?", (code,)).fetchone()
        first_invitee_id = _create_user("first-invitee")
        redeem_invite(invite["id"], first_invitee_id)
        get_db().commit()

        db = get_db()
        with pytest.raises(ValueError):
            cursor = db.execute(
                """
                INSERT INTO users (username, email, password_hash, role, email_verified, points, created_at)
                VALUES ('second-invitee', '', 'hash', 'user', 1, 0, 'now')
                """
            )
            redeem_invite(invite["id"], cursor.lastrowid)
            db.commit()

        db.rollback()

        second_user = db.execute("SELECT id FROM users WHERE username = 'second-invitee'").fetchone()
        updated_invite = db.execute("SELECT used_count FROM invite_codes WHERE id = ?", (invite["id"],)).fetchone()
        redemption_count = db.execute("SELECT COUNT(*) AS value FROM invite_redemptions WHERE invite_code_id = ?", (invite["id"],)).fetchone()

    assert second_user is None
    assert updated_invite["used_count"] == 1
    assert redemption_count["value"] == 1
