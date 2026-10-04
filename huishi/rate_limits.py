from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Any

from flask import Flask


_MEMORY_BUCKETS: dict[str, deque[float]] = defaultdict(deque)
_MEMORY_LOGIN_FAILURES: dict[str, dict[str, float | int]] = {}


def rate_limiting_enabled(app: Flask) -> bool:
    return bool(app.config.get("RATE_LIMITING_ENABLED", True))


def redis_client_for_app(app: Flask):
    redis_url = str(app.config.get("REDIS_URL") or "").strip()
    if not redis_url:
        return None
    try:
        from redis import Redis
    except ImportError as exc:
        raise RuntimeError("Install redis to use shared rate limits") from exc
    return Redis.from_url(redis_url)


def rate_limit_bucket(app: Flask, key: str, limit: int, window_seconds: int) -> bool:
    if not rate_limiting_enabled(app):
        return True
    limit = max(1, int(limit))
    window_seconds = max(1, int(window_seconds))
    redis = redis_client_for_app(app)
    namespace = str(app.config.get("RATE_LIMIT_NAMESPACE", "huishi"))
    if redis is not None:
        redis_key = f"{namespace}:ratelimit:{key}"
        current = int(redis.incr(redis_key))
        if current == 1:
            redis.expire(redis_key, window_seconds)
        if current > limit:
            redis.decr(redis_key)
            return False
        return True

    now = time.time()
    bucket = _MEMORY_BUCKETS[key]
    while bucket and now - bucket[0] > window_seconds:
        bucket.popleft()
    if len(bucket) >= limit:
        return False
    bucket.append(now)
    return True


def login_failure_state(app: Flask, identifier: str) -> dict[str, float | int]:
    if not rate_limiting_enabled(app):
        return {"failures": 0, "locked_until": 0.0, "window_started_at": 0.0}
    redis = redis_client_for_app(app)
    namespace = str(app.config.get("RATE_LIMIT_NAMESPACE", "huishi"))
    if redis is None:
        return _MEMORY_LOGIN_FAILURES.setdefault(
            identifier,
            {"failures": 0, "locked_until": 0.0, "window_started_at": 0.0},
        )
    key = f"{namespace}:login-failure:{identifier}"
    raw: dict[Any, Any] = redis.hgetall(key)
    if not raw:
        return {"failures": 0, "locked_until": 0.0, "window_started_at": 0.0}
    decoded = {
        (k.decode() if isinstance(k, bytes) else str(k)): (v.decode() if isinstance(v, bytes) else v)
        for k, v in raw.items()
    }
    return {
        "failures": int(decoded.get("failures") or 0),
        "locked_until": float(decoded.get("locked_until") or 0.0),
        "window_started_at": float(decoded.get("window_started_at") or 0.0),
    }


def save_login_failure_state(app: Flask, identifier: str, state: dict[str, float | int]) -> None:
    if not rate_limiting_enabled(app):
        return
    redis = redis_client_for_app(app)
    namespace = str(app.config.get("RATE_LIMIT_NAMESPACE", "huishi"))
    if redis is None:
        _MEMORY_LOGIN_FAILURES[identifier] = dict(state)
        return
    key = f"{namespace}:login-failure:{identifier}"
    redis.hset(
        key,
        mapping={
            "failures": int(state.get("failures") or 0),
            "locked_until": float(state.get("locked_until") or 0.0),
            "window_started_at": float(state.get("window_started_at") or 0.0),
        },
    )
    ttl = max(
        int(app.config.get("LOGIN_LOCKOUT_SECONDS", 900)),
        int(app.config.get("LOGIN_RATE_LIMIT_WINDOW_SECONDS", 300)),
    )
    redis.expire(key, max(60, ttl))


def clear_login_failure_state(app: Flask, identifier: str) -> None:
    redis = redis_client_for_app(app)
    namespace = str(app.config.get("RATE_LIMIT_NAMESPACE", "huishi"))
    if redis is None:
        _MEMORY_LOGIN_FAILURES.pop(identifier, None)
        return
    redis.delete(f"{namespace}:login-failure:{identifier}")


def clear_login_failure_states_for_candidates(app: Flask, candidates: list[str]) -> None:
    normalized = [candidate for candidate in candidates if candidate]
    if not normalized:
        return
    redis = redis_client_for_app(app)
    namespace = str(app.config.get("RATE_LIMIT_NAMESPACE", "huishi"))
    if redis is None:
        for key in list(_MEMORY_LOGIN_FAILURES.keys()):
            if any(key.endswith(f":{candidate}") or key == candidate for candidate in normalized):
                _MEMORY_LOGIN_FAILURES.pop(key, None)
        return
    for candidate in normalized:
        redis.delete(f"{namespace}:login-failure:{candidate}")
    for candidate in normalized:
        pattern = f"{namespace}:login-failure:*:{candidate}"
        for key in redis.scan_iter(match=pattern, count=100):
            redis.delete(key)
