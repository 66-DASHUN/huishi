from __future__ import annotations

from pathlib import Path

import pytest

from app import create_app
from huishi.canvas_session import issue_canvas_session_token
from huishi.db import get_db
from huishi.db_backend import PostgreSQLConnection


@pytest.fixture()
def app(tmp_path: Path):
    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "test.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"
    app.config["CANVAS_APP_URL"] = "http://127.0.0.1:3000"
    with app.app_context():
        from huishi.db import init_db

        init_db()
    return app


def test_canvas_chat_messages_enforce_server_owned_creative_scope():
    from huishi import routes_workspace

    assert hasattr(routes_workspace, "_canvas_scoped_chat_messages")
    messages = routes_workspace._canvas_scoped_chat_messages(
        [
            {"role": "system", "content": "client tool rules"},
            {"role": "user", "content": "hello"},
        ]
    )

    assert [item["role"] for item in messages].count("system") == 1
    assert messages[0]["role"] == "system"
    assert "\u7ed8\u4e16\u521b\u4f5c Agent" in messages[0]["content"]
    assert "\u751f\u56fe\u8bbe\u8ba1" in messages[0]["content"]
    assert "\u660e\u663e\u65e0\u5173" in messages[0]["content"]
    assert "\u4e0d\u8c03\u7528\u4efb\u4f55\u753b\u5e03\u5de5\u5177" in messages[0]["content"]
    assert "client tool rules" in messages[0]["content"]


def test_canvas_chat_messages_convert_reference_images_to_text_for_prompt_provider():
    from huishi import routes_workspace

    messages = routes_workspace._canvas_scoped_chat_messages(
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "reference 1 (id: image-1, type: image)"},
                    {"type": "text", "text": "reference 2 (id: image-2, type: image)"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,BBBB"}},
                ],
            }
        ]
    )

    assert messages[1]["content"] == (
        "reference 1 (id: image-1, type: image)\n"
        "reference 2 (id: image-2, type: image)"
    )
    assert "image_url" not in messages[1]["content"]


def test_canvas_chat_error_message_hides_provider_deserialization_details():
    from huishi import routes_workspace

    message = routes_workspace._canvas_chat_error_message(
        RuntimeError("unknown variant `image_url`, expected `text`; invalid_request_error")
    )

    assert message == "\u5f53\u524d\u6587\u672c\u6a21\u578b\u4e0d\u652f\u6301\u76f4\u63a5\u8bc6\u522b\u53c2\u8003\u56fe\uff0c\u5df2\u6539\u7528\u753b\u5e03\u4e2d\u7684\u53c2\u8003\u4fe1\u606f\u3002"
    assert "image_url" not in message
    assert "invalid_request_error" not in message


def _create_user(username: str = "canvas-user") -> int:
    cursor = get_db().execute(
        """
        INSERT INTO users (username, email, password_hash, role, email_verified, points, created_at)
        VALUES (?, '', 'hash', 'user', 1, 20, 'now')
        """,
        (username,),
    )
    get_db().commit()
    return int(cursor.lastrowid)


def _issue_token(user_id: int) -> str:
    user = get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    token, _ = issue_canvas_session_token(user)
    return token


