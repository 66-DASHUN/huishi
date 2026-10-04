from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

import requests
from flask import current_app

from huishi.db import get_db


ProbeResult = dict[str, object]


def _checked_at() -> str:
    return datetime.now(timezone.utc).isoformat()


def _result(status: str, message: str, **values: object) -> ProbeResult:
    return {"status": status, "message": message, "checked_at": _checked_at(), **values}


def _safe_probe(probe: Callable[[], ProbeResult]) -> ProbeResult:
    try:
        result = dict(probe())
        result.setdefault("checked_at", _checked_at())
        return result
    except Exception as exc:
        return _result("error", type(exc).__name__)


def probe_database() -> ProbeResult:
    row = get_db().execute("SELECT 1 AS value").fetchone()
    if row is None or int(row["value"]) != 1:
        raise RuntimeError("database probe returned no value")
    return _result("ok", "连接正常")


def probe_redis() -> ProbeResult:
    redis_url = str(current_app.config.get("REDIS_URL") or "").strip()
    if not redis_url:
        return _result("warning", "未配置 Redis")
    from redis import Redis

    client = Redis.from_url(redis_url, socket_connect_timeout=0.75, socket_timeout=0.75)
    client.ping()
    queue_name = str(current_app.config.get("RQ_QUEUE_NAME") or "huishi-generation")
    queued = int(client.llen(f"rq:queue:{queue_name}"))
    return _result("ok", f"队列 {queued} 项", queued=queued)


def _probe_http(url: str, label: str) -> ProbeResult:
    if not url:
        return _result("warning", f"未配置{label}地址")
    response = requests.get(url, timeout=(0.5, 1.0), verify=False)
    response.raise_for_status()
    latency_ms = int(response.elapsed.total_seconds() * 1000)
    return _result("ok", f"{response.status_code} · {latency_ms} ms", latency_ms=latency_ms)


def probe_canvas() -> ProbeResult:
    if current_app.config.get("TESTING"):
        return _result("unknown", "测试环境未探测")
    url = str(current_app.config.get("CANVAS_APP_URL") or "").rstrip("/")
    return _probe_http(url, "画布")


def probe_agent() -> ProbeResult:
    if current_app.config.get("TESTING"):
        return _result("unknown", "测试环境未探测")
    url = str(current_app.config.get("CANVAS_AGENT_URL") or "http://127.0.0.1:17371").rstrip("/")
    return _probe_http(f"{url}/health", "Agent")


def probe_disk() -> ProbeResult:
    target = Path("/") if not current_app.config.get("TESTING") else Path(current_app.config["OUTPUT_DIR"]).parent
    target.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(target)
    percent = round((usage.used / usage.total) * 100, 1) if usage.total else 0.0
    status = "error" if percent >= 92 else "warning" if percent >= 80 else "ok"
    return _result(status, f"已用 {percent}% · 剩余 {usage.free // (1024 ** 3)} GB", used_percent=percent, free_bytes=usage.free)


def probe_backup() -> ProbeResult:
    backup_dir = Path(current_app.config.get("BACKUP_DIR") or "/var/backups/huishi/postgres")
    status_path = backup_dir / "status.json"
    if not status_path.is_file():
        return _result("warning", "尚无备份状态")
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    if not payload.get("ok"):
        return _result("error", str(payload.get("error") or "最近备份失败"), updated_at=payload.get("updated_at", ""))
    backup_path = Path(str(payload.get("path") or ""))
    if not backup_path.is_file():
        return _result("error", "备份文件不存在")
    size = int(payload.get("size_bytes") or backup_path.stat().st_size)
    return _result("ok", f"{size} bytes · {payload.get('updated_at', '')}", path=str(backup_path), size_bytes=size)


def probe_failed_tasks() -> ProbeResult:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    row = get_db().execute(
        "SELECT COUNT(*) AS value FROM generation_tasks WHERE status = 'failed' AND created_at >= ?",
        (cutoff,),
    ).fetchone()
    count = int(row["value"] if row is not None else 0)
    status = "warning" if count else "ok"
    return _result(status, f"24 小时内 {count} 条", count=count)


def probe_storage_cleanup() -> ProbeResult:
    return _result("unknown", "由 huishi-storage-sweep.timer 定时执行")


def collect_operations_health() -> dict[str, ProbeResult]:
    return {
        "database": _safe_probe(probe_database),
        "redis": _safe_probe(probe_redis),
        "canvas": _safe_probe(probe_canvas),
        "agent": _safe_probe(probe_agent),
        "disk": _safe_probe(probe_disk),
        "backup": _safe_probe(probe_backup),
        "failed_tasks": _safe_probe(probe_failed_tasks),
        "storage_cleanup": _safe_probe(probe_storage_cleanup),
    }
