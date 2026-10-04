from __future__ import annotations

import json

import pytest

from app import create_app
from huishi.canvas_session import issue_canvas_session_token
from huishi.billing import calculate_cost
from huishi.db import get_db, init_db
from huishi.providers import (
    audio_model_options,
    image_model_label,
    list_providers,
    normalize_provider,
    normalize_provider_api_format,
    normalize_provider_capabilities,
    save_provider,
    selectable_music_models,
    selectable_speech_models,
    validate_provider_type,
    video_model_options,
)


@pytest.fixture
def app(tmp_path):
    application = create_app(testing=True)
    application.config["DATABASE"] = tmp_path / "test.sqlite3"
    application.config["OUTPUT_DIR"] = tmp_path / "uploads"
    with application.app_context():
        init_db()
    return application


def test_video_provider_type_and_protocols_are_supported(app):
    assert validate_provider_type("video") == "video"
    assert normalize_provider_api_format("grok", "video") == "grok"
    assert normalize_provider_api_format("seedance", "video") == "seedance"
    assert normalize_provider_api_format("minimax", "video") == "minimax"


def test_audio_provider_type_and_capabilities_are_supported(app):
    assert validate_provider_type("audio") == "audio"
    assert normalize_provider_api_format("minimax", "audio") == "minimax"
    assert normalize_provider_capabilities(["speech", "music"], "audio") == ["audio", "speech", "music"]


def test_minimax_audio_catalog_has_separate_speech_and_music_models():
    speech = audio_model_options("minimax", capability="speech")
    music = audio_model_options("minimax", capability="music")

    assert {item["id"] for item in speech} >= {"speech-2.8-hd", "speech-2.8-turbo"}
    assert {item["id"] for item in music} >= {"music-3.0", "music-2.6", "music-cover"}
    assert not ({item["id"] for item in speech} & {item["id"] for item in music})


def test_model_label_resolves_audio_and_video_catalog_names():
    from huishi.providers import model_label

    assert model_label("speech-2.8-hd") == "MiniMax Speech 2.8 HD"
    assert model_label("grok-imagine-video") == "grok-imagine"


def test_video_model_catalog_has_named_official_presets():
    options = video_model_options("grok")
    assert {item["id"] for item in options} >= {"grok-imagine-video"}
    assert any(item["label"] == "grok-imagine" for item in options)


def test_save_provider_round_trips_capabilities_models_and_settings(app):
    with app.app_context():
        init_db()
        provider_id = save_provider(
            provider_type="video",
            name="MiniMax 3",
            base_url="https://api.minimaxi.com",
            api_key="test-video-key",
            model="MiniMax-Hailuo-3.0",
            api_format="minimax",
            priority=20,
            enabled=True,
            capabilities=["video"],
            models=[{"id": "MiniMax-Hailuo-3.0", "label": "MiniMax 3"}],
            settings={"create_path": "/v1/video_generation", "poll_interval": 4},
        )
        provider = next(item for item in list_providers("video") if item["id"] == provider_id)
        assert provider["capabilities"] == ["video"]
        assert provider["models"] == [{"id": "MiniMax-Hailuo-3.0", "label": "MiniMax 3"}]
        assert provider["settings"]["poll_interval"] == 4
        assert provider["api_key"] == "test-video-key"


def test_video_pricing_is_selected_before_default_image_rule(app):
    with app.app_context():
        init_db()
        db = get_db()
        db.execute(
            "INSERT INTO pricing_rules (mode, model, resolution, points_per_image, enabled, media_type, duration_tier) VALUES (?, ?, ?, ?, 1, ?, ?)",
            ("video", "grok-imagine-video", "6s", 17, "video", "6s"),
        )
        db.commit()
        assert calculate_cost("video", "6s", 1, model="grok-imagine-video") == 17


def test_legacy_image_provider_normalization_has_media_defaults(app):
    with app.app_context():
        init_db()
        db = get_db()
        db.execute(
            "INSERT INTO api_providers (provider_type, name, base_url, api_key, model, api_format, resolutions, priority, enabled, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("image", "legacy", "https://example.com/v1", "", "gpt-image-2", "openai", "[\"1K\"]", 1, 1, "now", "now"),
        )
        db.commit()
        provider = list_providers("image")[0]
        assert provider["capabilities"] == ["image"]
        assert provider["models"]
        assert image_model_label("gpt-image-2") == "GPT Image 2"


