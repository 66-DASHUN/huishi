from __future__ import annotations

"""用户自备 API Key 管理模块。

计费模式：
  Mode A（自备 Key）：用户在账户页配置了 api_key，生图时使用用户的 key +
    管理员第一优先级 provider 的 base_url / model，不扣积分。
  Mode B（积分计费）：未配置 key，走现有管理员 key 池 + 积分扣费逻辑。
"""

import logging

from huishi.db import get_db, utc_now
from huishi.secrets import decrypt_secret, encrypt_secret, is_encrypted_secret

logger = logging.getLogger(__name__)

_MASKED_VISIBLE = 4  # 前后各显示几位


def _mask_api_key(key: str) -> str:
    """返回脱敏后的 key，例如 sk-ab...xyz，两端各保留 _MASKED_VISIBLE 个字符。"""
    if not key:
        return ""
    if len(key) <= _MASKED_VISIBLE * 2:
        return "*" * len(key)
    return f"{key[:_MASKED_VISIBLE]}...{key[-_MASKED_VISIBLE:]}"


def get_user_api_key(user_id: int) -> str | None:
    """返回解密后的用户 api_key，未配置或为空时返回 None。"""
    row = get_db().execute(
        "SELECT api_key FROM user_settings WHERE user_id = ?",
        (int(user_id),),
    ).fetchone()
    if row is None:
        return None
    raw = str(row["api_key"] or "")
    if not raw:
        return None
    return decrypt_secret(raw) or None


def get_masked_user_api_key(user_id: int) -> str:
    """返回脱敏后的 api_key，用于前端展示。未配置时返回空字符串。"""
    key = get_user_api_key(user_id)
    return _mask_api_key(key) if key else ""


def save_user_api_key(user_id: int, api_key: str) -> None:
    """Upsert user_settings.api_key（Fernet 加密存储）。
    传入空字符串表示清除 api_key。
    """
    uid = int(user_id)
    raw = str(api_key or "").strip()
    encrypted = encrypt_secret(raw) if raw else ""
    get_db().execute(
        """
        INSERT INTO user_settings (user_id, base_url, api_key, updated_at)
        VALUES (?, '', ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
          api_key = excluded.api_key,
          updated_at = excluded.updated_at
        """,
        (uid, encrypted, utc_now()),
    )


def get_user_provider(user_id: int, *, model: str = "", resolution: str | None = None) -> dict | None:
    """若用户配置了有效 api_key，返回 provider-shaped dict 供直接调用生图 API。

    使用管理员配置的第一优先级 image provider 的 base_url 和 model，
    仅将 api_key 替换为用户自己的 key。若管理员未配置任何 image provider，
    降级返回 None（用户仍走 Mode B，但会因无 provider 而报错）。
    """
    # 检查管理员是否全局禁用了用户自备 Key 功能
    from huishi.providers import get_app_settings

    settings = get_app_settings("user_key_enabled")
    if settings.get("user_key_enabled", "1") != "1":
        return None

    api_key = get_user_api_key(user_id)
    if not api_key:
        return None

    # 取管理员第一优先级 provider 作为 base（不传 resolution 以获取全量候选）
    from huishi.providers import image_provider_candidates  # 延迟导入避免循环

    candidates = image_provider_candidates(resolution, model)
    requested_model = str(model or "").strip()
    if not candidates:
        from huishi.image_api import ConfigurationError  # noqa: PLC0415
        raise ConfigurationError(
            "您配置了 API Key，但管理员尚未设置生图提供商，无法完成生图。"
            "请联系管理员添加生图配置，或清除您的 API Key 以使用平台积分生图。"
        )

    base = candidates[0]
    return {
        "base_url": str(base.get("base_url") or ""),
        "api_key": api_key,
        "model": requested_model if requested_model and requested_model != "*" else str(base.get("model") or "gpt-image-2"),
        "api_format": str(base.get("api_format") or "openai"),
        "proxy_url": str(base.get("proxy_url") or ""),
    }
