from pathlib import Path

import pytest

from app import create_app
from huishi.db import get_db


@pytest.fixture()
def app(tmp_path: Path):
    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "test.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"
    app.config["CANVAS_SESSION_TTL_SECONDS"] = 600
    with app.app_context():
        from huishi.db import init_db

        init_db()
    return app


def create_user(role: str = "user", username: str = "canvas-user") -> int:
    cursor = get_db().execute(
        """
        INSERT INTO users (username, email, password_hash, role, email_verified, points, created_at)
        VALUES (?, '', 'hash', ?, 1, 20, 'now')
        """,
        (username, role),
    )
    get_db().commit()
    return int(cursor.lastrowid)


def test_canvas_session_ttl_fallback_matches_config_default(app):
    from huishi.canvas_session import canvas_session_ttl_seconds

    with app.app_context():
        app.config.pop("CANVAS_SESSION_TTL_SECONDS", None)

        ttl = canvas_session_ttl_seconds()

    assert ttl == 86400


def test_issue_canvas_session_token_contains_identity_fields(app):
    from huishi.canvas_session import issue_canvas_session_token, verify_canvas_session_token

    with app.app_context():
        user_id = create_user(role="admin", username="root")
        user = get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

        token, expires_at = issue_canvas_session_token(user)
        payload = verify_canvas_session_token(token)

    assert token
    assert expires_at > 0
    assert payload["user_id"] == user_id
    assert payload["username"] == "root"
    assert payload["role"] == "admin"
    assert payload["billing_identity"] == f"user:{user_id}"
    assert "issued_at" in payload
    assert "expires_at" in payload


def test_verify_canvas_session_token_rejects_expired_token(app, monkeypatch):
    from huishi.canvas_session import CanvasSessionError, issue_canvas_session_token, verify_canvas_session_token

    with app.app_context():
        user_id = create_user()
        user = get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        token, _ = issue_canvas_session_token(user)

        monkeypatch.setattr("huishi.canvas_session.time.time", lambda: 10**10)

        with pytest.raises(CanvasSessionError) as exc:
            verify_canvas_session_token(token)

    assert str(exc.value) == "expired"


def test_canvas_verify_endpoint_returns_live_user_context(app):
    from huishi.canvas_session import issue_canvas_session_token
    from huishi.providers import save_canvas_setting

    with app.app_context():
        save_canvas_setting("canvas_app_url", "http://127.0.0.1:3000")
        user_id = create_user(role="admin", username="captain")
        user = get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        token, _ = issue_canvas_session_token(user)
        get_db().commit()

    with app.test_client() as client:
        response = client.post(
            "/api/canvas/session/verify",
            json={},
            headers={'Origin': 'http://127.0.0.1:3000', 'X-Canvas-Session': token},
        )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["authenticated"] is True
    assert payload["user"]["id"] == user_id
    assert payload["user"]["role"] == "admin"
    assert payload["billing_identity"] == f"user:{user_id}"
    assert response.headers["Access-Control-Allow-Origin"] == "http://127.0.0.1:3000"
    assert 'X-Canvas-Session' in response.headers['Access-Control-Allow-Headers']


def test_canvas_verify_returns_stable_deduplicated_enabled_image_models(app):
    from huishi.canvas_session import issue_canvas_session_token
    from huishi.providers import save_canvas_setting, save_provider

    with app.app_context():
        save_canvas_setting("canvas_app_url", "http://127.0.0.1:3000")
        user_id = create_user(username="model-catalog-user")
        user = get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        token, _ = issue_canvas_session_token(user)
        save_provider(
            provider_type="image",
            name="grok-primary",
            base_url="https://grok.example",
            api_key="test-grok-key",
            model="grok-imagine-image-2.0",
            api_format="grok",
            priority=10,
            enabled=True,
            resolutions=["1K", "2K"],
        )
        save_provider(
            provider_type="image",
            name="grok-secondary",
            base_url="https://grok-secondary.example",
            api_key="test-grok-secondary-key",
            model="grok-imagine-image-2.0",
            api_format="grok",
            priority=20,
            enabled=True,
            resolutions=["2K"],
        )
        save_provider(
            provider_type="image",
            name="banana",
            base_url="https://banana.example",
            api_key="test-banana-key",
            model="gemini-3.1-flash-image",
            api_format="banana",
            priority=30,
            enabled=True,
            resolutions=["1K", "2K", "4K"],
        )
        save_provider(
            provider_type="image",
            name="custom-disabled",
            base_url="https://disabled.example",
            api_key="test-disabled-key",
            model="custom-disabled-model",
            priority=1,
            enabled=False,
            resolutions=["1K"],
        )
        get_db().commit()

    with app.test_client() as client:
        response = client.post(
            "/api/canvas/session/verify",
            json={},
            headers={"Origin": "http://127.0.0.1:3000", "X-Canvas-Session": token},
        )

    assert response.status_code == 200
    assert response.get_json()["image_models"] == [
        {"id": "grok-imagine-image-2.0", "label": "grok-imagine 2.0", "resolutions": ["1K", "2K"]},
        {"id": "gemini-3.1-flash-image", "label": "Nano Banana 2", "resolutions": ["1K", "2K", "4K"]},
    ]


