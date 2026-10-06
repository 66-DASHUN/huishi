from pathlib import Path

import pytest

from app import create_app
from huishi.db import get_db, init_db
from huishi.providers import save_provider


@pytest.fixture()
def app(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("HUISHI_DATABASE", str(tmp_path / "test.sqlite3"))
    monkeypatch.setenv("HUISHI_OUTPUT_DIR", str(tmp_path / "uploads"))
    app = create_app(testing=True)
    with app.app_context():
        init_db()
    return app


def _login_user(app, client, *, role: str = "user", username: str = "audio-user") -> int:
    with app.app_context():
        cursor = get_db().execute(
            """
            INSERT INTO users (username, email, password_hash, role, email_verified, points, created_at)
            VALUES (?, '', 'hash', ?, 1, 40, 'now')
            """,
            (username, role),
        )
        get_db().commit()
        user_id = int(cursor.lastrowid)
    with client.session_transaction() as session:
        session["user_id"] = user_id
    return user_id


def test_legacy_estimate_uses_selected_speech_model_price(app):
    with app.app_context():
        save_provider(
            provider_type="audio",
            name="MiniMax 音频",
            base_url="https://api.example.test",
            api_key="audio-key",
            model="speech-2.8-hd",
            api_format="minimax",
            capabilities=["speech", "music"],
            models=[{"id": "speech-2.8-hd", "label": "MiniMax Speech 2.8 HD", "media_type": "speech"}],
            enabled=True,
            priority=10,
        )
        get_db().execute(
            "INSERT INTO pricing_rules (mode, model, resolution, points_per_image, enabled, media_type, duration_tier) VALUES (?, ?, ?, ?, 1, ?, '')",
            ("speech", "speech-2.8-hd", "default", 9, "speech"),
        )
        get_db().commit()

    with app.test_client() as client:
        _login_user(app, client)
        response = client.get("/api/estimate?media_type=speech&mode=speech&model=speech-2.8-hd&count=1")

    assert response.status_code == 200
    assert response.get_json()["cost"] == 9


def test_settings_page_lists_audio_provider_and_add_action(app):
    with app.app_context():
        save_provider(
            provider_type="audio",
            name="MiniMax 音频",
            base_url="https://api.example.test",
            api_key="audio-key",
            model="speech-2.8-hd",
            api_format="minimax",
            capabilities=["speech", "music"],
            models=[
                {"id": "speech-2.8-hd", "label": "MiniMax Speech 2.8 HD", "media_type": "speech"},
                {"id": "music-3.0", "label": "MiniMax Music 3.0", "media_type": "music"},
            ],
            enabled=True,
            priority=10,
        )
        get_db().commit()

    with app.test_client() as client:
        _login_user(app, client, role="admin", username="admin-audio")
        response = client.get("/admin/config/settings")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "MiniMax 音频" in body
    # 音频渠道不再有独立的「新增音频」按钮：统一走渠道弹窗的
    # 「模型类型」下拉（语音合成 / 音乐生成）。
    assert 'value="speech"' in body
    assert 'value="music"' in body
    assert "语音合成" in body
    assert "音乐生成" in body


def test_audio_provider_form_uses_checked_capabilities(app):
    from huishi.routes_workspace import parse_provider_form

    with app.app_context(), app.test_request_context(
        "/settings/providers",
        method="POST",
        data={
            "provider_type": "audio",
            "name": "MiniMax speech only",
            "base_url": "https://api.example.test",
            "api_key": "audio-key",
            "model": "speech-2.8-hd",
            "api_format": "minimax",
            "capabilities_json": '["audio", "speech", "music"]',
            "audio_capabilities": "speech",
            "models_json": '[{"id":"speech-2.8-hd","label":"Speech","media_type":"speech"}]',
            "enabled": "1",
        },
    ):
        parsed = parse_provider_form()

    assert parsed["capabilities"] == ["audio", "speech"]


def test_audio_provider_form_preserves_endpoint_paths(app):
    from huishi.routes_workspace import parse_provider_form

    with app.app_context(), app.test_request_context(
        "/settings/providers",
        method="POST",
        data={
            "provider_type": "audio",
            "name": "Custom audio gateway",
            "base_url": "https://api.example.test",
            "api_key": "audio-key",
            "model": "speech-2.8-hd",
            "api_format": "minimax",
            "audio_capabilities": ["speech", "music"],
            "speech_path": "/custom/speech",
            "music_path": "/custom/music",
            "models_json": "[]",
            "enabled": "1",
        },
    ):
        parsed = parse_provider_form()

    assert parsed["settings"]["speech_path"] == "/custom/speech"
    assert parsed["settings"]["music_path"] == "/custom/music"


def test_audio_provider_generate_test_returns_playable_audio(app, monkeypatch):
    with app.app_context():
        provider_id = save_provider(
            provider_type="audio",
            name="MiniMax speech test",
            base_url="https://api.example.test",
            api_key="audio-key",
            model="speech-2.8-hd",
            api_format="minimax",
            capabilities=["speech"],
            models=[{"id": "speech-2.8-hd", "label": "Speech", "media_type": "speech"}],
            enabled=True,
            priority=10,
        )
        get_db().commit()

    def fake_generate_speech(_provider, _request):
        return {"content": b"fake-audio", "mime_type": "audio/mpeg", "extension": "mp3", "model": "speech-2.8-hd"}

    monkeypatch.setattr("huishi.audio_api.generate_speech", fake_generate_speech)

    with app.test_client() as client:
        _login_user(app, client, role="admin", username="admin-audio-test")
        response = client.post(
            f"/settings/providers/{provider_id}/test",
            data={"test_mode": "generate", "test_model": "speech-2.8-hd"},
            headers={"Accept": "application/json"},
        )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["audio"].endswith(".mp3")


def test_canvas_asset_library_includes_audio_records(app):
    from huishi.canvas_session import issue_canvas_session_token
    from huishi.providers import save_canvas_setting
    from huishi.records import create_record

    with app.app_context():
        save_canvas_setting("canvas_app_url", "http://127.0.0.1:3000")
        cursor = get_db().execute(
            "INSERT INTO users (username, email, password_hash, role, email_verified, points, created_at) VALUES (?, '', 'hash', 'admin', 1, 40, 'now')",
            ("audio-library-user",),
        )
        user_id = int(cursor.lastrowid)
        user = get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        token, _ = issue_canvas_session_token(user)
        upload_dir = app.config["OUTPUT_DIR"]
        upload_dir.mkdir(parents=True, exist_ok=True)
        (upload_dir / "library.mp3").write_bytes(b"audio")
        create_record(
            user_id=user_id,
            prompt="library audio",
            image_path="/static/uploads/library.mp3",
            mode="speech",
            ratio="auto",
            resolution="default",
            actual_size="",
            quality="auto",
            output_format="mp3",
            count=1,
            model_source="speech-2.8-hd",
            elapsed_seconds=0.1,
            points_charged=2,
            asset_source="audio",
            media_type="speech",
            mime_type="audio/mpeg",
            image_paths=["/static/uploads/library.mp3"],
        )
        get_db().commit()

    with app.test_client() as client:
        response = client.post(
            "/api/canvas/assets/library",
            json={"token": token},
            headers={"Origin": "http://127.0.0.1:3000"},
        )

    assert response.status_code == 200
    assert response.get_json()["assets"][0]["source"] == "audio"
