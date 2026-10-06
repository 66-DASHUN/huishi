from __future__ import annotations

import csv
from dataclasses import asdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from io import StringIO
import json
import re
from urllib.parse import urlencode

from flask import Blueprint, Response, abort, current_app, flash, g, redirect, render_template, request, url_for
from werkzeug.security import generate_password_hash

from huishi.admin_permissions import ALL_ROLES, has_permission
from huishi.admin_activity import EVENT_LABELS, STATUS_LABELS, query_activity_page
from huishi.admin_audit import (
    audit_rejected_admin_response,
    record_admin_audit,
    record_rejected_admin_audit,
)
from huishi.auth import admin_required, is_valid_email, permission_required, reset_login_failure_state_for_user
from huishi.billing import adjust_points
from huishi.db import (
    get_db,
    immediate_transaction,
    is_integrity_error,
    lock_enabled_admins_for_update,
    sql_placeholders,
    transaction,
    utc_now,
)
from huishi.invites import (
    create_invite_code,
    invite_default_reward_points,
    normalize_invite_code,
    set_invite_default_reward_points,
)
from huishi.pagination import PageQuery, Pagination
from huishi.operations import collect_operations_health
from huishi.providers import save_app_setting
from huishi.routes_workspace import build_settings_page_context, handle_settings_submission
from huishi.upload_storage import get_upload_storage

bp = Blueprint("admin", __name__, url_prefix="/admin")


AUDIT_ACTION_LABELS = {
    "provider.create": "创建服务商",
    "provider.update": "更新服务商",
    "provider.delete": "删除服务商",
    "provider.test": "测试服务商",
    "billing.rule.update": "更新计费规则",
    "package.create": "创建套餐",
    "package.update": "更新套餐",
    "package.delete": "删除套餐",
    "user.points.adjust": "调整用户积分",
    "user.create": "新增用户",
    "user.role.update": "修改用户角色",
    "user.status.update": "更新用户状态",
    "user.delete": "删除用户",
    "invite.create": "创建邀请码",
    "invite.update": "更新邀请码",
    "invite.delete": "删除邀请码",
    "settings.update": "更新系统配置",
    "storage.test": "测试对象存储",
    "storage.sync": "同步对象存储",
    "storage.compare": "比较存储库存",
    "storage.restore": "恢复本地缓存",
}


@bp.after_request
def audit_rejected_admin_write(response: Response) -> Response:
    return audit_rejected_admin_response(response)


def require_permission(permission: str) -> None:
    if g.user is None or not has_permission(str(g.user["role"]), permission):
        abort(403)


def config_nav_sections() -> list[dict[str, str]]:
    return [
        {"key": "settings", "label": "系统配置", "href": "/admin/config/settings"},
        {"key": "billing", "label": "计费规则", "href": "/admin/config/billing"},
        {"key": "packages", "label": "套餐说明", "href": "/admin/config/packages"},
    ]


def parse_int_field(name: str, *, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        value = int(request.form.get(name, ""))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} 必须是整数") from exc
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} 不能小于 {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} 不能大于 {maximum}")
    return value


