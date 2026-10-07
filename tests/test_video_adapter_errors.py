"""Video adapter error handling: shared layers, markers, and failover policy.

三个契约值得钉住，它们都属于"改错了不会有现象、只会在很久后以别的形式爆出来"
的那一类：

1. ``seedance_media.models()`` 只在**响应格式**不对时降级到内置目录。
   它原先靠比较错误字符串判断，文案一改就静默失效。
2. ``retryable`` 的错误重构：格式错误必须仍然可重试（畸形响应可能代表上游
   已受理的任务），但真实 HTTP/鉴权故障必须照常抛出。
3. 上游错误里不该泄露 api_key。
"""
from __future__ import annotations

import pytest

from huishi.video_adapters import common, seedance_media
from huishi.video_adapters.common import RetryableVideoError, is_response_format_error
from huishi.video_api import VideoApiError


class Response:
    """最小响应替身：只需 status_code / json() / text。"""

    def __init__(self, status_code, payload=None, *, json_error=None):
        self.status_code = status_code
        self._payload = payload
        self._json_error = json_error
        self.text = str(payload)

    def json(self):
        if self._json_error is not None:
            raise ValueError(self._json_error)
        return self._payload


PROVIDER = {"base_url": "https://seedance.example.com", "api_key": "sk-secret-key"}


def test_non_json_catalog_falls_back_to_builtin(monkeypatch):
    """上游返回网页（非 JSON）时应降级到内置目录，而不是报错。

    Laogou 的部署会在 /v1/catalog 上返回它的网页外壳，文档里的接口其实没开。
    """
    monkeypatch.setattr(
        common.requests, "get",
        lambda url, **kwargs: Response(200, json_error="Expecting value"),
    )

    models = seedance_media.models(PROVIDER)

    ids = [item["id"] for item in models]
    assert "seedance2.5" in ids
    assert all(item["capability_source"] == "builtin-fallback" for item in models)
    # 兜底目录的模型一律不上架，避免把未核对的渠道暴露出去
    assert all(item["enabled"] is False for item in models)


def test_real_http_failure_is_not_swallowed_by_the_fallback(monkeypatch):
    """鉴权/服务端故障必须照常抛出，不能被内置目录悄悄掩盖。

    把"上游 401"降级成"用内置目录"会让渠道看起来是好的，而其实完全不可用。
    """
    monkeypatch.setattr(
        common.requests, "get",
        lambda url, **kwargs: Response(401, {"error": {"message": "invalid token"}}),
    )

    # 401 属客户端错误，common 判为不可重试的 VideoApiError。
    # 注意断言类型要用 VideoApiError 而不是 RetryableVideoError：
    # 后者是前者的**子类**，用子类去 raises 接不住父类实例。
    with pytest.raises(VideoApiError) as excinfo:
        seedance_media.models(PROVIDER)

    assert not isinstance(excinfo.value, RetryableVideoError)
    assert not is_response_format_error(excinfo.value)
    assert "401" in str(excinfo.value)


def test_fallback_survives_a_rewording_of_the_shared_message(monkeypatch):
    """降级判定不得依赖错误文案。

    这正是原先的缺陷：`common` 的 "视频接口返回的不是 JSON" 一改字，
    `seedance_media` 的字符串比较就失配，降级静默失效——渠道明明能靠内置
    目录继续工作，却开始把"上游返回网页"当成硬故障抛出。
    """
    original = common.response_format_error

    def reworded(message):
        # 模拟有人改了文案但标记仍在
        return original("响应格式与预期不符（文案已调整）")

    monkeypatch.setattr(common, "response_format_error", reworded)
    monkeypatch.setattr(
        common.requests, "get",
        lambda url, **kwargs: Response(200, json_error="Expecting value"),
    )

    models = seedance_media.models(PROVIDER)
    assert [item["id"] for item in models]  # 仍然拿到了兜底目录


def test_marker_survives_the_retryable_rewrap():
    """标记必须穿过 request_json 的重新包装。

    格式错误会被重新包成 RetryableVideoError（保证队列会重试），所以调用方
    拿不到原始异常类型；标记若不带过去，调用方就无法区分格式问题与真故障。
    """
    original = common.response_format_error("视频接口返回的不是 JSON")
    assert is_response_format_error(original)

    wrapped = RetryableVideoError(str(original))
    wrapped.response_format_error = True
    assert is_response_format_error(wrapped)


