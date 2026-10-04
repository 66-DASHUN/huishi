"""
画布生图代理接口测试：/api/canvas/generate
覆盖：未授权拒绝、余额不足拒绝、成功扣费并返回图片、CORS 头正确。
"""
from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path

import pytest

from app import create_app
from huishi.canvas_session import issue_canvas_session_token
from huishi.db import get_db


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


def _create_user(points: int = 50, username: str = "testuser") -> int:
    cursor = get_db().execute(
        "INSERT INTO users (username, email, password_hash, role, email_verified, points, created_at) "
        "VALUES (?, \'\', \'hash\', \'user\', 1, ?, \'now\')",
        (username, points),
    )
    get_db().commit()
    return int(cursor.lastrowid)


def _issue_token(user_id: int) -> str:
    row = get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    token, _ = issue_canvas_session_token(dict(row))
    return token


def _fake_generate(**kwargs):
    from flask import current_app
    import secrets
    output_dir: Path = current_app.config["OUTPUT_DIR"]
    output_dir.mkdir(parents=True, exist_ok=True)
    png_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwADhQGAWjR9awAAAABJRU5ErkJggg=="
    )
    fname = f"test_{secrets.token_hex(4)}.png"
    (output_dir / fname).write_bytes(png_bytes)
    return {
        "image_path": f"/static/uploads/{fname}",
        "image_paths": [f"/static/uploads/{fname}"],
        "actual_size": "1024x1024",
        "model_source": "stub",
        "elapsed_seconds": 0.01,
    }


def _save_image_provider(*, model: str, enabled: bool = True, resolutions=None, priority: int = 10, name: str | None = None, api_format: str = "openai"):
    from huishi.providers import save_provider

    return save_provider(
        provider_type="image",
        name=name or model,
        base_url=f"https://{name or model}.example",
        api_key="test-provider-key",
        model=model,
        api_format=api_format,
        priority=priority,
        enabled=enabled,
        resolutions=resolutions or ["1K", "2K", "4K"],
    )


def test_canvas_generate_rejects_missing_token(app):
    with app.test_client() as client:
        resp = client.post(
            "/api/canvas/generate",
            json={"prompt": "test"},
            headers={"Origin": "http://127.0.0.1:3000"},
        )
    assert resp.status_code == 401


def test_canvas_generate_rejects_invalid_token(app):
    with app.test_client() as client:
        resp = client.post(
            "/api/canvas/generate",
            json={"token": "invalid.token.here", "prompt": "test"},
            headers={"Origin": "http://127.0.0.1:3000"},
        )
    assert resp.status_code == 401


def test_canvas_generate_rejects_token_after_its_user_is_disabled(app):
    with app.app_context():
        user_id = _create_user(points=50, username="disabled-generate-user")
        token = _issue_token(user_id)
        get_db().execute("UPDATE users SET enabled = 0 WHERE id = ?", (user_id,))
        get_db().commit()

    with app.test_client() as client:
        resp = client.post(
            "/api/canvas/generate",
            json={"token": token, "prompt": ""},
            headers={"Origin": "http://127.0.0.1:3000"},
        )

    assert resp.status_code == 401
    assert resp.get_json()["error"] == "user_disabled"


def test_canvas_generate_rejects_empty_prompt(app):
    with app.app_context():
        user_id = _create_user(points=50)
        token = _issue_token(user_id)
    with app.test_client() as client:
        resp = client.post(
            "/api/canvas/generate",
            json={"token": token, "prompt": ""},
            headers={"Origin": "http://127.0.0.1:3000"},
        )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["ok"] is False


def test_canvas_generate_rejects_insufficient_balance(app):
    with app.app_context():
        user_id = _create_user(points=0)
        token = _issue_token(user_id)
    with app.test_client() as client:
        resp = client.post(
            "/api/canvas/generate",
            json={"token": token, "prompt": "a cat", "ratio": "1:1", "resolution": "2K"},
            headers={"Origin": "http://127.0.0.1:3000"},
        )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["ok"] is False


def test_canvas_generate_deducts_points_and_returns_images(app, monkeypatch):
    monkeypatch.setattr("huishi.routes_workspace.generate_image_with_failover", _fake_generate)

    with app.app_context():
        user_id = _create_user(points=50)
        token = _issue_token(user_id)

    with app.test_client() as client:
        resp = client.post(
            "/api/canvas/generate",
            json={"token": token, "prompt": "a red circle", "ratio": "1:1", "resolution": "2K", "count": 1},
            headers={"Origin": "http://127.0.0.1:3000"},
        )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert len(data["images"]) >= 1
    assert data["images"][0]["dataUrl"].startswith("data:image/")
    assert data["cost"] > 0
    assert data["balance"] == 50 - data["cost"]