def test_canvas_verify_returns_enabled_video_models_for_host_picker(app):
    from huishi.canvas_session import issue_canvas_session_token
    from huishi.providers import save_canvas_setting, save_provider

    with app.app_context():
        save_canvas_setting("canvas_app_url", "http://127.0.0.1:3000")
        user_id = create_user(username="video-model-catalog-user")
        user = get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        token, _ = issue_canvas_session_token(user)
        save_provider(
            provider_type="video",
            name="video-channel",
            base_url="https://video.example",
            api_key="video-key",
            model="grok-imagine-video",
            api_format="grok",
            priority=10,
            enabled=True,
            models=[
                {"id": "grok-imagine-video", "label": "grok-imagine"},
                {"id": "seedance-2.0", "label": "Seedance 2.0"},
            ],
        )
        get_db().commit()

    with app.test_client() as client:
        response = client.post(
            "/api/canvas/session/verify",
            json={},
            headers={"Origin": "http://127.0.0.1:3000", "X-Canvas-Session": token},
        )

    assert response.status_code == 200
    # 每个视频模型现在还会带上 api_format 与 capabilities —— 画布端需要据此
    # 决定可选的时长/分辨率/比例以及参考素材上限，因此不再只是 id+label。
    models = response.get_json()["video_models"]
    assert [m["id"] for m in models] == ["grok-imagine-video", "seedance-2.0"]
    assert [m["label"] for m in models] == ["grok-imagine", "Seedance 2.0"]
    # 能力数据按模型分别解析：已声明的模型会带 api_format + capabilities，
    # 未在 video_capabilities() 中声明的模型则不带（这是当前已知的数据空缺，
    # 见需求④；此处只固定"有则必有 api_format"这一结构约束）。
    for item in models:
        assert item["id"] and item["label"]
        if "capabilities" in item:
            assert "api_format" in item
            assert isinstance(item["capabilities"], dict)


def test_canvas_verify_returns_separate_speech_and_music_models(app):
    from huishi.canvas_session import issue_canvas_session_token
    from huishi.providers import save_canvas_setting, save_provider

    with app.app_context():
        save_canvas_setting("canvas_app_url", "http://127.0.0.1:3000")
        user_id = create_user(username="audio-model-catalog-user")
        user = get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        token, _ = issue_canvas_session_token(user)
        save_provider(
            provider_type="audio",
            name="minimax-audio",
            base_url="https://audio.example",
            api_key="audio-key",
            model="speech-2.8-hd",
            api_format="minimax",
            priority=10,
            enabled=True,
            capabilities=["speech", "music"],
            models=[
                {"id": "speech-2.8-hd", "label": "MiniMax Speech 2.8 HD", "media_type": "speech"},
                {"id": "music-3.0", "label": "MiniMax Music 3.0", "media_type": "music"},
            ],
        )
        get_db().commit()

    with app.test_client() as client:
        response = client.post(
            "/api/canvas/session/verify",
            json={},
            headers={"Origin": "http://127.0.0.1:3000", "X-Canvas-Session": token},
        )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["speech_models"] == [{"id": "speech-2.8-hd", "label": "MiniMax Speech 2.8 HD"}]
    assert payload["music_models"] == [{"id": "music-3.0", "label": "MiniMax Music 3.0"}]


def test_canvas_verify_rejects_token_after_its_user_is_disabled(app):
    from huishi.canvas_session import issue_canvas_session_token
    from huishi.providers import save_canvas_setting

    with app.app_context():
        save_canvas_setting("canvas_app_url", "http://127.0.0.1:3000")
        user_id = create_user(username="disabled-canvas-user")
        user = get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        token, _ = issue_canvas_session_token(user)
        get_db().execute("UPDATE users SET enabled = 0 WHERE id = ?", (user_id,))
        get_db().commit()

    with app.test_client() as client:
        response = client.post(
            "/api/canvas/session/verify",
            json={"token": token},
            headers={"Origin": "http://127.0.0.1:3000"},
        )

    assert response.status_code == 401
    assert response.get_json() == {"authenticated": False, "reason": "user_disabled"}


