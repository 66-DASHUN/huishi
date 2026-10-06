"""Per-call channel (provider) telemetry.

Why this module exists: before it, a failed image generation left *no* database
trace of which channel was called. ``generate_image_with_failover`` wrote one
``logger.warning`` and nothing else, so ``generation_tasks.provider_id`` is
permanently NULL for image tasks and there was no way to compute a per-channel
failure rate. ``provider_call_logs`` records one row per upstream call attempt,
which is the granularity the failover loop actually works at.

Two invariants hold this module together:

1. ``record_provider_call`` never raises. Telemetry must not be able to fail a
   real generation, so the entire body is wrapped and errors are logged at
   debug level. If the table is missing, the database is down, or the payload is
   malformed, the call is silently dropped.
2. ``record_provider_call`` commits its own transaction. Callers must not be
   inside an open transaction, or this commit would take their work with it.

Reading is deliberately plain SQL aggregation rather than loading rows into
Python: ``provider_call_logs`` grows with every upstream call.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from huishi.db import get_db, utc_now
from huishi.secrets import redact_sensitive_text

logger = logging.getLogger(__name__)

# Personal BYOK calls carry provider_id = NULL (the route snapshot uses a
# synthetic provider with no id). They still count toward the window totals.
PERSONAL_PROVIDER_LABEL = "个人 API Key"

OUTCOME_SUCCEEDED = "succeeded"
OUTCOME_FAILED = "failed"

ERROR_CLASS_CONFIGURATION = "configuration"
ERROR_CLASS_UPSTREAM = "upstream"
ERROR_CLASS_UNKNOWN = "unknown"

# A channel needs at least this many calls in the window before a failure rate
# is meaningful; below it a single failure would read as a total outage.
MIN_CALLS_FOR_RATE = 3

STATUS_LABELS = {
    "healthy": "正常",
    "warning": "警告",
    "critical": "异常",
    "unknown": "无数据",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_int_or_none(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def record_provider_call(
    *,
    provider_id: object = None,
    provider_name: object = "",
    api_format: object = "",
    media_type: object = "",
    model: object = "",
    task_id: object = None,
    record_id: object = None,
    outcome: str = OUTCOME_SUCCEEDED,
    error_class: str = "",
    error_message: object = "",
    latency_ms: object = 0,
    attempt_index: object = 0,
) -> None:
    """Append one upstream call attempt. Never raises, never returns an error.

    ``error_message`` is redacted here rather than by the caller so a future
    call site cannot accidentally persist an api_key.
    """
    try:
        safe_error = ""
        if error_message:
            safe_error = redact_sensitive_text(error_message)[:2000]
        db = get_db()
        db.execute(
            "INSERT INTO provider_call_logs ("
            " provider_id, provider_name, api_format, media_type, model,"
            " task_id, record_id, outcome, error_class, error_message,"
            " latency_ms, attempt_index, created_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                _as_int_or_none(provider_id),
                str(provider_name or "")[:200],
                str(api_format or "")[:100],
                str(media_type or "")[:50],
                str(model or "")[:200],
                _as_int_or_none(task_id),
                _as_int_or_none(record_id),
                OUTCOME_FAILED if str(outcome) == OUTCOME_FAILED else OUTCOME_SUCCEEDED,
                str(error_class or "")[:50],
                safe_error,
                max(0, _as_int_or_none(latency_ms) or 0),
                max(0, _as_int_or_none(attempt_index) or 0),
                _now(),
            ),
        )
        db.commit()
    except Exception:  # noqa: BLE001 - telemetry must never break a generation
        logger.debug("provider_call_logs write skipped", exc_info=True)


def _cutoff(window_hours: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=max(1, int(window_hours)))).isoformat()


def _failure_rate(calls: int, failed: int) -> float:
    return round((failed / calls) * 100, 1) if calls else 0.0


def _health_status(*, enabled: bool, calls: int, failure_rate: float, disabled_at: str) -> str:
    # ``enabled`` 是权威开关。``disabled_at`` 只是一个历史诊断时间戳：
    # 管理员手动重新启用渠道时（``save_provider``）不会清它，所以它非空
    # 只说明"这个渠道历史上被自动停用过"，并不代表现在不可用。早期版本
    # 把二者并列判定，导致刚成功出片、成功率 100% 的渠道被显示成"异常"。
    if not enabled:
        return "critical"
    if not calls:
        return "unknown"
    if calls >= MIN_CALLS_FOR_RATE and failure_rate >= 50.0:
        return "critical"
    if failure_rate > 0.0:
        return "warning"
    return "healthy"


def _consecutive_failures(db, provider_id: int, cutoff: str) -> int:
    """Trailing run of failures for one channel, most recent first."""
    rows = db.execute(
        "SELECT outcome FROM provider_call_logs"
        " WHERE provider_id = ? AND created_at >= ?"
        " ORDER BY id DESC LIMIT 25",
        (provider_id, cutoff),
    ).fetchall()
    streak = 0
    for row in rows:
        if str(row["outcome"]) == OUTCOME_FAILED:
            streak += 1
        else:
            break
    return streak


def _top_errors(db, provider_id: int, cutoff: str, limit: int = 3) -> list[dict]:
    """Grouped failure reasons for the detail column.

    Grouping on the raw message keeps distinct causes apart; error_summary() is
    applied afterwards for display only, so the occurrence counts stay accurate.
    """
    from huishi.model_lifecycle import error_summary

    rows = db.execute(
        "SELECT error_message, COUNT(*) AS occurrences FROM provider_call_logs"
        " WHERE provider_id = ? AND outcome = ? AND created_at >= ?"
        " GROUP BY error_message ORDER BY occurrences DESC LIMIT ?",
        (provider_id, OUTCOME_FAILED, cutoff, limit),
    ).fetchall()
    return [
        {
            "message": str(row["error_message"] or ""),
            "label": error_summary(row["error_message"]) or "调用失败",
            "occurrences": int(row["occurrences"]),
        }
        for row in rows
    ]


def _personal_calls(db, cutoff: str) -> dict | None:
    """Aggregate the provider_id IS NULL bucket (personal BYOK, or pre-save rows).

    Surfaced on the page so the channel rows visibly reconcile with the total
    instead of silently dropping calls that carry no channel id.
    """
    row = db.execute(
        "SELECT COUNT(*) AS calls,"
        " SUM(CASE WHEN outcome = ? THEN 1 ELSE 0 END) AS failed,"
        " MAX(created_at) AS last_call_at,"
        " ROUND(AVG(CASE WHEN latency_ms > 0 THEN latency_ms END)) AS avg_latency_ms"
        " FROM provider_call_logs WHERE provider_id IS NULL AND created_at >= ?",
        (OUTCOME_FAILED, cutoff),
    ).fetchone()
    calls = int((row["calls"] if row is not None else 0) or 0)
    if not calls:
        return None
    failed = int((row["failed"] if row is not None else 0) or 0)
    return {
        "name": PERSONAL_PROVIDER_LABEL,
        "calls": calls,
        "failed": failed,
        "failure_rate": _failure_rate(calls, failed),
        "avg_latency_ms": int((row["avg_latency_ms"] if row is not None else 0) or 0),
        "last_call_at": str((row["last_call_at"] if row is not None else "") or ""),
    }


def _durable_task_counts(db, cutoff: str) -> dict[int, dict]:
    """Video/audio tasks carry provider_id, written by begin_task_route.

    Used only as a fallback so a channel that is being used but has no per-call
    log yet does not read as 'no data at all'.
    """
    rows = db.execute(
        "SELECT provider_id,"
        " SUM(CASE WHEN status = 'succeeded' THEN 1 ELSE 0 END) AS succeeded,"
        " SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed"
        " FROM generation_tasks"
        " WHERE provider_id IS NOT NULL AND created_at >= ?"
        " GROUP BY provider_id",
        (cutoff,),
    ).fetchall()
    return {
        int(row["provider_id"]): {
            "succeeded": int(row["succeeded"] or 0),
            "failed": int(row["failed"] or 0),
        }
        for row in rows
        if row["provider_id"] is not None
    }


def channel_health(window_hours: int = 24) -> dict:
    """Per-channel health over a rolling window.

    Returns ``{"window_hours", "totals", "channels", ...}``. Channels with no
    call data are reported with ``status='unknown'`` and an explicit note rather
    than a misleading 0% failure rate.
    """
    from huishi.model_lifecycle import error_summary

    window_hours = max(1, int(window_hours))
    cutoff = _cutoff(window_hours)
    db = get_db()

    log_rows = db.execute(
        "SELECT provider_id,"
        " COUNT(*) AS calls,"
        " SUM(CASE WHEN outcome = ? THEN 1 ELSE 0 END) AS succeeded,"
        " SUM(CASE WHEN outcome = ? THEN 1 ELSE 0 END) AS failed,"
        " MAX(created_at) AS last_call_at,"
        " ROUND(AVG(CASE WHEN latency_ms > 0 THEN latency_ms END)) AS avg_latency_ms"
        " FROM provider_call_logs WHERE created_at >= ?"
        " GROUP BY provider_id",
        (OUTCOME_SUCCEEDED, OUTCOME_FAILED, cutoff),
    ).fetchall()

    by_id: dict[int, dict] = {}
    for row in log_rows:
        if row["provider_id"] is None:
            continue
        by_id[int(row["provider_id"])] = {
            "calls": int(row["calls"] or 0),
            "succeeded": int(row["succeeded"] or 0),
            "failed": int(row["failed"] or 0),
            "last_call_at": str(row["last_call_at"] or ""),
            "avg_latency_ms": int(row["avg_latency_ms"] or 0),
        }

    providers = db.execute(
        "SELECT id, name, provider_type, api_format, enabled, priority,"
        " last_error, disabled_at, last_checked_at"
        " FROM api_providers ORDER BY priority ASC, id ASC",
    ).fetchall()

    durable = _durable_task_counts(db, cutoff)
    personal = _personal_calls(db, cutoff)

    channels: list[dict] = []
    for row in providers:
        provider_id = int(row["id"])
        bucket = by_id.get(provider_id)
        calls = bucket["calls"] if bucket else 0
        succeeded = bucket["succeeded"] if bucket else 0
        failed = bucket["failed"] if bucket else 0
        rate = _failure_rate(calls, failed)
        enabled = bool(row["enabled"])
        disabled_at = str(row["disabled_at"] or "")

        note = ""
        status = _health_status(
            enabled=enabled, calls=calls, failure_rate=rate, disabled_at=disabled_at
        )
        if not calls:
            fallback = durable.get(provider_id)
            if fallback and (fallback["succeeded"] or fallback["failed"]):
                calls = fallback["succeeded"] + fallback["failed"]
                succeeded = fallback["succeeded"]
                failed = fallback["failed"]
                rate = _failure_rate(calls, failed)
                note = "该渠道暂无逐次调用记录，以上为任务级统计"
                status = "warning" if failed else "healthy"
                if not enabled:
                    status = "critical"
            else:
                note = "窗口内无调用数据，无法判断健康度"

        channels.append(
            {
                "id": provider_id,
                "name": str(row["name"] or ""),
                "provider_type": str(row["provider_type"] or ""),
                "api_format": str(row["api_format"] or ""),
                "enabled": enabled,
                "priority": int(row["priority"] or 100),
                "disabled_at": disabled_at,
                "last_checked_at": str(row["last_checked_at"] or ""),
                "last_error": redact_sensitive_text(row["last_error"] or ""),
                "last_error_label": (
                    error_summary(row["last_error"]) if row["last_error"] else ""
                ),
                "calls": calls,
                "succeeded": succeeded,
                "failed": failed,
                "failure_rate": rate,
                "avg_latency_ms": bucket["avg_latency_ms"] if bucket else 0,
                "last_call_at": bucket["last_call_at"] if bucket else "",
                "consecutive_failures": _consecutive_failures(db, provider_id, cutoff),
                "top_errors": _top_errors(db, provider_id, cutoff),
                "status": status,
                "status_label": STATUS_LABELS.get(status, status),
                "note": note,
                "attributed": bucket is not None,
            }
        )

    personal_calls = personal["calls"] if personal else 0
    personal_failed = personal["failed"] if personal else 0
    total_calls = sum(c["calls"] for c in channels) + personal_calls
    total_failed = sum(c["failed"] for c in channels) + personal_failed

    totals = {
        "channels": len(channels),
        "calls": total_calls,
        "succeeded": total_calls - total_failed,
        "failed": total_failed,
        "critical": sum(1 for c in channels if c["status"] == "critical"),
        "warning": sum(1 for c in channels if c["status"] == "warning"),
        "success_rate": round(((total_calls - total_failed) / total_calls) * 100, 1)
        if total_calls
        else 0.0,
    }

    return {
        "window_hours": window_hours,
        "generated_at": utc_now(),
        "totals": totals,
        "channels": channels,
        "personal_provider": personal,
    }


def provider_balance(provider: dict) -> dict:
    """Query upstream account balance, for channel types that expose one.

    Only the seedance_media adapter defines a balance endpoint
    (``video_adapters/seedance_media.py``). Every other api_format reports
    ``unsupported`` rather than guessing a path.
    """
    if str(provider.get("api_format") or "") != "seedance_media":
        return {
            "status": "unsupported",
            "message": "该渠道类型不提供余额查询",
            "provider_id": provider.get("id"),
        }
    try:
        from huishi.video_adapters import seedance_media

        payload = seedance_media.balance(provider)
    except Exception as exc:  # noqa: BLE001 - a probe failure is a result, not a crash
        return {
            "status": "error",
            "message": redact_sensitive_text(str(exc))[:300],
            "provider_id": provider.get("id"),
        }
    value = None
    if isinstance(payload, dict):
        value = payload.get("balance")
        if value is None:
            data = payload.get("data")
            value = data.get("balance") if isinstance(data, dict) else None
    return {
        "status": "ok" if value is not None else "unknown",
        "message": str(value) if value is not None else "上游未返回余额字段",
        "balance": value,
        "provider_id": provider.get("id"),
        "checked_at": _now(),
    }
