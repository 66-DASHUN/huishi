from __future__ import annotations

from pathlib import Path

import pytest

from app import create_app
from huishi.db import init_db


@pytest.fixture()
def app(tmp_path: Path):
    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "test.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"
    app.config["GENERATION_INLINE"] = False
    with app.app_context():
        init_db()
    return app


def test_enqueue_generation_task_uses_rq_backend(app, monkeypatch):
    enqueued = {}

    class FakeQueue:
        def enqueue(self, func, app_import_path, task_id, cleanup_paths, job_timeout, result_ttl, failure_ttl):
            enqueued.update(
                {
                    "func": func,
                    "app_import_path": app_import_path,
                    "task_id": task_id,
                    "cleanup_paths": cleanup_paths,
                    "job_timeout": job_timeout,
                    "result_ttl": result_ttl,
                    "failure_ttl": failure_ttl,
                }
            )
            return "job-1"

    app.config["GENERATION_QUEUE_BACKEND"] = "rq"
    app.config["RQ_JOB_TIMEOUT_SECONDS"] = 600
    app.config["GENERATION_LIMIT_WAIT_TIMEOUT_SECONDS"] = 100
    app.config["IMAGE_API_TIMEOUT"] = 20
    app.config["RQ_RESULT_TTL_SECONDS"] = 60
    app.config["RQ_FAILURE_TTL_SECONDS"] = 86400
    monkeypatch.setattr("huishi.generation_queue.get_rq_queue", lambda flask_app, queue_name=None: FakeQueue())

    from huishi.generation_queue import enqueue_generation_task, run_generation_task_from_import_path

    enqueue_generation_task(app, 42, ["/static/uploads/ref.png"])

    assert enqueued == {
        "func": run_generation_task_from_import_path,
        "app_import_path": "app:create_app",
        "task_id": 42,
        "cleanup_paths": ["/static/uploads/ref.png"],
        "job_timeout": 600,
        "result_ttl": 60,
        "failure_ttl": 86400,
    }


def test_enqueue_generation_task_raises_rq_timeout_to_cover_limit_wait_and_api_timeout(app, monkeypatch):
    enqueued = {}

    class FakeQueue:
        def enqueue(self, _func, _app_import_path, _task_id, _cleanup_paths, **kwargs):
            enqueued["job_timeout"] = kwargs["job_timeout"]
            return "job-1"

    app.config["GENERATION_QUEUE_BACKEND"] = "rq"
    app.config["RQ_JOB_TIMEOUT_SECONDS"] = 900
    app.config["GENERATION_LIMIT_WAIT_TIMEOUT_SECONDS"] = 840
    app.config["IMAGE_API_TIMEOUT"] = 180
    monkeypatch.setattr("huishi.generation_queue.get_rq_queue", lambda flask_app, queue_name=None: FakeQueue())

    from huishi.generation_queue import enqueue_generation_task

    enqueue_generation_task(app, 42, [])

    assert enqueued["job_timeout"] >= 1080


def test_rq_backend_requires_redis_url(app):
    app.config["GENERATION_QUEUE_BACKEND"] = "rq"
    app.config["REDIS_URL"] = ""

    from huishi.generation_queue import get_rq_queue

    with pytest.raises(RuntimeError, match="HUISHI_REDIS_URL"):
        get_rq_queue(app)


def test_redis_generation_limiter_ttl_uses_effective_rq_timeout(app, monkeypatch):
    captured = {}

    class FakeRedisLimiter:
        def __init__(self, _redis, *, active_ttl_seconds, **_kwargs):
            captured["active_ttl_seconds"] = active_ttl_seconds

    app.config["REDIS_URL"] = "redis://127.0.0.1:6379/0"
    app.config["RQ_JOB_TIMEOUT_SECONDS"] = 900
    app.config["GENERATION_LIMIT_WAIT_TIMEOUT_SECONDS"] = 840
    app.config["IMAGE_API_TIMEOUT"] = 180
    monkeypatch.setattr("huishi.generation_queue.RedisGenerationLimiter", FakeRedisLimiter)

    from huishi.generation_queue import get_generation_limiter

    get_generation_limiter(app)

    assert captured["active_ttl_seconds"] >= 1080


