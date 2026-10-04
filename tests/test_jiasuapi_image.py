from __future__ import annotations

from types import SimpleNamespace

import pytest

from huishi import image_api
from huishi import jiasuapi


class Response:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


def test_async_image_create_polls_unknown_then_completed(monkeypatch):
    calls = []
    responses = iter([
        Response(200, {"id": "task_img_1", "task_id": "task_img_1", "status": "queued"}),
        Response(200, {"id": "task_img_1", "status": "unknown", "result_urls": []}),
        Response(200, {"id": "task_img_1", "status": "completed", "result_urls": ["https://m.jiasuapi.com/media/result.png"]}),
    ])

    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs.get("json")))
        return next(responses)

    monkeypatch.setattr(jiasuapi.requests, "request", fake_request)
    monkeypatch.setattr(jiasuapi.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(jiasuapi, "images_from_payload", lambda payload, **_: ["/static/uploads/result.png"])

    result = jiasuapi.generate_images(
        provider={"base_url": "https://ai.jiasuapi.com", "api_key": "secret", "settings": {"poll_interval": 0}},
        prompt="fog road", model="gpt-image-2.5-1k", ratio="16:9", resolution="1K",
        count=1, quality="high", reference_images=[], timeout=1,
    )

    assert result == ["/static/uploads/result.png"]
    assert calls[0][0:2] == ("POST", "https://ai.jiasuapi.com/v1/images/create")
    assert calls[0][2] == {
        "model": "gpt-image-2.5-1k", "prompt": "fog road", "n": 1,
        "quality": "high", "ratio": "16:9", "resolution": "1K",
    }
    assert calls[1][1:] == ("https://ai.jiasuapi.com/v1/images/tasks/task_img_1", None)
    assert calls[2][1:] == ("https://ai.jiasuapi.com/v1/images/tasks/task_img_1", None)


def test_async_image_failure_exposes_error_message_without_key(monkeypatch):
    responses = iter([
        Response(200, {"id": "task_img_2", "status": "queued"}),
        Response(200, {"id": "task_img_2", "status": "failed", "result_urls": [], "error": {"message": "bad secret"}}),
    ])
    monkeypatch.setattr(jiasuapi.requests, "request", lambda *args, **kwargs: next(responses))
    monkeypatch.setattr(jiasuapi.time, "sleep", lambda _seconds: None)

    with pytest.raises(image_api.ConfigurationError, match="bad") as exc_info:
        jiasuapi.generate_images(
            provider={"base_url": "https://ai.jiasuapi.com", "api_key": "secret", "settings": {"poll_interval": 0}},
            prompt="fog road", model="gpt-image-2.5-1k", ratio="1:1", resolution="1K",
            count=1, quality="auto", reference_images=[], timeout=1,
        )
    assert "secret" not in str(exc_info.value)


def test_async_image_result_download_uses_provider_proxy(monkeypatch):
    responses = iter([
        Response(200, {"id": "task_img_proxy", "status": "queued"}),
        Response(200, {"id": "task_img_proxy", "status": "completed", "result_urls": ["https://m.jiasuapi.com/media/result.png"]}),
    ])
    seen = {}

    monkeypatch.setattr(jiasuapi.requests, "request", lambda *args, **kwargs: next(responses))
    monkeypatch.setattr(jiasuapi.time, "sleep", lambda _seconds: None)

    def fake_images_from_payload(payload, **kwargs):
        seen.update(kwargs)
        return ["/static/uploads/result.png"]

    monkeypatch.setattr(jiasuapi, "images_from_payload", fake_images_from_payload)
    result = jiasuapi.generate_images(
        provider={"base_url": "https://ai.jiasuapi.com", "api_key": "secret", "proxy_url": "http://proxy.local:8080", "settings": {"poll_interval": 0}},
        prompt="fog road", model="gpt-image-2.5-1k", ratio="16:9", resolution="1K",
        count=1, quality="auto", reference_images=[], timeout=1,
    )

    assert result == ["/static/uploads/result.png"]
    assert seen["proxy_url"] == "http://proxy.local:8080"
