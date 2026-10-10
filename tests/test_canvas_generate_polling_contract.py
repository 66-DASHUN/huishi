"""画布生图轮询契约：主站已改为异步任务，前端必须提交后轮询。

背景：`/api/canvas/generate` 从"Web 线程里同步等上游 23 秒"改成
"建任务 → 入队 → 立即返回 202"。前端 `host-image.ts` 随之改为
提交 + 轮询 `/api/canvas/generate/<task_id>`。

这里用假 fetch 钉住三件事：
1. 提交只发一次 POST，且请求体带正确字段
2. 结果从查询端点取，成功时返回 data URL
3. **失败与"成功但读不到图"都必须抛出**，不能静默返回空数组
   （后者正是"扣了费却什么都没有"的前端表现）
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from app import create_app
from huishi.canvas_session import issue_canvas_session_token
from huishi.db import get_db

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 64


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


def _user_and_token(points: int = 100, username: str = "poll-user") -> tuple[int, str]:
    from huishi.providers import save_provider

    if get_db().execute("SELECT id FROM api_providers WHERE name='poll-channel'").fetchone() is None:
        save_provider(
            provider_type="image",
            name="poll-channel",
            base_url="https://image.example",
            api_key="k",
            model="gpt-image-2",
            api_format="openai",
            priority=10,
            enabled=True,
            resolutions=["1K", "2K", "4K"],
            models=[{"id": "gpt-image-2", "label": "GPT Image 2"}],
        )
    cursor = get_db().execute(
        "INSERT INTO users (username, email, password_hash, role, email_verified, points, created_at) "
        "VALUES (?, '', 'h', 'user', 1, ?, 'now')",
        (username, points),
    )
    get_db().commit()
    uid = int(cursor.lastrowid)
    row = get_db().execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    token, _ = issue_canvas_session_token(dict(row))
    return uid, token


def _fake_generate(**_kwargs):
    from flask import current_app

    out: Path = current_app.config["OUTPUT_DIR"]
    out.mkdir(parents=True, exist_ok=True)
    (out / "poll_result.png").write_bytes(PNG_BYTES)
    return {
        "image_path": "/static/uploads/poll_result.png",
        "image_paths": ["/static/uploads/poll_result.png"],
        "actual_size": "1024x1024",
        "model_source": "gpt-image-2",
        "elapsed_seconds": 0.01,
    }


def test_submit_returns_task_without_waiting_for_upstream(app, monkeypatch):
    """提交必须立刻返回任务号（这就是队列化的目的）。"""
    monkeypatch.setattr("huishi.generation_queue.generate_image_with_failover", _fake_generate)
    with app.app_context():
        user_id, token = _user_and_token()

    with app.test_client() as client:
        resp = client.post(
            "/api/canvas/generate",
            json={"token": token, "prompt": "p", "resolution": "2K", "model": "gpt-image-2"},
            headers={"Origin": "http://127.0.0.1:3000"},
        )

    assert resp.status_code == 202, resp.get_json()
    body = resp.get_json()
    assert body["ok"] is True
    assert body["task"]["id"]
    # 响应体不应包含图片——图片在查询端点
    assert "images" not in body


def test_status_endpoint_returns_data_url_when_succeeded(app, monkeypatch):
    """查询端点：任务成功时返回 data URL。"""
    monkeypatch.setattr("huishi.generation_queue.generate_image_with_failover", _fake_generate)
    with app.app_context():
        _uid, token = _user_and_token(points=100, username="status-user")

    headers = {"Origin": "http://127.0.0.1:3000", "X-Canvas-Session": token}
    with app.test_client() as client:
        submit = client.post(
            "/api/canvas/generate",
            json={"token": token, "prompt": "p", "resolution": "2K", "model": "gpt-image-2"},
            headers=headers,
        )
        task_id = submit.get_json()["task"]["id"]
        status = client.get(f"/api/canvas/generate/{task_id}", headers=headers)

    assert status.status_code == 200, status.get_json()
    body = status.get_json()
    assert body["task"]["status"] == "succeeded"
    assert len(body["images"]) == 1
    assert body["images"][0]["dataUrl"].startswith("data:image/")


def test_status_marks_images_unavailable_instead_of_empty_success(app, monkeypatch):
    """任务成功但结果文件读不出来：必须给 images_unavailable，不能装成成功。"""
    def fake_generate_to_nowhere(**_kwargs):
        return {
            "image_path": "/static/uploads/never_written.png",
            "image_paths": ["/static/uploads/never_written.png"],
            "actual_size": "1024x1024",
            "model_source": "gpt-image-2",
            "elapsed_seconds": 0.01,
        }

    monkeypatch.setattr(
        "huishi.generation_queue.generate_image_with_failover", fake_generate_to_nowhere
    )
    with app.app_context():
        _uid, token = _user_and_token(points=100, username="unavailable-user")

    headers = {"Origin": "http://127.0.0.1:3000", "X-Canvas-Session": token}
    with app.test_client() as client:
        submit = client.post(
            "/api/canvas/generate",
            json={"token": token, "prompt": "p", "resolution": "2K", "model": "gpt-image-2"},
            headers=headers,
        )
        task_id = submit.get_json()["task"]["id"]
        status = client.get(f"/api/canvas/generate/{task_id}", headers=headers)

    body = status.get_json()
    assert body["task"]["status"] == "succeeded"
    assert body.get("images_unavailable") is True
    assert body["images"] == []


def test_status_requires_a_token(app):
    """查询端点是 GET、无 body，必须能从头部取到 token，否则 401 而非 404。"""
    with app.test_client() as client:
        resp = client.get(
            "/api/canvas/generate/1",
            headers={"Origin": "http://127.0.0.1:3000"},
        )
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "missing_token"
