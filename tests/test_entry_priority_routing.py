"""条目级优先级：读写往返、选路生效、以及不改动既有行为。

这里钉住的是一个很安静的缺陷：``normalize_provider_models`` 的字段白名单
里没有 ``priority``，于是 ``save_model`` 把每个模型绑定的优先级写进
``models_json`` 之后，**任何一次读取都会把它丢掉**。界面上写着"数值越小
越优先，模型可以单独设置"，实际配了完全不生效，刷新页面还会看到它被
渠道级的值顶掉。

失败方式之所以难发现：没有报错、没有日志，只是"配了没反应"。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app import create_app
from huishi import providers
from huishi.db import get_db


@pytest.fixture()
def app(tmp_path: Path):
    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "test.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"
    with app.app_context():
        from huishi.db import init_db

        init_db()
    return app


def save_channel(name, *, models, priority=100, provider_type="mixed",
                 base_url=None, api_format="openai"):
    """建一个有多个模型条目的渠道。"""
    provider_id = providers.save_provider(
        provider_type=provider_type,
        name=name,
        base_url=base_url or f"https://{name}.example.com",
        api_key=f"sk-{name}",
        model=models[0]["id"],
        priority=priority,
        enabled=True,
        api_format=api_format,
        models=models,
    )
    get_db().commit()
    return provider_id


# ---------------------------------------------------------------- 读写往返

def test_entry_priority_survives_a_save_and_read_round_trip(app):
    """写在条目上的优先级必须能读回来。

    这是根因所在：白名单缺 priority 时，写入成功、读取静默丢失。
    """
    with app.app_context():
        provider_id = save_channel("multi", models=[
            {"id": "seedance2.5", "label": "seedance2.5", "media_type": "video", "priority": 30},
            {"id": "seedance2.0", "label": "seedance2.0", "media_type": "video", "priority": 70},
        ])
        stored = providers.get_provider(provider_id)
        by_id = {e["id"]: e for e in stored["models"]}

        assert by_id["seedance2.5"].get("priority") == 30
        assert by_id["seedance2.0"].get("priority") == 70


def test_missing_entry_priority_stays_absent_so_callers_can_fall_back(app):
    """没有条目优先级时不写这个键，让调用方回落到渠道级。

    写成 0 是错的：0 是合法的最小优先级，会把"未设置"和"排最前"混为一谈。
    """
    with app.app_context():
        provider_id = save_channel("plain", models=[
            {"id": "seedance2.5", "label": "seedance2.5", "media_type": "video"},
        ])
        entry = providers.get_provider(provider_id)["models"][0]
        assert "priority" not in entry


@pytest.mark.parametrize("raw", [None, "", "abc", -1, 10001, True, False])
def test_invalid_entry_priority_is_dropped_not_coerced(raw):
    """非法值一律视为"未设置"，而不是变成一个奇怪的数字。"""
    assert providers.provider_model_priority(raw) is None


@pytest.mark.parametrize("raw,expected", [("30", 30), (30, 30), ("0", 0), (10000, 10000)])
def test_valid_entry_priority_is_normalized_to_int(raw, expected):
    assert providers.provider_model_priority(raw) == expected


# ---------------------------------------------------------------- 选路生效

def test_entry_priority_overrides_the_channel_priority_in_candidates(app):
    """条目优先级必须投影到候选上，压过渠道级的值。

    否则"同一个模型挂多渠道、指定优先走哪个"根本无法表达。
    注意：无请求上下文时 local_candidates 不写缓存，每次直读数据库，
    所以这里不需要清缓存。
    """
    with app.app_context():
        # 渠道整体优先级 100，但把 seedance2.5 这个模型在**本渠道**提到 5
        save_channel("slowchannel", priority=100, models=[
            {"id": "seedance2.5", "label": "seedance2.5", "media_type": "video",
             "priority": 5, "api_format": "jiasuapi"},
        ])
        save_channel("fastchannel", priority=100, models=[
            {"id": "seedance2.5", "label": "seedance2.5", "media_type": "video",
             "priority": 90, "api_format": "jiasuapi"},
        ])

        candidates = providers.video_provider_candidates("seedance2.5")
        ordered = [c["name"] for c in candidates]

        assert ordered == ["slowchannel", "fastchannel"], ordered


def test_without_entry_priority_the_channel_priority_still_decides(app):
    """没配条目优先级时，行为与改动前一致——渠道优先级决定顺序。"""
    with app.app_context():
        save_channel("primary", priority=10, models=[
            {"id": "seedance2.5", "label": "seedance2.5", "media_type": "video", "api_format": "jiasuapi"},
        ])
        save_channel("secondary", priority=20, models=[
            {"id": "seedance2.5", "label": "seedance2.5", "media_type": "video", "api_format": "jiasuapi"},
        ])

        ordered = [c["name"] for c in providers.video_provider_candidates("seedance2.5")]
        assert ordered == ["primary", "secondary"], ordered


def test_equal_priority_keeps_a_stable_deterministic_order(app):
    """同优先级下顺序必须稳定（按渠道 id），否则出片渠道会随机漂移。"""
    with app.app_context():
        first = save_channel("a-chan", models=[
            {"id": "seedance2.5", "label": "seedance2.5", "media_type": "video", "api_format": "jiasuapi"},
        ])
        second = save_channel("b-chan", models=[
            {"id": "seedance2.5", "label": "seedance2.5", "media_type": "video", "api_format": "jiasuapi"},
        ])
        assert first < second

        for _ in range(3):
            ids = [c["id"] for c in providers.video_provider_candidates("seedance2.5")]
            assert ids == [first, second], ids


def test_image_routing_honours_entry_priority(app, monkeypatch):
    """图片侧按最小优先级分组轮询，条目优先级要能改变分组。"""
    with app.app_context():
        providers._round_robin_offsets.clear()
        save_channel("img-slow", provider_type="mixed", priority=100, models=[
            {"id": "gpt-image-2", "label": "gpt-image-2", "media_type": "image",
             "priority": 50, "api_format": "openai", "resolutions": ["1K"]},
        ])
        save_channel("img-fast", provider_type="mixed", priority=100, models=[
            {"id": "gpt-image-2", "label": "gpt-image-2", "media_type": "image",
             "priority": 5, "api_format": "openai", "resolutions": ["1K"]},
        ])

        candidates = providers.image_provider_candidates("1K", "gpt-image-2")
        assert [c["name"] for c in candidates][0] == "img-fast"


def test_other_models_on_the_same_channel_keep_their_own_priority(app):
    """一条渠道里不同模型可以有各自的优先级，互不干扰。"""
    with app.app_context():
        save_channel("mixed-prio", provider_type="mixed", priority=100, models=[
            {"id": "seedance2.5", "label": "seedance2.5", "media_type": "video",
             "priority": 10, "api_format": "jiasuapi"},
            {"id": "seedance2.0", "label": "seedance2.0", "media_type": "video",
             "priority": 200, "api_format": "jiasuapi"},
        ])

        top25 = providers.video_provider_candidates("seedance2.5")
        top20 = providers.video_provider_candidates("seedance2.0")

        assert [c["priority"] for c in top25] == [10]
        assert [c["priority"] for c in top20] == [200]
