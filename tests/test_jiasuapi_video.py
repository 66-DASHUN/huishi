from __future__ import annotations

import pytest

from huishi import video_api
from huishi.media_capabilities import validate_video_request, video_capabilities
from huishi.video_adapters import jiasuapi
from huishi import media_references


class Response:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


def test_jiasuapi_video_create_maps_reference_materials(monkeypatch):
    captured = {}

    def fake_request(method, url, **kwargs):
        captured.update(method=method, url=url, payload=kwargs.get("json"))
        return Response(200, {"id": "task_video_1", "status": "queued"})

    monkeypatch.setattr(jiasuapi.requests, "request", fake_request)
    task = jiasuapi.create(
        {"base_url": "https://ai.jiasuapi.com", "api_key": "secret", "settings": {}},
        {
            "model": "minimax-h3", "prompt": "turn around", "duration_seconds": 15,
            "ratio": "16:9", "resolution": "2k", "idempotency_key": "idem-1",
            "content": [
                {"type": "text", "text": "turn around"},
                {"type": "image_url", "image_url": {"url": "https://app.example/ref.png"}, "role": "reference_image"},
                {"type": "video_url", "video_url": {"url": "https://app.example/ref.mp4", "duration_seconds": 10}, "role": "reference_video"},
                {"type": "audio_url", "audio_url": {"url": "https://app.example/ref.mp3"}, "role": "reference_audio"},
            ],
        },
    )

    assert task.provider_task_id == "task_video_1"
    assert captured["method"] == "POST"
    assert captured["url"] == "https://ai.jiasuapi.com/v1/video/generations"
    assert captured["payload"]["images"] == [{"url": "https://app.example/ref.png"}]
    assert captured["payload"]["videos"] == [{"url": "https://app.example/ref.mp4", "duration_seconds": 10}]
    assert captured["payload"]["audios"] == [{"url": "https://app.example/ref.mp3"}]


def test_jiasuapi_video_poll_normalizes_result_urls(monkeypatch):
    responses = iter([
        Response(200, {"id": "task_video_1", "status": "in_progress", "result_urls": []}),
        Response(200, {"id": "task_video_1", "status": "completed", "result_urls": ["https://m.jiasuapi.com/media/video.mp4"]}),
    ])
    monkeypatch.setattr(jiasuapi.requests, "request", lambda *args, **kwargs: next(responses))

    pending = jiasuapi.poll({"base_url": "https://ai.jiasuapi.com", "api_key": "secret"}, "task_video_1")
    complete = jiasuapi.poll({"base_url": "https://ai.jiasuapi.com", "api_key": "secret"}, "task_video_1")
    assert pending.status == "pending"
    assert complete.status == "completed"
    assert complete.url == "https://m.jiasuapi.com/media/video.mp4"


def test_jiasuapi_h3_and_seedance_capabilities_are_constrained():
    h3 = video_capabilities("jiasuapi", "minimax-h3")
    assert h3["duration_range"] == {"min": 4, "max": 15, "step": 1}
    assert h3["resolutions"] == ["2k"]
    assert h3["max_reference_images"] == 9
    assert h3["max_reference_videos"] == 3
    assert h3["max_reference_audios"] == 3

    seedance = video_capabilities("jiasuapi", "seedance-2.5-101010")
    assert seedance["duration_range"] == {"min": 4, "max": 30, "step": 1}
    with pytest.raises(ValueError, match="时长"):
        validate_video_request("minimax-h3", h3, {"prompt": "x", "duration_seconds": 3})


def test_reference_metadata_preserves_h3_video_duration_and_mime(monkeypatch):
    class Row(dict):
        __getattr__ = dict.__getitem__

    class FakeDb:
        def execute(self, query, params):
            return type("Result", (), {"fetchone": lambda self: Row(id="ref-video", user_id=7, storage_key="ref.mp4", metadata_json='{"kind":"video"}')})()

    class FakeStorage:
        def ensure_local(self, key):
            return type("Path", (), {"read_bytes": lambda self: b"video"})()

    monkeypatch.setattr(media_references, "get_db", lambda: FakeDb())
    monkeypatch.setattr(media_references, "get_upload_storage", lambda: FakeStorage())
    monkeypatch.setattr(media_references, "inspect_media", lambda data, kind: {"kind": kind, "bytes": 5, "duration": 9.5, "mime": "video/mp4", "width": 1280, "height": 720})
    monkeypatch.setattr(media_references, "reference_signer", lambda: type("Signer", (), {"dumps": lambda self, value: "signed"})())
    monkeypatch.setattr(media_references, "url_for", lambda *args, **kwargs: "https://app.example/ref.mp4")
    monkeypatch.setattr(media_references, "validate_video_request", lambda model, caps, request: request)

    request = {"model": "minimax-h3", "prompt": "turn around", "duration_seconds": 15, "ratio": "16:9", "resolution": "2k"}
    result = media_references.prepare_references(
        7, "jiasuapi", video_capabilities("jiasuapi", "minimax-h3"), request,
        [{"id": "ref-video", "role": "reference_video"}],
    )

    item = result["content"][1]
    assert item["video_url"]["duration_seconds"] == 9.5
    assert item["video_url"]["mime"] == "video/mp4"
