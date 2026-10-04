from __future__ import annotations

import threading
import time
import secrets
from collections import deque
from dataclasses import dataclass
from typing import Callable


class GenerationLimitError(RuntimeError):
    pass


class GenerationLimitTimeout(GenerationLimitError):
    pass


@dataclass
class GenerationLease:
    release_callback: Callable[[], None]
    released: bool = False

    def release(self) -> None:
        if self.released:
            return
        self.released = True
        self.release_callback()

    def __enter__(self) -> "GenerationLease":
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        self.release()


class InMemoryGenerationLimiter:
    def __init__(self, *, max_concurrency: int, rpm: int, now: Callable[[], float] | None = None) -> None:
        self.max_concurrency = max(1, int(max_concurrency))
        self.rpm = max(1, int(rpm))
        self.now = now or time.time
        self._lock = threading.Lock()
        self._active = 0
        self._starts: deque[float] = deque()

    def acquire(
        self,
        *,
        block: bool = False,
        timeout_seconds: float | None = None,
        sleep_seconds: float = 1.0,
    ) -> GenerationLease:
        deadline = None if timeout_seconds is None else self.now() + max(0.0, float(timeout_seconds))
        while True:
            try:
                return self._try_acquire()
            except GenerationLimitError:
                if not block:
                    raise
                if deadline is not None and self.now() >= deadline:
                    raise GenerationLimitTimeout("timed out waiting for generation upstream capacity")
                time.sleep(max(0.05, float(sleep_seconds)))

    def _try_acquire(self) -> GenerationLease:
        with self._lock:
            now = self.now()
            while self._starts and now - self._starts[0] >= 60:
                self._starts.popleft()
            if self._active >= self.max_concurrency:
                raise GenerationLimitError("generation upstream concurrency limit reached")
            if len(self._starts) >= self.rpm:
                raise GenerationLimitError("generation upstream RPM limit reached")
            self._active += 1
            self._starts.append(now)
        return GenerationLease(self._release)

    def _release(self) -> None:
        with self._lock:
            self._active = max(0, self._active - 1)


class RedisGenerationLimiter:
    _ACQUIRE_SCRIPT = """
local active_key = KEYS[1]
local rpm_key = KEYS[2]
local max_concurrency = tonumber(ARGV[1])
local rpm = tonumber(ARGV[2])
local ttl = tonumber(ARGV[3])
local now_ms = tonumber(ARGV[4])
local token = ARGV[5]
redis.call('ZREMRANGEBYSCORE', active_key, '-inf', now_ms)
local active = tonumber(redis.call('ZCARD', active_key) or '0')
if active >= max_concurrency then
  return {0, 'concurrency'}
end
local current = tonumber(redis.call('INCR', rpm_key))
if current == 1 then
  redis.call('EXPIRE', rpm_key, 60)
elseif redis.call('TTL', rpm_key) < 0 then
  redis.call('EXPIRE', rpm_key, 60)
end
if current > rpm then
  redis.call('SET', rpm_key, rpm, 'EX', 60)
  return {0, 'RPM'}
end
redis.call('ZADD', active_key, now_ms + (ttl * 1000), token)
redis.call('EXPIRE', active_key, ttl)
return {1, ''}
"""

    def __init__(
        self,
        redis_client,
        *,
        namespace: str,
        max_concurrency: int,
        rpm: int,
        active_ttl_seconds: int = 900,
        token_factory: Callable[[], str] | None = None,
        now: Callable[[], float] | None = None,
    ) -> None:
        self.redis = redis_client
        self.namespace = namespace
        self.max_concurrency = max(1, int(max_concurrency))
        self.rpm = max(1, int(rpm))
        self.active_ttl_seconds = max(60, int(active_ttl_seconds))
        self.token_factory = token_factory or (lambda: secrets.token_urlsafe(24))
        self.now = now or time.time

    def acquire(
        self,
        *,
        block: bool = False,
        timeout_seconds: float | None = None,
        sleep_seconds: float = 1.0,
    ) -> GenerationLease:
        deadline = None if timeout_seconds is None else time.time() + max(0.0, float(timeout_seconds))
        while True:
            try:
                return self._try_acquire()
            except GenerationLimitError:
                if not block:
                    raise
                if deadline is not None and time.time() >= deadline:
                    raise GenerationLimitTimeout("timed out waiting for generation upstream capacity")
                time.sleep(max(0.05, float(sleep_seconds)))

    def _try_acquire(self) -> GenerationLease:
        active_key = f"{self.namespace}:generation:active"
        now = self.now()
        rpm_key = f"{self.namespace}:generation:rpm:{int(now // 60)}"
        token = self.token_factory()
        allowed, reason = self.redis.eval(
            self._ACQUIRE_SCRIPT,
            2,
            active_key,
            rpm_key,
            self.max_concurrency,
            self.rpm,
            self.active_ttl_seconds,
            int(now * 1000),
            token,
        )
        if int(allowed) != 1:
            if isinstance(reason, bytes):
                reason = reason.decode("utf-8", errors="replace")
            raise GenerationLimitError(f"generation upstream {reason} limit reached")

        def release() -> None:
            self.redis.zrem(active_key, token)

        return GenerationLease(release)
