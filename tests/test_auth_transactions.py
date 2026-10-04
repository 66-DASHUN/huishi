from __future__ import annotations

from pathlib import Path

import pytest

from app import create_app
from huishi.db import get_db, init_db


@pytest.fixture()
def app(tmp_path: Path):
    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "test.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"
    with app.app_context():
        init_db()
    return app


def test_verify_email_link_updates_user_and_logs_in(app):
    with app.app_context():
        user_id = get_db().execute(
            """
            INSERT INTO users
            (username, email, password_hash, role, email_verified, email_verification_code, email_verification_token, points, created_at)
            VALUES ('verify-user', 'verify@example.com', 'hash', 'user', 0, '123456', 'token-123', 0, 'now')
            """
        ).lastrowid
        get_db().commit()

    with app.test_client() as client:
        response = client.get("/verify-email-link?token=token-123")

        with client.session_transaction() as session:
            session_user_id = session.get("user_id")

    assert response.status_code == 302
    assert session_user_id == user_id

    with app.app_context():
        row = get_db().execute(
            """
            SELECT email_verified, email_verification_code, email_verification_token, email_verified_at
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        ).fetchone()

        assert row["email_verified"] == 1
        assert row["email_verification_code"] == ""
        assert row["email_verification_token"] == ""
        assert row["email_verified_at"] != ""


def test_verify_email_link_does_not_login_when_transaction_fails(app, monkeypatch):
    with app.app_context():
        get_db().execute(
            """
            INSERT INTO users
            (username, email, password_hash, role, email_verified, email_verification_code, email_verification_token, points, created_at)
            VALUES ('verify-fail-user', 'verify-fail@example.com', 'hash', 'user', 0, '123456', 'token-fail', 0, 'now')
            """
        )
        get_db().commit()

    def fail_transaction():
        raise RuntimeError("transaction unavailable")

    monkeypatch.setattr("huishi.auth.transaction", fail_transaction)

    with app.test_client() as client:
        with pytest.raises(RuntimeError, match="transaction unavailable"):
            client.get("/verify-email-link?token=token-fail")

        with client.session_transaction() as session:
            assert session.get("user_id") is None
