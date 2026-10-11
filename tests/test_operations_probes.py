"""运行总览三个探针的回归测试。

这三个都曾静默报错，且**看容器状态完全正常**——所以必须有测试钉住，
否则下次又会悄悄退化。

背景：
  * 画布探针：走公网域名 + 根路径 → 521/404，把健康服务判成异常
  * Agent 探针：agent 只绑 127.0.0.1 → 跨容器连不上，但容器 healthcheck
    （容器内打回环）是 healthy，问题只在总览页暴露
  * 存储清理：文案写死 "由 huishi-storage-sweep.timer 定时执行"，
    而线上根本没有那个 systemd timer
"""
from __future__ import annotations

import os
import time

import pytest

from huishi import operations


class _FakeResponse:
    def __init__(self, status_code: int = 200, elapsed_ms: float = 5.0) -> None:
        self.status_code = status_code
        self.elapsed = type("E", (), {"total_seconds": lambda self: elapsed_ms / 1000})()

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def _app(config: dict | None = None):
    from app import create_app

    app = create_app(testing=True)
    if config:
        app.config.update(config)
    return app


def _capture_url(monkeypatch) -> list[str]:
    seen: list[str] = []

    def fake_get(url, **_kwargs):
        seen.append(url)
        return _FakeResponse()

    monkeypatch.setattr(operations.requests, "get", fake_get)
    return seen


def test_canvas_probe_targets_basepath_not_root(monkeypatch):
    """画布是 Next.js，basePath=/canvas-app，根路径是 404。

    探针必须带 basePath，否则永远判失败。
    """
    app = _app({"CANVAS_APP_URL": "http://canvas:3000", "TESTING": False})
    seen = _capture_url(monkeypatch)
    with app.app_context():
        operations.probe_canvas()
    assert seen == ["http://canvas:3000/canvas-app"]


def test_canvas_probe_does_not_go_through_public_domain(monkeypatch):
    """探针不应绕公网。

    走公网要经 Cloudflare，站点重启瞬间边缘会返回 521，把内部健康服务
    误判为异常；而且往返本身就慢。
    """
    app = _app({"CANVAS_APP_URL": "http://canvas:3000", "TESTING": False})
    seen = _capture_url(monkeypatch)
    with app.app_context():
        operations.probe_canvas()
    assert not any("paintiworld" in u for u in seen)
    assert all(u.startswith("http://canvas") for u in seen)


def test_agent_probe_uses_container_hostname(monkeypatch):
    app = _app({"CANVAS_AGENT_URL": "http://canvas-agent:17371", "TESTING": False})
    seen = _capture_url(monkeypatch)
    with app.app_context():
        operations.probe_agent()
    assert seen == ["http://canvas-agent:17371/health"]


def test_storage_cleanup_reports_last_run_from_shared_log(monkeypatch, tmp_path):
    """有清理日志时，应报出最近一次执行的时间与结果。

    探针读的是**共享日志卷**（/var/log/huishi），不是宿主 /etc/cron.d——
    后者容器看不到，会永远报 warning（一个常报警的探针等于没有探针）。
    "任务最近有没有真的跑起来"比"定时配置存不存在"更接近健康的本意。
    """
    log = tmp_path / "huishi-storage-sweep.log"
    log.write_text(
        "2026-10-11T04:17:01Z storage-sweep deleted_files=32 deleted_bytes=29753541" + chr(10),
        encoding="utf-8",
    )
    app = _app()
    monkeypatch.setattr(operations, "_cleanup_log_dirs", lambda: (str(tmp_path),))
    with app.app_context():
        result = operations.probe_storage_cleanup()
    assert result["status"] == "ok"
    assert "上次清理" in result["message"]
    # 日志最后一行透出，便于直接在总览页看到执行结果
    assert "deleted_files=32" in result["message"]


def test_storage_cleanup_warns_when_log_is_stale(monkeypatch, tmp_path):
    """日志超过 36 小时未更新 → 任务可能没在跑。"""
    log = tmp_path / "huishi-storage-sweep.log"
    log.write_text("2026-10-01T04:17:01Z storage-sweep deleted_files=0" + chr(10), encoding="utf-8")
    stale = time.time() - 72 * 3600
    os.utime(log, (stale, stale))
    app = _app()
    monkeypatch.setattr(operations, "_cleanup_log_dirs", lambda: (str(tmp_path),))
    with app.app_context():
        result = operations.probe_storage_cleanup()
    assert result["status"] == "warning"
    assert "天前" in result["message"]


def test_storage_cleanup_warns_when_no_log(monkeypatch, tmp_path):
    """完全没有日志 → 保留策略可能未生效（此前长期存在的问题）。"""
    app = _app()
    monkeypatch.setattr(operations, "_cleanup_log_dirs", lambda: (str(tmp_path),))
    with app.app_context():
        result = operations.probe_storage_cleanup()
    assert result["status"] == "warning"
    assert "保留策略" in result["message"]
