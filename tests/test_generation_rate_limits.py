from __future__ import annotations

import pytest

from huishi.generation_limits import InMemoryGenerationLimiter, RedisGenerationLimiter


def test_generation_worker_marks_task_failed_when_limiter_rejects(tmp_path, monkeypatch):
    from app import create_app
    from huishi.db import get_db, init_db
    from huishi.generation_limits import GenerationLimitError
    from huishi.generation_queue import run_generation_task

    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "test.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"
    with app.app_context():
        init_db()
        user_id = get_db().execute(
            """
            INSERT INTO users (username, email, password_hash, role, email_verified, points, created_at)
            VALUES ('limited', '', 'hash', 'user', 1, 20, 'now')
            """
        ).lastrowid
        task_id = get_db().execute(
            """
            INSERT INTO generation_tasks
            (user_id, prompt, mode, ratio, resolution, actual_size, quality, output_format, count, cost, status, reference_paths, created_at, updated_at)
            VALUES (?, 'limited task', 'text', '16:9', '2K', '2560x1440', 'auto', 'png', 1, 2, 'queued', '[]', 'now', 'now')
            """,
            (user_id,),
        ).lastrowid
        get_db().commit()

    class RejectingLimiter:
        def acquire(self):
            raise GenerationLimitError("generation upstream RPM limit reached")

    monkeypatch.setattr("huishi.generation_queue.get_generation_limiter", lambda _app: RejectingLimiter())
    monkeypatch.setattr("huishi.generation_queue.generate_image_with_failover", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("should not call upstream")))

    run_generation_task(app, task_id, [])

    with app.app_context():
        task = get_db().execute("SELECT status, error_message FROM generation_tasks WHERE id = ?", (task_id,)).fetchone()
        assert task["status"] == "failed"
        assert "RPM" in task["error_message"]


def test_generation_worker_waits_for_limiter_capacity(tmp_path, monkeypatch):
    from app import create_app
    from huishi.db import get_db, init_db
    from huishi.generation_limits import GenerationLimitError, GenerationLease
    from huishi.generation_queue import run_generation_task

    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "test.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"
    app.config["GENERATION_LIMIT_WAIT_TIMEOUT_SECONDS"] = 2
    app.config["GENERATION_LIMIT_WAIT_SLEEP_SECONDS"] = 0.01
    with app.app_context():
        init_db()
        user_id = get_db().execute(
            """
            INSERT INTO users (username, email, password_hash, role, email_verified, points, created_at)
            VALUES ('waiter', '', 'hash', 'user', 1, 20, 'now')
            """
        ).lastrowid
        task_id = get_db().execute(
            """
            INSERT INTO generation_tasks
            (user_id, prompt, mode, ratio, resolution, actual_size, quality, output_format, count, cost, status, reference_paths, created_at, updated_at)
            VALUES (?, 'wait task', 'text', '16:9', '2K', '2560x1440', 'auto', 'png', 1, 2, 'queued', '[]', 'now', 'now')
            """,
            (user_id,),
        ).lastrowid
        get_db().commit()

    class FlakyLimiter:
        def __init__(self):
            self.calls = 0

        def acquire(self, **_kwargs):
            self.calls += 1
            if self.calls == 1 and not _kwargs.get("block"):
                raise GenerationLimitError("generation upstream RPM limit reached")
            if self.calls == 1:
                self.calls += 1
            return GenerationLease(lambda: None)

    limiter = FlakyLimiter()
    monkeypatch.setattr("huishi.generation_queue.get_generation_limiter", lambda _app: limiter)
    monkeypatch.setattr(
        "huishi.generation_queue.generate_image_with_failover",
        lambda **_kwargs: {
            "image_path": "/static/uploads/generated.png",
            "image_paths": ["/static/uploads/generated.png"],
            "actual_size": "2560x1440",
            "model_source": "fake",
            "elapsed_seconds": 0.1,
        },
    )

    run_generation_task(app, task_id, [])

    with app.app_context():
        task = get_db().execute("SELECT status FROM generation_tasks WHERE id = ?", (task_id,)).fetchone()
        assert task["status"] == "succeeded"
    assert limiter.calls == 2


