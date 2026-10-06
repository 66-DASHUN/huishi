from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer


CANVAS_SESSION_SALT = "huishi.canvas.session"
DEFAULT_CANVAS_SESSION_TTL_SECONDS = 86400


@dataclass(slots=True)
class CanvasSessionError(Exception):
    code: str

    def __str__(self) -> str:
        return self.code


def canvas_session_ttl_seconds() -> int:
    # 默认24小时，与主站登录会话生命周期对齐
    # 真正的访问控制在主站 login_required 层，token 只是传递身份
    return int(current_app.config.get("CANVAS_SESSION_TTL_SECONDS", DEFAULT_CANVAS_SESSION_TTL_SECONDS))


def canvas_billing_identity(user_id: int) -> str:
    return f"user:{int(user_id)}"


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(str(current_app.config["SECRET_KEY"]), salt=CANVAS_SESSION_SALT)


def issue_canvas_session_token(user) -> tuple[str, int]:
    now = int(time.time())
    ttl = canvas_session_ttl_seconds()
    payload = {
        "user_id": int(user["id"]),
        "username": str(user["username"] or ""),
        "role": str(user["role"] or "user"),
        "billing_identity": canvas_billing_identity(int(user["id"])),
        "issued_at": now,
        "expires_at": now + ttl,
    }
    return _serializer().dumps(payload), int(payload["expires_at"])


def verify_canvas_session_token(token: str) -> dict[str, Any]:
    if not str(token or "").strip():
        raise CanvasSessionError("missing")
    try:
        payload = _serializer().loads(str(token), max_age=canvas_session_ttl_seconds())
    except SignatureExpired as exc:
        raise CanvasSessionError("expired") from exc
    except BadSignature as exc:
        raise CanvasSessionError("invalid") from exc

    required = {"user_id", "username", "role", "billing_identity", "issued_at", "expires_at"}
    if not required.issubset(payload):
        raise CanvasSessionError("invalid")
    if str(payload["role"]) not in {"user", "admin"}:
        raise CanvasSessionError("invalid")
    if int(payload["expires_at"]) < int(time.time()):
        raise CanvasSessionError("expired")
    return payload
