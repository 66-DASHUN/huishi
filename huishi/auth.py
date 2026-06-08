from __future__ import annotations

from email.message import EmailMessage
from functools import wraps
import random
import smtplib
from typing import Callable
from urllib.parse import urlsplit

from flask import Blueprint, current_app, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from huishi.db import get_db, utc_now

bp = Blueprint("auth", __name__)


def safe_next_url(target: str | None) -> str:
    if not target:
        return url_for("account")
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or not target.startswith("/"):
        return url_for("account")
    return target


@bp.before_app_request
def load_logged_in_user() -> None:
    user_id = session.get("user_id")
    if user_id is None:
        g.user = None
        return
    g.user = get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def login_required(view: Callable):
    @wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return redirect(url_for("auth.login", next=request.path))
        return view(**kwargs)

    return wrapped_view


def admin_required(view: Callable):
    @wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return redirect(url_for("auth.login", next=request.path))
        if g.user["role"] != "admin":
            return ("无权限", 403)
        return view(**kwargs)

    return wrapped_view


@bp.route("/register", methods=("GET", "POST"))
def register():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not username and email:
            username = email.split("@", 1)[0]
        if email and not is_valid_email(email):
            flash("邮箱格式不正确")
        elif len(username) < 2 or len(password) < 6:
            flash("用户名至少 2 位，密码至少 6 位")
        else:
            db = get_db()
            verification_code = generate_email_code() if email else ""
            email_verified = 0 if email else 1
            try:
                cursor = db.execute(
                    """
                    INSERT INTO users (email, username, password_hash, role, email_verified, email_verification_token, points, created_at)
                    VALUES (?, ?, ?, 'user', ?, ?, 20, ?)
                    """,
                    (email, username, generate_password_hash(password), email_verified, verification_code, utc_now()),
                )
                db.execute(
                    """
                    INSERT INTO point_ledger (user_id, delta, reason, admin_note, created_at)
                    VALUES (?, 20, 'register_bonus', '新用户赠送', ?)
                    """,
                    (cursor.lastrowid, utc_now()),
                )
                if email:
                    send_verification_email(email, verification_code)
                db.commit()
            except RuntimeError as exc:
                db.rollback()
                flash(f"验证码发送失败：{exc}")
            except sqlite3.IntegrityError:
                db.rollback()
                flash("邮箱或用户名已存在")
            else:
                session.clear()
                session["user_id"] = cursor.lastrowid
                if email:
                    session["pending_email_user_id"] = cursor.lastrowid
                    return redirect(url_for("auth.verify_email"))
                return redirect(safe_next_url(request.args.get("next")))
    return render_template("auth_register.html", next_url=safe_next_url(request.args.get("next")))


@bp.route("/login", methods=("GET", "POST"))
def login():
    if request.method == "POST":
        identifier = (request.form.get("email") or request.form.get("username") or "").strip()
        password = request.form.get("password", "")
        user = find_user_by_login(identifier)
        if user is None or not check_password_hash(user["password_hash"], password):
            flash("账号或密码错误")
        else:
            session.clear()
            session["user_id"] = user["id"]
            return redirect(safe_next_url(request.args.get("next")))
    return render_template("auth_login.html", next_url=safe_next_url(request.args.get("next")))


@bp.route("/verify-email", methods=("GET", "POST"))
def verify_email():
    db = get_db()
    user = current_verification_user()
    if user is None:
        return redirect(url_for("auth.login"))
    if request.method == "POST":
        code = request.form.get("code", "").strip()
        if code != user["email_verification_token"]:
            return "验证码错误", 400
        db.execute(
            """
            UPDATE users
            SET email_verified = 1, email_verification_token = '', email_verified_at = ?
            WHERE id = ?
            """,
            (utc_now(), user["id"]),
        )
        db.commit()
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
    db.execute(
        """
        UPDATE users
        SET email_verified = 1, email_verification_token = '', email_verified_at = ?
        WHERE id = ?
        """,
        (utc_now(), user["id"]),
    )
    db.commit()
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


def is_valid_email(email: str) -> bool:
    if "@" not in email:
        return False
    local, domain = email.rsplit("@", 1)
    return bool(local) and "." in domain and not domain.startswith(".") and not domain.endswith(".")


def generate_email_code() -> str:
    return f"{random.SystemRandom().randint(0, 999999):06d}"


def send_verification_email(email: str, code: str) -> None:
    smtp_host = current_app.config.get("SMTP_HOST", "")
    smtp_from = current_app.config.get("SMTP_FROM", "")
    if not smtp_host or not smtp_from:
        raise RuntimeError("邮件服务未配置")

    message = EmailMessage()
    message["Subject"] = "绘世邮箱验证码"
    message["From"] = smtp_from
    message["To"] = email
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

    smtp_port = int(current_app.config.get("SMTP_PORT", 587))
    smtp_user = current_app.config.get("SMTP_USER", "")
    smtp_password = current_app.config.get("SMTP_PASSWORD", "")
    smtp_tls = bool(current_app.config.get("SMTP_TLS", True))
    try:
        smtp_timeout = int(current_app.config.get("SMTP_TIMEOUT", 10))
        with smtplib.SMTP(smtp_host, smtp_port, timeout=smtp_timeout) as smtp:
            if smtp_tls:
                smtp.starttls()
            if smtp_user:
                smtp.login(smtp_user, smtp_password)
            smtp.send_message(message)
    except (smtplib.SMTPException, OSError) as exc:
        raise RuntimeError(str(exc)) from exc


def current_verification_user():
    user_id = session.get("pending_email_user_id") or session.get("user_id")
    if user_id is None:
        return None
    return get_db().execute(
        "SELECT * FROM users WHERE id = ? AND email != '' AND email_verified = 0",
        (user_id,),
    ).fetchone()
