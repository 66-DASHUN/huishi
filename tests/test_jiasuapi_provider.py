from __future__ import annotations

from huishi import providers


class JsonResponse:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def test_jiasuapi_protocol_is_valid_for_shared_connections():
    assert providers.normalize_provider_api_format("jiasuapi", "mixed") == "jiasuapi"
    assert providers.normalize_provider_api_format("jiasuapi", "image") == "jiasuapi"
    assert providers.normalize_provider_api_format("jiasuapi", "video") == "jiasuapi"
    assert providers.provider_default_base_url("jiasuapi") == "https://ai.jiasuapi.com"
    assert providers.provider_supported_resolutions("jiasuapi") == ("1K", "2K", "4K")


def test_jiasuapi_discovery_uses_documented_endpoint_and_enriches_known_models(monkeypatch):
    calls = []
    payload = {
        "object": "list",
        "data": [
            {"id": "gpt-image-2.5-1k", "object": "model"},
            {"id": "seedance-2.5-101010", "object": "model"},
            {"id": "minimax-h3", "object": "model"},
            {"id": "grok-1.5", "object": "model"},
        ],
    }

    def fake_get(url, *args, **kwargs):
        calls.append(url)
        return JsonResponse(payload)

    monkeypatch.setattr(providers.requests, "get", fake_get)

    result = providers.fetch_provider_models(
        {
            "provider_type": "mixed",
            "api_format": "jiasuapi",
            "base_url": "https://ai.jiasuapi.com",
            "api_key": "secret",
        }
    )
    by_id = {entry["id"]: entry for entry in result}

    assert calls == ["https://ai.jiasuapi.com/v1/models"]
    assert set(by_id) == {
        "gpt-image-2.5-1k",
        "seedance-2.5-101010",
        "minimax-h3",
        "grok-1.5",
    }
    assert all(entry["api_format"] == "jiasuapi" for entry in result)
    assert all(entry["enabled"] is False for entry in result)
    assert by_id["gpt-image-2.5-1k"]["media_type"] == "image"
    assert by_id["gpt-image-2.5-1k"]["resolutions"] == ["1K"]
    assert by_id["seedance-2.5-101010"]["media_type"] == "video"
    assert by_id["seedance-2.5-101010"]["capabilities"]["duration_range"] == {
        "min": 4,
        "max": 30,
        "step": 1,
    }
    assert by_id["minimax-h3"]["media_type"] == "video"
    assert by_id["minimax-h3"]["capabilities"]["resolutions"] == ["2k"]
    assert by_id["grok-1.5"].get("media_type", "") == ""
