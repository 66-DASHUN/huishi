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
    app.config["CSRF_PROTECT_TESTING"] = True
    with app.app_context():
        init_db()
        get_db().execute(
            """
            INSERT INTO users (username, email, password_hash, role, points, email_verified, created_at)
            VALUES ('csrf-user', 'csrf@example.com', 'not-a-real-hash', 'user', 0, 1, 'now')
            """
        )
        get_db().commit()
    return app


def test_login_post_without_csrf_token_is_rejected(app):
    with app.test_client() as client:
        response = client.post(
            "/login",
            data={"email": "csrf@example.com", "password": "wrong-password"},
            headers={"X-Requested-With": "fetch", "Accept": "application/json"},
        )

    assert response.status_code == 403
    assert response.get_json()["error"]


def test_landing_page_exposes_csrf_token_for_auth_fetches(app):
    with app.test_client() as client:
        response = client.get("/")

    assert response.status_code == 200
    assert b"window.__HUISHI_CSRF_TOKEN__" in response.data


def test_home_auth_forms_send_csrf_token():
    source = Path("static/js/home.js").read_text(encoding="utf-8")

    assert "const CSRF_TOKEN = window.__HUISHI_CSRF_TOKEN__ || \"\";" in source
    assert '"X-CSRF-Token": CSRF_TOKEN' in source
    assert source.count('name="csrf_token" value={CSRF_TOKEN}') >= 3
