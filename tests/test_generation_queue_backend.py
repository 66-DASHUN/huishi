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
    monkeypatch.setattr("huishi.generation_queue.get_rq_queue", lambda flask_app: FakeQueue())

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
    monkeypatch.setattr("huishi.generation_queue.get_rq_queue", lambda flask_app: FakeQueue())

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
