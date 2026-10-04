from pathlib import Path

import pytest

from app import create_app
from huishi import image_api, providers, video_api
from huishi.db import get_db, init_db
from huishi.admin_audit import redact_audit_values
from huishi.network import openai_http_client


@pytest.fixture()
def app(tmp_path: Path):
    application = create_app(testing=True)
    application.config["DATABASE"] = tmp_path / "test.sqlite3"
    application.config["OUTPUT_DIR"] = tmp_path / "uploads"
    with application.app_context():
        init_db()
    return application


def test_provider_proxy_url_round_trips_and_supports_socks5(app):
    with app.app_context():
        provider_id = providers.save_provider(
            provider_type="image",
            name="Grok via Warp",
            base_url="https://api.x.ai/v1",
            api_key="test-key",
            model="grok-imagine-image-2.0",
            api_format="grok",
            priority=1,
            enabled=True,
            settings={"proxy_url": "socks5://grok-stack-warp-1:1080"},
        )
        get_db().commit()

        provider = providers.get_provider(provider_id)

    assert provider["proxy_url"] == "socks5://grok-stack-warp-1:1080"
    assert providers.normalize_proxy_url("https://proxy.example:8443") == "https://proxy.example:8443"


def test_post_provider_json_forwards_configured_proxy(app, monkeypatch):
    calls = {}

    class Response:
        status_code = 200

        def json(self):
            return {"ok": True}

    def fake_post(url, **kwargs):
        calls["url"] = url
        calls.update(kwargs)
        return Response()

    monkeypatch.setattr(image_api.requests, "post", fake_post)

    with app.app_context():
        payload = image_api.post_provider_json(
            "https://api.example/v1/interactions",
            headers={"Content-Type": "application/json"},
            payload={"model": "test"},
            timeout=10,
            proxy_url="socks5://grok-stack-warp-1:1080",
        )

    assert payload == {"ok": True}
    assert calls["proxies"] == {
        "http": "socks5://grok-stack-warp-1:1080",
        "https": "socks5://grok-stack-warp-1:1080",
    }


def test_model_listing_forwards_configured_proxy(app, monkeypatch):
    calls = {}

    class Response:
        status_code = 200

        def json(self):
            return {"data": [{"id": "grok-imagine-image-2.0"}]}

    def fake_get(url, **kwargs):
        calls["url"] = url
        calls.update(kwargs)
        return Response()

    monkeypatch.setattr(providers.requests, "get", fake_get)

    result = providers.fetch_provider_models(
        {
            "base_url": "https://api.x.ai/v1",
            "api_key": "test-key",
            "api_format": "grok",
            "proxy_url": "socks5://grok-stack-warp-1:1080",
        }
    )

    assert result == [{"id": "grok-imagine-image-2.0", "label": "grok-imagine-image-2.0"}]
    assert calls["proxies"]["https"] == "socks5://grok-stack-warp-1:1080"


def test_video_create_poll_and_download_forward_configured_proxy(monkeypatch):
    calls = []

    class Response:
        status_code = 200
        content = b"video-bytes"

        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return self.payload

    def fake_post(url, **kwargs):
        calls.append(("post", url, kwargs))
        return Response({"id": "task-1", "status": "pending"})

    def fake_get(url, **kwargs):
        calls.append(("get", url, kwargs))
        if url.endswith("/task-1"):
            return Response({"id": "task-1", "status": "completed", "video_url": "https://cdn.example/video.mp4"})
        return Response({})

    monkeypatch.setattr(video_api.requests, "post", fake_post)
    monkeypatch.setattr(video_api.requests, "get", fake_get)
    provider = {
        "api_format": "grok",
        "base_url": "https://api.x.ai/v1",
        "api_key": "test-key",
        "model": "grok-imagine-video",
        "proxy_url": "socks5://grok-stack-warp-1:1080",
    }

    task = video_api.create_video_task(provider, {"prompt": "test", "duration_seconds": 2})
    state = video_api.poll_video_task(provider, task.provider_task_id)
    content = video_api.download_video_result(provider, state)

    assert task.provider_task_id == "task-1"
    assert state.status == "completed"
    assert content == b"video-bytes"
    assert all(item[2]["proxies"]["https"] == "socks5://grok-stack-warp-1:1080" for item in calls)


def test_openai_http_client_uses_configured_proxy(monkeypatch):
    calls = {}

    class FakeClient:
        def close(self):
            pass

    def fake_default_client(**kwargs):
        calls.update(kwargs)
        return FakeClient()

    import openai

    monkeypatch.setattr(openai, "DefaultHttpxClient", fake_default_client)
    client = openai_http_client("socks5://grok-stack-warp-1:1080", timeout=12)

    assert isinstance(client, FakeClient)
    assert calls == {"proxy": "socks5://grok-stack-warp-1:1080", "timeout": 12}


def test_proxy_url_rejects_unsupported_protocol():
    with pytest.raises(ValueError, match="代理地址必须使用"):
        providers.normalize_proxy_url("ftp://proxy.example:21")


def test_proxy_url_is_redacted_from_admin_audit_values():
    assert redact_audit_values({"proxy_url": "socks5://user:password@proxy.example:1080"}) == {"proxy_url": "[redacted]"}
