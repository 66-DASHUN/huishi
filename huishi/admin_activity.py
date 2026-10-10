from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import re
from typing import Any

from huishi.providers import image_model_label


EVENT_LABELS = {
    "image_generation": "图像生成",
    "canvas_generation": "画布生成",
    "generation_charge": "生成扣费",
    "generation_refund": "生成退款",
    "invite_reward": "邀请奖励",
    "invite_signup_bonus": "受邀奖励",
    "admin_adjust": "余额调整",
    "admin_initial": "初始积分",
    "other": "其他流水",
}

STATUS_LABELS = {
    "success": "已完成",
    "failed": "失败",
    "refunded": "已退款",
    "credited": "已入账",
    "debited": "已扣除",
}

KNOWN_LEDGER_EVENTS = {
    "generation": "generation_charge",
    "generation_refund": "generation_refund",
    "invite_reward": "invite_reward",
    "invite_signup_bonus": "invite_signup_bonus",
    "admin_adjust": "admin_adjust",
    "admin_initial": "admin_initial",
}


@dataclass(frozen=True)
class ActivityPage:
    rows: list[dict[str, Any]]
    total: int
    page: int
    per_page: int


def query_activity_page(
    *,
    db=None,
    search: str = "",
    user: str = "",
    user_id: int | None = None,
    event_type: str = "",
    mode: str = "",
    status: str = "",
    from_date: str = "",
    to_date: str = "",
    page: int = 1,
    per_page: int = 20,
    limit: int | None = None,
) -> ActivityPage:
    """查询后台活动流。

    ``limit`` 是给"只要前几条"的场景（如管理首页只展示 8 条）用的**取数上限**：
    设了它就只从两个来源各取有限行再合并，避免为了显示几行把 records 与
    point_ledger 全表拉进内存。注意它限制的是**取数**，不是结果条数。

    为什么不直接在 SQL 里 LIMIT 到 limit：合并后的前 N 条可能来自任一来源，
    单边截断会漏行。这里按放大后的上限取（见下方 ``fetch_cap``），
    并在结果侧仍然截到 ``limit``，保证与不设上限时前 N 条一致。
    """
    if db is None:
        from huishi.db import get_db

        db = get_db()

    record_where, record_params = _base_activity_filters(
        table="records",
        user=user,
        user_id=user_id,
        from_date=from_date,
        to_date=to_date,
    )
    ledger_where, ledger_params = _base_activity_filters(
        table="point_ledger",
        user=user,
        user_id=user_id,
        from_date=from_date,
        to_date=to_date,
    )
    if mode:
        record_where.append("records.mode = ?")
        record_params.append(mode)
        ledger_where.append("linked_record.mode = ?")
        ledger_params.append(mode)

    # 取数上限。放大 4 倍是因为合并去重会消耗行（一条记录可能吃掉多行流水，
    # 流水也可能作为独立事件出现），留出余量后前 limit 条与全量查询结果一致。
    fetch_cap = None if limit is None else max(int(limit), 1) * 4
    record_sql_limit = "" if fetch_cap is None else f" LIMIT {fetch_cap}"
    ledger_sql_limit = "" if fetch_cap is None else f" LIMIT {fetch_cap}"

    records = db.execute(
        f"""
        SELECT records.*, users.username
        FROM records
        JOIN users ON users.id = records.user_id
        WHERE {' AND '.join(record_where) if record_where else '1 = 1'}
        ORDER BY records.id DESC{record_sql_limit}
        """,
        tuple(record_params),
    ).fetchall()
    ledger_rows = db.execute(
        f"""
        SELECT point_ledger.*, users.username
        FROM point_ledger
        JOIN users ON users.id = point_ledger.user_id
        LEFT JOIN records AS linked_record ON linked_record.id = point_ledger.record_id
        WHERE {' AND '.join(ledger_where) if ledger_where else '1 = 1'}
        ORDER BY point_ledger.id DESC{ledger_sql_limit}
        """,
        tuple(ledger_params),
    ).fetchall()

    rows = merge_activity_rows(records, ledger_rows)
    normalized_search = search.strip().lower()
    if normalized_search:
        rows = [row for row in rows if _activity_search_text(row).find(normalized_search) >= 0]
    if event_type:
        rows = [row for row in rows if row["event_type"] == event_type]
    if status:
        rows = [row for row in rows if row["status"] == status]

    if limit is not None:
        # 只取前 N 条的场景不需要 total 的绝对准确性，也无法在全量截断后算出
        # 真实 total，这里按已取到的行数报，调用方不展示它。
        capped = max(int(limit), 1)
        return ActivityPage(rows=rows[:capped], total=len(rows[:capped]), page=1, per_page=capped)

    normalized_page = max(1, int(page))
    normalized_per_page = min(100, max(10, int(per_page)))
    offset = (normalized_page - 1) * normalized_per_page
    return ActivityPage(
        rows=rows[offset : offset + normalized_per_page],
        total=len(rows),
        page=normalized_page,
        per_page=normalized_per_page,
    )


