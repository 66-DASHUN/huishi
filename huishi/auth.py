from __future__ import annotations

from email.message import EmailMessage
from functools import wraps
import random
import secrets
import smtplib
import time
from typing import Callable
from urllib.parse import urlsplit

from flask import Blueprint, current_app, flash, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from huishi.admin_permissions import has_permission
from huishi.db import get_db, is_integrity_error, transaction, utc_now
from huishi.invites import validate_invite_code, redeem_invite
from huishi.rate_limits import (
    clear_login_failure_state,
    clear_login_failure_states_for_candidates,
    login_failure_state as shared_login_failure_state,
    rate_limit_bucket,
    save_login_failure_state,
)

bp = Blueprint("auth", __name__)


def safe_next_url(target: str | None) -> str:
    if not target:
        return url_for("account")
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or not target.startswith("/"):
        return url_for("account")
    return target


def home_auth_url(mode: str = "login", target: str | None = None) -> str:
    return url_for("home", auth=mode, next=safe_next_url(target))


def render_home_auth(mode: str = "login", target: str | None = None):
    from huishi.providers import get_canvas_settings
    canvas_settings = get_canvas_settings()
    canvas_app_url = str(canvas_settings.get("canvas_app_url") or "").strip().rstrip("/")
    return render_template(
        "home.html",
        auth_intent={"mode": mode, "next": safe_next_url(target)},
        canvas_app_url=canvas_app_url,
    )


def wants_json_response() -> bool:
    return request.headers.get("X-Requested-With") == "fetch"


def json_error(message: str, status_code: int = 400):
    return jsonify({"ok": False, "error": message}), status_code


def json_success(**payload):
    return jsonify({"ok": True, **payload})


def client_ip() -> str:
    forwarded = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    if forwarded:
        return forwarded
    return request.remote_addr or "unknown"


def _rate_limit_bucket(key: str, limit: int, window_seconds: int) -> bool:
    return rate_limit_bucket(current_app, key, limit, window_seconds)


def rate_limit_response(message: str, status_code: int = 429):
    if wants_json_response():
        return json_error(message, status_code)
    return message, status_code


def login_failure_state(identifier: str) -> dict[str, float | int]:
    return shared_login_failure_state(current_app, identifier)


def reset_login_failure_state(identifier: str) -> None:
    clear_login_failure_state(current_app, identifier)


def reset_login_failure_state_for_user(user: dict | int | str) -> None:
    keys: list[str] = []
    if isinstance(user, dict):
        identifier = str(user.get("username") or "").strip().lower()
        if identifier:
            keys.append(identifier)
        email = str(user.get("email") or "").strip().lower()
        if email:
            keys.append(email)
    elif isinstance(user, int):
        keys = [key for key in _LOGIN_FAILURE_STATE if key.endswith(f":{user}")]
    else:
        identifier = str(user).strip().lower()
        if identifier:
            keys.append(identifier)
    clear_login_failure_states_for_candidates(current_app, keys)


def record_login_failure(identifier: str) -> None:
    if not current_app.config.get("RATE_LIMITING_ENABLED", True):
        return
    state = login_failure_state(identifier)
    now = time.time()
    window_seconds = int(current_app.config.get("LOGIN_RATE_LIMIT_WINDOW_SECONDS", 300))
    if now - float(state["window_started_at"]) > window_seconds:
        state["failures"] = 0
        state["window_started_at"] = now
    state["failures"] = int(state["failures"]) + 1
    attempts = int(current_app.config.get("LOGIN_RATE_LIMIT_ATTEMPTS", 5))
    if int(state["failures"]) >= attempts:
        lockout_seconds = int(current_app.config.get("LOGIN_LOCKOUT_SECONDS", 900))
        state["locked_until"] = now + lockout_seconds
    save_login_failure_state(current_app, identifier, state)


def login_is_locked(identifier: str) -> bool:
    if not current_app.config.get("RATE_LIMITING_ENABLED", True):
        return False
    state = login_failure_state(identifier)
    return time.time() < float(state.get("locked_until", 0.0))


@bp.before_app_request
def load_logged_in_user() -> None:
    user_id = session.get("user_id")
    if user_id is None:
        g.user = None
        return
    user = get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if user is None or not user["enabled"]:
        session.clear()
        g.user = None
        return
    g.user = user


