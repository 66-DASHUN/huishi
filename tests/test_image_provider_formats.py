from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path

import pytest
from werkzeug.datastructures import FileStorage

from app import create_app
from huishi import image_api, providers
from huishi.db import get_db, init_db


@pytest.fixture()
def app(tmp_path: Path):
    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "test.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"
    with app.app_context():
        init_db()
    return app


def test_provider_api_format_is_persisted_and_dispatched(app, monkeypatch):
    captured: dict[str, object] = {}

    with app.app_context():
        provider_id = providers.save_provider(
            provider_type="image",
            name="Gemini official",
            base_url="https://generativelanguage.googleapis.com",
            api_key="gemini-key",
            model="gemini-3.1-flash-image",
            api_format="gemini",
            priority=10,
            enabled=True,
            resolutions=["1K", "2K", "4K"],
        )
        get_db().commit()
        assert providers.get_provider(provider_id)["api_format"] == "gemini"

        def fake_generate_image(**kwargs):
            captured.update(kwargs)
            return {"image_paths": ["/static/uploads/test.png"]}

        monkeypatch.setattr(providers, "generate_image", fake_generate_image)
        providers.generate_image_with_failover(
            prompt="test",
            mode="text",
            ratio="16:9",
            resolution="2K",
            count=1,
            quality="auto",
            output_format="png",
            reference_images=[],
        )

    assert captured["api_format"] == "gemini"


def test_settings_displays_banana_label_but_keeps_api_model_id(app):
    with app.app_context():
        providers.save_provider(
            provider_type="image",
            name="Nano Banana 2",
            base_url="https://generativelanguage.googleapis.com",
            api_key="gemini-key",
            model="gemini-3.1-flash-image",
            api_format="banana",
            priority=10,
            enabled=True,
            resolutions=["1K", "2K"],
        )
        get_db().commit()
        admin = get_db().execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1").fetchone()

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = admin["id"]
        response = client.get("/admin/config/settings")

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert '<strong title="gemini-3.1-flash-image">Nano Banana 2</strong>' in body
    assert 'name="model" data-model-select' in body
    assert '<option value="gemini-3.1-flash-image" selected>Nano Banana 2</option>' in body
    assert '真实 ID：<code>gemini-3.1-flash-image</code>' in body


def test_grok_provider_does_not_advertise_unsupported_4k(app):
    with app.app_context():
        provider_id = providers.save_provider(
            provider_type="image",
            name="Grok official",
            base_url="https://api.x.ai/v1",
            api_key="xai-key",
            model="grok-imagine-image-2.0",
            api_format="grok",
            priority=10,
            enabled=True,
            resolutions=["1K", "2K", "4K"],
        )
        get_db().commit()

        assert providers.get_provider(provider_id)["resolutions"] == ["1K", "2K"]


def test_provider_form_validates_image_api_format(app):
    from huishi.routes_workspace import parse_provider_form

    with app.app_context():
        with app.test_request_context(
            "/settings/providers",
            method="POST",
            data={
                "provider_type": "image",
                "name": "Grok",
                "base_url": "https://api.x.ai/v1",
                "api_key": "xai-key",
                "model": "grok-imagine-image-2.0",
                "api_format": "grok",
                "priority": "20",
                "enabled": "1",
                "resolutions": ["1K", "2K"],
            },
        ):
            assert parse_provider_form()["api_format"] == "grok"

        with app.test_request_context(
            "/settings/providers",
            method="POST",
            data={
                "provider_type": "image",
                "name": "Unknown",
                "base_url": "https://api.example.com",
                "api_key": "api-key",
                "model": "image-model",
                "api_format": "unknown",
            },
        ):
            with pytest.raises(ValueError, match="调用协议"):
                parse_provider_form()


def test_provider_form_uses_custom_model_when_enabled(app):
    from huishi.routes_workspace import parse_provider_form

    with app.app_context(), app.test_request_context(
        "/settings/providers",
        method="POST",
        data={
            "provider_type": "image",
            "name": "Custom gateway",
            "base_url": "https://api.example.com/v1",
            "api_key": "gateway-key",
            "model": "gpt-image-2",
            "custom_model_enabled": "1",
            "custom_model": "gateway-image-v2026",
            "api_format": "openai",
            "priority": "100",
            "enabled": "1",
            "resolutions": ["1K"],
        },
    ):
        assert parse_provider_form()["model"] == "gateway-image-v2026"