def merge_activity_rows(
    records: Iterable[Mapping[str, Any]],
    ledger_rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    normalized_records = [dict(row) for row in records]
    normalized_ledger = [dict(row) for row in ledger_rows]
    ledger_by_record: dict[int, list[dict[str, Any]]] = {}
    for row in normalized_ledger:
        record_id = row.get("record_id")
        if record_id is not None:
            ledger_by_record.setdefault(int(record_id), []).append(row)

    consumed_ledger_ids: set[int] = set()
    events: list[dict[str, Any]] = []
    for record in normalized_records:
        linked_rows = ledger_by_record.get(int(record["id"]), [])
        ledger = _select_linked_ledger(record, linked_rows)
        if ledger is not None:
            consumed_ledger_ids.add(int(ledger["id"]))
        events.append(build_record_event(record, ledger))

    for ledger in normalized_ledger:
        if int(ledger["id"]) not in consumed_ledger_ids:
            events.append(build_ledger_event(ledger))

    return sorted(events, key=lambda row: (str(row["occurred_at"]), str(row["id"])), reverse=True)


def build_record_event(record: Mapping[str, Any], ledger: Mapping[str, Any] | None) -> dict[str, Any]:
    reason = str((ledger or {}).get("reason") or "")
    refunded = reason == "generation_refund"
    asset_source = str(record.get("asset_source") or "image")
    event_type = "generation_refund" if refunded else ("canvas_generation" if asset_source == "canvas" else "image_generation")
    status = "refunded" if refunded else str(record.get("status") or "success")
    prompt = str(record.get("prompt") or "")
    record_id = int(record["id"])
    ledger_id = int(ledger["id"]) if ledger is not None else None
    occurred_at = str((ledger or {}).get("created_at") or record.get("created_at") or "")
    points_delta = int(ledger["delta"]) if ledger is not None and ledger.get("delta") is not None else -int(record.get("points_charged") or 0)
    model_source = str(record.get("model_source") or "")
    return {
        "id": f"record:{record_id}:ledger:{ledger_id or 0}",
        "occurred_at": occurred_at,
        "user_id": int(record["user_id"]),
        "username": str(record.get("username") or ""),
        "event_type": event_type,
        "event_label": EVENT_LABELS[event_type],
        "summary": prompt or f"生成记录 #{record_id}",
        "points_delta": points_delta,
        "status": status,
        "status_label": STATUS_LABELS.get(status, status or "未知"),
        "record_id": record_id,
        "ledger_id": ledger_id,
        "mode": str(record.get("mode") or ""),
        "resolution": str(record.get("resolution") or ""),
        "actual_size": str(record.get("actual_size") or ""),
        "model_source": model_source,
        "model_label": image_model_label(model_source),
        "prompt": prompt,
        "reason": reason,
        "admin_note": str((ledger or {}).get("admin_note") or ""),
    }


def build_ledger_event(ledger: Mapping[str, Any]) -> dict[str, Any]:
    reason = str(ledger.get("reason") or "")
    event_type = KNOWN_LEDGER_EVENTS.get(reason, "other")
    delta = int(ledger.get("delta") or 0)
    status = "refunded" if event_type == "generation_refund" else ("credited" if delta >= 0 else "debited")
    ledger_id = int(ledger["id"])
    note = str(ledger.get("admin_note") or "")
    return {
        "id": f"ledger:{ledger_id}",
        "occurred_at": str(ledger.get("created_at") or ""),
        "user_id": int(ledger["user_id"]),
        "username": str(ledger.get("username") or ""),
        "event_type": event_type,
        "event_label": EVENT_LABELS[event_type],
        "summary": note or EVENT_LABELS[event_type],
        "points_delta": delta,
        "status": status,
        "status_label": STATUS_LABELS[status],
        "record_id": int(ledger["record_id"]) if ledger.get("record_id") is not None else None,
        "ledger_id": ledger_id,
        "mode": "",
        "resolution": "",
        "actual_size": "",
        "model_source": "",
        "model_label": "",
        "prompt": "",
        "reason": reason,
        "admin_note": note,
    }


def _select_linked_ledger(record: Mapping[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    if str(record.get("status") or "") == "failed":
        refund = next((row for row in rows if row.get("reason") == "generation_refund"), None)
        if refund is not None:
            return refund
    charge = next((row for row in rows if row.get("reason") == "generation"), None)
    return charge or next((row for row in rows if row.get("reason") == "generation_refund"), rows[0])


def _base_activity_filters(
    *,
    table: str,
    user: str,
    user_id: int | None,
    from_date: str,
    to_date: str,
) -> tuple[list[str], list[object]]:
    where: list[str] = []
    params: list[object] = []
    if user_id is not None:
        where.append(f"{table}.user_id = ?")
        params.append(int(user_id))
    if user.strip():
        where.append("LOWER(users.username) LIKE ?")
        params.append(f"%{user.strip().lower()}%")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", from_date or ""):
        where.append(f"{table}.created_at >= ?")
        params.append(f"{from_date}T00:00:00+00:00")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", to_date or ""):
        where.append(f"{table}.created_at <= ?")
        params.append(f"{to_date}T23:59:59.999999+00:00")
    return where, params


def _activity_search_text(row: Mapping[str, Any]) -> str:
    return " ".join(
        str(row.get(key) or "")
        for key in (
            "username",
            "event_label",
            "summary",
            "prompt",
            "reason",
            "admin_note",
            "mode",
            "resolution",
            "actual_size",
            "model_source",
            "record_id",
            "ledger_id",
        )
    ).lower()