def test_video_task_routes_to_the_dedicated_video_queue(app, monkeypatch):
    """视频必须进 huishi-video，而不是和图片抢同一条队列。

    为什么要有这条：视频会在 worker 里轮询上游，单条最长占用槽位 20 分钟，
    而图片只要几十秒。同队列时几个人提交视频就能把图片生成的槽位全占满。
    """
    picked = {}

    class FakeQueue:
        def enqueue(self, *_args, **_kwargs):
            return "job-1"

    def fake_get_rq_queue(_app, queue_name=None):
        picked["queue_name"] = queue_name
        return FakeQueue()

    monkeypatch.setattr("huishi.generation_queue.get_rq_queue", fake_get_rq_queue)
    app.config["GENERATION_QUEUE_BACKEND"] = "rq"
    app.config["RQ_QUEUE_NAME"] = "huishi-generation"
    app.config["RQ_VIDEO_QUEUE_NAME"] = "huishi-video"

    from huishi.db import get_db
    from huishi.generation_queue import enqueue_generation_task
    from huishi.records import create_generation_task

    with app.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO users (username, email, password_hash, role, email_verified, points, created_at) "
            "VALUES ('route-video', '', 'h', 'user', 1, 100, 'now')"
        )
        db.commit()
        user_id = int(db.execute("SELECT id FROM users WHERE username='route-video'").fetchone()["id"])
        video_task = create_generation_task(
            user_id=user_id, prompt="v", mode="video", ratio="16:9", resolution="720p",
            actual_size="1280x720", quality="auto", output_format="mp4", count=1, cost=0,
            media_type="video",
        )
        image_task = create_generation_task(
            user_id=user_id, prompt="i", mode="text", ratio="1:1", resolution="2K",
            actual_size="2048x2048", quality="auto", output_format="png", count=1, cost=0,
            media_type="image",
        )
        db.commit()

    enqueue_generation_task(app, video_task, [])
    assert picked["queue_name"] == "huishi-video", picked

    enqueue_generation_task(app, image_task, [])
    assert picked["queue_name"] == "huishi-generation", picked


def test_enqueue_outside_app_context_still_routes_correctly(app, monkeypatch):
    """没有 app context 时也要正确分流。

    这是真缺陷的回归测试：早先的实现在无 context 时读不到任务行，
    被 except 吞掉后**静默回退到图片队列**，视频分流形同虚设。
    """
    picked = {}

    class FakeQueue:
        def enqueue(self, *_args, **_kwargs):
            return "job-1"

    def fake_get_rq_queue(_app, queue_name=None):
        picked["queue_name"] = queue_name
        return FakeQueue()

    monkeypatch.setattr("huishi.generation_queue.get_rq_queue", fake_get_rq_queue)
    app.config["GENERATION_QUEUE_BACKEND"] = "rq"
    app.config["RQ_VIDEO_QUEUE_NAME"] = "huishi-video"

    from huishi.db import get_db
    from huishi.generation_queue import enqueue_generation_task
    from huishi.records import create_generation_task

    with app.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO users (username, email, password_hash, role, email_verified, points, created_at) "
            "VALUES ('route-nocontext', '', 'h', 'user', 1, 100, 'now')"
        )
        db.commit()
        user_id = int(db.execute("SELECT id FROM users WHERE username='route-nocontext'").fetchone()["id"])
        video_task = create_generation_task(
            user_id=user_id, prompt="v2", mode="video", ratio="16:9", resolution="720p",
            actual_size="1280x720", quality="auto", output_format="mp4", count=1, cost=0,
            media_type="video",
        )
        db.commit()

    # 关键：在 with app.app_context() **之外**调用
    enqueue_generation_task(app, video_task, [])
    assert picked["queue_name"] == "huishi-video", picked
