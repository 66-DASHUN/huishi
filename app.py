from __future__ import annotations

from datetime import date, datetime, timezone, timedelta
import logging
import os
import re
import secrets
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import click
from flask import Flask, abort, flash, g, jsonify, redirect, render_template, request, send_from_directory, session, url_for
from cryptography.fernet import Fernet
from werkzeug.middleware.proxy_fix import ProxyFix

from huishi.auth import bp as auth_bp, login_required
from huishi.admin_permissions import has_permission
from huishi.backup import create_backup
from huishi.config import Config, parse_size_bytes
from huishi.db import close_db, get_db, init_db
from huishi.invites import create_invite_code
from huishi import providers as provider_store
from huishi.routes_admin import bp as admin_bp
from huishi.routes_workspace import bp as workspace_bp
from huishi.storage import sweep_local_uploads
from huishi.upload_storage import (
    StorageUnavailable,
    build_upload_storage,
    get_upload_storage,
    storage_configuration_signature,
)
from huishi.user_key import get_masked_user_api_key, get_user_api_key, get_user_provider, save_user_api_key

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("huishi")
DEFAULT_SECRET_KEY = "dev-change-me"
DEFAULT_ADMIN_PASSWORD = "1qaz@WSX"
DEFAULT_LOG_DIR = Path("logs")
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,80}$")
LOCAL_TIMEZONE = timezone(timedelta(hours=8))
LEDGER_REASON_LABELS = {
    "generation": "生成扣费",
    "admin_adjust": "管理员调整",
    "admin_initial": "初始积分",
    "invite_reward": "邀请奖励",
    "invitee_reward": "注册奖励",
    "refund": "积分返还",
    "recharge": "账户充值",
}


def display_ledger_reason(reason: str) -> str:
    normalized = (reason or "").strip()
    if normalized in LEDGER_REASON_LABELS:
        return LEDGER_REASON_LABELS[normalized]
    return normalized.replace("_", " ").strip() or "积分变动"