def test_custom_model_can_be_saved_through_provider_post(app):
    with app.app_context():
        admin = get_db().execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1").fetchone()

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = admin["id"]
        response = client.post(
            "/settings/providers",
            data={
                "provider_type": "image",
                "name": "Custom gateway",
                "base_url": "https://api.example.com/v1",
                "api_key": "gateway-key",
                "model": "gpt-image-2",
                "custom_model_enabled": "1",
                "custom_model": "gateway-image-v2026",
                "api_format": "openai",
                "priority": "100",
                "enabled": "1",
                "resolutions": ["1K"],
            },
        )

    assert response.status_code == 302
    with app.app_context():
        assert providers.list_providers("image")[0]["model"] == "gateway-image-v2026"


def test_custom_provider_can_switch_back_to_an_official_model_without_javascript(app):
    with app.app_context():
        provider_id = providers.save_provider(
            provider_type="image",
            name="Custom gateway",
            base_url="https://api.example.com/v1",
            api_key="gateway-key",
            model="gateway-image-v2026",
            api_format="openai",
            priority=100,
            enabled=True,
            resolutions=["1K"],
        )
        get_db().commit()
        admin = get_db().execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1").fetchone()

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = admin["id"]
        response = client.post(
            f"/settings/providers/{provider_id}",
            data={
                "provider_type": "image",
                "name": "Custom gateway",
                "base_url": "https://api.example.com/v1",
                "api_key": "",
                "model": "gpt-image-1",
                "custom_model": "gateway-image-v2026",
                "api_format": "openai",
                "priority": "100",
                "enabled": "1",
                "resolutions": ["1K"],
            },
        )

    assert response.status_code == 302
    with app.app_context():
        assert providers.get_provider(provider_id)["model"] == "gpt-image-1"


def test_provider_post_rejects_an_empty_model_before_persisting(app):
    with app.app_context():
        admin = get_db().execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1").fetchone()

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = admin["id"]
        response = client.post(
            "/settings/providers",
            data={
                "provider_type": "image",
                "name": "Invalid model",
                "base_url": "https://api.example.com/v1",
                "api_key": "gateway-key",
                "model": "",
                "custom_model": "",
                "api_format": "openai",
                "priority": "100",
                "enabled": "1",
                "resolutions": ["1K"],
            },
        )

    assert response.status_code == 400
    with app.app_context():
        assert providers.list_providers("image") == []


def test_banana_provider_api_format_is_persisted_and_dispatched(app, monkeypatch):
    captured: dict[str, object] = {}

    with app.app_context():
        provider_id = providers.save_provider(
            provider_type="image",
            name="Nano Banana",
            base_url="https://generativelanguage.googleapis.com",
            api_key="gemini-key",
            model="gemini-3.1-flash-image",
            api_format="banana",
            priority=10,
            enabled=True,
            resolutions=["1K", "2K", "4K"],
        )
        get_db().commit()
        assert providers.get_provider(provider_id)["api_format"] == "banana"

        def fake_generate_image(**kwargs):
            captured.update(kwargs)
            return {"image_paths": ["/static/uploads/test.png"]}

        monkeypatch.setattr(providers, "generate_image", fake_generate_image)
        providers.generate_image_with_failover(
            prompt="test",
            mode="text",
            ratio="16:9",
            resolution="2K",
            count=1,
            quality="auto",
            output_format="png",
            reference_images=[],
        )

    assert captured["api_format"] == "banana"


def test_banana_generation_uses_official_interactions_payload(monkeypatch):
    captured: dict[str, object] = {}
    encoded = base64.b64encode(b"banana-image").decode("ascii")

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {"output_image": {"data": encoded, "mime_type": "image/png"}}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr(image_api.requests, "post", fake_post)
    monkeypatch.setattr(image_api, "images_from_payload", lambda payload, **_kwargs: [payload["data"][0]["b64_json"]])
    monkeypatch.setattr(
        image_api,
        "current_app",
        type("App", (), {"config": {"IMAGE_API_TIMEOUT": 180, "IMAGE_API_MAX_RETRIES": 0}})(),
    )

    result = image_api.generate_image(
        prompt="a banana product photo",
        mode="text",
        ratio="16:9",
        resolution="2K",
        count=1,
        api_key="gemini-key",
        base_url="https://generativelanguage.googleapis.com",
        model="gemini-3.1-flash-image",
        api_format="banana",
    )

    assert captured["url"] == "https://generativelanguage.googleapis.com/v1beta/interactions"
    assert captured["headers"] == {"Content-Type": "application/json", "x-goog-api-key": "gemini-key"}
    assert captured["json"]["model"] == "gemini-3.1-flash-image"
    assert captured["json"]["response_format"] == {
        "type": "image",
        "mime_type": "image/png",
        "aspect_ratio": "16:9",
        "image_size": "2K",
    }
    assert result["image_paths"] == [encoded]