def login_required(view: Callable):
    @wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return render_home_auth("login", request.full_path.rstrip("?"))
        return view(**kwargs)

    return wrapped_view


def permission_required(permission: str):
    def decorator(view: Callable):
        @wraps(view)
        def wrapped_view(**kwargs):
            if g.user is None:
                return render_home_auth("login", request.full_path.rstrip("?"))
            if not has_permission(str(g.user["role"]), permission):
                return ("无权限", 403)
            return view(**kwargs)

        return wrapped_view

    return decorator


def admin_required(view: Callable):
    return permission_required("admin.view")(view)


@bp.route("/register", methods=("GET", "POST"))
def register():
    email_value = request.args.get("email", "").strip().lower()
    if request.method == "GET":
        return redirect(home_auth_url("register", request.args.get("next")))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        email_value = email
        email_code = request.form.get("email_code", "").strip()
        invite_code = request.form.get("invite_code", "").strip()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        invite = None
        if not username and email:
            username = email.split("@", 1)[0]
        if not email:
            error_message = "请填写邮箱并获取验证码"
        elif not is_valid_email(email):
            error_message = "邮箱格式不正确"
        elif len(username) < 2 or len(password) < 6:
            error_message = "用户名至少 2 位，密码至少 6 位"
        elif email_exists(email) or username_exists(username):
            error_message = "邮箱或用户名已存在"
        elif error := validate_registration_email_code(email, email_code):
            error_message = error
        else:
            error_message = ""
            invite, invite_error = validate_invite_code(invite_code)
            if invite_error:
                if wants_json_response():
                    return json_error(invite_error)
                flash(invite_error)
                return redirect(home_auth_url("register", request.args.get("next")))
            try:
                with transaction() as db:
                    cursor = db.execute(
                        """
                        INSERT INTO users (
                            email, username, password_hash, role, email_verified,
                            email_verification_code, email_verification_token, email_verified_at, points, created_at
                        )
                        VALUES (?, ?, ?, 'user', 1, '', '', ?, 0, ?)
                        """,
                        (
                            email,
                            username,
                            generate_password_hash(password),
                            utc_now(),
                            utc_now(),
                        ),
                    )
                    if invite is not None:
                        redeem_invite(invite["id"], cursor.lastrowid)
            except RuntimeError as exc:
                error_message = f"验证码发送失败：{exc}"
            except ValueError as exc:
                error_message = str(exc)
            except Exception as exc:
                if not is_integrity_error(exc):
                    raise
                error_message = "邮箱或用户名已存在"
            else:
                session.clear()
                session["user_id"] = cursor.lastrowid
                clear_registration_email_code()
                if wants_json_response():
                    return json_success(next=safe_next_url(request.args.get("next")))
                return redirect(safe_next_url(request.args.get("next")))
        if error_message:
            if wants_json_response():
                return json_error(error_message)
            flash(error_message)
    return redirect(home_auth_url("register", request.args.get("next")))


@bp.post("/register/send-code")
def send_registration_email_code():
    email = request.form.get("email", "").strip().lower()
    error_status = 400
    if not email:
        error_message = "请先填写邮箱"
    elif not is_valid_email(email):
        error_message = "邮箱格式不正确"
    elif email_exists(email):
        error_message = "邮箱或用户名已存在"
    elif not _rate_limit_bucket(
        f"register-send-code:ip:{client_ip()}",
        int(current_app.config.get("EMAIL_CODE_RATE_LIMIT_PER_MINUTE", 1)),
        60,
    ):
        error_status = 429
        error_message = "验证码发送过于频繁，请稍后再试"
    elif not _rate_limit_bucket(
        f"register-send-code:email:{email}",
        int(current_app.config.get("EMAIL_CODE_RATE_LIMIT_PER_MINUTE", 1)),
        60,
    ):
        error_status = 429
        error_message = "验证码发送过于频繁，请稍后再试"
    elif not _rate_limit_bucket(
        f"register-send-code:email-hour:{email}",
        int(current_app.config.get("EMAIL_CODE_RATE_LIMIT_PER_HOUR", 5)),
        3600,
    ):
        error_status = 429
        error_message = "验证码发送过于频繁，请稍后再试"
    else:
        error_message = ""
        code = generate_email_code()
        try:
            send_verification_email(email, code)
        except RuntimeError as exc:
            clear_registration_email_code()
            error_message = f"验证码发送失败：{exc}"
        else:
            session["registration_email_verification"] = {
                "email": email,
                "code": code,
                "expires_at": time.time() + registration_email_code_ttl_seconds(),
            }
            success_message = "验证码已发送，请查看邮箱"
            if wants_json_response():
                return json_success(message=success_message)
            flash(success_message)
    if error_message:
        if wants_json_response():
            return json_error(error_message, error_status)
        flash(error_message)
    return redirect(home_auth_url("register", request.form.get("next")))