def display_account_time(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return "时间未知"
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return raw
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(LOCAL_TIMEZONE).strftime("%Y-%m-%d %H:%M")


def build_account_ledger_items(ledger) -> list[dict[str, str | int | bool]]:
    items: list[dict[str, str | int | bool]] = []
    for item in ledger:
        delta = int(item["delta"])
        items.append(
            {
                "label": display_ledger_reason(str(item["reason"])),
                "delta": delta,
                "delta_text": f"{delta:+d} 点",
                "is_positive": delta > 0,
                "time": display_account_time(str(item["created_at"])),
                "note": str(item["admin_note"] or ""),
                "record_id": item["record_id"],
            }
        )
    return items


class DailyFileHandler(logging.Handler):
    def __init__(self, log_dir: Path, *, today=date.today) -> None:
        super().__init__()
        self.log_dir = Path(log_dir)
        self.today = today
        self.current_date: date | None = None
        self.stream = None
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._open_stream_for_today()
            assert self.stream is not None
            self.stream.write(self.format(record) + "\n")
            self.stream.flush()
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        if self.stream is not None:
            self.stream.close()
            self.stream = None
        super().close()

    def _open_stream_for_today(self) -> None:
        today_value = self.today()
        if self.stream is not None and self.current_date == today_value:
            return
        if self.stream is not None:
            self.stream.close()
        self.current_date = today_value
        log_path = self.log_dir / f"huishi-{today_value:%Y-%m-%d}.log"
        self.stream = log_path.open("a", encoding="utf-8")


def configure_daily_file_logging(*, log_dir: Path | str | None = None, today=date.today) -> logging.Handler:
    target_dir = Path(log_dir or os.environ.get("HUISHI_LOG_DIR", DEFAULT_LOG_DIR))
    handler = DailyFileHandler(target_dir, today=today)
    handler.setLevel(logging.INFO)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logging.getLogger().addHandler(handler)
    return handler


def create_app(*, testing: bool = False) -> Flask:
    app = Flask(__name__)
    app.jinja_env.filters["model_label"] = provider_store.model_label
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
    app.config.from_object(Config)
    app.config["LOG_DIR"] = Path(os.environ.get("HUISHI_LOG_DIR", DEFAULT_LOG_DIR))
    app.config["SECRET_KEY"] = os.environ.get("HUISHI_SECRET_KEY", app.config["SECRET_KEY"])
    app.config["ENCRYPTION_KEY"] = os.environ.get("HUISHI_ENCRYPTION_KEY", app.config["ENCRYPTION_KEY"])
    app.config["ADMIN_PASSWORD"] = os.environ.get("HUISHI_ADMIN_PASSWORD", app.config["ADMIN_PASSWORD"])
    app.config["DATABASE"] = Path(os.environ.get("HUISHI_DATABASE", app.config["DATABASE"]))
    if testing:
        app.config["DATABASE_URL"] = os.environ.get("HUISHI_TEST_DATABASE_URL", "")
        app.config["REQUIRE_POSTGRES"] = os.environ.get("HUISHI_TEST_REQUIRE_POSTGRES", "0") == "1"
    else:
        app.config["DATABASE_URL"] = os.environ.get("DATABASE_URL", "")
        app.config["REQUIRE_POSTGRES"] = os.environ.get(
            "HUISHI_REQUIRE_POSTGRES",
            "1" if app.config.get("REQUIRE_POSTGRES") else "0",
        ) == "1"
    app.config["OUTPUT_DIR"] = Path(os.environ.get("HUISHI_OUTPUT_DIR", app.config["OUTPUT_DIR"]))
    app.config["BACKUP_DIR"] = Path(os.environ.get("HUISHI_BACKUP_DIR", app.config["BACKUP_DIR"]))
    app.config["BACKUP_KEEP"] = int(os.environ.get("HUISHI_BACKUP_KEEP", app.config["BACKUP_KEEP"]))
    app.config["CANVAS_APP_URL"] = os.environ.get("HUISHI_CANVAS_APP_URL", app.config["CANVAS_APP_URL"])
    app.config["REDIS_URL"] = os.environ.get("HUISHI_REDIS_URL", "")
    app.config["REQUIRE_REDIS_LIMITS"] = os.environ.get(
        "HUISHI_REQUIRE_REDIS_LIMITS",
        "1" if is_production_environment() else "0",
    ) == "1"
    app.config["TESTING"] = testing
    app.config["IS_PRODUCTION"] = is_production_environment()
    if not testing:
        configure_daily_file_logging(log_dir=app.config["LOG_DIR"])
    if app.config.get("REQUIRE_POSTGRES") and not is_postgresql_database_url(app.config.get("DATABASE_URL", "")):
        raise RuntimeError("DATABASE_URL must be set to postgresql:// when HUISHI_REQUIRE_POSTGRES=1")
    if app.config["IS_PRODUCTION"]:
        if app.config["SECRET_KEY"] == DEFAULT_SECRET_KEY:
            raise RuntimeError("HUISHI_SECRET_KEY must be set to a non-default value in production")
        if app.config["ADMIN_PASSWORD"] == DEFAULT_ADMIN_PASSWORD:
            raise RuntimeError("HUISHI_ADMIN_PASSWORD must be set to a non-default value in production")
        if not app.config.get("ENCRYPTION_KEY"):
            raise RuntimeError("HUISHI_ENCRYPTION_KEY must be set in production")
        if app.config.get("REQUIRE_REDIS_LIMITS") and not app.config.get("REDIS_URL"):
            raise RuntimeError("HUISHI_REDIS_URL must be set in production for shared rate limits and generation protection")
        try:
            Fernet(str(app.config["ENCRYPTION_KEY"]).encode("ascii"))
        except (TypeError, ValueError) as exc:
            raise RuntimeError("HUISHI_ENCRYPTION_KEY must be a valid Fernet key") from exc
    if testing:
        app.config["GENERATION_INLINE"] = True
        app.config["RATE_LIMITING_ENABLED"] = False
    app.config["SESSION_COOKIE_SECURE"] = bool(app.config.get("SESSION_COOKIE_SECURE")) or bool(app.config["IS_PRODUCTION"])
    app.config["OUTPUT_DIR"].mkdir(parents=True, exist_ok=True)
    app.extensions["upload_storage"] = build_upload_storage(app.config)
    app.extensions["upload_storage_signature"] = storage_configuration_signature(app.config)
    app.config["DATABASE"].parent.mkdir(parents=True, exist_ok=True)
    app.teardown_appcontext(close_db)

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(workspace_bp)
    from huishi.routes_model_management import bp as model_management_bp
    app.register_blueprint(model_management_bp)

    CSRF_EXEMPT_METHODS = {"GET", "HEAD", "OPTIONS"}
    CSRF_EXEMPT_PATHS = {
        "/logout",
        "/verify-email-link",
        "/api/canvas/assets/library",
        "/api/canvas/session/verify",
        "/api/canvas/generate",
        "/api/canvas/estimate",
    }

    # Endpoints that authenticate a cross-origin canvas request via the signed
    # host session token (see canvas_api_user) instead of a cookie. Listed
    # explicitly so a new canvas route is not exempted by accident.
    CANVAS_CSRF_EXEMPT_ENDPOINTS = {
        "workspace.import_canvas_assets",
        "workspace.canvas_assets_library",
        "workspace.canvas_asset_library_item",
        "workspace.canvas_conversations_list",
        "workspace.canvas_conversations_create",
        "workspace.canvas_conversations_update",
        "workspace.canvas_conversation_messages",
        "workspace.canvas_estimate",
        "workspace.canvas_generate",
        "workspace.canvas_projects_collection",
        "workspace.canvas_project_item",
        "workspace.canvas_session_verify",
        "workspace.canvas_text_chat",
        "workspace.canvas_user_key_get",
        "workspace.canvas_user_key_post",
    }

    @app.before_request
    def assign_request_id():
        incoming = request.headers.get("X-Request-ID", "").strip()
        g.request_id = incoming if REQUEST_ID_PATTERN.fullmatch(incoming) else secrets.token_hex(12)

    @app.before_request
    def csrf_protect():
        if app.config.get("TESTING") and not app.config.get("CSRF_PROTECT_TESTING"):
            return
        if request.method in CSRF_EXEMPT_METHODS:
            return
        if request.path in CSRF_EXEMPT_PATHS:
            return
        # Cross-origin canvas endpoints authenticate the signed host token in
        # canvas_api_user rather than a cookie, so CSRF does not apply to them.
        # This is an explicit endpoint list on purpose: a blanket
        # ``request.path.startswith("/api/canvas/")`` would silently exempt every
        # future canvas route, including any that authenticates by cookie only.
        # Add new canvas endpoints here deliberately.
        if request.endpoint in CANVAS_CSRF_EXEMPT_ENDPOINTS:
            return
        if request.headers.get("X-Canvas-Session") and request.endpoint in (
            "workspace.create_video_task_api", "workspace.upload_media_reference",
            "workspace.cancel_video_task_api",
        ):
            return
        if request.path.startswith("/static/"):
            return
        token = session.get("csrf_token")
        if not token:
            token = secrets.token_hex(32)
            session["csrf_token"] = token
        if request.headers.get("X-Requested-With") == "fetch":
            header_token = request.headers.get("X-CSRF-Token", "")
        else:
            header_token = request.form.get("csrf_token", "")
        if not header_token:
            logger.warning("CSRF token missing for %s %s", request.method, request.path)
            if request.headers.get("X-Requested-With") == "fetch":
                return jsonify({"ok": False, "error": "CSRF token 缺失"}), 403
            abort(403)
        if not secrets.compare_digest(header_token, token):
            logger.warning("CSRF token mismatch for %s %s", request.method, request.path)
            if request.headers.get("X-Requested-With") == "fetch":
                return jsonify({"ok": False, "error": "CSRF token 无效"}), 403
            abort(403)

    @app.context_processor
    def inject_csrf_token():
        token = session.get("csrf_token")
        if not token:
            token = secrets.token_hex(32)
            session["csrf_token"] = token
        return {
            "csrf_token": token,
            "can": lambda permission: bool(
                g.user is not None and has_permission(str(g.user["role"]), str(permission))
            ),
        }

    @app.after_request
    def add_security_headers(response):
        response.headers["X-Request-ID"] = str(getattr(g, "request_id", ""))
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if app.config.get("IS_PRODUCTION"):
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
            response.headers.setdefault(
                "Content-Security-Policy",
                production_content_security_policy(app.config.get("CANVAS_APP_URL", "")),
            )
            response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
        return response

    @app.get("/")
    def home():
        canvas_settings = provider_store.get_canvas_settings()
        canvas_app_url = str(canvas_settings.get("canvas_app_url") or "").strip().rstrip("/")
        return render_template("home.html", canvas_app_url=canvas_app_url)

    @app.get("/assets/<path:filename>")
    def vite_assets(filename: str):
        try:
            return send_from_directory(Path(app.root_path) / "dist" / "assets", filename)
        except FileNotFoundError:
            abort(404)

    @app.get("/static/uploads/<path:filename>")
    def uploaded_asset(filename: str):
        if Path(filename).name != filename:
            abort(404)
        try:
            local_path = get_upload_storage().ensure_local(filename)
        except FileNotFoundError:
            abort(404)
        except StorageUnavailable:
            abort(503)
        response = send_from_directory(local_path.parent, local_path.name, conditional=True)
        response.headers["Cache-Control"] = "public, max-age=604800"
        return response

    @app.get("/api/csrf-token")
    def csrf_token_endpoint():
        token = session.get("csrf_token")
        if not token:
            token = secrets.token_hex(32)
            session["csrf_token"] = token
        return jsonify({"csrf_token": token})

    @app.get("/api/session")
    def session_info():
        if g.user is None:
            return jsonify({"authenticated": False})
        return jsonify(
            {
                "authenticated": True,
                "user": {
                    "id": g.user["id"],
                    "username": g.user["username"],
                    "role": g.user["role"],
                    "points": g.user["points"],
                },
            }
        )

    @app.get("/account")
    @login_required
    def account():
        db = get_db()
        ledger = db.execute(
            "SELECT * FROM point_ledger WHERE user_id = ? ORDER BY id DESC LIMIT 20",
            (g.user["id"],),
        ).fetchall()
        invites = db.execute(
            "SELECT * FROM invite_codes WHERE owner_user_id = ? ORDER BY id DESC",
            (g.user["id"],),
        ).fetchall()
        has_user_key = bool(get_user_api_key(g.user["id"]))
        ledger_items = build_account_ledger_items(ledger)
        return render_template(
            "account.html",
            user=g.user,
            ledger=ledger_items,
            invites=invites,
            has_user_key=has_user_key,
        )

    @app.post("/account/invites")
    @login_required
    def create_account_invite():
        create_invite_code(owner_user_id=g.user["id"])
        get_db().commit()
        return redirect(url_for("account"))

    @app.route("/account/api-key", methods=("GET", "POST"))
    @login_required
    def account_api_key():
        user_id = int(g.user["id"])
        user_key_enabled = provider_store.get_app_settings("user_key_enabled").get("user_key_enabled", "1") == "1"
        if request.method == "POST":
            clear = request.form.get("clear_api_key") == "1"
            try:
                if clear:
                    save_user_api_key(user_id, "")
                    get_db().commit()
                    flash("API Key 已清除，将使用共享资源并消耗积分")
                elif not user_key_enabled:
                    flash("管理员已禁用用户自备 Key 功能，无法保存 API Key")
                else:
                    raw_key = request.form.get("api_key", "").strip()
                    if raw_key:
                        save_user_api_key(user_id, raw_key)
                        get_db().commit()
                        flash("API Key 已保存，生图将使用您的 Key，不消耗积分")
                    else:
                        flash("请填写 API Key")
            except Exception as exc:
                logger.exception("account_api_key save failed user_id=%d", user_id)
                flash(f"保存失败，请稍后重试（{exc}）")
            return redirect(url_for("account_api_key"))

        masked_key = get_masked_user_api_key(user_id)
        has_user_key = bool(masked_key)
        return render_template(
            "account_api_key.html",
            user=g.user,
            masked_key=masked_key,
            has_user_key=has_user_key,
            user_key_enabled=user_key_enabled,
        )

    @app.get("/pricing")
    def pricing():
        db = get_db()
        rules = db.execute(
            "SELECT * FROM pricing_rules WHERE enabled = 1 AND mode = 'text' ORDER BY CASE WHEN model = '*' THEN 0 ELSE 1 END, model, resolution"
        ).fetchall()
        packages = db.execute(
            "SELECT * FROM packages WHERE enabled = 1 ORDER BY points ASC, id ASC"
        ).fetchall()
        return render_template("pricing.html", rules=rules, packages=packages, user=g.user)

    @app.cli.command("storage-sweep")
    @click.option("--retention-days", type=int, default=None, help="Legacy shortcut: use the same retention window for all deletable uploads.")
    @click.option("--orphan-retention-days", type=int, default=None, help="Delete truly unreferenced uploads older than this many days.")
    @click.option("--hidden-retention-days", type=int, default=None, help="Delete hidden/deleted asset uploads older than this many days.")
    @click.option("--max-bytes", default=None, help="Report capacity pressure above this size, e.g. 50G. Does not delete referenced files.")
    @click.option("--batch-size", type=int, default=None, help="Deprecated alias for --max-delete-files.")
    @click.option("--max-delete-files", type=int, default=None, help="Maximum eligible upload files to delete in one run. Use 0 for unlimited.")
    @click.option("--min-age-seconds", type=int, default=None, help="Never delete upload files newer than this age, even when retention is 0.")
    @click.option("--delete", "delete_files", is_flag=True, help="Actually delete files. Without this flag the command is a dry run.")
    def storage_sweep_command(
        retention_days: int | None,
        orphan_retention_days: int | None,
        hidden_retention_days: int | None,
        max_bytes: str | None,
        batch_size: int | None,
        max_delete_files: int | None,
        min_age_seconds: int | None,
        delete_files: bool,
    ) -> None:
        if retention_days is not None:
            orphan_retention_days = retention_days if orphan_retention_days is None else orphan_retention_days
            hidden_retention_days = retention_days if hidden_retention_days is None else hidden_retention_days
        orphan_retention_days = int(app.config.get("STORAGE_ORPHAN_RETENTION_DAYS", 7) if orphan_retention_days is None else orphan_retention_days)
        hidden_retention_days = int(app.config.get("STORAGE_HIDDEN_RETENTION_DAYS", 14) if hidden_retention_days is None else hidden_retention_days)
        configured_max_bytes = int(app.config.get("STORAGE_MAX_BYTES", 0) or 0)
        effective_max_bytes = parse_size_bytes(max_bytes) if max_bytes else (configured_max_bytes or None)
        if max_delete_files is None:
            max_delete_files = batch_size if batch_size is not None else int(app.config.get("STORAGE_SWEEP_MAX_DELETE_FILES", 20000))
        effective_min_age_seconds = int(app.config.get("STORAGE_SWEEP_MIN_AGE_SECONDS", 300) if min_age_seconds is None else min_age_seconds)
        result = sweep_local_uploads(
            app.config["OUTPUT_DIR"],
            get_db(),
            retention_seconds=max(0, hidden_retention_days) * 86400,
            orphan_retention_seconds=max(0, orphan_retention_days) * 86400,
            hidden_retention_seconds=max(0, hidden_retention_days) * 86400,
            max_bytes=effective_max_bytes,
            max_delete_files=max_delete_files,
            min_age_seconds=effective_min_age_seconds,
            dry_run=not delete_files,
            storage=get_upload_storage(),
        )
        click.echo(
            "storage-sweep "
            f"dry_run={result.dry_run} "
            f"orphan_retention_days={orphan_retention_days} "
            f"hidden_retention_days={hidden_retention_days} "
            f"total_files={result.total_files} "
            f"referenced_files={result.referenced_files} "
            f"hidden_files={result.hidden_files} "
            f"orphan_files={result.orphan_files} "
            f"max_delete_files={0 if result.max_delete_files is None else result.max_delete_files} "
            f"min_age_seconds={result.min_age_seconds} "
            f"delete_limit_reached={result.delete_limit_reached} "
            f"remaining_deletable_files={result.remaining_deletable_files} "
            f"deleted_files={len(result.deleted_files)} "
            f"deleted_bytes={result.deleted_bytes} "
            f"total_bytes={result.total_bytes}"
        )
        if result.capacity_warning:
            click.echo(f"capacity_warning=True over_capacity_bytes={result.over_capacity_bytes}")
        for upload_path in result.deleted_files:
            click.echo(upload_path)

    @app.cli.command("backup-postgres")
    def backup_postgres_command() -> None:
        path = create_backup(
            app.config["DATABASE_URL"],
            Path(app.config["BACKUP_DIR"]),
            int(app.config["BACKUP_KEEP"]),
        )
        click.echo(path)

    return app


def should_enable_debug() -> bool:
    return os.environ.get("FLASK_DEBUG", "0") == "1"


def is_production_environment() -> bool:
    env = os.environ.get("HUISHI_ENV", "").strip().lower()
    flask_env = os.environ.get("FLASK_ENV", "").strip().lower()
    return env == "production" or flask_env == "production"


def is_postgresql_database_url(database_url: object) -> bool:
    raw_url = str(database_url or "").strip()
    if ":" not in raw_url:
        return False
    return raw_url.split(":", 1)[0].lower() in {"postgres", "postgresql"}


def url_origin(raw_url: object) -> str:
    parsed = urlsplit(str(raw_url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def production_content_security_policy(canvas_app_url: object = "") -> str:
    frame_sources = ["'self'"]
    canvas_origin = url_origin(canvas_app_url)
    if canvas_origin:
        frame_sources.append(canvas_origin)
    return (
        "default-src 'self'; img-src 'self' data: blob:; media-src 'self' https: data: blob:; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; script-src 'self' 'unsafe-inline' 'unsafe-eval' https:; "
        "connect-src 'self' https: wss:; "
        f"frame-src {' '.join(frame_sources)}; frame-ancestors 'self'; form-action 'self'"
    )


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        init_db()
    app.run(host="0.0.0.0", port=8000, debug=should_enable_debug())
