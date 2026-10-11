"""分池的契约测试。

三个池子（图片/音频/视频）必须真正独立，同时图片池**必须沿用旧键名**——
滚动发布期间新旧 worker 并存，若键名变了，两边各算各的额度，实际并发翻倍。

不依赖线上 Redis：用假的 Redis 客户端断言键名，用进程内实现断言容量。
"""
from __future__ import annotations

import pytest

from huishi.generation_queue import get_generation_limiter


class _FakeRedis:
    """只记录 eval 的键名，用来断言池子是否真的分开。"""

    def __init__(self) -> None:
        self.namespaces: list[str] = []

    def eval(self, script, numkeys, active_key, rpm_key, *args):  # noqa: ANN001
        self.namespaces.append(active_key)
        return [1, ""]

    def zrem(self, *_args):  # noqa: ANN002
        return 1


def _app(config_overrides: dict):
    """构造测试用 app。

    必须 `testing=True`：不配 Redis 时只有 testing 允许用进程内限流器，
    否则会抛 "Redis must be configured for shared generation limits"。
    """
    from app import create_app

    app = create_app(testing=True)
    app.config.update(config_overrides)
    return app


@pytest.fixture(autouse=True)
def _clean_inprocess_limiters():
    """清掉进程内限流器缓存。

    `_memory_limiter` 是模块级 dict（按池名缓存），在同一 pytest 进程里
    跨测试存活；容量相同的池会被复用，导致上一条测试占用的名额漏到下一条。
    """
    import huishi.generation_queue as gq

    gq._memory_limiter.clear()
    yield
    gq._memory_limiter.clear()


@pytest.fixture
def fake_redis(monkeypatch):
    """替换 `from redis import Redis` 拿到的东西。

    `Redis` 是**函数内局部导入**的，打 `huishi.generation_queue.Redis`
    这种模块属性无效，必须替换 `sys.modules["redis"].Redis`。
    """
    import redis as redis_module

    fake = _FakeRedis()
    monkeypatch.setattr(
        redis_module,
        "Redis",
        type("FakeRedis", (), {"from_url": staticmethod(lambda *_: fake)}),
    )
    return fake


def test_image_pool_keeps_the_legacy_key_name(fake_redis):
    """图片池必须仍是 `<ns>:generation:active`。

    零迁移的硬要求：改键名 → 滚动发布时新旧进程各算各的额度 → 并发翻倍。
    """
    app = _app({"REDIS_URL": "redis://localhost:6379/0"})
    app.config["RATE_LIMIT_NAMESPACE"] = "huishi"

    get_generation_limiter(app, pool="image")._try_acquire()

    assert fake_redis.namespaces == ["huishi:generation:active"]


def test_audio_and_video_pools_have_distinct_keys(fake_redis):
    """音频/视频必须是独立键，否则会互相挤占。"""
    app = _app({"REDIS_URL": "redis://localhost:6379/0"})
    app.config["RATE_LIMIT_NAMESPACE"] = "huishi"

    get_generation_limiter(app, pool="audio")._try_acquire()
    get_generation_limiter(app, pool="video")._try_acquire()

    assert fake_redis.namespaces == [
        "huishi:audio:generation:active",
        "huishi:video:generation:active",
    ]


def test_pools_use_their_own_capacity_settings():
    """各池读各自的配置，不能串。"""
    app = _app({"REDIS_URL": ""})
    app.config.update(
        {
            "UPSTREAM_MAX_CONCURRENCY": 240,
            "UPSTREAM_RPM_LIMIT": 300,
            "UPSTREAM_AUDIO_MAX_CONCURRENCY": 32,
            "UPSTREAM_AUDIO_RPM_LIMIT": 120,
            "UPSTREAM_VIDEO_MAX_CONCURRENCY": 64,
            "UPSTREAM_VIDEO_RPM_LIMIT": 2400,
        }
    )
    assert get_generation_limiter(app, pool="image").max_concurrency == 240
    assert get_generation_limiter(app, pool="audio").max_concurrency == 32
    assert get_generation_limiter(app, pool="video").max_concurrency == 64
    assert get_generation_limiter(app, pool="video").rpm == 2400


