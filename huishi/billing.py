from __future__ import annotations

import re

from huishi.db import get_db, utc_now


RESOLUTION_TIERS = (("1K", 0, 1560), ("2K", 1561, 2440), ("4K", 2441, 4280))


def tier_for_size(size: str) -> str:
    match = re.fullmatch(r"(-?\d+)x(-?\d+)", size)
    if match is None:
        return size

    width = int(match.group(1))
    height = int(match.group(2))
    if width <= 0 or height <= 0:
        raise ValueError("分辨率必须大于 0")

    longest_edge = max(width, height)
    for tier, lower_bound, upper_bound in RESOLUTION_TIERS:
        if lower_bound <= longest_edge <= upper_bound:
            return tier

    raise ValueError("分辨率超过 4K 上限，请降低分辨率")


def calculate_cost(mode: str, resolution: str, count: int) -> int:
    """统一计费：参考图模式与文生图模式使用相同的计费规则，不再区分模式。"""
    if count < 1:
        raise ValueError("生成数量必须大于 0")
    billing_resolution = tier_for_size(resolution)
    db = get_db()
    row = db.execute(
        """
        SELECT points_per_image, enabled
        FROM pricing_rules
        WHERE mode = 'text' AND resolution = ?
        """,
        (billing_resolution,),
    ).fetchone()
    if row is None:
        raise ValueError("未找到计费规则")
    if not row["enabled"]:
        raise ValueError(f"{billing_resolution} 当前未启用")
    return int(row["points_per_image"]) * int(count)


def require_balance(user_id: int, required_points: int) -> None:
    row = get_db().execute("SELECT points FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise ValueError("用户不存在")
    if int(row["points"]) < required_points:
        raise ValueError("积分余额不足")


def adjust_points(user_id: int, delta: int, reason: str, *, record_id: int | None = None, admin_note: str = "") -> None:
    db = get_db()
    db.execute("UPDATE users SET points = points + ? WHERE id = ?", (delta, user_id))
    db.execute(
        """
        INSERT INTO point_ledger (user_id, delta, reason, record_id, admin_note, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (user_id, delta, reason, record_id, admin_note, utc_now()),
    )