def test_canvas_video_task_route_uses_configured_provider_and_returns_task(app, monkeypatch):
    from huishi.routes_workspace import enqueue_generation_task

    monkeypatch.setattr("huishi.routes_workspace.enqueue_generation_task", lambda *args, **kwargs: None)
    app.config["CANVAS_APP_URL"] = "http://127.0.0.1:3000"
    with app.app_context():
        user_id = int(get_db().execute(
            "INSERT INTO users (username, email, password_hash, role, email_verified, points, created_at) VALUES (?, '', 'hash', 'user', 1, 100, 'now') RETURNING id",
            ("video-user",),
        ).fetchone()["id"])
        token, _ = issue_canvas_session_token(dict(get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()))
        save_provider(
            provider_type="video",
            name="Grok Video",
            base_url="https://api.x.ai/v1",
            api_key="test-key",
            model="grok-imagine-video",
            api_format="grok",
            priority=1,
            enabled=True,
        )
        get_db().execute(
            "INSERT INTO pricing_rules (mode, model, resolution, points_per_image, enabled, media_type, duration_tier) VALUES ('video', 'grok-imagine-video', '720p', 12, 1, 'video', '6s')"
        )
        get_db().commit()
    with app.test_client() as client:
        preflight = client.options(
            "/api/video/tasks/1/content",
            headers={"Origin": "http://127.0.0.1:3000", "Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "X-Canvas-Session"},
        )
        assert preflight.status_code == 204
        assert preflight.headers.get("Access-Control-Allow-Origin") == "http://127.0.0.1:3000"
        response = client.post(
            "/api/video/tasks",
            json={"prompt": "a short film", "model": "grok-imagine-video", "duration_seconds": 6},
            headers={"Origin": "http://127.0.0.1:3000", "X-Canvas-Session": token},
        )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["task"]["media_type"] == "video"


def test_canvas_audio_task_route_accepts_music_media_type(app, monkeypatch):
    from huishi.routes_workspace import enqueue_generation_task

    monkeypatch.setattr("huishi.routes_workspace.enqueue_generation_task", lambda *args, **kwargs: None)
    app.config["CANVAS_APP_URL"] = "http://127.0.0.1:3000"
    with app.app_context():
        user_id = int(get_db().execute(
            "INSERT INTO users (username, email, password_hash, role, email_verified, points, created_at) VALUES (?, '', 'hash', 'user', 1, 100, 'now') RETURNING id",
            ("music-user",),
        ).fetchone()["id"])
        token, _ = issue_canvas_session_token(dict(get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()))
        provider_id = save_provider(
            provider_type="audio",
            name="MiniMax Music",
            base_url="https://api.minimaxi.com",
            api_key="test-key",
            model="music-3.0",
            api_format="minimax",
            priority=1,
            enabled=True,
            capabilities=["music"],
            models=[{"id": "music-3.0", "label": "MiniMax Music 3.0", "media_type": "music"}],
        )
        get_db().execute(
            "INSERT INTO pricing_rules (mode, model, resolution, points_per_image, enabled, media_type) VALUES ('music', 'music-3.0', 'default', 9, 1, 'music')"
        )
        get_db().commit()
    with app.test_client() as client:
        response = client.post(
            "/api/audio/tasks",
            json={"prompt": "钢琴配乐", "model": "music-3.0", "media_type": "music"},
            headers={"Origin": "http://127.0.0.1:3000", "X-Canvas-Session": token},
        )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["task"]["media_type"] == "music"
    assert payload["task"]["model"] == "music-3.0"
    assert payload["task"]["provider_id"] == provider_id


def test_admin_billing_accepts_speech_and_music_rules(app):
    with app.app_context():
        user_id = int(get_db().execute(
            "INSERT INTO users (username, email, password_hash, role, email_verified, points, created_at) VALUES (?, '', 'hash', 'admin', 1, 100, 'now') RETURNING id",
            ("billing-audio-admin",),
        ).fetchone()["id"])
        get_db().commit()
    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = user_id

    speech = client.post(
        "/admin/config/billing",
        data={
            "action": "create",
            "media_type": "speech",
            "model": "speech-2.8-hd",
            "resolution": "default",
            "points_per_image": "4",
            "csrf_token": "csrf",
        },
    )
    music = client.post(
        "/admin/config/billing",
        data={
            "action": "create",
            "media_type": "music",
            "model": "music-3.0",
            "resolution": "default",
            "points_per_image": "8",
            "csrf_token": "csrf",
        },
    )

    assert speech.status_code == 302
    assert music.status_code == 302
    with app.app_context():
        rows = get_db().execute("SELECT media_type, mode FROM pricing_rules WHERE model IN ('speech-2.8-hd', 'music-3.0') ORDER BY model").fetchall()
    assert [dict(row) for row in rows] == [
        {"media_type": "music", "mode": "music"},
        {"media_type": "speech", "mode": "speech"},
    ]


def test_admin_can_add_video_pricing_rule(app):
    with app.app_context():
        admin = get_db().execute("SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1").fetchone()
        if admin is None:
            get_db().execute(
                "INSERT INTO users (username, email, password_hash, role, email_verified, points, created_at) VALUES ('admin-test', '', 'hash', 'admin', 1, 0, 'now')"
            )
            get_db().commit()
            admin = get_db().execute("SELECT id FROM users WHERE username = 'admin-test'").fetchone()
        client = app.test_client()
        with client.session_transaction() as active_session:
            active_session["user_id"] = int(admin["id"])
            active_session["csrf_token"] = "csrf"
    response = client.post(
        "/admin/config/billing",
        data={"action": "create", "media_type": "video", "model": "MiniMax-Hailuo-3.0", "resolution": "6s", "duration_tier": "6s", "points_per_image": "13", "csrf_token": "csrf"},
    )
    assert response.status_code in {302, 303}
    with app.app_context():
        rule = get_db().execute("SELECT * FROM pricing_rules WHERE media_type = 'video' AND model = 'MiniMax-Hailuo-3.0'").fetchone()
        assert rule["points_per_image"] == 13