def test_unknown_pool_is_rejected():
    app = _app({"REDIS_URL": ""})
    with pytest.raises(ValueError):
        get_generation_limiter(app, pool="nope")


def test_pools_are_independent_in_memory():
    """一个池子占满不应影响另一个池子。"""
    app = _app({"REDIS_URL": ""})
    app.config.update(
        {
            "UPSTREAM_MAX_CONCURRENCY": 1,
            "UPSTREAM_RPM_LIMIT": 100,
            "UPSTREAM_VIDEO_MAX_CONCURRENCY": 1,
            "UPSTREAM_VIDEO_RPM_LIMIT": 100,
        }
    )
    image_limiter = get_generation_limiter(app, pool="image")
    video_limiter = get_generation_limiter(app, pool="video")

    held = image_limiter.acquire()
    try:
        # 图片池已满；视频池应仍可获取
        with video_limiter.acquire():
            pass
    finally:
        held.release()


def test_video_rpm_is_sized_for_polling_not_task_count():
    """视频 RPM 必须远大于并发数。

    一条视频 300 秒内每 5 秒轮询一次 = 约 60 次请求；64 条并发就是约 768 次/分钟。
    若 RPM 只按任务数给（比如 120），池子会被自己的轮询打满而自锁。
    """
    app = _app({"REDIS_URL": ""})
    limiter = get_generation_limiter(app, pool="video")
    assert limiter.rpm >= limiter.max_concurrency * 10, (
        f"视频 RPM({limiter.rpm}) 相对并发({limiter.max_concurrency})太小，轮询会自锁"
    )


def test_video_capacity_wait_renews_its_lease(monkeypatch):
    """视频排队等额度期间必须续租。

    租约 TTL 是 180 秒，而 `recover_video_tasks` 会把「status IN
    ('queued','running') 且无有效租约」的视频任务重新入队。若等待池子期间
    不续租，任务会被当僵尸重复入队——越拥塞重复越多，恰好在最需要扩容时
    把队列堆满。

    做法：让限流器先拒一次再放行，把续租周期压到 0，断言期间确实续了租。
    """
    import huishi.generation_queue as gq
    import huishi.media_tasks as mt
    from huishi.generation_limits import GenerationLimitError
    from huishi.generation_queue import _acquire_video_pool

    renewals: list[str] = []
    calls = {"n": 0}

    class _Lease:
        def release(self) -> None:
            pass

    class _FlakyLimiter:
        def acquire(self, **_kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise GenerationLimitError("busy")
            return _Lease()

    app = _app({"REDIS_URL": ""})
    app.config.update(
        {
            "GENERATION_LIMIT_WAIT_TIMEOUT_SECONDS": 5.0,
            "GENERATION_LIMIT_WAIT_SLEEP_SECONDS": 0.01,
            "VIDEO_CAPACITY_RENEW_SECONDS": 0.0,  # 每轮都续，测试不必等 60 秒
        }
    )

    # 两者都是在函数体内按名字取用的：get_generation_limiter 是模块级函数、
    # save_phase 是函数内 `from huishi.media_tasks import save_phase`。
    # 后者取的是模块属性，所以 patch 模块对象即可（在导入语句执行时读取）。
    monkeypatch.setattr(gq, "get_generation_limiter", lambda _app, pool="image": _FlakyLimiter())
    monkeypatch.setattr(mt, "save_phase", lambda task_id, token, metadata, phase, **kw: renewals.append(phase))

    # 必须提供 app context：_acquire_video_pool 续租后会调 close_db()，
    # 而它依赖 `g`。真实调用方（worker）本来就跑在 app_context 里。
    with app.app_context():
        lease = _acquire_video_pool(app, 1, "tok", {})

    assert lease is not None
    assert renewals, "排队期间没有续租，租约会在 180 秒后过期并被重复入队"
    assert renewals[0] == "waiting_capacity"
