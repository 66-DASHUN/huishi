"""Regression tests for how the canvas session token travels in the embed URL.

The token is a signed bearer credential. It must not appear in the query
string, because the query string reaches the server and therefore the nginx
access log, and it also travels in the Referer header and the browser-history
entry for the embed URL. It belongs in the URL fragment, which is never sent
to the server.
"""
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from app import create_app
from huishi.db import get_db


@pytest.fixture()
def app(tmp_path: Path):
    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "test.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"
    app.config["CANVAS_APP_URL"] = "https://canvas.example"
    with app.app_context():
        from huishi.db import init_db

        init_db()
    return app


def create_user(role: str = "user", username: str = "token-user") -> int:
    cursor = get_db().execute(
        """
        INSERT INTO users (username, email, password_hash, role, email_verified, points, created_at)
        VALUES (?, '', 'hash', ?, 1, 20, 'now')
        """,
        (username, role),
    )
    get_db().commit()
    return int(cursor.lastrowid)


def build_embed_url(app) -> str:
    from huishi.routes_workspace import build_canvas_embed_url

    with app.test_request_context("/canvas"):
        token, _ = _issue(app)
        return build_canvas_embed_url("https://canvas.example", token)


def _issue(app):
    from huishi.canvas_session import issue_canvas_session_token

    user = get_db().execute("SELECT * FROM users ORDER BY id LIMIT 1").fetchone()
    return issue_canvas_session_token(user)


def test_embed_url_keeps_session_token_out_of_the_query_string(app):
    with app.app_context():
        create_user()
        url = build_embed_url(app)

    parts = urlsplit(url)
    query = parse_qs(parts.query)

    assert "host_session_token" not in query, (
        f"session token must not travel in the query string (it reaches the access log): {url}"
    )
    fragment = parse_qs(parts.fragment)
    assert fragment.get("host_session_token"), f"session token must be carried in the URL fragment: {url}"


def test_embed_url_still_carries_required_host_parameters(app):
    with app.app_context():
        create_user()
        url = build_embed_url(app)

    query = parse_qs(urlsplit(url).query)
    for key in (
        "host_mode",
        "host_session_verify_url",
        "host_generate_url",
        "host_chat_url",
        "host_projects_url",
        "host_origin",
        "host_user_key_url",
    ):
        assert key in query, f"missing host parameter {key} in {url}"


def test_user_key_url_does_not_embed_the_session_token(app):
    with app.app_context():
        create_user()
        url = build_embed_url(app)

    query = parse_qs(urlsplit(url).query)
    user_key_url = query["host_user_key_url"][0]
    assert "token=" not in user_key_url, (
        f"host_user_key_url must not repeat the session token; it is sent via the X-Canvas-Session header: {user_key_url}"
    )
