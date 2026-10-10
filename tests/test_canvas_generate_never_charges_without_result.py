"""画布生图：结果不可读时不得扣费。

背景（2026-10-10）：``canvas_generate`` 原先的顺序是
``_finalize_generation``（建记录 + 扣费）→ ``_canvas_record_data_url`` 取图。
后者在文件缺失时**静默返回空字符串**，被调用方跳过，接口仍然回
``{"ok": true, "images": [], "cost": N, "balance": 已扣}``。

而画布前端 ``host-image.ts`` 对空 images 会抛
"主站生图代理失败，请稍后重试"。于是用户看到的是失败提示，积分却已经扣了。

生产实测该路径尚未触发（17 条扣费记录的文件全部存在），属**潜在缺陷**：
文件因手工清理、备份恢复错配或写入中断而缺失时就会发生。

这组测试钉住两件事：
1. 结果读不出来 → 接口失败且**一分不扣**、**不建记录**；
2. 正常路径的扣费行为不变（顺序调整不能改变成功时的结果）。
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


def _fake_generate_pointing_at_missing_file(**_kwargs):
    """模拟"上游说成功了，但文件并不在磁盘上"。

    这正是缺陷的触发形态：image_path 有值，ensure_local 抛 FileNotFoundError。
    """
    return {
        "image_path": "/static/uploads/definitely_not_on_disk.png",
        "image_paths": ["/static/uploads/definitely_not_on_disk.png"],
        "actual_size": "1024x1024",
        "model_source": "gpt-image-2",
        "elapsed_seconds": 0.01,
    }


def test_missing_result_file_fails_without_charging(app, monkeypatch):
    """核心契约：读不到结果 → 500，且不扣费、不建记录。"""
    monkeypatch.setattr(
        "huishi.routes_workspace.generate_image_with_failover",
        _fake_generate_pointing_at_missing_file,
    )
    with app.app_context():
        user_id, token = _setup_user_and_provider()

    with app.test_client() as client:
        response = client.post(
            "/api/canvas/generate",
            json={"token": token, "prompt": "a cat", "resolution": "2K", "model": "gpt-image-2"},
            headers={"Origin": "http://127.0.0.1:3000"},
        )

    assert response.status_code == 500, response.get_json()
    body = response.get_json()
    assert body["ok"] is False
    assert "未扣费" in body["error"]

    with app.app_context():
        balance = get_db().execute("SELECT points FROM users WHERE id = ?", (user_id,)).fetchone()["points"]
        assert balance == 50, "结果读不出来时余额必须原封不动"
        ledger = get_db().execute(
            "SELECT COUNT(*) AS value FROM point_ledger WHERE user_id = ?", (user_id,)
        ).fetchone()["value"]
        assert ledger == 0, "不得留下任何扣费流水"
        records = get_db().execute(
            "SELECT COUNT(*) AS value FROM records WHERE user_id = ?", (user_id,)
        ).fetchone()["value"]
        assert records == 0, "不得留下指向不存在文件的记录"


def test_readable_result_still_charges_normally(app, monkeypatch):
    """正常路径不受影响：能读到图就照常扣费并返回 data URL。"""
    def fake_generate(**kwargs):
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

    monkeypatch.setattr("huishi.routes_workspace.generate_image_with_failover", fake_generate)
    with app.app_context():
        user_id, token = _setup_user_and_provider(points=50, username="readable-result-user")

    with app.test_client() as client:
        response = client.post(
            "/api/canvas/generate",
            json={"token": token, "prompt": "a cat", "resolution": "2K", "model": "gpt-image-2"},
            headers={"Origin": "http://127.0.0.1:3000"},
        )

    assert response.status_code == 200
    body = response.get_json()
    assert body["ok"] is True
    assert len(body["images"]) == 1
    assert body["images"][0]["dataUrl"].startswith("data:image/")
    assert body["cost"] > 0
    assert body["balance"] == 50 - body["cost"]


def test_active_task_limit_rejects_before_calling_upstream(app, monkeypatch):
    """并发上限：已有排队任务时必须在调上游**之前**拒绝，不花上游的钱。"""
    called = {"upstream": False}

    def must_not_be_called(**_kwargs):
        called["upstream"] = True
        raise AssertionError("额度已满时不得调用上游")

    monkeypatch.setattr("huishi.routes_workspace.generate_image_with_failover", must_not_be_called)
    with app.app_context():
        user_id, token = _setup_user_and_provider(points=50, username="busy-user")
        get_db().execute(
            "INSERT INTO generation_tasks "
            "(user_id, prompt, mode, ratio, resolution, actual_size, quality, output_format, "
            " count, cost, status, created_at, updated_at) "
            "VALUES (?, 'busy', 'text', '1:1', '2K', '2048x2048', 'auto', 'png', 1, 0, 'queued', 'now', 'now')",
            (user_id,),
        )
        get_db().execute(
            "INSERT INTO generation_tasks "
            "(user_id, prompt, mode, ratio, resolution, actual_size, quality, output_format, "
            " count, cost, status, created_at, updated_at) "
            "VALUES (?, 'busy2', 'text', '1:1', '2K', '2048x2048', 'auto', 'png', 1, 0, 'running', 'now', 'now')",
            (user_id,),
        )
        get_db().commit()

    with app.test_client() as client:
        response = client.post(
            "/api/canvas/generate",
            json={"token": token, "prompt": "a cat", "resolution": "2K", "model": "gpt-image-2"},
            headers={"Origin": "http://127.0.0.1:3000"},
        )

    assert response.status_code == 400
    assert called["upstream"] is False
    with app.app_context():
        balance = get_db().execute("SELECT points FROM users WHERE id = ?", (user_id,)).fetchone()["points"]
        assert balance == 50


def test_canvas_locks_user_before_checking_balance_and_slot(app, monkeypatch):
    """并发契约：必须先锁用户行，再校验余额与额度。

    与工作台/音频/视频保持同一顺序（见 ``test_workspace_generation_flow.py``
    里的同名约束）。顺序反了的话，两个并发请求会同时通过无锁预检，
    各自去调上游（真实成本已发生），最后只有先到的那个能扣到费——
    差额由管理员的 Key 承担。

    这里断言的是**调用顺序**，所以用打点而不是看结果。
    """
    order: list[str] = []

    def fake_generate(**_kwargs):
        order.append("upstream")
        return {
            "image_path": "/static/uploads/ok_order.png",
            "image_paths": ["/static/uploads/ok_order.png"],
            "actual_size": "1024x1024",
            "model_source": "gpt-image-2",
            "elapsed_seconds": 0.01,
        }

    def track_lock(_user_id):
        order.append("lock")

    def track_points(_user_id, _cost):
        order.append("points")

    def track_slot(_user_id):
        order.append("slot")

    def make_readable(_paths):
        from flask import current_app

        output_dir: Path = current_app.config["OUTPUT_DIR"]
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "ok_order.png").write_bytes(PNG_BYTES)
        return ["data:image/png;base64,AAAA"]

    monkeypatch.setattr("huishi.routes_workspace.generate_image_with_failover", fake_generate)
    monkeypatch.setattr("huishi.routes_workspace.lock_user_for_update", track_lock)
    monkeypatch.setattr("huishi.routes_workspace.require_available_generation_points", track_points)
    monkeypatch.setattr("huishi.routes_workspace.require_active_generation_task_slot", track_slot)
    monkeypatch.setattr("huishi.routes_workspace._canvas_read_result_data_urls", make_readable)

    with app.app_context():
        _user_id, token = _setup_user_and_provider(points=50, username="lock-order-user")

    with app.test_client() as client:
        response = client.post(
            "/api/canvas/generate",
            json={"token": token, "prompt": "lock order", "resolution": "2K", "model": "gpt-image-2"},
            headers={"Origin": "http://127.0.0.1:3000"},
        )

    assert response.status_code == 200, response.get_json()
    # 注意 slot 会出现两次：一次是上游之前的廉价前置检查，一次是锁内的权威校验。
    # 这里要断的是**锁内那次**，所以取最后一次出现。
    assert "lock" in order and "points" in order and order.count("slot") >= 2, order
    assert order.index("lock") < order.index("points"), order
    assert order.index("lock") < len(order) - 1 - order[::-1].index("slot"), order
    # 前置检查在上游之前（省成本），权威结算在上游之后（拿结果才扣费）
    assert order.index("slot") < order.index("upstream"), order
    assert order.index("upstream") < order.index("lock"), order


def test_canvas_generate_is_rate_limited_per_user(app, monkeypatch):
    """画布生图必须有单用户提交频率闸门。

    为什么需要：画布在 Web 线程里**同步等上游**（生产埋点实测生图平均 22.9s、
    最长 43.8s），而 gunicorn 只有 `-w 2 --threads 4` 共 8 个单元。工作台走
    RQ 队列 + RedisGenerationLimiter 有统一闸门，画布此前一个都没有——
    一个用户连点几下就能把 Web 池占满，其他用户全部被拖住。

    这里把上限设成 2、窗口 60 秒，第 3 次提交必须 429，且**不扣费、不调上游**。
    """
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

    monkeypatch.setattr("huishi.routes_workspace.generate_image_with_failover", fake_generate)

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
            resp = client.post(
                "/api/canvas/generate",
                json={"token": token, "prompt": "p", "resolution": "2K", "model": "gpt-image-2"},
                headers={"Origin": "http://127.0.0.1:3000"},
            )
            codes.append(resp.status_code)

    assert codes[:2] == [200, 200], codes
    assert codes[2] == 429, codes
    # 被限流的那次不得消耗上游成本
    assert upstream_calls["n"] == 2, upstream_calls