def test_canvas_generate_passes_configured_count_and_bills_each_image(app, monkeypatch):
    captured = {}

    def fake_generate(**kwargs):
        captured.update(kwargs)
        return _fake_generate(**kwargs)

    monkeypatch.setattr("huishi.routes_workspace.generate_image_with_failover", fake_generate)
    with app.app_context():
        user_id = _create_user(points=50)
        token = _issue_token(user_id)

    with app.test_client() as client:
        resp = client.post(
            "/api/canvas/generate",
            json={"token": token, "prompt": "three variants", "count": 3},
            headers={"Origin": "http://127.0.0.1:3000"},
        )

    assert resp.status_code == 200
    assert captured["count"] == 3
    assert resp.get_json()["cost"] == 6


def test_canvas_generate_uses_selected_model_for_generation_record_and_billing(app, monkeypatch):
    captured = {}

    def fake_generate(**kwargs):
        captured.update(kwargs)
        result = _fake_generate(**kwargs)
        result["model_source"] = kwargs["model"]
        return result

    monkeypatch.setattr("huishi.routes_workspace.generate_image_with_failover", fake_generate)
    with app.app_context():
        user_id = _create_user(points=50, username="selected-model-user")
        token = _issue_token(user_id)
        _save_image_provider(model="grok-imagine-image-2.0", api_format="grok", resolutions=["1K", "2K"])
        _save_image_provider(model="gemini-3.1-flash-image", api_format="banana", priority=20)
        get_db().execute(
            "UPDATE pricing_rules SET points_per_image = 3 WHERE model = ? AND resolution = '2K'",
            ("grok-imagine-image-2.0",),
        )
        get_db().execute(
            "UPDATE pricing_rules SET points_per_image = 7 WHERE model = ? AND resolution = '2K'",
            ("gemini-3.1-flash-image",),
        )
        get_db().commit()

    with app.test_client() as client:
        response = client.post(
            "/api/canvas/generate",
            json={"token": token, "prompt": "banana cat", "resolution": "2K", "model": "gemini-3.1-flash-image"},
            headers={"Origin": "http://127.0.0.1:3000"},
        )

    assert response.status_code == 200
    assert response.get_json()["cost"] == 7
    assert response.get_json()["balance"] == 43
    assert captured["model"] == "gemini-3.1-flash-image"
    with app.app_context():
        record = get_db().execute("SELECT model_source, points_charged FROM records WHERE user_id = ?", (user_id,)).fetchone()
        assert dict(record) == {"model_source": "gemini-3.1-flash-image", "points_charged": 7}


def test_canvas_generate_user_key_mode_uses_selected_enabled_provider_model(app, monkeypatch):
    from huishi.user_key import save_user_api_key

    captured = {}

    def fake_generate(**kwargs):
        captured.update(kwargs)
        result = _fake_generate(**kwargs)
        result["model_source"] = kwargs["model"]
        return result

    monkeypatch.setattr("huishi.routes_workspace.generate_image", fake_generate)
    with app.app_context():
        user_id = _create_user(points=50, username="user-key-selected-model")
        token = _issue_token(user_id)
        _save_image_provider(model="grok-imagine-image-2.0", api_format="grok", resolutions=["1K", "2K"], name="grok", priority=10)
        _save_image_provider(model="gemini-3.1-flash-image", api_format="banana", name="banana", priority=20)
        save_user_api_key(user_id, "test-user-key")
        get_db().commit()

    with app.test_client() as client:
        response = client.post(
            "/api/canvas/generate",
            json={"token": token, "prompt": "banana with own key", "resolution": "2K", "model": "gemini-3.1-flash-image"},
            headers={"Origin": "http://127.0.0.1:3000"},
        )

    assert response.status_code == 200
    assert response.get_json()["cost"] == 0
    assert captured["model"] == "gemini-3.1-flash-image"
    assert captured["base_url"] == "https://banana.example"