def test_format_error_stays_retryable():
    """格式错误必须仍是可重试类型。

    畸形响应可能代表上游已经受理了任务——当成硬失败会让用户的任务被丢弃，
    而钱可能已经花了。
    """
    error = common.response_format_error("视频接口返回格式不支持")
    assert isinstance(error, VideoApiError)
    assert isinstance(RetryableVideoError("视频接口返回格式不支持"), RetryableVideoError)


def test_upstream_error_text_redacts_the_api_key(monkeypatch):
    """上游回显密钥时，错误文案里不得出现它。"""
    monkeypatch.setattr(
        common.requests, "get",
        lambda url, **kwargs: Response(500, {"error": {"message": "auth failed for sk-secret-key"}}),
    )

    with pytest.raises(RetryableVideoError) as excinfo:
        common.request_json(PROVIDER, "GET", "/v1/anything")

    assert "sk-secret-key" not in str(excinfo.value)
    assert "[redacted]" in str(excinfo.value) or "redacted" in str(excinfo.value).lower()


def test_request_json_sends_no_redirects_and_idempotency_key(monkeypatch):
    """请求不得跟随重定向——错误分类与脱敏都按原地址判断。"""
    captured = {}

    def fake_get(url, **kwargs):
        captured.update(url=url, **kwargs)
        return Response(200, {"ok": True})

    monkeypatch.setattr(common.requests, "get", fake_get)
    common.request_json(PROVIDER, "GET", "/v1/thing", idempotency_key="idem-1")

    assert captured["allow_redirects"] is False
    assert captured["headers"]["Idempotency-Key"] == "idem-1"
    assert captured["timeout"] == (15, 60)


def test_unsupported_model_error_is_shared_and_names_the_model():
    """三个适配器说"不支持此模型"时必须用同一套措辞，并带上模型名。

    原先各写一句（"DMC H3 渠道不支持此模型" / "JiasuAPI 不支持该视频模型" /
    "Seedance Media 渠道不支持此模型"），说的是同一件事却三种写法；而且都只说
    "此模型"，管理员还得回去翻请求才知道是哪个模型。
    """
    error = common.unsupported_model_error("DMC H3", "unknown-model")
    assert isinstance(error, VideoApiError)
    assert "DMC H3" in str(error)
    assert "unknown-model" in str(error)

    # 渠道名照传，措辞一致
    for channel in ("JiasuAPI", "Seedance Media", "DMC H3"):
        text = str(common.unsupported_model_error(channel, "m"))
        assert channel in text
        assert text.endswith("：m")


def test_unsupported_model_error_handles_a_missing_model_name():
    """模型名为空时不能拼出"不支持模型：""这样的残缺文案。"""
    text = str(common.unsupported_model_error("JiasuAPI", ""))
    assert "JiasuAPI" in text
    assert text.endswith("（未指定）")
    assert "：" in text


def test_each_adapter_reports_an_unknown_model_consistently():
    """真正走一遍三个适配器，确认它们都抛出统一措辞。

    这比只测构造器更有价值：真正要防的是某个适配器**漏改**，继续用旧文案。
    """
    for adapter, channel, model in (
        (seedance_media, "Seedance Media", "not-a-real-model"),
        (__import__("huishi.video_adapters.dmc_h3", fromlist=["dmc_h3"]), "DMC H3", "not-a-real-model"),
        (__import__("huishi.video_adapters.jiasuapi", fromlist=["jiasuapi"]), "JiasuAPI", "not-a-real-model"),
    ):
        with pytest.raises(VideoApiError) as excinfo:
            adapter.create(
                {"base_url": "https://example.com", "api_key": "k", "settings": {}},
                {"model": model, "prompt": "x", "duration_seconds": 5,
                 "ratio": "16:9", "resolution": "720p", "idempotency_key": "idem-1"},
            )
        text = str(excinfo.value)
        assert channel in text, (channel, text)
        assert model in text, (channel, text)
