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

from pathlib import Path

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


def test_storage_cleanup_reports_real_cron_schedule(monkeypatch, tmp_path):
    """存在 cron 条目时，应报出真实的执行时间，而不是写死的假文案。"""
    cron = tmp_path / "huishi-storage-sweep"
    cron.write_text(
        "SHELL=/bin/bash\n"
        "PATH=/usr/local/bin:/usr/bin\n"
        "17 4 * * * root /usr/local/bin/huishi-storage-sweep >> /var/log/x.log 2>&1\n",
        encoding="utf-8",
    )
    app = _app()
    real_isfile = operations.os.path.isfile
    monkeypatch.setattr(
        operations.os.path,
        "isfile",
        lambda p: str(p) == str(cron) or real_isfile(p),
    )
    # 把候选路径指向临时文件
    monkeypatch.setattr(
        operations,
        "_cron_candidates",
        lambda: ((str(cron), "cron"),),
        raising=False,
    )
    with app.app_context():
        result = operations.probe_storage_cleanup()
    assert result["status"] == "ok"
    assert "04:17" in result["message"]
    assert "timer" not in result["message"]


def test_storage_cleanup_warns_when_nothing_scheduled(monkeypatch):
    """没有任何定时任务时应报警——这意味着保留策略在空转。"""
    app = _app()
    monkeypatch.setattr(operations, "_cron_candidates", lambda: (), raising=False)
    with app.app_context():
        result = operations.probe_storage_cleanup()
    assert result["status"] == "warning"
