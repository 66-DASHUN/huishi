from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from flask import Response, current_app, g, has_request_context, request

from huishi.db import get_db, utc_now


SECRET_FIELDS = {
    "password",
    "password_hash",
    "api_key",
    "smtp_password",
    "canvas_agent_token",
    "storage_access_key_id",
    "storage_secret_access_key",
    "token",
    "secret",
    "proxy_url",
}

ADMIN_WRITE_AUDIT_TARGETS: dict[str, tuple[str, str, str]] = {
    "admin.config_settings": ("settings.update", "settings", "global"),
    "admin.config_billing": ("billing.rule.update", "pricing_rule", "global"),
    "admin.config_packages": ("package.create", "package", "new"),
    "admin.pricing": ("billing.rule.update", "pricing_rule", "global"),
    "admin.users": ("user.points.adjust", "user", ""),
    "admin.invites": ("invite.create", "invite", "new"),
    "admin.update_invite_default": ("invite.default.update", "invite_settings", "global"),
    "admin.update_invite": ("invite.update", "invite", ""),
    "admin.delete_invite": ("invite.delete", "invite", ""),
    "admin.bulk_update_invites": ("invite.bulk", "invite_batch", "batch"),
    "admin.import_users": ("user.import", "user_batch", "batch"),
    "admin.create_user": ("user.create", "user", "new"),
    "admin.adjust_user": ("user.points.adjust", "user", ""),
    "admin.bulk_update_users": ("user.bulk", "user_batch", "batch"),
    "admin.reset_user_password": ("user.password.reset", "user", ""),
    "admin.reset_user_login_failures": ("user.login_failures.reset", "user", ""),
    "admin.update_user_role": ("user.role.update", "user", ""),
    "admin.update_user_status": ("user.status.update", "user", ""),
    "admin.delete_user": ("user.delete", "user", ""),
    "admin.packages": ("package.create", "package", "new"),
    "admin.update_package": ("package.update", "package", ""),
    "admin.delete_package": ("package.delete", "package", ""),
    "workspace.settings": ("settings.update", "settings", "global"),
    "workspace.create_api_provider": ("provider.create", "provider", "new"),
    "workspace.update_api_provider": ("provider.update", "provider", ""),
    "workspace.delete_api_provider": ("provider.delete", "provider", ""),
    "workspace.test_api_provider": ("provider.test", "provider", ""),
}


def _is_secret_field(key: str) -> bool:
    normalized = key.strip().lower().replace("-", "_")
    return normalized in SECRET_FIELDS or normalized.endswith(("_password", "_api_key", "_token", "_secret"))


def _redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): "[redacted]" if _is_secret_field(str(key)) else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def redact_audit_values(values: Mapping[str, object] | None) -> dict[str, object]:
    return dict(_redact(dict(values or {})))


def record_admin_audit(
    actor_user_id: int | None,
    action: str,
    target_type: str = "",
    target_id: object = "",
    *,
    summary: str = "",
    before: Mapping[str, object] | None = None,
    after: Mapping[str, object] | None = None,
    result: str = "success",
    request_id: str = "",
) -> None:
    effective_request_id = request_id
    if not effective_request_id and has_request_context():
        effective_request_id = str(getattr(g, "request_id", ""))
    get_db().execute(
        """
        INSERT INTO admin_audit_logs (
            actor_user_id, action, target_type, target_id, summary,
            before_json, after_json, result, request_id, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            actor_user_id,
            str(action).strip()[:120],
            str(target_type).strip()[:80],
            str(target_id).strip()[:120],
            str(summary).strip()[:500],
            json.dumps(redact_audit_values(before), ensure_ascii=False, sort_keys=True),
            json.dumps(redact_audit_values(after), ensure_ascii=False, sort_keys=True),
            str(result).strip()[:40] or "success",
            effective_request_id[:80],
            utc_now(),
        ),
    )


def record_rejected_admin_audit(
    actor_user_id: int | None,
    action: str,
    target_type: str = "",
    target_id: object = "",
    *,
    summary: str = "",
    error_code: str = "rejected",
) -> None:
    if not _mark_request_audit_once(action, target_type, target_id, "rejected"):
        return
    record_admin_audit(
        actor_user_id,
        action,
        target_type,
        target_id,
        summary=summary,
        after={"error_code": str(error_code).strip()[:80] or "rejected"},
        result="rejected",
    )


def _mark_request_audit_once(
    action: str,
    target_type: str,
    target_id: object,
    result: str,
) -> bool:
    if not has_request_context():
        return True
    key = (str(action), str(target_type), str(target_id), str(result))
    seen = getattr(g, "_admin_request_audit_keys", None)
    if seen is None:
        seen = set()
        g._admin_request_audit_keys = seen
    if key in seen:
        return False
    seen.add(key)
    return True


def _rejected_request_target(
    endpoint: str,
    default_target_id: str,
) -> tuple[str, str]:
    action, _, _ = ADMIN_WRITE_AUDIT_TARGETS[endpoint]
    view_args = request.view_args or {}
    for key in ("user_id", "provider_id", "package_id", "code"):
        if key in view_args:
            return action, str(view_args[key])
    if endpoint == "admin.users":
        return action, request.form.get("user_id", "")[:120]
    if endpoint == "admin.bulk_update_users":
        bulk_action = request.form.get("action", "")
        if bulk_action in {"delete", "reset_login_failures"}:
            action = f"user.bulk.{bulk_action}"
    elif endpoint == "admin.bulk_update_invites":
        bulk_action = request.form.get("action", "")
        if bulk_action in {"enable", "disable", "delete"}:
            action = f"invite.bulk.{bulk_action}"
    return action, default_target_id


def audit_rejected_admin_response(response: Response) -> Response:
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return response
    if response.status_code < 400:
        return response
    endpoint = str(request.endpoint or "")
    target = ADMIN_WRITE_AUDIT_TARGETS.get(endpoint)
    if target is None or getattr(g, "user", None) is None:
        return response

    action, target_type, default_target_id = target
    action, target_id = _rejected_request_target(endpoint, default_target_id)
    db = get_db()
    try:
        db.rollback()
        actor_user_id = int(g.user["id"])
        if response.status_code < 500:
            record_rejected_admin_audit(
                actor_user_id,
                action,
                target_type,
                target_id,
                summary=f"管理请求被拒绝（HTTP {response.status_code}）",
                error_code=f"http_{response.status_code}",
            )
        elif _mark_request_audit_once(action, target_type, target_id, "failed"):
            record_admin_audit(
                actor_user_id,
                action,
                target_type,
                target_id,
                summary=f"管理请求失败（HTTP {response.status_code}）",
                after={"error_code": f"http_{response.status_code}"},
                result="failed",
            )
        db.commit()
    except Exception:
        db.rollback()
        current_app.logger.exception(
            "failed to write rejected admin audit endpoint=%s status=%s",
            endpoint,
            response.status_code,
        )
    return response