@bp.route("/login", methods=("GET", "POST"))
def login():
    if request.method == "GET":
        return redirect(home_auth_url("login", request.args.get("next")))
    if request.method == "POST":
        identifier = (request.form.get("email") or request.form.get("username") or "").strip()
        client_identifier = f"{client_ip()}:{identifier.lower()}"
        if login_is_locked(client_identifier):
            return rate_limit_response("登录失败次数过多，请稍后再试", 429)
        password = request.form.get("password", "")
        user = find_user_by_login(identifier)
        if user is None or not check_password_hash(user["password_hash"], password) or not user["enabled"]:
            record_login_failure(client_identifier)
            if wants_json_response():
                return json_error("账号或密码错误")
            flash("账号或密码错误")
            return render_home_auth("login", request.args.get("next"))
        else:
            reset_login_failure_state(client_identifier)
            session.clear()
            session["user_id"] = user["id"]
            if wants_json_response():
                return json_success(next=safe_next_url(request.args.get("next")))
            return redirect(safe_next_url(request.args.get("next")))
    return redirect(home_auth_url("login", request.args.get("next")))


@bp.get("/forgot-password")
def forgot_password():
    return render_template("forgot_password.html")


@bp.post("/forgot-password/send-code")
def send_password_reset_code():
    email = request.form.get("email", "").strip().lower()
    if not email:
        flash("请先填写邮箱")
    elif not is_valid_email(email):
        flash("邮箱格式不正确")
    elif not email_exists(email):
        flash("邮箱未注册")
    elif not _rate_limit_bucket(
        f"forgot-send-code:ip:{client_ip()}",
        int(current_app.config.get("EMAIL_CODE_RATE_LIMIT_PER_MINUTE", 1)),
        60,
    ):
        flash("验证码发送过于频繁，请稍后再试")
    elif not _rate_limit_bucket(
        f"forgot-send-code:email:{email}",
        int(current_app.config.get("EMAIL_CODE_RATE_LIMIT_PER_MINUTE", 1)),
        60,
    ):
        flash("验证码发送过于频繁，请稍后再试")
    elif not _rate_limit_bucket(
        f"forgot-send-code:email-hour:{email}",
        int(current_app.config.get("EMAIL_CODE_RATE_LIMIT_PER_HOUR", 5)),
        3600,
    ):
        flash("验证码发送过于频繁，请稍后再试")
    else:
        code = generate_email_code()
        try:
            send_password_reset_email(email, code)
        except RuntimeError as exc:
            clear_password_reset_email_code()
            flash(f"验证码发送失败：{exc}")
        else:
            session["password_reset_email_verification"] = {
                "email": email,
                "code": code,
                "expires_at": time.time() + registration_email_code_ttl_seconds(),
            }
            flash("验证码已发送，请查看邮箱")
    return redirect(url_for("auth.forgot_password"))


@bp.post("/forgot-password/reset")
def reset_password_with_email_code():
    email = request.form.get("email", "").strip().lower()
    code = request.form.get("code", "").strip()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")
    if not email:
        flash("请先填写邮箱")
    elif not is_valid_email(email):
        flash("邮箱格式不正确")
    elif not email_exists(email):
        flash("邮箱未注册")
    elif len(password) < 6:
        flash("密码至少 6 位")
    elif password != confirm_password:
        flash("两次输入的密码不一致")
    elif not _rate_limit_bucket(
        f"forgot-reset:ip:{client_ip()}",
        int(current_app.config.get("PASSWORD_RESET_RATE_LIMIT_ATTEMPTS", 5)),
        int(current_app.config.get("PASSWORD_RESET_RATE_LIMIT_WINDOW_SECONDS", 300)),
    ):
        flash("操作过于频繁，请稍后再试")
    elif error := validate_password_reset_email_code(email, code):
        flash(error)
    else:
        with transaction() as db:
            db.execute(
                "UPDATE users SET password_hash = ? WHERE lower(email) = lower(?)",
                (generate_password_hash(password), email),
            )
        clear_password_reset_email_code()
        flash("密码已重置，请使用新密码登录")
        return redirect(home_auth_url("login", None))
    return redirect(url_for("auth.forgot_password"))