def test_canvas_generate_records_selected_model_even_if_upstream_metadata_differs(app, monkeypatch):
    def fake_generate(**kwargs):
        result = _fake_generate(**kwargs)
        result["model_source"] = "untrusted-upstream-label"
        return result

    monkeypatch.setattr("huishi.routes_workspace.generate_image_with_failover", fake_generate)
    with app.app_context():
        user_id = _create_user(points=50, username="record-selected-model-user")
        token = _issue_token(user_id)
        _save_image_provider(model="gemini-3.1-flash-image", api_format="banana", resolutions=["1K", "2K", "4K"])
        get_db().commit()

    with app.test_client() as client:
        response = client.post(
            "/api/canvas/generate",
            json={"token": token, "prompt": "record selected model", "resolution": "2K", "model": "gemini-3.1-flash-image"},
            headers={"Origin": "http://127.0.0.1:3000"},
        )

    assert response.status_code == 200
    with app.app_context():
        record = get_db().execute("SELECT model_source FROM records WHERE user_id = ?", (user_id,)).fetchone()
        assert record["model_source"] == "gemini-3.1-flash-image"


@pytest.mark.parametrize(
    ("model", "resolution", "enabled"),
    [
        ("unknown-image-model", "2K", True),
        ("disabled-image-model", "2K", False),
        ("grok-imagine-image-2.0", "4K", True),
    ],
)
def test_canvas_generate_rejects_invalid_disabled_or_unsupported_model(app, monkeypatch, model, resolution, enabled):
    monkeypatch.setattr(
        "huishi.routes_workspace.generate_image_with_failover",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("upstream must not be called")),
    )
    with app.app_context():
        user_id = _create_user(points=50, username=f"reject-{model}-{resolution}")
        token = _issue_token(user_id)
        if model != "unknown-image-model":
            _save_image_provider(
                model=model,
                enabled=enabled,
                resolutions=["1K", "2K"],
                api_format="grok" if model.startswith("grok-") else "openai",
            )
        get_db().commit()

    with app.test_client() as client:
        response = client.post(
            "/api/canvas/generate",
            json={"token": token, "prompt": "must reject", "resolution": resolution, "model": model},
            headers={"Origin": "http://127.0.0.1:3000"},
        )

    assert response.status_code == 400
    assert response.get_json()["ok"] is False


def test_canvas_generate_creates_record_in_db(app, monkeypatch):
    monkeypatch.setattr("huishi.routes_workspace.generate_image_with_failover", _fake_generate)

    with app.app_context():
        user_id = _create_user(points=50)
        token = _issue_token(user_id)

    with app.test_client() as client:
        resp = client.post(
            "/api/canvas/generate",
            json={"token": token, "prompt": "sunset", "ratio": "16:9", "resolution": "1K"},
            headers={"Origin": "http://127.0.0.1:3000"},
        )

    assert resp.status_code == 200
    data = resp.get_json()
    with app.app_context():
        record = get_db().execute(
            "SELECT * FROM records WHERE id = ?", (data["record_id"],)
        ).fetchone()
        assert record is not None
        assert record["user_id"] == user_id
        assert record["prompt"] == "sunset"
        assert record["asset_source"] in {"image", "canvas"}


def test_canvas_generate_cors_headers(app, monkeypatch):
    monkeypatch.setattr("huishi.routes_workspace.generate_image_with_failover", _fake_generate)

    with app.app_context():
        user_id = _create_user(points=50)
        token = _issue_token(user_id)

    with app.test_client() as client:
        resp = client.post(
            "/api/canvas/generate",
            json={"token": token, "prompt": "test cors"},
            headers={"Origin": "http://127.0.0.1:3000"},
        )

    assert "Access-Control-Allow-Origin" in resp.headers


def test_canvas_generate_options_preflight(app):
    with app.test_client() as client:
        resp = client.options(
            "/api/canvas/generate",
            headers={"Origin": "http://127.0.0.1:3000"},
        )
    assert resp.status_code in {200, 204}


def test_canvas_user_key_get_accepts_query_token(app):
    with app.app_context():
        user_id = _create_user(points=50)
        token = _issue_token(user_id)

    with app.test_client() as client:
        resp = client.get(
            "/api/canvas/user-key",
            query_string={"token": token},
            headers={"Origin": "http://127.0.0.1:3000"},
        )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["has_key"] is False


def test_canvas_user_key_post_accepts_query_token(app):
    with app.app_context():
        user_id = _create_user(points=50)
        token = _issue_token(user_id)

    with app.test_client() as client:
        resp = client.post(
            "/api/canvas/user-key",
            query_string={"token": token},
            json={},
            headers={"Origin": "http://127.0.0.1:3000"},
        )

    assert resp.status_code == 400
    data = resp.get_json()
    assert data["ok"] is False
    assert data["error"] == "API Key 不能为空"