def test_canvas_verify_allows_localhost_alias_for_local_canvas(app):
    from huishi.canvas_session import issue_canvas_session_token
    from huishi.providers import save_canvas_setting

    with app.app_context():
        save_canvas_setting("canvas_app_url", "http://127.0.0.1:3000")
        user_id = create_user(role="admin", username="local-alias")
        user = get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        token, _ = issue_canvas_session_token(user)
        get_db().commit()

    with app.test_client() as client:
        response = client.post(
            "/api/canvas/session/verify",
            json={"token": token},
            headers={"Origin": "http://localhost:3000"},
        )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["authenticated"] is True
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"


def test_canvas_origin_alias_helper_accepts_localhost_and_loopback():
    from huishi.routes_workspace import is_allowed_canvas_origin

    assert is_allowed_canvas_origin("http://localhost:3000", "http://127.0.0.1:3000")
    assert is_allowed_canvas_origin("http://127.0.0.1:3000", "http://localhost:3000")
    assert not is_allowed_canvas_origin("http://localhost:3001", "http://127.0.0.1:3000")


def test_canvas_assets_library_endpoint_returns_host_assets(app):
    from huishi.canvas_session import issue_canvas_session_token
    from huishi.providers import save_canvas_setting
    from huishi.records import create_record

    with app.app_context():
        save_canvas_setting("canvas_app_url", "http://127.0.0.1:3000")
        user_id = create_user(role="admin", username="captain")
        user = get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        token, _ = issue_canvas_session_token(user)
        upload_dir = app.config["OUTPUT_DIR"]
        upload_dir.mkdir(parents=True, exist_ok=True)
        (upload_dir / "host-library.png").write_bytes(b"png")
        create_record(
            user_id=user_id,
            prompt="host library asset",
            image_path="/static/uploads/host-library.png",
            mode="text",
            ratio="16:9",
            resolution="2K",
            actual_size="2560x1440",
            quality="auto",
            output_format="png",
            count=1,
            model_source="gpt-image-2",
            elapsed_seconds=0.1,
            points_charged=2,
            asset_source="image",
            image_paths=["/static/uploads/host-library.png"],
        )
        get_db().commit()

    with app.test_client() as client:
        response = client.post(
            "/api/canvas/assets/library",
            json={"token": token},
            headers={"Origin": "http://127.0.0.1:3000"},
        )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["ok"] is True
    assert len(payload["assets"]) == 1
    assert payload["assets"][0]["title"] == "host library asset"
    assert payload["assets"][0]["image_path"] == "/static/uploads/host-library.png"
    assert payload["assets"][0]["image_url"].endswith("/static/uploads/host-library.png")
    assert payload["assets"][0]["width"] == 2560
    assert payload["assets"][0]["height"] == 1440
    assert response.headers["Access-Control-Allow-Origin"] == "http://127.0.0.1:3000"


def test_canvas_asset_library_item_returns_data_url(app):
    from huishi.canvas_session import issue_canvas_session_token
    from huishi.providers import save_canvas_setting
    from huishi.records import create_record

    png_bytes = (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
        b"\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00\xc9\xfe\x92\xef"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    with app.app_context():
        save_canvas_setting("canvas_app_url", "http://127.0.0.1:3000")
        user_id = create_user(role="admin", username="captain")
        user = get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        token, _ = issue_canvas_session_token(user)
        upload_dir = app.config["OUTPUT_DIR"]
        upload_dir.mkdir(parents=True, exist_ok=True)
        (upload_dir / "host-item.png").write_bytes(png_bytes)
        record_id = create_record(
            user_id=user_id,
            prompt="host item asset",
            image_path="/static/uploads/host-item.png",
            mode="text",
            ratio="1:1",
            resolution="1K",
            actual_size="1024x1024",
            quality="auto",
            output_format="png",
            count=1,
            model_source="gpt-image-2",
            elapsed_seconds=0.1,
            points_charged=2,
            asset_source="image",
            image_paths=["/static/uploads/host-item.png"],
        )
        get_db().commit()

    with app.test_client() as client:
        response = client.post(
            f"/api/canvas/assets/library/{record_id}",
            json={"token": token},
            headers={"Origin": "http://127.0.0.1:3000"},
        )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["asset"]["title"] == "host item asset"
    assert payload["asset"]["data_url"].startswith("data:image/png;base64,")
    assert response.headers["Access-Control-Allow-Origin"] == "http://127.0.0.1:3000"
