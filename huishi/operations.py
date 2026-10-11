from __future__ import annotations

import os

import json
import shutil
import time
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
    response = requests.get(url, timeout=(0.5, 1.0), verify=True)
    response.raise_for_status()
    latency_ms = int(response.elapsed.total_seconds() * 1000)
    return _result("ok", f"{response.status_code} · {latency_ms} ms", latency_ms=latency_ms)


def probe_canvas() -> ProbeResult:
    """探测画布是否在线。

    优先用**容器网络内的地址**（compose 里的服务名 canvas:3000），而不是
    公网域名：走公网要绕 Cloudflare，站点重启的瞬间边缘会返回 521，
    把内部服务判成"异常"；而且公网往返本身就慢。

    画布是 Next.js 且 basePath=/canvas-app，所以根路径返回 404，
    必须带上 basePath 才算探活成功。
    """
    if current_app.config.get("TESTING"):
        return _result("unknown", "测试环境未探测")
    url = str(current_app.config.get("CANVAS_APP_URL") or "").rstrip("/")
    if not url:
        return _result("warning", "未配置画布地址")
    return _probe_http(f"{url}/canvas-app", "画布")


def probe_agent() -> ProbeResult:
    """探测画布 Agent 是否在线。

    注意：agent 容器自身的 healthcheck 是**在容器内**打 127.0.0.1，所以
    即使它只绑回环、外部完全连不上，容器状态也显示 healthy。
    这类"容器健康但服务不可达"只能靠这里的跨容器探测发现。
    """
    if current_app.config.get("TESTING"):
        return _result("unknown", "测试环境未探测")
    url = str(current_app.config.get("CANVAS_AGENT_URL") or "").rstrip("/")
    if not url:
        return _result("warning", "未配置 Agent 地址")
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


def probe_paused_media_tasks() -> ProbeResult:
    """待人工核对的视频任务。

    这些任务的上游受理状态未知（可能已扣费也可能没有），因此代码**刻意**
    不自动恢复也不会改投其它渠道——只能由管理员确认原渠道后手动恢复。
    问题在于此前没有任何可发现性：管理员除非恰好打开业务流水页并往下翻，
    否则不知道有任务卡在那里等核对。

    这里把它做成运行总览的一行，并指向业务流水的待核对表格。
    """
    from huishi.media_tasks import count_needs_reconciliation

    count = count_needs_reconciliation()
    if not count:
        return _result("ok", "无待核对任务", count=0)
    return _result(
        "warning",
        f"{count} 条待核对，需人工确认上游受理状态",
        count=count,
        href="/admin/records#media-reconciliation",
    )


# 清理任务的日志文件名。任务由**宿主 cron** 触发，但它把结果写进
# 容器与宿主共享的日志卷（compose 的 logs 卷挂在 /var/log/huishi），
# 所以容器内的探针能读到——这是它能观测宿主任务的唯一途径。
_CLEANUP_LOG_NAMES = (
    "huishi-storage-sweep.log",
    "huishi-disk-cleanup.log",
)


def _cleanup_log_dirs() -> tuple[str, ...]:
    """清理日志所在目录（按可能性排序）。

    抽成函数是为了测试能注入——否则测试只能依赖真实文件系统。
    """
    log_dir = str(current_app.config.get("LOG_DIR") or "/var/log/huishi")
    return (log_dir, "/var/log/huishi")


def _read_cleanup_log_tail() -> tuple[str, float] | None:
    """返回（最后一行内容, 文件修改时间），取不到则 None。"""
    newest: tuple[str, float] | None = None
    for directory in _cleanup_log_dirs():
        for name in _CLEANUP_LOG_NAMES:
            path = os.path.join(directory, name)
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                continue
            if newest is not None and mtime <= newest[1]:
                continue
            tail = ""
            try:
                with open(path, encoding="utf-8", errors="replace") as fh:
                    lines = [ln.strip() for ln in fh if ln.strip()]
                tail = lines[-1] if lines else ""
            except OSError:
                tail = ""
            newest = (tail, mtime)
    return newest


def probe_storage_cleanup() -> ProbeResult:
    """uploads 清理任务的真实状态。

    历史：这里曾写死 "由 huishi-storage-sweep.timer 定时执行" —— 但线上
    根本没有那个 systemd 单元，实际执行的是**宿主 cron**。运维照那句话去
    systemctl status 只会一无所获。

    后来改成读 /etc/cron.d —— 又错了：backend 在容器里，看不到宿主文件系统，
    于是永远报 warning，一个常报警的探针等于没有探针。

    现在读**共享日志卷**：任务把结果写进 /var/log/huishi（compose 的 logs 卷，
    容器与宿主都能看到）。"任务最近有没有真的跑起来、结果如何"比"定时配置
    存不存在"更接近健康的本意 —— 配置存在但任务失败才是更危险的情况。

    刻意不做 TESTING 短路：它只读本地文件、不依赖外部服务，
    测试环境同样该如实反映，否则这条探针永远测不到。
    """
    found = _read_cleanup_log_tail()
    if found is not None:
        tail, mtime = found
        age_hours = (time.time() - mtime) / 3600
        # 每天跑一次；超过 36 小时没动静说明任务没在跑或一直失败。
        if age_hours > 36:
            return _result(
                "warning",
                f"上次清理在 {age_hours / 24:.0f} 天前，可能未按计划执行",
                age_hours=round(age_hours, 1),
            )
        detail = tail or "已执行"
        return _result("ok", f"上次清理 {age_hours:.1f} 小时前 · {detail}", age_hours=round(age_hours, 1))
    return _result("warning", "未见清理日志，保留策略可能未生效")


def collect_operations_health() -> dict[str, ProbeResult]:
    return {
        "database": _safe_probe(probe_database),
        "redis": _safe_probe(probe_redis),
        "canvas": _safe_probe(probe_canvas),
        "agent": _safe_probe(probe_agent),
        "disk": _safe_probe(probe_disk),
        "backup": _safe_probe(probe_backup),
        "failed_tasks": _safe_probe(probe_failed_tasks),
        "paused_media_tasks": _safe_probe(probe_paused_media_tasks),
        "storage_cleanup": _safe_probe(probe_storage_cleanup),
    }
