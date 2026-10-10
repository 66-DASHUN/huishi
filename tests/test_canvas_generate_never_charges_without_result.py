"""画布生图（入队版）的计费与并发契约。

历史：2026-10-10 起 `/api/canvas/generate` 由「同步等上游」改为「建任务并入队」。
这组测试随之改写，钉住三件事：

1. **提交阶段被拒时一分不扣、不建任务**（余额不足 / 额度已满 / 限流）。
2. **成功路径照常扣费一次**，记录带 `asset_source='canvas'`。
3. **结果读不出来时不得谎报成功**——查询端点给出 `images_unavailable`，
   前端据此抛错而不是静默返回空图。

（队列化本身还解决了原先「Web 线程 + DB 连接被长请求独占 23 秒」的容量问题，
那部分由 test_canvas_generate_proxy 里的协议断言覆盖。）
"""
from __future__ import annotations

import base64
from pathlib import Path

import pytest

from app import create_app
from huishi.canvas_session import issue_canvas_session_token
from huishi.db import get_db

PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwADhQGAWjR9awAAAABJRU5ErkJggg=="
)


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


def _setup_user_and_provider(points: int = 50, username: str = "no-result-user") -> tuple[int, str]:
    from huishi.providers import save_provider

    existing = get_db().execute(
        "SELECT id FROM api_providers WHERE name='canvas-no-result-channel'"
    ).fetchone()
    if existing is None:
        save_provider(
            provider_type="image",
            name="canvas-no-result-channel",
            base_url="https://image.example",
            api_key="platform-key",
            model="gpt-image-2",
            api_format="openai",
            priority=10,
            enabled=True,
            resolutions=["1K", "2K", "4K"],
            models=[{"id": "gpt-image-2", "label": "GPT Image 2"}],
        )
    cursor = get_db().execute(
        "INSERT INTO users (username, email, password_hash, role, email_verified, points, created_at) "
        "VALUES (?, '', 'hash', 'user', 1, ?, 'now')",
        (username, points),
    )
    get_db().commit()
    user_id = int(cursor.lastrowid)
    row = get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    token, _ = issue_canvas_session_token(dict(row))
    return user_id, token


def _submit(client, token: str, **overrides):
    body = {"token": token, "prompt": "a cat", "resolution": "2K", "model": "gpt-image-2"}
    body.update(overrides)
    return client.post(
        "/api/canvas/generate",
        json=body,
        headers={"Origin": "http://127.0.0.1:3000"},
    )


def _fetch(client, task_id, token: str):
    """查询任务。

    查询是 **GET**、没有 body，而 `canvas_api_user` 只从
    `X-Canvas-Session` 头 / body / 查询参数取 token——所以必须显式带头，
    否则会拿到 401 missing_token（而不是"任务不存在"）。
    """
    return client.get(
        f"/api/canvas/generate/{task_id}",
        headers={"Origin": "http://127.0.0.1:3000", "X-Canvas-Session": token},
    )


def _fake_generate_pointing_at_missing_file(**_kwargs):
    """上游"成功"了，但文件并不在磁盘上——这正是取图失败的形态。"""
    return {
        "image_path": "/static/uploads/definitely_not_on_disk.png",
        "image_paths": ["/static/uploads/definitely_not_on_disk.png"],
        "actual_size": "1024x1024",
        "model_source": "gpt-image-2",
        "elapsed_seconds": 0.01,
    }


def test_missing_result_is_reported_not_silently_empty(app, monkeypatch):
    """任务成功但结果文件缺失：必须给出 images_unavailable，不能回空数组冒充成功。

    这条是"扣了费却没有图"的兜底：记录与扣费都已经发生（worker 确实出图了），
    所以这里不改状态、不退款，但要**明确告诉前端**拿不到图，
    而不是回 `images: []` 让前端以为"生成成功但没有图"。
    """
    monkeypatch.setattr(
        "huishi.generation_queue.generate_image_with_failover",
        _fake_generate_pointing_at_missing_file,
    )
    with app.app_context():
        user_id, token = _setup_user_and_provider()

    with app.test_client() as client:
        submit = _submit(client, token)
        assert submit.status_code == 202, submit.get_json()
        task_id = submit.get_json()["task"]["id"]
        status = _fetch(client, task_id, token)

    assert status.status_code == 200
    body = status.get_json()
    assert body["task"]["status"] == "succeeded"
    assert body.get("images_unavailable") is True
    assert body["images"] == []

    # 计费语义：任务确实成功，钱照扣（不是"重复扣费"，是这一单真实发生）
    with app.app_context():
        ledger = get_db().execute(
            "SELECT COUNT(*) AS value FROM point_ledger WHERE user_id = ?", (user_id,)
        ).fetchone()["value"]
        assert ledger == 1