@bp.route("/verify-email", methods=("GET", "POST"))
def verify_email():
    db = get_db()
    user = current_verification_user()
    if user is None:
        return redirect(home_auth_url("login", None))
    if request.method == "POST":
        code = request.form.get("code", "").strip()
        if code != user["email_verification_code"]:
            return "验证码错误", 400
        with transaction() as db:
            db.execute(
                """
                UPDATE users
                SET email_verified = 1, email_verification_code = '', email_verification_token = '', email_verified_at = ?
                WHERE id = ?
                """,
                (utc_now(), user["id"]),
            )
        session.pop("pending_email_user_id", None)
        flash("邮箱已验证")
        return redirect(url_for("workspace.workspace"))
    return render_template("verify_email.html", user=user)


@bp.get("/verify-email-link")
def verify_email_link():
    token = request.args.get("token", "").strip()
    if not token:
        return "验证链接无效", 400
    db = get_db()
    user = db.execute("SELECT id FROM users WHERE email_verification_token = ?", (token,)).fetchone()
    if user is None:
        return "验证链接无效或已使用", 400
    with transaction() as db:
        db.execute(
            """
            UPDATE users
            SET email_verified = 1, email_verification_code = '', email_verification_token = '', email_verified_at = ?
            WHERE id = ?
            """,
            (utc_now(), user["id"]),
        )
    session.clear()
    session["user_id"] = user["id"]
    flash("邮箱已验证")
    return redirect(url_for("account"))


@bp.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


def find_user_by_login(identifier: str):
    if "@" in identifier:
        return get_db().execute("SELECT * FROM users WHERE lower(email) = lower(?)", (identifier,)).fetchone()
    return get_db().execute("SELECT * FROM users WHERE username = ?", (identifier,)).fetchone()


def email_exists(email: str) -> bool:
    if not email:
        return False
    row = get_db().execute("SELECT id FROM users WHERE lower(email) = lower(?)", (email,)).fetchone()
    return row is not None


def username_exists(username: str) -> bool:
    row = get_db().execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    return row is not None


def is_valid_email(email: str) -> bool:
    if "@" not in email:
        return False
    local, domain = email.rsplit("@", 1)
    return bool(local) and "." in domain and not domain.startswith(".") and not domain.endswith(".")


def generate_email_code() -> str:
    return f"{random.SystemRandom().randint(0, 999999):06d}"


def generate_email_token() -> str:
    return secrets.token_urlsafe(24)


def registration_email_code_ttl_seconds() -> int:
    return int(current_app.config.get("REGISTRATION_EMAIL_CODE_TTL_SECONDS", 600))


def validate_registration_email_code(email: str, code: str) -> str:
    pending = session.get("registration_email_verification")
    if not pending:
        return "请先获取邮箱验证码"
    if pending.get("email") != email:
        return "请重新获取当前邮箱的验证码"
    if time.time() > float(pending.get("expires_at", 0)):
        clear_registration_email_code()
        return "验证码已过期，请重新获取"
    if not code or not secrets.compare_digest(str(pending.get("code", "")), code):
        return "验证码错误"
    return ""


def clear_registration_email_code() -> None:
    session.pop("registration_email_verification", None)


def validate_password_reset_email_code(email: str, code: str) -> str:
    pending = session.get("password_reset_email_verification")
    if not pending:
        return "验证码错误"
    if pending.get("email") != email:
        return "请重新获取当前邮箱的验证码"
    if time.time() > float(pending.get("expires_at", 0)):
        clear_password_reset_email_code()
        return "验证码已过期，请重新获取"
    if not code or not secrets.compare_digest(str(pending.get("code", "")), code):
        return "验证码错误"
    return ""


def clear_password_reset_email_code() -> None:
    session.pop("password_reset_email_verification", None)


