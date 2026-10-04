from __future__ import annotations

from pathlib import Path
from fnmatch import fnmatch

import pytest


@pytest.fixture()
def app(tmp_path: Path):
    from app import create_app

    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "test.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"
    app.config["RATE_LIMITING_ENABLED"] = True
    return app


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, int] = {}
        self.hashes: dict[str, dict[str, object]] = {}
        self.deleted: list[str] = []

    def incr(self, key: str) -> int:
        self.values[key] = int(self.values.get(key, 0)) + 1
        return self.values[key]

    def decr(self, key: str) -> int:
        self.values[key] = int(self.values.get(key, 0)) - 1
        return self.values[key]

    def expire(self, _key: str, _seconds: int) -> None:
        return None

    def hgetall(self, key: str):
        return dict(self.hashes.get(key, {}))

    def hset(self, key: str, mapping: dict[str, object]) -> None:
        self.hashes[key] = dict(mapping)

    def delete(self, key: str) -> None:
        self.deleted.append(key)
        self.values.pop(key, None)
        self.hashes.pop(key, None)

    def scan_iter(self, match: str, count: int = 100):
        keys = list(self.hashes) + list(self.values)
        for key in keys:
            if fnmatch(key, match):
                yield key


def test_redis_rate_limit_bucket_rolls_back_rejected_attempt(app, monkeypatch):
    from huishi import rate_limits

    redis = FakeRedis()
    monkeypatch.setattr(rate_limits, "redis_client_for_app", lambda _app: redis)
    app.config["RATE_LIMIT_NAMESPACE"] = "test"

    assert rate_limits.rate_limit_bucket(app, "email:test@example.com", 1, 60) is True
    assert rate_limits.rate_limit_bucket(app, "email:test@example.com", 1, 60) is False
    assert redis.values["test:ratelimit:email:test@example.com"] == 1


def test_login_failure_state_can_be_saved_and_cleared_from_shared_store(app, monkeypatch):
    from huishi import rate_limits

    redis = FakeRedis()
    monkeypatch.setattr(rate_limits, "redis_client_for_app", lambda _app: redis)
    app.config["RATE_LIMIT_NAMESPACE"] = "test"

    rate_limits.save_login_failure_state(
        app,
        "127.0.0.1:user@example.com",
        {"failures": 3, "locked_until": 123.5, "window_started_at": 100.0},
    )

    state = rate_limits.login_failure_state(app, "127.0.0.1:user@example.com")
    assert state["failures"] == 3
    assert state["locked_until"] == 123.5
    assert state["window_started_at"] == 100.0

    rate_limits.clear_login_failure_states_for_candidates(app, ["user@example.com"])
    assert "test:login-failure:127.0.0.1:user@example.com" in redis.deleted