def test_canvas_estimate_rejects_missing_token(app):
    with app.test_client() as client:
        resp = client.get(
            "/api/canvas/estimate",
            query_string={"resolution": "2K", "count": "1"},
            headers={"Origin": "http://127.0.0.1:3000"},
        )

    assert resp.status_code == 401
    assert resp.get_json()["error"] == "missing_token"


def test_canvas_estimate_returns_platform_cost_and_balance(app):
    with app.app_context():
        user_id = _create_user(points=50)
        token = _issue_token(user_id)

    with app.test_client() as client:
        resp = client.get(
            "/api/canvas/estimate",
            query_string={"token": token, "resolution": "2K", "count": "3"},
            headers={"Origin": "http://127.0.0.1:3000"},
        )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data == {"ok": True, "cost": 6, "billing_mode": "platform", "balance": 50}


def test_canvas_estimate_accepts_post_json_without_query_token(app):
    with app.app_context():
        user_id = _create_user(points=50)
        token = _issue_token(user_id)

    with app.test_client() as client:
        resp = client.post(
            "/api/canvas/estimate",
            json={"token": token, "resolution": "2K", "count": "3"},
            headers={"Origin": "http://127.0.0.1:3000"},
        )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data == {"ok": True, "cost": 6, "billing_mode": "platform", "balance": 50}


def test_canvas_estimate_uses_selected_model_price(app):
    with app.app_context():
        user_id = _create_user(points=50, username="estimate-model-user")
        token = _issue_token(user_id)
        _save_image_provider(model="grok-imagine-image-2.0", api_format="grok", resolutions=["1K", "2K"])
        _save_image_provider(model="gemini-3.1-flash-image", api_format="banana", priority=20)
        get_db().execute(
            "UPDATE pricing_rules SET points_per_image = 3 WHERE model = ? AND resolution = '2K'",
            ("grok-imagine-image-2.0",),
        )
        get_db().execute(
            "UPDATE pricing_rules SET points_per_image = 7 WHERE model = ? AND resolution = '2K'",
            ("gemini-3.1-flash-image",),
        )
        get_db().commit()

    with app.test_client() as client:
        grok = client.post(
            "/api/canvas/estimate",
            json={"token": token, "resolution": "2K", "count": 2, "model": "grok-imagine-image-2.0"},
            headers={"Origin": "http://127.0.0.1:3000"},
        )
        banana = client.post(
            "/api/canvas/estimate",
            json={"token": token, "resolution": "2K", "count": 2, "model": "gemini-3.1-flash-image"},
            headers={"Origin": "http://127.0.0.1:3000"},
        )

    assert grok.status_code == 200
    assert grok.get_json()["cost"] == 6
    assert banana.status_code == 200
    assert banana.get_json()["cost"] == 14


def test_canvas_estimate_rejects_explicit_unknown_model(app):
    with app.app_context():
        user_id = _create_user(points=50, username="estimate-unknown-model-user")
        token = _issue_token(user_id)

    with app.test_client() as client:
        response = client.post(
            "/api/canvas/estimate",
            json={"token": token, "resolution": "2K", "model": "unknown-image-model"},
            headers={"Origin": "http://127.0.0.1:3000"},
        )

    assert response.status_code == 400
    assert response.get_json()["ok"] is False


def test_canvas_estimate_returns_zero_cost_for_user_key_mode(app):
    from huishi.providers import save_provider
    from huishi.user_key import save_user_api_key

    with app.app_context():
        user_id = _create_user(points=50)
        save_provider(
            provider_type="image",
            name="platform",
            base_url="https://api.example.com",
            api_key="sk-platform",
            model="gpt-image-2",
            priority=100,
            enabled=True,
            resolutions=["1K", "2K", "4K"],
        )
        save_user_api_key(user_id, "sk-user")
        get_db().commit()
        token = _issue_token(user_id)

    with app.test_client() as client:
        resp = client.get(
            "/api/canvas/estimate",
            query_string={"token": token, "resolution": "2K", "count": "3"},
            headers={"Origin": "http://127.0.0.1:3000"},
        )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data == {"ok": True, "cost": 0, "billing_mode": "user_key", "balance": 50}


def test_canvas_estimate_options_preflight(app):
    with app.test_client() as client:
        resp = client.options(
            "/api/canvas/estimate",
            headers={"Origin": "http://127.0.0.1:3000"},
        )

    assert resp.status_code in {200, 204}
    assert resp.headers["Access-Control-Allow-Origin"] == "http://127.0.0.1:3000"