def test_gemini_generation_uses_official_interactions_payload(monkeypatch):
    captured: dict[str, object] = {}
    encoded = base64.b64encode(b"gemini-image").decode("ascii")

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {"output_image": {"data": encoded, "mime_type": "image/png"}}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr(image_api.requests, "post", fake_post)
    monkeypatch.setattr(image_api, "images_from_payload", lambda payload, **_kwargs: [payload["data"][0]["b64_json"]])
    monkeypatch.setattr(
        image_api,
        "current_app",
        type("App", (), {"config": {"IMAGE_API_TIMEOUT": 180, "IMAGE_API_MAX_RETRIES": 0}})(),
    )

    result = image_api.generate_image(
        prompt="a clean product photo",
        mode="text",
        ratio="16:9",
        resolution="2048x1152",
        count=1,
        api_key="gemini-key",
        base_url="https://generativelanguage.googleapis.com",
        model="gemini-3.1-flash-image",
        api_format="gemini",
    )

    assert captured["url"] == "https://generativelanguage.googleapis.com/v1beta/interactions"
    assert captured["headers"] == {"Content-Type": "application/json", "x-goog-api-key": "gemini-key"}
    assert captured["json"] == {
        "model": "gemini-3.1-flash-image",
        "input": "a clean product photo",
        "response_format": {
            "type": "image",
            "mime_type": "image/png",
            "aspect_ratio": "16:9",
            "image_size": "2K",
        },
        "store": False,
    }
    assert result["image_paths"] == [encoded]


def test_grok_generation_uses_official_openai_compatible_parameters(monkeypatch):
    captured: dict[str, object] = {}

    class FakeResponse:
        def to_dict(self):
            return {"data": [{"b64_json": "Z3Jvaw=="}]}

    class DummyImages:
        def generate(self, **kwargs):
            captured.update(kwargs)
            return FakeResponse()

    class DummyClient:
        images = DummyImages()

    monkeypatch.setattr(image_api, "OpenAI", lambda **_kwargs: DummyClient())
    monkeypatch.setattr(image_api, "images_from_payload", lambda _payload, **_kwargs: ["saved.png"])
    monkeypatch.setattr(
        image_api,
        "current_app",
        type("App", (), {"config": {"IMAGE_API_TIMEOUT": 180, "IMAGE_API_MAX_RETRIES": 0}})(),
    )

    image_api.generate_image(
        prompt="a neon city",
        mode="text",
        ratio="16:9",
        resolution="2048x1152",
        count=3,
        api_key="xai-key",
        base_url="https://api.x.ai/v1",
        model="grok-imagine-image-2.0",
        api_format="grok",
        quality="high",
        output_format="png",
    )

    assert captured == {
        "model": "grok-imagine-image-2.0",
        "prompt": "a neon city",
        "n": 3,
        "response_format": "b64_json",
        "extra_body": {"aspect_ratio": "16:9", "resolution": "2k", "quality": "medium"},
    }


def test_grok_backend_rejects_unsupported_4k_resolution():
    with pytest.raises(image_api.ConfigurationError, match="Grok 官方生图仅支持 1K 或 2K"):
        image_api.grok_extra_body(ratio="16:9", resolution="4K", quality="high")


def test_grok_reference_edit_uses_json_endpoint(monkeypatch):
    captured: dict[str, object] = {}

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {"data": [{"b64_json": "Z3Jvaw=="}]}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr(image_api.requests, "post", fake_post)
    monkeypatch.setattr(image_api, "images_from_payload", lambda _payload, **_kwargs: ["saved.png"])
    monkeypatch.setattr(
        image_api,
        "current_app",
        type("App", (), {"config": {"IMAGE_API_TIMEOUT": 180, "IMAGE_API_MAX_RETRIES": 0}})(),
    )
    reference = FileStorage(stream=BytesIO(b"reference-image"), filename="reference.png", content_type="image/png")

    image_api.generate_image(
        prompt="make it cinematic",
        mode="reference",
        ratio="3:2",
        resolution="1K",
        count=1,
        api_key="xai-key",
        base_url="https://api.x.ai/v1",
        model="grok-imagine-image-2.0",
        api_format="grok",
        reference_images=[reference],
    )

    assert captured["url"] == "https://api.x.ai/v1/images/edits"
    assert captured["headers"]["Authorization"] == "Bearer xai-key"
    assert captured["json"]["image"] == {
        "type": "image_url",
        "url": "data:image/png;base64,cmVmZXJlbmNlLWltYWdl",
    }
    assert captured["json"]["aspect_ratio"] == "3:2"
    assert captured["json"]["resolution"] == "1k"