def parse_price_cents(raw_price: str | None) -> int:
    try:
        price = Decimal(raw_price or "")
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("price 必须是有效金额") from exc
    if price < 0:
        raise ValueError("price 不能为负数")
    return int((price * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def parse_package_amounts() -> tuple[int, int]:
    price_cents = parse_price_cents(request.form.get("price"))
    points = parse_int_field("points", minimum=1)
    if price_cents != points:
        raise ValueError("套餐必须按 1 积分 = 1 分设置，价格（分）必须等于积分")
    return price_cents, points


def parse_optional_positive_int(name: str, *, minimum: int = 0) -> int | None:
    raw_value = request.form.get(name, "").strip()
    if raw_value == "":
        return None
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} 必须是整数") from exc
    if value < minimum:
        raise ValueError(f"{name} 不能小于 {minimum}")
    return value


@bp.get("/")
@permission_required("operations.view")
def index():
    db = get_db()
    stats = {
        "user_count": db.execute("SELECT COUNT(*) AS value FROM users").fetchone()["value"],
        "total_points": db.execute("SELECT COALESCE(SUM(points), 0) AS value FROM users").fetchone()["value"],
        "record_count": db.execute("SELECT COUNT(*) AS value FROM records").fetchone()["value"],
        "points_charged": db.execute("SELECT COALESCE(SUM(points_charged), 0) AS value FROM records").fetchone()["value"],
    }
    recent_activity = query_activity_page(db=db, page=1, per_page=10).rows[:8]
    return render_template(
        "admin/dashboard.html",
        stats=stats,
        recent_activity=recent_activity,
        operations_health=collect_operations_health(),
    )


@bp.get("/config")
@permission_required("providers.view")
def config_center():
    return redirect(url_for("admin.config_settings"))


@bp.route("/config/settings", methods=("GET", "POST"))
@permission_required("providers.view")
def config_settings():
    if request.method == "POST":
        require_permission("providers.update")
        return handle_settings_submission(redirect_endpoint="admin.config_settings")
    return render_template(
        "admin/config_settings.html",
        config_nav_sections=config_nav_sections(),
        config_nav_active="settings",
        **build_settings_page_context(),
    )


@bp.post("/config/settings/diagnostics")
@permission_required("providers.view")
def config_settings_diagnostics():
    context = build_settings_page_context()
    diagnostics = context.get("canvas_diagnostics", {})
    image_status = context.get("image_config_status", {})
    video_status = context.get("video_config_status", {})
    prompt_status = context.get("prompt_config_status", {})
    messages: list[str] = []

    if diagnostics.get("canvas_app_url"):
        messages.append("画布应用地址已配置")
    else:
        messages.append("画布应用地址未配置")

    if image_status.get("is_ready"):
        messages.append(f"画布生图 Provider 可用：{image_status.get('effective_provider_name') or image_status.get('effective_base_url')}")
    else:
        messages.append(f"画布生图 Provider 不可用：{image_status.get('missing_reason') or '未启用 Provider'}")

    if video_status.get("is_ready"):
        messages.append(f"视频 Provider 可用：{video_status.get('effective_provider_name') or video_status.get('effective_base_url')}")
    else:
        messages.append(f"视频 Provider 不可用：{video_status.get('missing_reason') or '未启用 Provider'}")

    if prompt_status.get("is_ready"):
        messages.append(f"在线助手文本 Provider 可用：{prompt_status.get('effective_provider_name') or prompt_status.get('effective_base_url')}")
    else:
        messages.append(f"在线助手文本 Provider 不可用：{prompt_status.get('missing_reason') or '未启用 Prompt Provider'}")

    if diagnostics.get("canvas_agent_url"):
        messages.append("本地 Agent/MCP 地址已配置")
    elif diagnostics.get("canvas_local_start_cmd"):
        messages.append("已配置本地 Agent 启动参数")
    else:
        messages.append("本地 Agent/MCP 未配置，不影响在线助手")

    for message in messages:
        flash(message)
    return redirect(url_for("admin.config_settings"))


@bp.post("/config/settings/storage/test")
@permission_required("providers.update")
def config_storage_test():
    try:
        get_upload_storage().healthcheck()
    except Exception as exc:
        message = f"failed:{utc_now()}:{exc}"
        save_app_setting("storage_last_health", message[:500])
        record_admin_audit(
            int(g.user["id"]),
            "storage.test",
            "storage",
            "global",
            summary="存储连接检测失败",
            result="failed",
        )
        get_db().commit()
        flash("存储连接失败，请检查配置")
    else:
        save_app_setting("storage_last_health", f"ok:{utc_now()}")
        record_admin_audit(
            int(g.user["id"]),
            "storage.test",
            "storage",
            "global",
            summary="存储连接检测成功",
        )
        get_db().commit()
        flash("存储连接正常")
    return redirect(url_for("admin.config_settings"))


def _record_storage_operation(action: str, result, summary: str) -> None:
    payload = json.dumps(asdict(result), ensure_ascii=False, sort_keys=True)
    save_app_setting("storage_last_sync", f"{action}:{utc_now()}:{payload}"[:1000])
    record_admin_audit(
        int(g.user["id"]),
        f"storage.{action}",
        "storage",
        "global",
        summary=summary,
        after=asdict(result),
    )
    get_db().commit()


@bp.post("/config/settings/storage/sync")
@permission_required("providers.update")
def config_storage_sync():
    from tools.upload_storage_cli import sync_to_remote

    storage = get_upload_storage()
    if storage.remote is None:
        flash("当前是本地存储，无需同步")
        return redirect(url_for("admin.config_settings"))
    result = sync_to_remote(storage.local_dir, storage.remote, prefix=storage.prefix)
    _record_storage_operation("sync", result, "同步本地图片到远端存储")
    flash(f"存储同步完成：新增 {result.copied}，跳过 {result.skipped}，冲突 {len(result.conflicts)}")
    return redirect(url_for("admin.config_settings"))


@bp.post("/config/settings/storage/compare")
@permission_required("providers.update")
def config_storage_compare():
    from tools.upload_storage_cli import compare_storage

    result = compare_storage(get_upload_storage())
    _record_storage_operation("compare", result, "比较本地与远端存储库存")
    flash(
        f"库存比较完成：仅本地 {len(result.local_only)}，仅远端 {len(result.remote_only)}，冲突 {len(result.conflicts)}"
    )
    return redirect(url_for("admin.config_settings"))


@bp.post("/config/settings/storage/restore")
@permission_required("providers.update")
def config_storage_restore():
    from tools.upload_storage_cli import restore_missing

    result = restore_missing(get_upload_storage())
    _record_storage_operation("restore", result, "从远端恢复缺失的本地图片")
    flash(f"本地缓存恢复完成：恢复 {result.copied}，跳过 {result.skipped}")
    return redirect(url_for("admin.config_settings"))


@bp.route("/config/billing", methods=("GET", "POST"))
@permission_required("billing.view")
def config_billing():
    db = get_db()
    if request.method == "POST":
        require_permission("billing.update")
        if request.form.get('action') == 'video_price':
            try:
                model=request.form.get('model','').strip()
                resolution=request.form.get('resolution','').strip()
                unit=request.form.get('billing_unit','per_request')
                seconds=int(request.form.get('duration_seconds') or 0)
                points=parse_int_field('points',minimum=1)
                if not model or model == '*' or not resolution or unit not in ('per_second','per_request') or seconds<0:
                    raise ValueError('视频定价参数无效')
                from huishi.media_capabilities import video_capabilities, SEEDANCE_DURATIONS, GROK_VIDEO_MODELS
                protocol='dmc_h3' if model=='MiniMax-H3' else 'seedance_media' if model in SEEDANCE_DURATIONS else 'grok' if model in GROK_VIDEO_MODELS else ''
                caps=video_capabilities(protocol,model)
                if caps and resolution not in caps['resolutions']:
                    raise ValueError('此模型不支持该分辨率')
                if unit=='per_request' and (seconds > 0 and caps and seconds not in caps['durations']):
                    raise ValueError('此模型不支持该时长档位')
                if unit=='per_second':
                    seconds=0
                conflict=db.execute('SELECT id FROM video_pricing_rules WHERE model=? AND resolution=? AND billing_unit<>? AND enabled=1', (model,resolution,unit)).fetchone()
                if conflict and request.form.get('enabled')=='on':
                    raise ValueError('请先停用此模型冲突的计费方式')
                db.execute('INSERT INTO video_pricing_rules(model,resolution,billing_unit,duration_seconds,points,enabled) VALUES (?,?,?,?,?,?) ON CONFLICT(model,resolution,billing_unit,duration_seconds) DO UPDATE SET points=excluded.points,enabled=excluded.enabled',
                           (model,resolution,unit,seconds,points,int(request.form.get('enabled')=='on')))
                record_admin_audit(int(g.user['id']),'billing.rule.update','video_pricing_rule',model,summary='更新视频模型定价',after={'model':model,'resolution':resolution,'duration':seconds,'unit':unit,'points':points})
                db.commit()
            except ValueError as exc:
                db.rollback()
                return str(exc),400
            return redirect(url_for('admin.config_billing'))
        if request.form.get("action") == "create":
            media_type = request.form.get("media_type", "video").strip().lower() or "video"
            if media_type not in {"image", "video", "speech", "music"}:
                return "媒体类型无效", 400
            mode = media_type if media_type in {"video", "speech", "music"} else "text"
            model = request.form.get("model", "*").strip() or "*"
            resolution = request.form.get("resolution", "").strip()
            duration_tier = request.form.get("duration_tier", "").strip()
            try:
                points_per_image = parse_int_field("points_per_image", minimum=1)
            except ValueError as exc:
                return str(exc), 400
            if model == "*":
                return "必须指定具体模型，不能创建通配计费规则", 400
            if not resolution:
                return "清晰度或时长不能为空", 400
            try:
                db.execute(
                    "INSERT INTO pricing_rules (mode, model, resolution, points_per_image, enabled, media_type, duration_tier) VALUES (?, ?, ?, ?, 1, ?, ?)",
                    (mode, model, resolution, points_per_image, media_type, duration_tier),
                )
                db.commit()
            except Exception:
                db.rollback()
                return "该计费规则已存在或参数无效", 400
            record_admin_audit(
                int(g.user["id"]),
                "billing.rule.create",
                "pricing_rule",
                "new",
                summary=f"新增 {media_type} / {model} / {resolution} 计费规则",
                after={"media_type": media_type, "model": model, "resolution": resolution, "duration_tier": duration_tier, "points_per_image": points_per_image},
            )
            db.commit()
            return redirect(url_for("admin.config_billing"))
        try:
            points_per_image = parse_int_field("points_per_image", minimum=1)
        except ValueError as exc:
            return str(exc), 400
        mode = request.form.get("mode", "")
        model = request.form.get("model", "*").strip() or "*"
        resolution = request.form.get("resolution", "")
        media_type = request.form.get("media_type", "image").strip().lower() or "image"
        duration_tier = request.form.get("duration_tier", "").strip()
        if model == "*":
            return "不再支持通配计费规则，请为具体模型配置价格", 400
        rule = db.execute(
            "SELECT * FROM pricing_rules WHERE media_type = ? AND mode = ? AND model = ? AND resolution = ?",
            (media_type, mode, model, resolution),
        ).fetchone()
        if rule is None:
            return "计费规则不存在", 400
        enabled = 1 if request.form.get("enabled") == "on" else 0
        db.execute(
            """
            UPDATE pricing_rules
            SET points_per_image = ?, enabled = ?
            WHERE media_type = ? AND mode = ? AND model = ? AND resolution = ?
            """,
            (
                points_per_image,
                enabled,
                media_type,
                mode,
                model,
                resolution,
            ),
        )
        record_admin_audit(
            int(g.user["id"]),
            "billing.rule.update",
            "pricing_rule",
            rule["id"],
            summary=f"更新 {mode} / {model} / {resolution} 计费规则",
            before={"model": str(rule["model"] or "*"), "points_per_image": int(rule["points_per_image"]), "enabled": bool(rule["enabled"])},
            after={"model": model, "points_per_image": points_per_image, "enabled": bool(enabled)},
        )
        db.commit()
        return redirect(url_for("admin.config_billing"))
    rules = db.execute("SELECT * FROM pricing_rules ORDER BY media_type, mode, CASE WHEN model = '*' THEN 0 ELSE 1 END, model, resolution").fetchall()
    return render_template(
        "admin/config_billing.html",
        rules=rules,
        video_rules=db.execute('SELECT * FROM video_pricing_rules ORDER BY model,resolution,duration_seconds').fetchall(),
        config_nav_sections=config_nav_sections(),
        config_nav_active="billing",
    )


@bp.route("/config/packages", methods=("GET", "POST"))
@permission_required("packages.view")
def config_packages():
    db = get_db()
    if request.method == "POST":
        require_permission("packages.update")
        name = request.form.get("name", "").strip()
        if not name:
            return "套餐名称不能为空", 400
        try:
            price_cents, points = parse_package_amounts()
        except ValueError as exc:
            return str(exc), 400
        enabled = 1 if request.form.get("enabled") == "on" else 0
        cursor = db.execute(
            """
            INSERT INTO packages (name, price_cents, points, description, enabled)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                name,
                price_cents,
                points,
                request.form.get("description", ""),
                enabled,
            ),
        )
        package_id = int(cursor.lastrowid)
        record_admin_audit(
            int(g.user["id"]),
            "package.create",
            "package",
            package_id,
            summary=f"创建套餐 {name}",
            after={
                "name": name,
                "price_cents": price_cents,
                "points": points,
                "description": request.form.get("description", ""),
                "enabled": bool(enabled),
            },
        )
        db.commit()
        return redirect(url_for("admin.config_packages"))
    packages = db.execute("SELECT * FROM packages ORDER BY id DESC").fetchall()
    return render_template(
        "admin/config_packages.html",
        packages=packages,
        config_nav_sections=config_nav_sections(),
        config_nav_active="packages",
    )


@bp.route("/pricing", methods=("GET", "POST"))
@permission_required("billing.view")
def pricing():
    return redirect(url_for("admin.config_billing"))


@bp.route("/users", methods=("GET", "POST"))
@permission_required("users.view")
def users():
    db = get_db()
    if request.method == "POST":
        require_permission("users.points.adjust")
        try:
            user_id = parse_int_field("user_id", minimum=1)
            delta = parse_int_field("delta", minimum=-100000, maximum=100000)
        except ValueError as exc:
            return str(exc), 400
        user = db.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
        if user is None:
            return "用户不存在", 400
        return adjust_user_points(user_id, delta, request.form.get("admin_note", ""), redirect_to="admin.users")
    page_query = PageQuery.from_values(request.args.get("page"), request.args.get("per_page"))
    search = request.args.get("q", "").strip()
    role_filter = request.args.get("role", "").strip()
    where = []
    params: list[object] = []
    if search:
        pattern = f"%{search.lower()}%"
        where.append("(LOWER(users.email) LIKE ? OR LOWER(users.username) LIKE ?)")
        params.extend((pattern, pattern))
    if role_filter in ALL_ROLES:
        where.append("users.role = ?")
        params.append(role_filter)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    total = int(
        db.execute(
            f"SELECT COUNT(*) AS value FROM users {where_sql}",
            tuple(params),
        ).fetchone()["value"]
    )
    users = db.execute(
        f"""
        SELECT users.*, recent_usage.last_used_at
        FROM users
        LEFT JOIN (
          SELECT user_id, MAX(used_at) AS last_used_at
          FROM (
            SELECT user_id, created_at AS used_at
            FROM records
            UNION ALL
            SELECT user_id, COALESCE(NULLIF(updated_at, ''), created_at) AS used_at
            FROM generation_tasks
          )
          GROUP BY user_id
        ) AS recent_usage ON recent_usage.user_id = users.id
        {where_sql}
        ORDER BY users.id DESC
        LIMIT ? OFFSET ?
        """
        ,
        (*params, page_query.per_page, page_query.offset),
    ).fetchall()
    return render_template(
        "admin/users.html",
        users=users,
        pagination=Pagination.from_query(page_query, total),
        search=search,
        role_filter=role_filter,
        management_roles=ALL_ROLES,
        pagination_query=urlencode(
            {"q": search, "role": role_filter, "per_page": page_query.per_page}
        ),
    )


@bp.get("/audit")
@permission_required("audit.view")
def audit_logs():
    db = get_db()
    page_query = PageQuery.from_values(request.args.get("page"), request.args.get("per_page"), default_per_page=30)
    search = request.args.get("q", "").strip()
    action_filter = request.args.get("action", "").strip()
    result_filter = request.args.get("result", "").strip()
    actor_filter = request.args.get("actor", "").strip()
    from_filter = request.args.get("from", "").strip()
    to_filter = request.args.get("to", "").strip()
    where: list[str] = []
    params: list[object] = []
    if search:
        pattern = f"%{search.lower()}%"
        where.append(
            "(LOWER(admin_audit_logs.action) LIKE ? OR LOWER(admin_audit_logs.summary) LIKE ? "
            "OR LOWER(admin_audit_logs.target_type) LIKE ? OR LOWER(admin_audit_logs.target_id) LIKE ?)"
        )
        params.extend((pattern, pattern, pattern, pattern))
    if action_filter:
        where.append("admin_audit_logs.action = ?")
        params.append(action_filter)
    if result_filter in {"success", "rejected", "failed"}:
        where.append("admin_audit_logs.result = ?")
        params.append(result_filter)
    if actor_filter:
        where.append("LOWER(COALESCE(users.username, '')) LIKE ?")
        params.append(f"%{actor_filter.lower()}%")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", from_filter):
        where.append("admin_audit_logs.created_at >= ?")
        params.append(f"{from_filter}T00:00:00+00:00")
    else:
        from_filter = ""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", to_filter):
        where.append("admin_audit_logs.created_at <= ?")
        params.append(f"{to_filter}T23:59:59.999999+00:00")
    else:
        to_filter = ""
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    total = int(
        db.execute(
            f"""
            SELECT COUNT(*) AS value
            FROM admin_audit_logs
            LEFT JOIN users ON users.id = admin_audit_logs.actor_user_id
            {where_sql}
            """,
            tuple(params),
        ).fetchone()["value"]
    )
    rows = db.execute(
        f"""
        SELECT admin_audit_logs.*, users.username AS actor_username
        FROM admin_audit_logs
        LEFT JOIN users ON users.id = admin_audit_logs.actor_user_id
        {where_sql}
        ORDER BY admin_audit_logs.id DESC
        LIMIT ? OFFSET ?
        """,
        (*params, page_query.per_page, page_query.offset),
    ).fetchall()
    actions = db.execute(
        "SELECT DISTINCT action FROM admin_audit_logs ORDER BY action"
    ).fetchall()
    return render_template(
        "admin/audit.html",
        audit_rows=rows,
        actions=[row["action"] for row in actions],
        action_labels=AUDIT_ACTION_LABELS,
        pagination=Pagination.from_query(page_query, total),
        search=search,
        action_filter=action_filter,
        result_filter=result_filter,
        actor_filter=actor_filter,
        from_filter=from_filter,
        to_filter=to_filter,
        role_filter="",
        pagination_query=urlencode(
            {
                "q": search,
                "action": action_filter,
                "result": result_filter,
                "actor": actor_filter,
                "from": from_filter,
                "to": to_filter,
                "per_page": page_query.per_page,
            }
        ),
    )


@bp.route("/invites", methods=("GET", "POST"))
@permission_required("invites.view")
def invites():
    db = get_db()
    if request.method == "POST":
        require_permission("invites.update")
        code = normalize_invite_code(request.form.get("code", ""))
        try:
            owner_user_id = parse_int_field("owner_user_id", minimum=1)
            reward_points = parse_int_field("reward_points", minimum=0)
            max_uses = parse_optional_positive_int("max_uses", minimum=1)
        except ValueError as exc:
            return str(exc), 400
        owner = db.execute("SELECT id FROM users WHERE id = ?", (owner_user_id,)).fetchone()
        if owner is None:
            return "用户不存在", 400
        try:
            created_code = create_invite_code(
                owner_user_id=owner_user_id,
                reward_points=reward_points,
                max_uses=max_uses,
                enabled=request.form.get("enabled") == "on",
                code=code or None,
                created_by_admin_id=g.user["id"],
            )
            record_admin_audit(
                int(g.user["id"]),
                "invite.create",
                "invite",
                created_code,
                summary=f"创建邀请码 {created_code}",
                after={
                    "owner_user_id": owner_user_id,
                    "reward_points": reward_points,
                    "max_uses": max_uses,
                    "enabled": request.form.get("enabled") == "on",
                },
            )
            db.commit()
        except Exception as exc:
            db.rollback()
            return str(exc), 400
        return redirect(url_for("admin.invites"))
    page_query = PageQuery.from_values(request.args.get("page"), request.args.get("per_page"))
    total = int(db.execute("SELECT COUNT(*) AS value FROM invite_codes").fetchone()["value"])
    invite_rows = db.execute(
        """
        SELECT invite_codes.*, users.username AS owner_username
        FROM invite_codes
        JOIN users ON users.id = invite_codes.owner_user_id
        ORDER BY invite_codes.id DESC
        LIMIT ? OFFSET ?
        """,
        (page_query.per_page, page_query.offset),
    ).fetchall()
    users = db.execute("SELECT id, username, email FROM users ORDER BY id DESC").fetchall()
    return render_template(
        "admin/invites.html",
        invites=invite_rows,
        users=users,
        invite_default_reward_points=invite_default_reward_points(),
        pagination=Pagination.from_query(page_query, total),
        pagination_query=urlencode({"per_page": page_query.per_page}),
    )


@bp.post("/invites/default")
@permission_required("invites.update")
def update_invite_default():
    before_points = invite_default_reward_points()
    try:
        points = parse_int_field("invite_default_reward_points", minimum=0)
    except ValueError as exc:
        return str(exc), 400
    set_invite_default_reward_points(points)
    record_admin_audit(
        int(g.user["id"]),
        "invite.default.update",
        "invite_setting",
        "default_reward_points",
        summary="更新邀请码默认奖励",
        before={"reward_points": before_points},
        after={"reward_points": points},
    )
    get_db().commit()
    return redirect(url_for("admin.invites"))


@bp.post("/invites/<code>")
@permission_required("invites.update")
def update_invite(code: str):
    db = get_db()
    normalized = normalize_invite_code(code)
    invite = db.execute("SELECT * FROM invite_codes WHERE code = ?", (normalized,)).fetchone()
    if invite is None:
        return "邀请码不存在", 404
    try:
        reward_points = parse_int_field("reward_points", minimum=0)
        max_uses = parse_optional_positive_int("max_uses", minimum=1)
    except ValueError as exc:
        return str(exc), 400
    if max_uses is not None and max_uses < int(invite["used_count"]):
        return "max_uses 不能小于当前已使用次数", 400
    db.execute(
        """
        UPDATE invite_codes
        SET reward_points = ?, max_uses = ?, enabled = ?, updated_at = ?
        WHERE code = ?
        """,
        (reward_points, max_uses, 1 if request.form.get("enabled") == "on" else 0, utc_now(), normalized),
    )
    record_admin_audit(
        int(g.user["id"]),
        "invite.update",
        "invite",
        normalized,
        summary=f"更新邀请码 {normalized}",
        before={
            "reward_points": int(invite["reward_points"]),
            "max_uses": invite["max_uses"],
            "enabled": bool(invite["enabled"]),
        },
        after={
            "reward_points": reward_points,
            "max_uses": max_uses,
            "enabled": request.form.get("enabled") == "on",
        },
    )
    db.commit()
    return redirect(url_for("admin.invites"))


@bp.post("/invites/<code>/delete")
@permission_required("invites.update")
def delete_invite(code: str):
    db = get_db()
    normalized = normalize_invite_code(code)
    invite = db.execute("SELECT * FROM invite_codes WHERE code = ?", (normalized,)).fetchone()
    if invite is None:
        return "邀请码不存在", 404
    db.execute("DELETE FROM invite_codes WHERE id = ?", (invite["id"],))
    record_admin_audit(
        int(g.user["id"]),
        "invite.delete",
        "invite",
        normalized,
        summary=f"删除邀请码 {normalized}",
        before={
            "owner_user_id": int(invite["owner_user_id"]),
            "reward_points": int(invite["reward_points"]),
            "max_uses": invite["max_uses"],
            "used_count": int(invite["used_count"]),
            "enabled": bool(invite["enabled"]),
        },
    )
    db.commit()
    return redirect(url_for("admin.invites"))


@bp.post("/invites/bulk")
@permission_required("invites.update")
def bulk_update_invites():
    db = get_db()
    action = request.form.get("action", "")
    invite_ids = []
    for raw_id in request.form.getlist("invite_ids[]") or request.form.getlist("invite_ids"):
        try:
            invite_ids.append(int(raw_id))
        except (TypeError, ValueError):
            continue
    if not invite_ids:
        return "请选择邀请码", 400
    if action not in {"enable", "disable", "delete"}:
        return "批量操作无效", 400
    placeholders, invite_params = sql_placeholders(invite_ids)
    existing_invites = db.execute(
        f"SELECT * FROM invite_codes WHERE id IN ({placeholders})",
        invite_params,
    ).fetchall()
    existing_ids = [row["id"] for row in existing_invites]
    if not existing_ids:
        return "邀请码不存在", 404
    existing_placeholders, existing_params = sql_placeholders(existing_ids)
    if action == "delete":
        db.execute(f"DELETE FROM invite_codes WHERE id IN ({existing_placeholders})", existing_params)
    else:
        enabled = 1 if action == "enable" else 0
        db.execute(
            f"UPDATE invite_codes SET enabled = ?, updated_at = ? WHERE id IN ({existing_placeholders})",
            (enabled, utc_now(), *existing_params),
        )
    record_admin_audit(
        int(g.user["id"]),
        f"invite.bulk.{action}",
        "invite_batch",
        ",".join(str(value) for value in existing_ids),
        summary=f"批量{action}邀请码 {len(existing_ids)} 个",
        before={"count": len(existing_ids), "codes": [str(row["code"]) for row in existing_invites]},
        after={"action": action},
    )
    db.commit()
    return redirect(url_for("admin.invites"))


@bp.get("/users/export")
@permission_required("users.view")
def export_users():
    db = get_db()
    users = db.execute("SELECT * FROM users ORDER BY id ASC").fetchall()
    output = StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["id", "email", "username", "role", "enabled", "email_verified", "points", "created_at"])
    for user in users:
        writer.writerow([
            user["id"],
            user["email"],
            user["username"],
            user["role"],
            user["enabled"],
            user["email_verified"],
            user["points"],
            user["created_at"],
        ])
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=huishi-users.csv"},
    )


@bp.get("/users/import-template")
@permission_required("users.import")
def import_users_template():
    return Response(
        "email,password,username,role,points,email_verified,enabled\nuser@example.com,secret123,nickname,user,20,0,1\n",
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=huishi-users-import-template.csv"},
    )


@bp.post("/users/create")
@permission_required("users.create")
def create_user():
    username = request.form.get("username", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    role = request.form.get("role", "user").strip()
    enabled = request.form.get("enabled") in {"1", "on", "true", "True"}
    try:
        points = parse_int_field("points", minimum=0)
    except ValueError as exc:
        return str(exc), 400
    if not email or not is_valid_email(email):
        return "邮箱格式不正确", 400
    if len(username) < 2:
        return "用户名至少 2 位", 400
    if len(password) < 6:
        return "密码至少 6 位", 400
    if role not in {"user", "admin"}:
        return "角色无效", 400

    db = get_db()
    existing = db.execute(
        "SELECT id FROM users WHERE lower(email) = lower(?) OR username = ?",
        (email, username),
    ).fetchone()
    if existing is not None:
        return "邮箱或用户名已存在", 400
    try:
        with transaction() as db:
            now = utc_now()
            cursor = db.execute(
                """
                INSERT INTO users (
                    email, username, password_hash, role, email_verified,
                    email_verification_code, email_verification_token, email_verified_at,
                    enabled, points, created_at
                )
                VALUES (?, ?, ?, ?, 1, '', '', ?, ?, 0, ?)
                """,
                (email, username, generate_password_hash(password), role, now, 1 if enabled else 0, now),
            )
            user_id = int(cursor.lastrowid)
            if points:
                adjust_points(user_id, points, "admin_initial")
            record_admin_audit(
                int(g.user["id"]),
                "user.create",
                "user",
                user_id,
                summary=f"新增用户 {username}",
                after={
                    "id": user_id,
                    "username": username,
                    "email": email,
                    "role": role,
                    "enabled": enabled,
                    "points": points,
                },
            )
    except Exception as exc:
        if not is_integrity_error(exc):
            raise
        return "邮箱或用户名已存在", 400
    return redirect(url_for("admin.users"))


@bp.post("/users/import")
@permission_required("users.import")
def import_users():
    uploaded_file = request.files.get("file")
    if uploaded_file is None or not uploaded_file.filename:
        return "请上传 CSV 文件", 400
    uploaded_file.stream.seek(0, 2)
    file_size = uploaded_file.stream.tell()
    uploaded_file.stream.seek(0)
    max_bytes = int(current_app.config.get("ADMIN_IMPORT_MAX_BYTES", 2 * 1024 * 1024))
    if file_size > max_bytes:
        return "CSV 文件过大", 413
    try:
        content = uploaded_file.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        return "CSV 必须使用 UTF-8 编码", 400
    created = import_users_csv(content)
    record_admin_audit(
        int(g.user["id"]),
        "user.import",
        "user_batch",
        uploaded_file.filename,
        summary=f"导入用户 {created} 个",
        after={"created": created, "filename": uploaded_file.filename, "file_size": file_size},
    )
    get_db().commit()
    return redirect(url_for("admin.users", imported=created))


@bp.post("/users/<int:user_id>/adjust")
@permission_required("users.points.adjust")
def adjust_user(user_id: int):
    try:
        delta = parse_int_field("delta", minimum=-100000, maximum=100000)
    except ValueError as exc:
        return str(exc), 400
    return adjust_user_points(user_id, delta, request.form.get("admin_note", ""), redirect_to="admin.users")


@bp.post("/users/bulk")
@permission_required("users.view")
def bulk_update_users():
    db = get_db()
    action = request.form.get("action", "")
    user_ids = []
    for raw_id in request.form.getlist("user_ids[]") or request.form.getlist("user_ids"):
        try:
            user_ids.append(int(raw_id))
        except (TypeError, ValueError):
            continue
    if not user_ids:
        return "请先选择用户", 400
    if action not in {"reset_login_failures", "delete"}:
        return "批量操作无效", 400
    require_permission("users.delete" if action == "delete" else "users.login_failures.reset")
    placeholders, user_params = sql_placeholders(user_ids)
    users = db.execute(f"SELECT * FROM users WHERE id IN ({placeholders})", user_params).fetchall()
    if not users:
        return "用户不存在", 404
    existing_ids = [int(user["id"]) for user in users]
    if action == "delete":
        if g.user is not None and int(g.user["id"]) in existing_ids:
            return "不能删除当前登录用户", 400
        selected_admin_ids = [int(user["id"]) for user in users if user["role"] == "admin"]
        if selected_admin_ids:
            existing_placeholders, existing_params = sql_placeholders(existing_ids)
            remaining_admin_count = db.execute(
                f"SELECT COUNT(*) AS value FROM users WHERE role = 'admin' AND id NOT IN ({existing_placeholders})",
                existing_params,
            ).fetchone()["value"]
            if remaining_admin_count <= 0:
                return "至少保留一个管理员", 400
        for user in users:
            delete_user_cascade(db, int(user["id"]))
        record_admin_audit(
            int(g.user["id"]),
            "user.bulk.delete",
            "user_batch",
            ",".join(str(value) for value in existing_ids),
            summary=f"批量删除用户 {len(existing_ids)} 个",
            before={
                "count": len(existing_ids),
                "users": [
                    {"id": int(user["id"]), "username": str(user["username"]), "role": str(user["role"])}
                    for user in users
                ],
            },
        )
        db.commit()
        return redirect(url_for("admin.users"))
    for user in users:
        reset_login_failure_state_for_user(dict(user))
    record_admin_audit(
        int(g.user["id"]),
        "user.bulk.login_failures.reset",
        "user_batch",
        ",".join(str(value) for value in existing_ids),
        summary=f"批量重置登录失败次数 {len(existing_ids)} 个",
        after={"count": len(existing_ids)},
    )
    db.commit()
    return redirect(url_for("admin.users"))


@bp.post("/users/<int:user_id>/password")
@permission_required("users.password.reset")
def reset_user_password(user_id: int):
    password = request.form.get("password", "")
    if len(password) < 6:
        record_rejected_admin_audit(
            int(g.user["id"]),
            "user.password.reset",
            "user",
            user_id,
            summary="拒绝密码重置：密码长度不足",
            error_code="password_too_short",
        )
        get_db().commit()
        return "密码至少 6 位", 400
    db = get_db()
    user = db.execute("SELECT id, username FROM users WHERE id = ?", (user_id,)).fetchone()
    if user is None:
        return "用户不存在", 404
    db.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (generate_password_hash(password), user_id),
    )
    record_admin_audit(
        int(g.user["id"]),
        "user.password.reset",
        "user",
        user_id,
        summary=f"重置用户 {user['username']} 的密码",
        after={"password_changed": True},
    )
    db.commit()
    return redirect(url_for("admin.users"))


@bp.post("/users/<int:user_id>/login-failures/reset")
@permission_required("users.login_failures.reset")
def reset_user_login_failures(user_id: int):
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if user is None:
        return "用户不存在", 404
    reset_login_failure_state_for_user(dict(user))
    record_admin_audit(
        int(g.user["id"]),
        "user.login_failures.reset",
        "user",
        user_id,
        summary=f"重置用户 {user['username']} 的登录失败次数",
    )
    db.commit()
    return redirect(url_for("admin.users"))


@bp.post("/users/<int:user_id>/role")
@permission_required("users.role.update")
def update_user_role(user_id: int):
    role = request.form.get("role", "")
    if role not in ALL_ROLES:
        return "角色无效", 400
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if user is None:
        return "用户不存在", 404
    if user["role"] in {"admin", "super_admin"} and role not in {"admin", "super_admin"}:
        admin_count = db.execute(
            "SELECT COUNT(*) AS value FROM users WHERE role IN ('admin', 'super_admin')"
        ).fetchone()["value"]
        if admin_count <= 1:
            return "至少保留一个管理员", 400
    db.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
    record_admin_audit(
        int(g.user["id"]),
        "user.role.update",
        "user",
        user_id,
        summary=f"更新用户 {user['username']} 的角色",
        before={"role": user["role"]},
        after={"role": role},
    )
    db.commit()
    return redirect(url_for("admin.users"))


@bp.post("/users/<int:user_id>/status")
@permission_required("users.status.update")
def update_user_status(user_id: int):
    raw_enabled = request.form.get("enabled", "")
    enabled = 1 if str(raw_enabled).strip().lower() in {"1", "true", "yes", "on", "enabled"} else 0
    with immediate_transaction() as db:
        user = db.execute(
            "SELECT id, username, email, role, enabled FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if user is None:
            return "用户不存在", 404
        if not enabled:
            if int(user["id"]) == int(g.user["id"]):
                return "不能禁用当前登录管理员", 400
            if user["role"] in {"admin", "super_admin"} and int(user["enabled"]):
                enabled_admins = lock_enabled_admins_for_update()
                if len(enabled_admins) <= 1:
                    return "至少保留一个启用管理员", 400
        db.execute("UPDATE users SET enabled = ? WHERE id = ?", (enabled, user_id))
        record_admin_audit(
            int(g.user["id"]),
            "user.status.update",
            "user",
            user_id,
            summary=f"{'启用' if enabled else '禁用'}用户 {user['username']}",
            before={"enabled": bool(user["enabled"])},
            after={"enabled": bool(enabled)},
        )
    return redirect(url_for("admin.users"))


@bp.post("/users/<int:user_id>/delete")
@permission_required("users.delete")
def delete_user(user_id: int):
    if g.user is not None and int(g.user["id"]) == user_id:
        return "不能删除当前登录用户", 400
    db = get_db()
    user = db.execute("SELECT id, username, email, role, points FROM users WHERE id = ?", (user_id,)).fetchone()
    if user is None:
        abort(404)
    delete_user_cascade(db, user_id)
    record_admin_audit(
        int(g.user["id"]),
        "user.delete",
        "user",
        user_id,
        summary=f"删除用户 {user['username']}",
        before={
            "username": user["username"],
            "email": user["email"],
            "role": user["role"],
            "points": int(user["points"]),
        },
    )
    db.commit()
    return redirect(url_for("admin.users"))


@bp.get("/users/<int:user_id>/ledger")
@permission_required("users.view")
def user_ledger(user_id: int):
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if user is None:
        return "用户不存在", 404

    page_query = PageQuery.from_values(request.args.get("page"), request.args.get("per_page"))
    search = request.args.get("q", "").strip()
    event_type_filter = request.args.get("event_type", "").strip()
    mode_filter = request.args.get("mode", "").strip()
    status_filter = request.args.get("status", "").strip()
    from_filter = request.args.get("from", "").strip()
    to_filter = request.args.get("to", "").strip()
    activity_page = query_activity_page(
        db=db,
        search=search,
        user_id=user_id,
        event_type=event_type_filter,
        mode=mode_filter,
        status=status_filter,
        from_date=from_filter,
        to_date=to_filter,
        page=page_query.page,
        per_page=page_query.per_page,
    )
    modes = [row["mode"] for row in db.execute("SELECT DISTINCT mode FROM records WHERE user_id = ? AND mode != '' ORDER BY mode", (user_id,)).fetchall()]
    pagination_query = urlencode(
        {
            "q": search,
            "event_type": event_type_filter,
            "mode": mode_filter,
            "status": status_filter,
            "from": from_filter,
            "to": to_filter,
            "per_page": page_query.per_page,
        }
    )
    return render_template(
        "admin/user_ledger.html",
        user=user,
        events=activity_page.rows,
        search=search,
        event_type_filter=event_type_filter,
        mode_filter=mode_filter,
        status_filter=status_filter,
        from_filter=from_filter,
        to_filter=to_filter,
        modes=modes,
        event_types=EVENT_LABELS.items(),
        statuses=STATUS_LABELS.items(),
        pagination=Pagination.from_query(page_query, activity_page.total),
        pagination_query=pagination_query,
    )


def adjust_user_points(user_id: int, delta: int, note: str, *, redirect_to: str):
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if user is None:
        return "用户不存在", 400
    if delta == 0:
        return "调整点数不能为 0", 400
    if int(user["points"]) + delta < 0:
        return "扣费不能超过用户当前余额", 400
    if abs(delta) >= 10000 and not note.strip():
        return "大额调整必须填写备注", 400
    before_points = int(user["points"])
    adjust_points(user_id, delta, "admin_adjust", admin_note=note.strip())
    record_admin_audit(
        int(g.user["id"]),
        "user.points.adjust",
        "user",
        user_id,
        summary=note.strip(),
        before={"points": before_points},
        after={"points": before_points + delta, "delta": delta},
    )
    db.commit()
    return redirect(url_for(redirect_to))


def delete_user_cascade(db, user_id: int) -> None:
    db.execute(
        """
        DELETE FROM canvas_messages
        WHERE conversation_id IN (
            SELECT id FROM canvas_conversations WHERE user_id = ?
        )
        """,
        (user_id,),
    )
    db.execute("DELETE FROM canvas_conversations WHERE user_id = ?", (user_id,))
    db.execute(
        """
        DELETE FROM invite_redemptions
        WHERE invite_code_id IN (
            SELECT id FROM invite_codes WHERE owner_user_id = ?
        )
           OR inviter_user_id = ?
           OR invitee_user_id = ?
        """,
        (user_id, user_id, user_id),
    )
    db.execute("UPDATE invite_codes SET created_by_admin_id = NULL WHERE created_by_admin_id = ?", (user_id,))
    db.execute("DELETE FROM invite_codes WHERE owner_user_id = ?", (user_id,))
    record_ids = [
        row["id"]
        for row in db.execute("SELECT id FROM records WHERE user_id = ?", (user_id,)).fetchall()
    ]
    if record_ids:
        placeholders, params = sql_placeholders(record_ids)
        db.execute(f"UPDATE generation_tasks SET record_id = NULL WHERE record_id IN ({placeholders})", params)
        db.execute(f"DELETE FROM point_ledger WHERE record_id IN ({placeholders})", params)
    db.execute("DELETE FROM generation_tasks WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM point_ledger WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM records WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM dialogues WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM user_settings WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM users WHERE id = ?", (user_id,))


def import_users_csv(content: str) -> int:
    db = get_db()
    reader = csv.DictReader(StringIO(content))
    required = {"email", "password", "username", "role", "points", "email_verified"}
    if reader.fieldnames is None or not required.issubset(set(reader.fieldnames)):
        raise ValueError("CSV 字段必须包含 email,password,username,role,points,email_verified")
    created = 0
    max_rows = int(current_app.config.get("ADMIN_IMPORT_MAX_ROWS", 2000))
    max_field_length = int(current_app.config.get("ADMIN_IMPORT_MAX_FIELD_LENGTH", 256))
    for row_index, row in enumerate(reader, start=1):
        if row_index > max_rows:
            raise ValueError("CSV 行数过多")
        if any(len(str(value or "")) > max_field_length for value in row.values()):
            raise ValueError("CSV 字段过长")
        email = (row.get("email") or "").strip().lower()
        password = row.get("password") or ""
        username = (row.get("username") or "").strip() or (email.split("@", 1)[0] if email else "")
        role = (row.get("role") or "user").strip()
        enabled_value = row.get("enabled")
        enabled = 1 if enabled_value is None or str(enabled_value).strip().lower() in {"1", "true", "yes", "on", "enabled"} else 0
        if not email or not password or len(password) < 6 or role not in {"user", "admin"}:
            continue
        try:
            points = int(row.get("points") or "0")
            email_verified = 1 if str(row.get("email_verified") or "").strip() in {"1", "true", "True", "yes", "on"} else 0
        except ValueError:
            continue
        existing = db.execute(
            "SELECT id FROM users WHERE lower(email) = lower(?) OR username = ?",
            (email, username),
        ).fetchone()
        if existing is not None:
            continue
        initial_points = max(points, 0)
        cursor = db.execute(
            """
            INSERT INTO users (email, username, password_hash, role, email_verified, email_verification_token, enabled, points, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                email,
                username,
                generate_password_hash(password),
                role,
                email_verified,
                "" if email_verified else "",
                enabled,
                0,
                utc_now(),
            ),
        )
        if initial_points:
            adjust_points(int(cursor.lastrowid), initial_points, "admin_initial")
        created += 1
    return created


@bp.route("/packages", methods=("GET", "POST"))
@permission_required("packages.view")
def packages():
    return redirect(url_for("admin.config_packages"))
    db = get_db()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            return "套餐名称不能为空", 400
        try:
            price_cents, points = parse_package_amounts()
        except ValueError as exc:
            return str(exc), 400
        enabled = 1 if request.form.get("enabled") == "on" else 0
        db.execute(
            """
            INSERT INTO packages (name, price_cents, points, description, enabled)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                name,
                price_cents,
                points,
                request.form.get("description", ""),
                enabled,
            ),
        )
        db.commit()
        return redirect(url_for("admin.packages"))
    packages = db.execute("SELECT * FROM packages ORDER BY id DESC").fetchall()
    return render_template("admin/packages.html", packages=packages)


@bp.post("/packages/<int:package_id>")
@permission_required("packages.update")
def update_package(package_id: int):
    db = get_db()
    package = db.execute("SELECT * FROM packages WHERE id = ?", (package_id,)).fetchone()
    if package is None:
        return "套餐不存在", 404
    name = request.form.get("name", "").strip()
    if not name:
        return "套餐名称不能为空", 400
    try:
        price_cents, points = parse_package_amounts()
    except ValueError as exc:
        return str(exc), 400
    enabled = 1 if request.form.get("enabled") == "on" else 0
    db.execute(
        """
        UPDATE packages
        SET name = ?, price_cents = ?, points = ?, description = ?, enabled = ?
        WHERE id = ?
        """,
        (
            name,
            price_cents,
            points,
            request.form.get("description", ""),
            enabled,
            package_id,
        ),
    )
    record_admin_audit(
        int(g.user["id"]),
        "package.update",
        "package",
        package_id,
        summary=f"更新套餐 {name}",
        before={
            "name": package["name"],
            "price_cents": int(package["price_cents"]),
            "points": int(package["points"]),
            "description": package["description"],
            "enabled": bool(package["enabled"]),
        },
        after={
            "name": name,
            "price_cents": price_cents,
            "points": points,
            "description": request.form.get("description", ""),
            "enabled": bool(enabled),
        },
    )
    db.commit()
    return redirect(url_for("admin.packages"))


@bp.post("/packages/<int:package_id>/delete")
@permission_required("packages.update")
def delete_package(package_id: int):
    db = get_db()
    package = db.execute("SELECT * FROM packages WHERE id = ?", (package_id,)).fetchone()
    if package is None:
        return "套餐不存在", 404
    db.execute("DELETE FROM packages WHERE id = ?", (package_id,))
    record_admin_audit(
        int(g.user["id"]),
        "package.delete",
        "package",
        package_id,
        summary=f"删除套餐 {package['name']}",
        before={
            "name": package["name"],
            "price_cents": int(package["price_cents"]),
            "points": int(package["points"]),
            "enabled": bool(package["enabled"]),
        },
    )
    db.commit()
    return redirect(url_for("admin.packages"))


@bp.get("/records")
@permission_required("records.view")
def records():
    db = get_db()
    page_query = PageQuery.from_values(request.args.get("page"), request.args.get("per_page"))
    search = request.args.get("q", "").strip()
    user_filter = request.args.get("user", "").strip()
    event_type_filter = request.args.get("event_type", "").strip()
    mode_filter = request.args.get("mode", "").strip()
    status_filter = request.args.get("status", "").strip()
    from_filter = request.args.get("from", "").strip()
    to_filter = request.args.get("to", "").strip()
    activity_page = query_activity_page(
        db=db,
        search=search,
        user=user_filter,
        event_type=event_type_filter,
        mode=mode_filter,
        status=status_filter,
        from_date=from_filter,
        to_date=to_filter,
        page=page_query.page,
        per_page=page_query.per_page,
    )
    modes = [
        row["mode"]
        for row in db.execute(
            "SELECT DISTINCT mode FROM records WHERE mode != '' ORDER BY mode"
        ).fetchall()
    ]
    pagination_query = urlencode(
        {
            "q": search,
            "user": user_filter,
            "event_type": event_type_filter,
            "mode": mode_filter,
            "status": status_filter,
            "from": from_filter,
            "to": to_filter,
            "per_page": page_query.per_page,
        }
    )
    return render_template(
        "admin/records.html",
        media_reconciliation_tasks=[{**dict(row), 'metadata':json.loads(row['metadata_json'] or '{}')} for row in db.execute(
            "SELECT id,user_id,model,provider_id,provider_task_id,metadata_json FROM generation_tasks WHERE media_type='video' AND status IN ('queued','running') ORDER BY id DESC"
        ).fetchall() if json.loads(row['metadata_json'] or '{}').get('phase')=='needs_reconciliation'],
        events=activity_page.rows,
        search=search,
        user_filter=user_filter,
        event_type_filter=event_type_filter,
        mode_filter=mode_filter,
        status_filter=status_filter,
        from_filter=from_filter,
        to_filter=to_filter,
        modes=modes,
        event_types=EVENT_LABELS.items(),
        statuses=STATUS_LABELS.items(),
        pagination=Pagination.from_query(page_query, activity_page.total),
        pagination_query=pagination_query,
    )


@bp.get("/channel-health")
@permission_required("providers.view")
def channel_health():
    """Per-channel success rate, latency and failure reasons.

    Read-only: ``provider_call_logs`` is filled by the generation path, so this
    page never issues an upstream request and cannot slow down a worker.
    """
    from huishi.provider_metrics import channel_health as collect_channel_health

    window_raw = request.args.get("window", "").strip()
    window_hours = int(window_raw) if window_raw.isdigit() else 24
    window_hours = window_hours if window_hours in {1, 6, 24, 72, 168} else 24
    return render_template(
        "admin/channel_health.html",
        health=collect_channel_health(window_hours=window_hours),
        window_hours=window_hours,
        window_options=[
            (1, "最近 1 小时"),
            (6, "最近 6 小时"),
            (24, "最近 24 小时"),
            (72, "最近 3 天"),
            (168, "最近 7 天"),
        ],
    )


@bp.post('/media-tasks/<int:task_id>/resume')
@permission_required('providers.update')
def resume_media_task(task_id):
    from huishi.media_tasks import resume_video_task
    try:
        resume_video_task(current_app._get_current_object(),task_id)
    except ValueError as exc:
        return str(exc),409
    record_admin_audit(int(g.user['id']),'media_task.resume','generation_task',task_id,
                       summary='恢复原视频任务查询或同键请求，不创建新逻辑任务')
    get_db().commit()
    flash('原任务已恢复处理；请查看业务流水和资产结果')
    return redirect(url_for('admin.records'))