def test_generation_worker_reports_limiter_wait_timeout(tmp_path, monkeypatch):
    from app import create_app
    from huishi.db import get_db, init_db
    from huishi.generation_limits import GenerationLimitTimeout
    from huishi.generation_queue import run_generation_task

    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "test.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"
    app.config["GENERATION_LIMIT_WAIT_TIMEOUT_SECONDS"] = 0.01
    app.config["GENERATION_LIMIT_WAIT_SLEEP_SECONDS"] = 0.01
    with app.app_context():
        init_db()
        user_id = get_db().execute(
            """
            INSERT INTO users (username, email, password_hash, role, email_verified, points, created_at)
            VALUES ('timeout-user', '', 'hash', 'user', 1, 20, 'now')
            """
        ).lastrowid
        task_id = get_db().execute(
            """
            INSERT INTO generation_tasks
            (user_id, prompt, mode, ratio, resolution, actual_size, quality, output_format, count, cost, status, reference_paths, created_at, updated_at)
            VALUES (?, 'timeout task', 'text', '16:9', '2K', '2560x1440', 'auto', 'png', 1, 2, 'queued', '[]', 'now', 'now')
            """,
            (user_id,),
        ).lastrowid
        get_db().commit()

    class TimeoutLimiter:
        def acquire(self, **_kwargs):
            raise GenerationLimitTimeout("timed out waiting for generation upstream capacity")

    monkeypatch.setattr("huishi.generation_queue.get_generation_limiter", lambda _app: TimeoutLimiter())
    monkeypatch.setattr("huishi.generation_queue.generate_image_with_failover", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("should not call upstream")))

    run_generation_task(app, task_id, [])

    with app.app_context():
        task = get_db().execute("SELECT status, error_message FROM generation_tasks WHERE id = ?", (task_id,)).fetchone()
        assert task["status"] == "failed"
        assert "timed out waiting for generation upstream capacity" in task["error_message"]


def test_in_memory_generation_limiter_rejects_when_concurrency_full():
    limiter = InMemoryGenerationLimiter(max_concurrency=1, rpm=300)

    first = limiter.acquire()
    assert first is not None

    with pytest.raises(RuntimeError, match="concurrency"):
        limiter.acquire()

    first.release()
    second = limiter.acquire()
    assert second is not None
    second.release()


def test_in_memory_generation_limiter_rejects_when_rpm_full():
    limiter = InMemoryGenerationLimiter(max_concurrency=240, rpm=1, now=lambda: 100.0)

    first = limiter.acquire()
    assert first is not None
    first.release()

    with pytest.raises(RuntimeError, match="RPM"):
        limiter.acquire()


def test_redis_generation_limiter_rolls_back_rejected_rpm_attempt():
    class FakeRedis:
        def __init__(self):
            self.values = {}
            self.expirations = {}
            self.zsets = {}

        def eval(self, _script, _key_count, active_key, rpm_key, max_concurrency, rpm, ttl, now_ms, token):
            active_slots = self.zsets.setdefault(active_key, {})
            active_slots = {member: score for member, score in active_slots.items() if score > now_ms}
            self.zsets[active_key] = active_slots
            if len(active_slots) >= int(max_concurrency):
                return [0, "concurrency"]
            current = int(self.values.get(rpm_key, 0)) + 1
            self.values[rpm_key] = current
            if current == 1 or self.expirations.get(rpm_key, -1) < 0:
                self.expirations[rpm_key] = 60
            if current > int(rpm):
                self.values[rpm_key] = int(rpm)
                self.expirations[rpm_key] = 60
                return [0, "RPM"]
            active_slots[token] = now_ms + int(ttl) * 1000
            self.expirations[active_key] = int(ttl)
            return [1, ""]

        def zrem(self, key, member):
            self.zsets.get(key, {}).pop(member, None)

    redis = FakeRedis()
    limiter = RedisGenerationLimiter(redis, namespace="test", max_concurrency=240, rpm=1)
    lease = limiter.acquire()
    lease.release()
    with pytest.raises(RuntimeError, match="RPM"):
        limiter.acquire()

    rpm_keys = [key for key in redis.values if ":generation:rpm:" in key]
    assert len(rpm_keys) == 1
    assert redis.values[rpm_keys[0]] == 1
    assert redis.expirations[rpm_keys[0]] == 60


def test_redis_generation_limiter_releases_individual_expiring_slot_token():
    class RecordingRedis:
        def __init__(self):
            self.eval_args = None
            self.zrem_calls = []

        def eval(self, _script, _key_count, *args):
            self.eval_args = args
            return [1, ""]

        def zrem(self, key, member):
            self.zrem_calls.append((key, member))

        def decr(self, _key):
            raise AssertionError("active slots must not use a global DECR counter")

    redis = RecordingRedis()
    limiter = RedisGenerationLimiter(
        redis,
        namespace="test",
        max_concurrency=1,
        rpm=300,
        active_ttl_seconds=900,
        token_factory=lambda: "slot-1",
        now=lambda: 100.0,
    )

    lease = limiter.acquire()
    lease.release()

    assert redis.zrem_calls == [("test:generation:active", "slot-1")]
    assert redis.eval_args[-2:] == (100000, "slot-1")
