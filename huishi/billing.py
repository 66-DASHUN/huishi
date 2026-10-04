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


def normalize_billing_model(model: object = None) -> str:
    value = str(model or "").strip()
    return value


def calculate_cost(
    mode: str,
    resolution: str,
    count: int,
    *,
    model: str = "",
    media_type: str | None = None,
    duration_seconds: int = 0,
) -> int:
    """Return the exact media/model price from the active pricing contract."""
    if count < 1:
        raise ValueError("生成数量必须大于 0")
    billing_resolution = tier_for_size(resolution)
    normalized_media_type = str(media_type or ("video" if mode == "video" else "image")).strip().lower() or "image"
    if normalized_media_type == "video":
        pricing_mode = "video"
    elif normalized_media_type in {"speech", "music"}:
        pricing_mode = normalized_media_type
    else:
        pricing_mode = "text"
    billing_model = normalize_billing_model(model)
    if not billing_model:
        raise ValueError("必须选择模型后才能计费")
    duration_tier = f"{int(duration_seconds)}s" if int(duration_seconds or 0) > 0 else str(resolution or "").strip()
    db = get_db()
    if normalized_media_type == 'video':
        rules = db.execute(
            'SELECT * FROM video_pricing_rules WHERE model=? AND resolution=? AND enabled=1',
            (billing_model, billing_resolution),
        ).fetchall()
        per_second = [rule for rule in rules if rule['billing_unit'] == 'per_second']
        per_request = [rule for rule in rules if rule['billing_unit'] == 'per_request']
        if len(per_second) > 1 or (per_second and per_request):
            raise ValueError('视频定价规则冲突，请联系管理员')
        if per_second:
            rule = per_second[0]
            return int(rule['points']) * int(duration_seconds) * int(count)
        matching = [
            rule for rule in per_request
            if int(rule['duration_seconds'] or 0) == 0
            or int(duration_seconds or 0) <= int(rule['duration_seconds'])
        ]
        if matching:
            # A positive duration is an upper bound; choose the tightest
            # matching tier. The zero-duration rule is the unlimited fallback.
            rule = min(
                matching,
                key=lambda item: (
                    int(item['duration_seconds'] or 0) == 0,
                    int(item['duration_seconds'] or 0) or 2**31,
                ),
            )
            return int(rule['points']) * int(count)
        from huishi.media_capabilities import SEEDANCE_DURATIONS
        from huishi.model_lifecycle import managed_model
        if managed_model(normalized_media_type, billing_model) or billing_model == 'MiniMax-H3' or billing_model in SEEDANCE_DURATIONS:
            raise ValueError('此模型尚未设置明确的视频定价')
    row = db.execute(
        """
        SELECT points_per_image, enabled
        FROM pricing_rules
        WHERE media_type = ?
          AND mode = ?
          AND resolution = ?
          AND model = ?
          AND (media_type <> 'video' OR duration_tier = '' OR duration_tier = ?)
        ORDER BY id ASC
        LIMIT 1
        """,
        (normalized_media_type, pricing_mode, billing_resolution, billing_model, duration_tier),
    ).fetchone()
    if row is None and normalized_media_type == "video":
        row = db.execute(
            """
            SELECT points_per_image, enabled
            FROM pricing_rules
            WHERE media_type = 'video'
              AND mode = ?
              AND (duration_tier = ? OR resolution = ?)
              AND model = ?
            ORDER BY id ASC
            LIMIT 1
            """,
            (pricing_mode, duration_tier, duration_tier, billing_model),
        ).fetchone()
    if row is None:
        raise ValueError("未找到计费规则")
    if not row["enabled"]:
        raise ValueError(f"{billing_resolution} 当前未启用")
    points_per_image = int(row["points_per_image"])
    if points_per_image < 1:
        raise ValueError("计费规则每张积分必须至少为 1")
    return points_per_image * int(count)


def require_balance(user_id: int, required_points: int) -> None:
    row = get_db().execute("SELECT points FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise ValueError("用户不存在")
    if int(row["points"]) < required_points:
        raise ValueError("积分余额不足")


def reserved_generation_points(user_id: int) -> int:
    row = get_db().execute(
        """
        SELECT COALESCE(SUM(cost), 0) AS reserved
        FROM generation_tasks
        WHERE user_id = ? AND status IN ('queued', 'running')
        """,
        (user_id,),
    ).fetchone()
    return int(row["reserved"]) if row is not None else 0


def available_generation_points(user_id: int) -> int:
    row = get_db().execute("SELECT points FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise ValueError("用户不存在")
    return int(row["points"]) - reserved_generation_points(user_id)


def require_available_generation_points(user_id: int, required_points: int) -> None:
    if available_generation_points(user_id) < required_points:
        reserved = reserved_generation_points(user_id)
        raise ValueError(f"积分余额不足，已有生成任务占用 {reserved} 点")


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


def deduct_points_if_sufficient(
    user_id: int,
    required_points: int,
    *,
    reason: str,
    record_id: int | None = None,
    admin_note: str = "",
) -> None:
    if required_points <= 0:
        raise ValueError("扣费点数必须大于 0")
    db = get_db()
    cursor = db.execute(
        """
        UPDATE users
        SET points = points - ?
        WHERE id = ? AND points >= ?
        """,
        (required_points, user_id, required_points),
    )
    if cursor.rowcount != 1:
        raise ValueError("积分余额不足")
    db.execute(
        """
        INSERT INTO point_ledger (user_id, delta, reason, record_id, admin_note, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (user_id, -required_points, reason, record_id, admin_note, utc_now()),
    )
