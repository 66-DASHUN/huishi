from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from huishi.db import get_db, init_db
from huishi.generation_queue import run_video_generation_task
from huishi.providers import save_provider
from huishi.records import create_generation_task, get_generation_task
from huishi.video_api import VideoTask, VideoTaskState, create_video_task, poll_video_task


@pytest.fixture
def app(tmp_path: Path):
    from app import create_app

    application = create_app(testing=True)
    application.config["DATABASE"] = tmp_path / "test.sqlite3"
    application.config["OUTPUT_DIR"] = tmp_path / "uploads"
    with application.app_context():
        init_db()
    return application


def _user_id():
    return int(get_db().execute(
        "INSERT INTO users (username, email, password_hash, role, email_verified, points, created_at) VALUES (?, '', 'hash', 'user', 1, 100, 'now') RETURNING id",
        ("worker-video-user",),
    ).fetchone()["id"])


@dataclass
class FakeResponse:
    payload: dict
    status_code: int = 200

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload


def test_grok_video_adapter_uses_async_generation_endpoint(monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append(("POST", url, kwargs["json"]))
        return FakeResponse({"request_id": "grok-task-1", "status": "pending"})

    monkeypatch.setattr("huishi.video_api.requests.post", fake_post)
    task = create_video_task(
        {"api_format": "grok", "base_url": "https://api.x.ai/v1", "api_key": "secret", "model": "grok-imagine-video"},
        {"prompt": "a paper boat", "duration_seconds": 6, "ratio": "16:9"},
    )
    assert task.provider_task_id == "grok-task-1"
    assert calls[0][1].endswith("/v1/videos/generations")
    assert calls[0][2]["model"] == "grok-imagine-video"


def test_minimax_poll_adapter_returns_completed_file_id(monkeypatch):
    def fake_get(url, **kwargs):
        assert "query/video_generation" in url
        return FakeResponse({"status": "Success", "task_id": "mm-1", "file_id": "file-9"})

    monkeypatch.setattr("huishi.video_api.requests.get", fake_get)
    state = poll_video_task(
        {"api_format": "minimax", "base_url": "https://api.minimaxi.com", "api_key": "secret", "model": "MiniMax-Hailuo-3.0"},
        "mm-1",
    )
    assert state.status == "completed"
    assert state.file_id == "file-9"


def test_video_worker_persists_downloaded_video_as_asset(app, monkeypatch):
    app.config["VIDEO_GENERATION_TIMEOUT_SECONDS"] = 30
    with app.app_context():
        user_id = _user_id()
        provider_id = save_provider(
            provider_type="video",
            name="Grok",
            base_url="https://api.x.ai/v1",
            api_key="secret",
            model="grok-imagine-video",
            api_format="grok",
            priority=1,
            enabled=True,
        )
        db = get_db()
        db.execute("INSERT INTO pricing_rules (mode, model, resolution, points_per_image, enabled, media_type, duration_tier) VALUES ('video', '*', '720p', 5, 1, 'video', '6s')")
        task_id = create_generation_task(
            user_id=user_id,
            prompt="short video",
            mode="video",
            media_type="video",
            provider_id=provider_id,
            ratio="16:9",
            resolution="720p",
            actual_size="1280x720",
            quality="auto",
            output_format="mp4",
            count=1,
            cost=5,
            model="grok-imagine-video",
            duration_seconds=6,
        )
        db.commit()

    monkeypatch.setattr("huishi.generation_queue.create_video_task", lambda provider, payload: VideoTask("remote-1"))
    monkeypatch.setattr("huishi.generation_queue.poll_video_task", lambda provider, task_id: VideoTaskState("completed", url="https://cdn.example/video.mp4"))
    monkeypatch.setattr("huishi.generation_queue.download_video_result", lambda provider, state: b"video-bytes")
    with app.app_context():
        run_video_generation_task(app, task_id)
        task = get_generation_task(task_id)
        record = get_db().execute("SELECT * FROM records WHERE id = ?", (task["record_id"],)).fetchone()
        assert task["status"] == "succeeded"
        assert task["media_type"] == "video"
        assert record["asset_source"] == "video"
        assert Path(app.config["OUTPUT_DIR"], Path(record["image_path"]).name).read_bytes() == b"video-bytes"
