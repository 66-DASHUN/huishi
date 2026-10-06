"""Tests for huishi.provider_metrics.

The whole point of this module is that channel telemetry exists at all: before
it, a failed image generation recorded nothing about which channel was called.
Two properties matter enough to pin here:

* ``record_provider_call`` must never raise. If it can fail a generation, the
  cure is worse than the disease, so the failure modes are tested explicitly.
* Channel ids and api_keys must not leak into the stored error text.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app import create_app
from huishi import provider_metrics as pm
from huishi import providers
from huishi.db import get_db


@pytest.fixture()
def app(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("HUISHI_DATABASE", str(tmp_path / "test.sqlite3"))
    monkeypatch.setenv("HUISHI_OUTPUT_DIR", str(tmp_path / "uploads"))
    app = create_app(testing=True)
    with app.app_context():
        from huishi.db import init_db

        init_db()
    return app


def save_channel(name: str, *, enabled: bool = True, api_format: str = "openai") -> int:
    provider_id = providers.save_provider(
        provider_type="image",
        name=name,
        base_url="https://example.com",
        api_key=f"sk-{name}-secret",
        model="gpt-image-2",
        priority=100,
        enabled=enabled,
        resolutions=["1K", "2K", "4K"],
    )
    get_db().commit()
    return provider_id


def log(provider_id, outcome, *, latency_ms=0, error="", error_class="", **extra):
    pm.record_provider_call(
        provider_id=provider_id,
        provider_name="渠道",
        api_format="openai",
        media_type="image",
        model="gpt-image-2",
        task_id=1,
        outcome=outcome,
        error_class=error_class,
        error_message=error,
        latency_ms=latency_ms,
        **extra,
    )


def save_video_task(provider_id: int, status: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    # Idempotent: several tasks share one owner.
    get_db().execute(
        "INSERT OR IGNORE INTO users"
        " (email,username,password_hash,role,email_verified,points,created_at)"
        " VALUES (?,?,?,?,?,?,?)",
        ("u@example.com", "u", "h", "user", 1, 0, now),
    )
    get_db().execute(
        "INSERT INTO generation_tasks (user_id,prompt,mode,ratio,resolution,actual_size,"
        "quality,output_format,count,status,media_type,provider_id,created_at,updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (1, "p", "text", "16:9", "2K", "2560x1440", "auto", "png", 1, status,
         "video", provider_id, now, now),
    )
    get_db().commit()


class TestRecordProviderCallNeverRaises:
    """Telemetry failing must never surface as a generation failure."""

    def test_missing_table_is_silently_ignored(self, app):
        with app.app_context():
            get_db().execute("DROP TABLE provider_call_logs")
            get_db().commit()
            # Must not raise even though the table is gone.
            log(1, pm.OUTCOME_FAILED, error="boom")

    def test_database_error_is_silently_ignored(self, app, monkeypatch):
        def exploding_db():
            raise RuntimeError("database is unreachable")

        monkeypatch.setattr(pm, "get_db", exploding_db)
        with app.app_context():
            log(1, pm.OUTCOME_SUCCEEDED)

    def test_bad_field_types_are_coerced_not_raised(self, app):
        with app.app_context():
            get_db().commit()
            pm.record_provider_call(
                provider_id="not-an-int",
                outcome=pm.OUTCOME_SUCCEEDED,
                latency_ms="oops",
                task_id=None,
            )
            row = get_db().execute(
                "SELECT provider_id, latency_ms FROM provider_call_logs"
            ).fetchone()
            assert row["provider_id"] is None
            assert row["latency_ms"] == 0

    def test_unknown_outcome_falls_back_to_succeeded(self, app):
        """A typo in outcome must not create a third state downstream."""
        with app.app_context():
            get_db().commit()
            log(1, "banana")
            row = get_db().execute("SELECT outcome FROM provider_call_logs").fetchone()
            assert row["outcome"] == pm.OUTCOME_SUCCEEDED


class TestRedaction:
    def test_stored_error_does_not_contain_the_api_key(self, app):
        with app.app_context():
            provider_id = save_channel("alpha")
            get_db().commit()
            secret = get_db().execute(
                "SELECT api_key FROM api_providers WHERE id = ?", (provider_id,)
            ).fetchone()["api_key"]
            assert secret, "fixture should have stored a key"

            log(provider_id, pm.OUTCOME_FAILED, error=f"upstream rejected key {secret}")
            stored = get_db().execute(
                "SELECT error_message FROM provider_call_logs"
            ).fetchone()["error_message"]
            assert secret not in stored
            assert "[redacted]" in stored

    def test_long_errors_are_truncated(self, app):
        with app.app_context():
            get_db().commit()
            log(1, pm.OUTCOME_FAILED, error="x" * 5000)
            stored = get_db().execute(
                "SELECT error_message FROM provider_call_logs"
            ).fetchone()["error_message"]
            assert len(stored) <= 2000


class TestFailureRateAndStatus:
    def test_rate_and_average_latency_are_computed_per_channel(self, app):
        with app.app_context():
            provider_id = save_channel("alpha")
            get_db().commit()
            log(provider_id, pm.OUTCOME_SUCCEEDED, latency_ms=1000)
            log(provider_id, pm.OUTCOME_SUCCEEDED, latency_ms=3000)
            log(provider_id, pm.OUTCOME_FAILED, error="Read timed out")

            channel = pm.channel_health(24)["channels"][0]
            assert channel["calls"] == 3
            assert channel["succeeded"] == 2
            assert channel["failed"] == 1
            assert channel["failure_rate"] == pytest.approx(33.3)
            # Only successful samples carry a latency here (1000, 3000).
            assert channel["avg_latency_ms"] == 2000

    def test_one_failure_alone_does_not_read_as_an_outage(self, app):
        """Below MIN_CALLS_FOR_RATE a single failure is a warning, not critical."""
        with app.app_context():
            provider_id = save_channel("alpha")
            get_db().commit()
            log(provider_id, pm.OUTCOME_FAILED, error="boom")

            channel = pm.channel_health(24)["channels"][0]
            assert channel["failure_rate"] == 100.0
            assert channel["status"] == "warning"

    def test_half_failing_channel_is_critical(self, app):
        with app.app_context():
            provider_id = save_channel("alpha")
            get_db().commit()
            for _ in range(3):
                log(provider_id, pm.OUTCOME_FAILED, error="boom")
            log(provider_id, pm.OUTCOME_SUCCEEDED)

            channel = pm.channel_health(24)["channels"][0]
            assert channel["failure_rate"] == 75.0
            assert channel["status"] == "critical"

    def test_healthy_channel_is_healthy(self, app):
        with app.app_context():
            provider_id = save_channel("alpha")
            get_db().commit()
            log(provider_id, pm.OUTCOME_SUCCEEDED)

            channel = pm.channel_health(24)["channels"][0]
            assert channel["status"] == "healthy"
            assert channel["failure_rate"] == 0.0

    def test_disabled_channel_is_critical_even_with_no_calls(self, app):
        with app.app_context():
            save_channel("disabled", enabled=False)
            get_db().commit()

            channel = pm.channel_health(24)["channels"][0]
            assert channel["enabled"] is False
            assert channel["status"] == "critical"

    def test_stale_disabled_at_on_an_enabled_channel_is_not_critical(self, app):
        """Stale ``disabled_at`` must not outrank ``enabled``.

        Found in production 2026-10-06: the ``grok`` channel had
        ``enabled=1`` but a ``disabled_at`` left over from 2026-09-13, so a
        channel that had just served a successful generation (100% success
        rate) was rendered as 异常. ``save_provider`` sets ``enabled`` without
        clearing ``disabled_at``, so any manually re-enabled channel hits this.
        """
        with app.app_context():
            provider_id = save_channel("grok")
            get_db().execute(
                "UPDATE api_providers SET disabled_at=? WHERE id=?",
                (datetime.now(timezone.utc).isoformat(), provider_id),
            )
            log(provider_id, pm.OUTCOME_SUCCEEDED)
            get_db().commit()

            channel = pm.channel_health(24)["channels"][0]
            assert channel["enabled"] is True
            assert channel["calls"] == 1
            assert channel["failure_rate"] == 0.0
            assert channel["status"] == "healthy"

    def test_disabled_channel_stays_critical_even_when_it_has_successes(self, app):
        """The converse: a genuinely disabled channel must not look healthy."""
        with app.app_context():
            provider_id = save_channel("turned-off", enabled=False)
            get_db().execute(
                "UPDATE api_providers SET disabled_at=? WHERE id=?",
                (datetime.now(timezone.utc).isoformat(), provider_id),
            )
            log(provider_id, pm.OUTCOME_SUCCEEDED)
            get_db().commit()

            channel = pm.channel_health(24)["channels"][0]
            assert channel["status"] == "critical"

    def test_consecutive_failures_counts_only_the_trailing_run(self, app):
        with app.app_context():
            provider_id = save_channel("alpha")
            get_db().commit()
            log(provider_id, pm.OUTCOME_FAILED, error="old")
            log(provider_id, pm.OUTCOME_SUCCEEDED)
            log(provider_id, pm.OUTCOME_FAILED, error="a")
            log(provider_id, pm.OUTCOME_FAILED, error="b")

            channel = pm.channel_health(24)["channels"][0]
            assert channel["consecutive_failures"] == 2


class TestNoDataChannel:
    def test_channel_without_calls_reports_unknown_not_zero_percent(self, app):
        """A 0% failure rate with no calls behind it would be a lie."""
        with app.app_context():
            save_channel("never-used")
            get_db().commit()

            channel = pm.channel_health(24)["channels"][0]
            assert channel["calls"] == 0
            assert channel["status"] == "unknown"
            assert channel["attributed"] is False
            assert "无调用数据" in channel["note"]

    def test_channel_with_only_durable_tasks_falls_back_and_says_so(self, app):
        """Video tasks carry provider_id, so they can stand in for call logs."""
        with app.app_context():
            provider_id = save_channel("video-only")
            save_video_task(provider_id, "succeeded")
            save_video_task(provider_id, "failed")

            channel = pm.channel_health(24)["channels"][0]
            assert channel["calls"] == 2
            assert channel["failed"] == 1
            assert channel["status"] == "warning"
            assert "任务级统计" in channel["note"]

    def test_window_excludes_older_rows(self, app):
        with app.app_context():
            provider_id = save_channel("alpha")
            old = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
            get_db().execute(
                "INSERT INTO provider_call_logs (provider_id,outcome,created_at)"
                " VALUES (?,?,?)",
                (provider_id, pm.OUTCOME_FAILED, old),
            )
            get_db().commit()

            channel = pm.channel_health(24)["channels"][0]
            assert channel["calls"] == 0
            assert channel["status"] == "unknown"


class TestPersonalProviderBucket:
    def test_null_provider_id_is_counted_in_totals_but_not_as_a_channel(self, app):
        """Personal BYOK has no channel row; it must not vanish from the totals."""
        with app.app_context():
            provider_id = save_channel("alpha")
            get_db().commit()
            log(provider_id, pm.OUTCOME_SUCCEEDED)
            pm.record_provider_call(
                provider_id=None,
                provider_name=pm.PERSONAL_PROVIDER_LABEL,
                outcome=pm.OUTCOME_FAILED,
                error_message="boom",
            )

            result = pm.channel_health(24)
            assert result["totals"]["calls"] == 2
            assert result["totals"]["failed"] == 1
            assert len(result["channels"]) == 1
            assert result["personal_provider"]["calls"] == 1
            assert result["personal_provider"]["name"] == pm.PERSONAL_PROVIDER_LABEL

    def test_no_personal_bucket_when_there_are_no_such_calls(self, app):
        with app.app_context():
            save_channel("alpha")
            get_db().commit()
            assert pm.channel_health(24)["personal_provider"] is None


class TestTotals:
    def test_success_rate_spans_all_channels(self, app):
        with app.app_context():
            first = save_channel("alpha")
            second = save_channel("beta")
            get_db().commit()
            log(first, pm.OUTCOME_SUCCEEDED)
            log(first, pm.OUTCOME_SUCCEEDED)
            log(second, pm.OUTCOME_FAILED, error="boom")

            totals = pm.channel_health(24)["totals"]
            assert totals["calls"] == 3
            assert totals["failed"] == 1
            assert totals["success_rate"] == pytest.approx(66.7)
            assert totals["channels"] == 2

    def test_empty_database_reports_zeroes_without_dividing_by_zero(self, app):
        with app.app_context():
            get_db().commit()
            totals = pm.channel_health(24)["totals"]
            assert totals["calls"] == 0
            assert totals["success_rate"] == 0.0


class TestProviderBalance:
    def test_non_seedance_channel_reports_unsupported(self, app):
        with app.app_context():
            result = pm.provider_balance({"id": 1, "api_format": "openai"})
            assert result["status"] == "unsupported"
            assert "不提供余额查询" in result["message"]

    def test_seedance_adapter_failure_is_returned_not_raised(self, app, monkeypatch):
        from huishi.video_adapters import seedance_media

        def boom(provider):
            raise RuntimeError("sk-live-secret rejected")

        monkeypatch.setattr(seedance_media, "balance", boom)
        with app.app_context():
            result = pm.provider_balance({"id": 1, "api_format": "seedance_media"})
            assert result["status"] == "error"
            assert "sk-live-secret" not in result["message"]

    def test_seedance_balance_is_surfaced(self, app, monkeypatch):
        from huishi.video_adapters import seedance_media

        monkeypatch.setattr(seedance_media, "balance", lambda provider: {"balance": 12345})
        with app.app_context():
            result = pm.provider_balance({"id": 7, "api_format": "seedance_media"})
            assert result["status"] == "ok"
            assert result["balance"] == 12345


def login(client, user_id: int) -> None:
    with client.session_transaction() as session:
        session["user_id"] = user_id


def admin_id() -> int:
    return int(
        get_db().execute("SELECT id FROM users WHERE role='admin' LIMIT 1").fetchone()["id"]
    )


class TestChannelHealthPage:
    """The admin page is the only consumer of this module; render it for real."""

    def test_admin_can_open_the_page_and_see_channels(self, app):
        with app.app_context():
            provider_id = save_channel("示例渠道")
            get_db().commit()
            log(provider_id, pm.OUTCOME_SUCCEEDED, latency_ms=1200)
            log(provider_id, pm.OUTCOME_FAILED, error="Read timed out")
            who = admin_id()

        client = app.test_client()
        with app.app_context():
            login(client, who)
        response = client.get("/admin/channel-health")
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "渠道健康度" in body
        assert "示例渠道" in body
        assert "Read timed out" in body
        assert 'data-health-status="' in body
        # The sidebar entry that leads here.
        assert "/admin/channel-health" in body

    def test_page_never_echoes_the_api_key(self, app):
        with app.app_context():
            provider_id = save_channel("alpha")
            get_db().commit()
            secret = get_db().execute(
                "SELECT api_key FROM api_providers WHERE id = ?", (provider_id,)
            ).fetchone()["api_key"]
            log(provider_id, pm.OUTCOME_FAILED, error=f"rejected {secret}")
            who = admin_id()

        client = app.test_client()
        with app.app_context():
            login(client, who)
        assert secret not in client.get("/admin/channel-health").get_data(as_text=True)

    @pytest.mark.parametrize("window", ["1", "6", "24", "72", "168"])
    def test_supported_windows_render(self, app, window):
        client = app.test_client()
        with app.app_context():
            login(client, admin_id())
        response = client.get(f"/admin/channel-health?window={window}")
        assert response.status_code == 200
        assert f"窗口 {window} 小时" in response.get_data(as_text=True)

    def test_bogus_window_falls_back_instead_of_erroring(self, app):
        client = app.test_client()
        with app.app_context():
            login(client, admin_id())
        response = client.get("/admin/channel-health?window=abc999")
        assert response.status_code == 200
        assert "窗口 24 小时" in response.get_data(as_text=True)

    def test_user_without_provider_permission_is_refused(self, app):
        with app.app_context():
            get_db().execute(
                "INSERT INTO users (email,username,password_hash,role,email_verified,"
                "points,created_at) VALUES (?,?,?,?,?,?,?)",
                ("plain@example.com", "plain", "h", "user", 1, 0,
                 datetime.now(timezone.utc).isoformat()),
            )
            get_db().commit()
            who = int(
                get_db().execute("SELECT id FROM users WHERE role='user' LIMIT 1").fetchone()["id"]
            )
        client = app.test_client()
        with app.app_context():
            login(client, who)
        assert client.get("/admin/channel-health").status_code == 403

    def test_anonymous_visitor_gets_the_login_page_not_channel_data(self, app):
        with app.app_context():
            save_channel("机密渠道名")
            get_db().commit()
        body = app.test_client().get("/admin/channel-health").get_data(as_text=True)
        assert "机密渠道名" not in body

    def test_empty_state_explains_that_history_cannot_be_backfilled(self, app):
        client = app.test_client()
        with app.app_context():
            login(client, admin_id())
        body = client.get("/admin/channel-health").get_data(as_text=True)
        assert "没有渠道调用记录" in body


class TestTaskIdIsNotForwardedUpstream:
    """``task_id`` is telemetry-only and must not reach ``generate_image``.

    Regression for a production outage found 2026-10-06: the queue path passed
    ``task_id=`` into ``generate_image_with_failover``, which forwards its kwargs
    to ``generate_image``. ``generate_image`` has no such parameter, so *every*
    queued image generation died with a TypeError before any upstream call --
    which also meant no telemetry row was ever written.
    """

    def test_failover_does_not_forward_task_id_to_generate_image(self, app, monkeypatch):
        captured: dict[str, object] = {}

        def fake_generate_image(**kwargs):
            captured.update(kwargs)
            return {"image_path": "x.png", "image_paths": ["x.png"], "prompt": "p"}

        monkeypatch.setattr(providers, "generate_image", fake_generate_image)

        with app.app_context():
            save_channel("alpha")
            get_db().commit()

            providers.generate_image_with_failover(
                task_id=4242,
                prompt="p",
                mode="text",
                ratio="1:1",
                resolution="1K",
                count=1,
                quality="auto",
                output_format="png",
                reference_images=[],
                model="gpt-image-2",
            )

        assert "task_id" not in captured, "task_id 泄漏到了上游 generate_image"
        assert captured["prompt"] == "p"
        assert captured["resolution"] == "1K"

    def test_task_id_still_reaches_the_telemetry_row(self, app, monkeypatch):
        """The fix must not silently drop the attribution it exists for."""
        recorded: list[dict] = []

        def fake_record(**kwargs):
            recorded.append(kwargs)

        monkeypatch.setattr(
            "huishi.provider_metrics.record_provider_call", fake_record
        )
        monkeypatch.setattr(
            providers,
            "generate_image",
            lambda **kw: {"image_path": "x.png", "image_paths": ["x.png"], "prompt": "p"},
        )

        with app.app_context():
            save_channel("alpha")
            get_db().commit()

            providers.generate_image_with_failover(
                task_id=4242,
                prompt="p",
                mode="text",
                ratio="1:1",
                resolution="1K",
                count=1,
                quality="auto",
                output_format="png",
                reference_images=[],
                model="gpt-image-2",
            )

        assert recorded, "成功调用应当写一条埋点"
        assert recorded[0]["task_id"] == 4242


class TestSaveProviderClearsStaleDisabledAt:
    """重新启用渠道必须清掉历史 disabled_at，否则显示层会永久误报。

    线上 2026-10-06 有三行（grok / ai.junze.me / Prompt Provider）
    ``enabled=1`` 却残留 disabled_at。根因是 ``save_provider`` 的 UPDATE
    只写 ``enabled``，从不碰 ``disabled_at``。
    """

    def test_enabling_clears_disabled_at(self, app):
        with app.app_context():
            provider_id = save_channel("alpha", enabled=False)
            get_db().execute(
                "UPDATE api_providers SET disabled_at=? WHERE id=?",
                ("2026-01-01T00:00:00+00:00", provider_id),
            )
            get_db().commit()

            providers.save_provider(
                provider_id=provider_id,
                provider_type="image",
                name="alpha",
                base_url="https://example.com",
                api_key="sk-alpha-secret",
                model="gpt-image-2",
                priority=100,
                enabled=True,
                resolutions=["1K", "2K", "4K"],
            )
            get_db().commit()

            row = get_db().execute(
                "SELECT enabled, disabled_at FROM api_providers WHERE id=?", (provider_id,)
            ).fetchone()
            assert row["enabled"] == 1
            assert row["disabled_at"] == ""

    def test_enabling_a_channel_that_was_never_disabled_is_harmless(self, app):
        """对没有 disabled_at 的渠道重复保存不应出错。"""
        with app.app_context():
            provider_id = save_channel("beta")
            providers.save_provider(
                provider_id=provider_id,
                provider_type="image",
                name="beta",
                base_url="https://example.com",
                api_key="sk-beta-secret",
                model="gpt-image-2",
                priority=100,
                enabled=True,
                resolutions=["1K", "2K", "4K"],
            )
            get_db().commit()

            row = get_db().execute(
                "SELECT enabled, disabled_at FROM api_providers WHERE id=?", (provider_id,)
            ).fetchone()
            assert row["enabled"] == 1
            assert row["disabled_at"] == ""

    def test_saving_a_channel_as_disabled_preserves_existing_disabled_at(self, app):
        """停用态保存不应抹掉已有的停用时间戳。"""
        with app.app_context():
            provider_id = save_channel("gamma", enabled=False)
            stamp = "2026-01-01T00:00:00+00:00"
            get_db().execute(
                "UPDATE api_providers SET disabled_at=? WHERE id=?", (stamp, provider_id)
            )
            get_db().commit()

            providers.save_provider(
                provider_id=provider_id,
                provider_type="image",
                name="gamma",
                base_url="https://example.com",
                api_key="sk-gamma-secret",
                model="gpt-image-2",
                priority=100,
                enabled=False,
                resolutions=["1K", "2K", "4K"],
            )
            get_db().commit()

            row = get_db().execute(
                "SELECT enabled, disabled_at FROM api_providers WHERE id=?", (provider_id,)
            ).fetchone()
            assert row["enabled"] == 0
            assert row["disabled_at"] == stamp


class TestNonJsonUpstreamResponseIsHandled:
    """上游返回网页/字符串时，必须抛可恢复的 RuntimeError。

    线上 2026-10-06 渠道 ai.junze.me（base_url 缺 /v1）返回 HTTP 200 + 一个
    New API 的 HTML 落地页。旧代码直接把它当 dict 用，抛
    ``AttributeError: 'str' object has no attribute 'get'``——而
    AttributeError **不在** failover 捕获的异常类型里，于是既不切换下一个
    渠道、也不写渠道埋点，用户只看到"生成结果保存失败"。
    """

    def test_html_response_raises_runtime_error_with_actionable_message(self):
        from huishi.image_api import images_from_payload

        html = "<!doctype html>\n<html><head><title>New API</title></head></html>"
        with pytest.raises(RuntimeError) as excinfo:
            images_from_payload(html)
        message = str(excinfo.value)
        assert "网页" in message
        assert "/v1" in message, "报错应指出最常见的成因（缺少 /v1）"

    def test_plain_string_payload_raises_runtime_error(self):
        from huishi.image_api import images_from_payload

        with pytest.raises(RuntimeError) as excinfo:
            images_from_payload("not json at all")
        assert "不支持的数据格式" in str(excinfo.value)

    def test_none_payload_raises_runtime_error_not_attribute_error(self):
        from huishi.image_api import images_from_payload

        with pytest.raises(RuntimeError):
            images_from_payload(None)

    def test_valid_dict_payload_without_images_raises_the_existing_message(self):
        """防御不能改变已有语义：空 data 仍抛"没有解析到图片结果"。"""
        from huishi.image_api import images_from_payload

        with pytest.raises(RuntimeError) as excinfo:
            images_from_payload({"data": []})
        assert "没有解析到图片结果" in str(excinfo.value)

    def test_webpage_response_is_recorded_as_upstream_failure(self, app, monkeypatch):
        """网页响应必须写成 upstream 失败埋点（旧代码连埋点都写不了）。

        注意 failover 对上游错误是**刻意不切换渠道**的：上游可能已受理，
        自动重试会造成重复生成与重复扣费。所以这里断言的是"被记录"，
        而不是"切换到下一个渠道"。
        """

        def fake_generate_image(**kwargs):
            raise RuntimeError("生图接口返回了网页而不是图片数据")

        monkeypatch.setattr(providers, "generate_image", fake_generate_image)

        with app.app_context():
            save_channel("broken", api_format="openai")
            get_db().commit()

            with pytest.raises(RuntimeError) as excinfo:
                providers.generate_image_with_failover(
                    prompt="p",
                    mode="text",
                    ratio="1:1",
                    resolution="1K",
                    count=1,
                    quality="auto",
                    output_format="png",
                    reference_images=[],
                    model="gpt-image-2",
                )
            assert "已停止自动重试" in str(excinfo.value)

            rows = get_db().execute(
                "SELECT outcome, error_class, error_message FROM provider_call_logs ORDER BY id"
            ).fetchall()
            assert len(rows) == 1, "失败必须留下埋点（旧代码这里会是 0 行）"
            assert rows[0]["outcome"] == pm.OUTCOME_FAILED
            assert rows[0]["error_class"] == pm.ERROR_CLASS_UPSTREAM
            assert "网页" in rows[0]["error_message"]