def test_readable_result_charges_once_and_tags_canvas(app, monkeypatch):
    """正常路径：扣费一次，记录标成 canvas。"""
    def fake_generate(**_kwargs):
        from flask import current_app

        output_dir: Path = current_app.config["OUTPUT_DIR"]
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "ok_result.png").write_bytes(PNG_BYTES)
        return {
            "image_path": "/static/uploads/ok_result.png",
            "image_paths": ["/static/uploads/ok_result.png"],
            "actual_size": "1024x1024",
            "model_source": "gpt-image-2",
            "elapsed_seconds": 0.01,
        }

    monkeypatch.setattr("huishi.generation_queue.generate_image_with_failover", fake_generate)
    with app.app_context():
        user_id, token = _setup_user_and_provider(points=50, username="readable-result-user")

    with app.test_client() as client:
        submit = _submit(client, token)
        assert submit.status_code == 202, submit.get_json()
        payload = submit.get_json()
        status = _fetch(client, payload["task"]["id"], token)

    assert payload["cost"] > 0
    body = status.get_json()
    assert not body.get("images_unavailable")
    assert len(body["images"]) == 1
    assert body["images"][0]["dataUrl"].startswith("data:image/")
    assert body["balance"] == 50 - payload["cost"]

    with app.app_context():
        record = get_db().execute(
            "SELECT asset_source, points_charged FROM records WHERE user_id = ?", (user_id,)
        ).fetchone()
        assert record["asset_source"] == "canvas"
        assert record["points_charged"] == payload["cost"]
        ledger = get_db().execute(
            "SELECT COUNT(*) AS value FROM point_ledger WHERE user_id = ?", (user_id,)
        ).fetchone()["value"]
        assert ledger == 1, "一次生成只能有一条扣费流水"


def test_active_task_limit_rejects_before_enqueue(app, monkeypatch):
    """并发额度：已有排队任务时必须在建任务前拒绝，不消耗上游成本。"""
    called = {"upstream": False}

    def must_not_be_called(**_kwargs):
        called["upstream"] = True
        raise AssertionError("额度已满时不得调用上游")

    monkeypatch.setattr("huishi.generation_queue.generate_image_with_failover", must_not_be_called)
    with app.app_context():
        user_id, token = _setup_user_and_provider(points=50, username="busy-user")
        for status in ("queued", "running"):
            get_db().execute(
                "INSERT INTO generation_tasks "
                "(user_id, prompt, mode, ratio, resolution, actual_size, quality, output_format, "
                " count, cost, status, created_at, updated_at) "
                "VALUES (?, ?, 'text', '1:1', '2K', '2048x2048', 'auto', 'png', 1, 0, ?, 'now', 'now')",
                (user_id, f"busy-{status}", status),
            )
        get_db().commit()

    with app.test_client() as client:
        response = _submit(client, token)

    assert response.status_code == 400
    assert called["upstream"] is False
    with app.app_context():
        balance = get_db().execute("SELECT points FROM users WHERE id = ?", (user_id,)).fetchone()["points"]
        assert balance == 50
        # 不得留下新任务
        tasks = get_db().execute(
            "SELECT COUNT(*) AS value FROM generation_tasks WHERE user_id = ?", (user_id,)
        ).fetchone()["value"]
        assert tasks == 2


def test_canvas_generate_is_rate_limited_per_user(app, monkeypatch):
    """单用户提交频率闸门：上限 2 时第 3 次必须 429，且不建任务、不调上游。"""
    upstream_calls = {"n": 0}

    def fake_generate(**_kwargs):
        upstream_calls["n"] += 1
        return {
            "image_path": "/static/uploads/rate.png",
            "image_paths": ["/static/uploads/rate.png"],
            "actual_size": "1024x1024",
            "model_source": "gpt-image-2",
            "elapsed_seconds": 0.01,
        }

    monkeypatch.setattr("huishi.generation_queue.generate_image_with_failover", fake_generate)

    def make_readable(_paths):
        from flask import current_app

        output_dir: Path = current_app.config["OUTPUT_DIR"]
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "rate.png").write_bytes(PNG_BYTES)
        return ["data:image/png;base64,AAAA"]

    monkeypatch.setattr("huishi.routes_workspace._canvas_read_result_data_urls", make_readable)

    app.config["RATE_LIMITING_ENABLED"] = True
    app.config["CANVAS_GENERATE_RATE_LIMIT"] = 2
    app.config["CANVAS_GENERATE_RATE_WINDOW_SECONDS"] = 60

    with app.app_context():
        user_id, token = _setup_user_and_provider(points=200, username="ratelimit-user")

    codes = []
    with app.test_client() as client:
        for _ in range(3):
            codes.append(_submit(client, token).status_code)

    assert codes[:2] == [202, 202], codes
    assert codes[2] == 429, codes
    assert upstream_calls["n"] == 2, upstream_calls


def test_status_endpoint_rejects_another_users_task(app, monkeypatch):
    """别人的任务号必须 404——任务查询按 user_id 过滤。"""
    def fake_generate(**_kwargs):
        from flask import current_app

        output_dir: Path = current_app.config["OUTPUT_DIR"]
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "own.png").write_bytes(PNG_BYTES)
        return {
            "image_path": "/static/uploads/own.png",
            "image_paths": ["/static/uploads/own.png"],
            "actual_size": "1024x1024",
            "model_source": "gpt-image-2",
            "elapsed_seconds": 0.01,
        }

    monkeypatch.setattr("huishi.generation_queue.generate_image_with_failover", fake_generate)
    with app.app_context():
        _owner_id, owner_token = _setup_user_and_provider(points=50, username="task-owner")
        _other_id, other_token = _setup_user_and_provider(points=50, username="task-other")

    with app.test_client() as client:
        submit = _submit(client, owner_token)
        assert submit.status_code == 202, submit.get_json()
        task_id = submit.get_json()["task"]["id"]
        # 换一个用户的会话去查同一个任务号
        # 用另一个用户的会话去查同一个任务号
        stolen = client.get(
            f"/api/canvas/generate/{task_id}",
            headers={"Origin": "http://127.0.0.1:3000", "X-Canvas-Session": other_token},
        )

    assert stolen.status_code == 404
