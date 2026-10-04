from huishi.video_api import poll_video_task


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload


def test_grok_poll_accepts_nested_relative_video_url(monkeypatch):
    def fake_get(url, **kwargs):
        assert url.endswith("/v1/videos/grok-task-2")
        return FakeResponse({
            "status": "done",
            "video": {"url": "/v1/videos/grok-task-2/content"},
        })

    monkeypatch.setattr("huishi.video_api.requests.get", fake_get)
    state = poll_video_task(
        {"api_format": "grok", "base_url": "https://o10.top", "api_key": "secret", "model": "grok-imagine-video"},
        "grok-task-2",
    )
    assert state.status == "completed"
    assert state.url == "https://o10.top/v1/videos/grok-task-2/content"