def send_verification_email(email: str, code: str) -> None:
    message = EmailMessage()
    prepare_email_message(message, "绘世邮箱验证码", email)
    message.set_content(
        "\n".join(
            [
                "您好，",
                "",
                f"您的绘世邮箱验证码是：{code}",
                "验证码用于完成邮箱验证，请勿转发给他人。",
                "",
                "绘世",
            ]
        )
    )
    send_email_message(message)


def send_password_reset_email(email: str, code: str) -> None:
    message = EmailMessage()
    prepare_email_message(message, "绘世密码重置验证码", email)
    message.set_content(
        "\n".join(
            [
                "您好，",
                "",
                f"您的绘世密码重置验证码是：{code}",
                "验证码用于重置账号密码，请勿转发给他人。",
                "",
                "绘世",
            ]
        )
    )
    send_email_message(message)


def prepare_email_message(message: EmailMessage, subject: str, recipient: str) -> None:
    smtp_config = effective_smtp_config()
    smtp_from = smtp_config["from"]
    if not smtp_config["host"] or not smtp_from:
        raise RuntimeError("邮件服务未配置")
    message["Subject"] = subject
    message["From"] = smtp_from
    message["To"] = recipient


def send_email_message(message: EmailMessage) -> None:
    smtp_config = effective_smtp_config()
    smtp_host = smtp_config["host"]
    smtp_from = smtp_config["from"]
    if not smtp_host or not smtp_from:
        raise RuntimeError("邮件服务未配置")

    smtp_port = int(smtp_config["port"])
    smtp_user = smtp_config["user"]
    smtp_password = smtp_config["password"]
    smtp_tls = bool(smtp_config["tls"])
    smtp_ssl_config = smtp_config["ssl"]
    smtp_ssl = smtp_port == 465 if smtp_ssl_config is None else bool(smtp_ssl_config)
    try:
        smtp_timeout = int(smtp_config["timeout"])
        smtp_factory = smtplib.SMTP_SSL if smtp_ssl else smtplib.SMTP
        with smtp_factory(smtp_host, smtp_port, timeout=smtp_timeout) as smtp:
            if smtp_tls and not smtp_ssl:
                smtp.starttls()
            if smtp_user:
                smtp.login(smtp_user, smtp_password)
            smtp.send_message(message)
    except (smtplib.SMTPException, OSError) as exc:
        raise RuntimeError(str(exc)) from exc


def effective_smtp_config() -> dict[str, object]:
    settings = load_smtp_settings()
    smtp_user = settings.get("smtp_user") or current_app.config.get("SMTP_USER", "")
    smtp_from = settings.get("smtp_from") or current_app.config.get("SMTP_FROM", "") or smtp_user
    smtp_port = settings.get("smtp_port") or current_app.config.get("SMTP_PORT", 587)
    return {
        "host": settings.get("smtp_host") or current_app.config.get("SMTP_HOST", ""),
        "port": int(smtp_port),
        "user": smtp_user,
        "password": settings.get("smtp_password") or current_app.config.get("SMTP_PASSWORD", ""),
        "from": smtp_from,
        "ssl": smtp_bool_setting(settings.get("smtp_ssl"), current_app.config.get("SMTP_SSL", None)),
        "tls": smtp_bool_setting(settings.get("smtp_tls"), current_app.config.get("SMTP_TLS", True), default=True),
        "timeout": int(current_app.config.get("SMTP_TIMEOUT", 10)),
    }


def load_smtp_settings() -> dict[str, str]:
    try:
        from huishi.providers import get_app_settings

        return get_app_settings("smtp_host", "smtp_port", "smtp_user", "smtp_password", "smtp_from", "smtp_ssl", "smtp_tls")
    except RuntimeError:
        return {}


def smtp_bool_setting(raw_value, fallback, *, default: bool | None = None) -> bool | None:
    if raw_value not in (None, ""):
        return str(raw_value) not in {"0", "false", "False", "off", "OFF"}
    if fallback is not None:
        return bool(fallback)
    return default


def current_verification_user():
    user_id = session.get("pending_email_user_id") or session.get("user_id")
    if user_id is None:
        return None
    return get_db().execute(
        "SELECT * FROM users WHERE id = ? AND email != '' AND email_verified = 0",
        (user_id,),
    ).fetchone()
