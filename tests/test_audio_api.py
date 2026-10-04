from __future__ import annotations

import base64

import pytest

from huishi.audio_api import AudioApiError, generate_music, generate_speech


class JsonResponse:
    status_code = 200
    headers = {"content-type": "application/json"}
    content = b""

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


def test_speech_hex_payload_is_decoded(monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return JsonResponse({"data": {"audio": "68656c6c6f"}, "base_resp": {"status_code": 0}})

    monkeypatch.setattr("huishi.audio_api.requests.post", fake_post)

    result = generate_speech(
        {"api_key": "test-key", "base_url": "https://api.minimaxi.com", "api_format": "minimax"},
        {"model": "speech-2.8-hd", "text": "你好"},
    )

    assert captured["url"] == "https://api.minimaxi.com/v1/t2a_v2"
    assert captured["json"]["model"] == "speech-2.8-hd"
    assert result["content"] == b"hello"
    assert result["mime_type"] == "audio/mpeg"
    assert result["extension"] == "mp3"


def test_speech_base64_payload_is_decoded(monkeypatch):
    encoded = base64.b64encode(b"wav-bytes").decode("ascii")
    monkeypatch.setattr(
        "huishi.audio_api.requests.post",
        lambda *args, **kwargs: JsonResponse({"data": {"audio": encoded}, "base_resp": {"status_code": 0}}),
    )

    result = generate_speech(
        {"api_key": "test-key", "base_url": "https://api.minimaxi.com", "api_format": "minimax"},
        {"model": "speech-2.8-hd", "text": "你好", "output_format": "base64"},
    )

    assert result["content"] == b"wav-bytes"


def test_audio_endpoint_path_can_be_overridden_per_provider(monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        return JsonResponse({"data": {"audio": "6869"}, "base_resp": {"status_code": 0}})

    monkeypatch.setattr("huishi.audio_api.requests.post", fake_post)

    generate_speech(
        {"api_key": "test-key", "base_url": "https://gateway.example", "api_format": "minimax", "settings": {"speech_path": "/custom/speech"}},
        {"model": "speech-2.8-hd", "text": "你好"},
    )

    assert captured["url"] == "https://gateway.example/custom/speech"


def test_music_cover_forwards_reference_audio_and_returns_bytes(monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return JsonResponse({"data": {"audio": "music-bytes"}, "base_resp": {"status_code": 0}})

    monkeypatch.setattr("huishi.audio_api.requests.post", fake_post)

    result = generate_music(
        {"api_key": "test-key", "base_url": "https://api.minimaxi.com", "api_format": "minimax"},
        {"model": "music-cover", "prompt": "钢琴", "audio_base64": "reference-audio"},
    )

    assert captured["url"] == "https://api.minimaxi.com/v1/music_generation"
    assert captured["json"]["audio_base64"] == "reference-audio"
    assert result["content"] == b"music-bytes"
    assert result["mime_type"] == "audio/mpeg"


def test_music_non_cover_omits_reference_audio(monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        captured.update(kwargs)
        return JsonResponse({"data": {"audio": "music-bytes"}, "base_resp": {"status_code": 0}})

    monkeypatch.setattr("huishi.audio_api.requests.post", fake_post)

    generate_music(
        {"api_key": "test-key", "base_url": "https://api.minimaxi.com", "api_format": "minimax"},
        {"model": "music-3.0", "prompt": "钢琴", "audio_base64": "should-not-forward"},
    )

    assert "audio_base64" not in captured["json"]


def test_audio_api_redacts_provider_secret_on_http_error(monkeypatch):
    class ErrorResponse(JsonResponse):
        status_code = 401

        def json(self):
            return {"error": {"message": "Bearer test-secret-key is invalid"}}

    monkeypatch.setattr("huishi.audio_api.requests.post", lambda *args, **kwargs: ErrorResponse({}))

    with pytest.raises(AudioApiError, match="\[redacted\]"):
        generate_speech(
            {"api_key": "test-secret-key", "base_url": "https://api.minimaxi.com", "api_format": "minimax"},
            {"model": "speech-2.8-hd", "text": "你好"},
        )