def test_init_db_creates_canvas_conversation_tables(app):
    with app.app_context():
        db = get_db()
        if isinstance(db, PostgreSQLConnection):
            rows = db.execute(
                """
                SELECT table_name AS name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN ('canvas_conversations', 'canvas_messages')
                """
            ).fetchall()
        else:
            rows = db.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table' AND name IN ('canvas_conversations', 'canvas_messages')
                """
            ).fetchall()
        tables = {row["name"] for row in rows}

    assert tables == {"canvas_conversations", "canvas_messages"}


def test_canvas_conversation_routes_create_list_archive_and_read_messages(app):
    with app.app_context():
        user_id = _create_user("owner")
        other_user_id = _create_user("other")
        token = _issue_token(user_id)
        now = "2026-07-04T00:00:00+00:00"
        other_cursor = get_db().execute(
            """
            INSERT INTO canvas_conversations (user_id, title, archived, created_at, updated_at)
            VALUES (?, 'other conversation', 0, ?, ?)
            """,
            (other_user_id, now, now),
        )
        get_db().commit()
        other_conversation_id = int(other_cursor.lastrowid)

    with app.test_client() as client:
        created = client.post(
            "/api/canvas/conversations",
            json={"token": token, "title": "first chat"},
            headers={"Origin": "http://127.0.0.1:3000"},
        )

        assert created.status_code == 200
        created_payload = created.get_json()
        conversation = created_payload["conversation"]
        conversation_id = conversation["id"]
        assert created_payload["ok"] is True
        assert conversation["title"] == "first chat"
        assert created.headers["Access-Control-Allow-Origin"] == "http://127.0.0.1:3000"

        listed = client.open(
            "/api/canvas/conversations",
            method="GET",
            json={"token": token},
            headers={"Origin": "http://127.0.0.1:3000"},
        )
        list_payload = listed.get_json()
        assert listed.status_code == 200
        assert [item["id"] for item in list_payload["conversations"]] == [conversation_id]

        with app.app_context():
            get_db().execute(
                """
                INSERT INTO canvas_messages (conversation_id, role, content, tool_calls, created_at)
                VALUES (?, 'user', 'hello', '[]', ?)
                """,
                (conversation_id, now),
            )
            get_db().commit()

        messages = client.open(
            f"/api/canvas/conversations/{conversation_id}/messages",
            method="GET",
            json={"token": token},
            headers={"Origin": "http://127.0.0.1:3000"},
        )
        messages_payload = messages.get_json()
        assert messages.status_code == 200
        assert messages_payload["messages"][0]["role"] == "user"
        assert messages_payload["messages"][0]["content"] == "hello"
        assert messages_payload["messages"][0]["tool_calls"] == "[]"

        foreign_messages = client.open(
            f"/api/canvas/conversations/{other_conversation_id}/messages",
            method="GET",
            json={"token": token},
            headers={"Origin": "http://127.0.0.1:3000"},
        )
        assert foreign_messages.status_code == 404

        archived = client.patch(
            f"/api/canvas/conversations/{conversation_id}",
            json={"token": token, "archived": True, "title": "renamed"},
            headers={"Origin": "http://127.0.0.1:3000"},
        )
        assert archived.status_code == 200
        assert archived.get_json() == {"ok": True}

        listed_after_archive = client.open(
            "/api/canvas/conversations",
            method="GET",
            json={"token": token},
            headers={"Origin": "http://127.0.0.1:3000"},
        )
        assert listed_after_archive.get_json()["conversations"] == []

        with app.app_context():
            row = get_db().execute(
                "SELECT title, archived FROM canvas_conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
            assert row["title"] == "renamed"
            assert row["archived"] == 1


def test_canvas_text_chat_persists_non_stream_messages(app, monkeypatch):
    class FakeToolCall:
        def model_dump(self):
            return {"id": "call-1", "type": "function", "function": {"name": "draw", "arguments": "{}"}}

    class FakeMessage:
        content = "assistant reply"
        tool_calls = [FakeToolCall()]

    class FakeChoice:
        message = FakeMessage()

    class FakeResult:
        choices = [FakeChoice()]

        def model_dump(self):
            return {"choices": [{"message": {"content": "assistant reply"}}]}

    class FakeCompletions:
        def create(self, **kwargs):
            assert kwargs["stream"] is False
            return FakeResult()

    class FakeChat:
        completions = FakeCompletions()

    class FakeOpenAI:
        chat = FakeChat()

        def __init__(self, **kwargs):
            pass

    monkeypatch.setattr(
        "huishi.providers.prompt_provider_candidates",
        lambda: [{"api_key": "key", "base_url": "http://example.test", "model": "chat-model"}],
    )
    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)

    with app.app_context():
        user_id = _create_user("chat-owner")
        token = _issue_token(user_id)
        now = "2026-07-04T00:00:00+00:00"
        cursor = get_db().execute(
            """
            INSERT INTO canvas_conversations (user_id, title, archived, created_at, updated_at)
            VALUES (?, 'chat', 0, ?, ?)
            """,
            (user_id, now, now),
        )
        conversation_id = int(cursor.lastrowid)
        get_db().commit()

    with app.test_client() as client:
        response = client.post(
            "/api/canvas/text-chat",
            json={
                "token": token,
                "conversation_id": conversation_id,
                "stream": False,
                "messages": [
                    {"role": "system", "content": "system"},
                    {"role": "user", "content": "first"},
                    {"role": "user", "content": "last user message"},
                ],
            },
            headers={"Origin": "http://127.0.0.1:3000"},
        )

    assert response.status_code == 200
    with app.app_context():
        rows = get_db().execute(
            """
            SELECT role, content, tool_calls
            FROM canvas_messages
            WHERE conversation_id = ?
            ORDER BY id ASC
            """,
            (conversation_id,),
        ).fetchall()
        conversation = get_db().execute(
            "SELECT updated_at FROM canvas_conversations WHERE id = ?",
            (conversation_id,),
        ).fetchone()

    assert [(row["role"], row["content"]) for row in rows] == [
        ("user", "last user message"),
        ("assistant", "assistant reply"),
    ]
    assert rows[1]["tool_calls"] == '[{"id": "call-1", "type": "function", "function": {"name": "draw", "arguments": "{}"}}]'
    assert conversation["updated_at"] != now


def test_canvas_text_chat_rejects_incomplete_prompt_provider(app, monkeypatch):
    monkeypatch.setattr(
        "huishi.providers.prompt_provider_candidates",
        lambda: [{"api_key": "", "base_url": "http://example.test", "model": "chat-model"}],
    )

    with app.app_context():
        user_id = _create_user("chat-owner-missing-key")
        token = _issue_token(user_id)

    with app.test_client() as client:
        response = client.post(
            "/api/canvas/text-chat",
            json={"token": token, "stream": False, "messages": [{"role": "user", "content": "hello"}]},
            headers={"Origin": "http://127.0.0.1:3000"},
        )

    assert response.status_code == 400
    data = response.get_json()
    assert data["ok"] is False
    assert "Prompt Provider 配置不完整" in data["error"]
    assert "API Key" in data["error"]


def test_canvas_text_chat_options_preflight(app):
    with app.test_client() as client:
        response = client.options(
            "/api/canvas/text-chat",
            headers={
                "Origin": "http://127.0.0.1:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type",
            },
        )

    assert response.status_code in {200, 204}
    assert response.headers["Access-Control-Allow-Origin"] == "http://127.0.0.1:3000"
    assert "POST" in response.headers["Access-Control-Allow-Methods"]


def test_canvas_text_chat_post_is_token_protected_not_csrf_blocked(app):
    app.config["CSRF_PROTECT_TESTING"] = True
    with app.test_client() as client:
        response = client.post(
            "/api/canvas/text-chat",
            json={"token": "bad-token", "stream": False, "messages": [{"role": "user", "content": "hi"}]},
            headers={"Origin": "http://127.0.0.1:3000"},
        )

    assert response.status_code == 401
    assert response.get_json()["error"] != "CSRF token 缺失"
    assert response.headers["Access-Control-Allow-Origin"] == "http://127.0.0.1:3000"
