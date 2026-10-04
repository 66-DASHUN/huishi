from __future__ import annotations

import secrets
import string

from huishi.billing import adjust_points
from huishi.db import get_db, utc_now


INVITE_ALPHABET = string.ascii_uppercase + string.digits
INVITE_CODE_LENGTH = 8
INVITE_DEFAULT_REWARD_KEY = "invite_default_reward_points"


def normalize_invite_code(code: str) -> str:
    return "".join(str(code or "").strip().upper().split())


def generate_invite_code() -> str:
    db = get_db()
    while True:
        code = "".join(secrets.choice(INVITE_ALPHABET) for _ in range(INVITE_CODE_LENGTH))
        existing = db.execute("SELECT id FROM invite_codes WHERE code = ?", (code,)).fetchone()
        if existing is None:
            return code


def invite_default_reward_points() -> int:
    row = get_db().execute(
        "SELECT value FROM app_settings WHERE key = ?",
        (INVITE_DEFAULT_REWARD_KEY,),
    ).fetchone()
    if row is None:
        return 0
    try:
        return max(int(row["value"]), 0)
    except (TypeError, ValueError):
        return 0


def set_invite_default_reward_points(points: int) -> None:
    db = get_db()
    db.execute(
        """
        INSERT INTO app_settings (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """,
        (INVITE_DEFAULT_REWARD_KEY, str(points), utc_now()),
    )


def create_invite_code(
    *,
    owner_user_id: int,
    reward_points: int | None = None,
    max_uses: int | None = None,
    enabled: bool = True,
    code: str | None = None,
    created_by_admin_id: int | None = None,
) -> str:
    invite_code = normalize_invite_code(code or generate_invite_code())
    if not invite_code:
        invite_code = generate_invite_code()
    points = invite_default_reward_points() if reward_points is None else reward_points
    now = utc_now()
    get_db().execute(
        """
        INSERT INTO invite_codes
        (code, owner_user_id, reward_points, max_uses, used_count, enabled, created_by_admin_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?)
        """,
        (invite_code, owner_user_id, points, max_uses, 1 if enabled else 0, created_by_admin_id, now, now),
    )
    return invite_code


def validate_invite_code(code: str):
    normalized = normalize_invite_code(code)
    if not normalized:
        return None, ""
    row = get_db().execute("SELECT * FROM invite_codes WHERE code = ?", (normalized,)).fetchone()
    if row is None or not row["enabled"]:
        return None, "邀请码不可用"
    max_uses = row["max_uses"]
    if max_uses is not None and int(row["used_count"]) >= int(max_uses):
        return None, "邀请码已达到使用次数上限"
    return row, ""


def redeem_invite(invite_code_id: int, invitee_user_id: int) -> None:
    db = get_db()
    invite = db.execute("SELECT * FROM invite_codes WHERE id = ?", (invite_code_id,)).fetchone()
    if invite is None or not invite["enabled"]:
        raise ValueError("邀请码不可用")
    max_uses = invite["max_uses"]
    if max_uses is not None and int(invite["used_count"]) >= int(max_uses):
        raise ValueError("邀请码已达到使用次数上限")

    reward_points = int(invite["reward_points"])
    inviter_user_id = int(invite["owner_user_id"])
    db.execute(
        "UPDATE invite_codes SET used_count = used_count + 1, updated_at = ? WHERE id = ?",
        (utc_now(), invite_code_id),
    )
    db.execute(
        """
        INSERT INTO invite_redemptions
        (invite_code_id, inviter_user_id, invitee_user_id, reward_points, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (invite_code_id, inviter_user_id, invitee_user_id, reward_points, utc_now()),
    )
    if reward_points > 0:
        note = f"邀请码 {invite['code']}"
        adjust_points(invitee_user_id, reward_points, "invite_signup_bonus", admin_note=note)
        adjust_points(inviter_user_id, reward_points, "invite_reward", admin_note=note)
