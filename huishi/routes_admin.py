from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from io import StringIO

from flask import Blueprint, Response, current_app, redirect, render_template, request, url_for
from werkzeug.security import generate_password_hash

from huishi.auth import admin_required
from huishi.billing import adjust_points
from huishi.db import get_db, utc_now

bp = Blueprint("admin", __name__, url_prefix="/admin")


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


@bp.get("/")
@admin_required
def index():
    db = get_db()
    stats = {
        "user_count": db.execute("SELECT COUNT(*) AS value FROM users").fetchone()["value"],
        "total_points": db.execute("SELECT COALESCE(SUM(points), 0) AS value FROM users").fetchone()["value"],
        "record_count": db.execute("SELECT COUNT(*) AS value FROM records").fetchone()["value"],
        "points_charged": db.execute("SELECT COALESCE(SUM(points_charged), 0) AS value FROM records").fetchone()["value"],
    }
    recent_records_limit = int(current_app.config.get("DASHBOARD_RECENT_RECORDS_LIMIT", 6))
    recent_records = db.execute(
        f"""
        SELECT records.*, users.username
        FROM records
        JOIN users ON users.id = records.user_id
        ORDER BY records.id DESC
        LIMIT {recent_records_limit}
        """
    ).fetchall()
    recent_ledger_limit = int(current_app.config.get("DASHBOARD_RECENT_LEDGER_LIMIT", 8))
    recent_ledger = db.execute(
        f"""
        SELECT point_ledger.*, users.username
        FROM point_ledger
        JOIN users ON users.id = point_ledger.user_id
        ORDER BY point_ledger.id DESC
        LIMIT {recent_ledger_limit}
        """
    ).fetchall()
    return render_template(
        "admin/dashboard.html",
        stats=stats,
        recent_records=recent_records,
        recent_ledger=recent_ledger,
    )


@bp.route("/pricing", methods=("GET", "POST"))
@admin_required
def pricing():
    db = get_db()
    if request.method == "POST":
        try:
            points_per_image = parse_int_field("points_per_image", minimum=0)
        except ValueError as exc:
            return str(exc), 400
        mode = request.form.get("mode", "")
        resolution = request.form.get("resolution", "")
        rule = db.execute(
            "SELECT id FROM pricing_rules WHERE mode = ? AND resolution = ?",
            (mode, resolution),
        ).fetchone()
        if rule is None:
            return "计费规则不存在", 400
        enabled = 1 if request.form.get("enabled") == "on" else 0
        db.execute(
            """
            UPDATE pricing_rules
            SET points_per_image = ?, enabled = ?
            WHERE mode = ? AND resolution = ?
            """,
            (
                points_per_image,
                enabled,
                mode,
                resolution,
            ),
        )
        db.commit()
        return redirect(url_for("admin.pricing"))
    rules = db.execute("SELECT * FROM pricing_rules ORDER BY mode, resolution").fetchall()
    return render_template("admin/pricing.html", rules=rules)


@bp.route("/users", methods=("GET", "POST"))
@admin_required
def users():
    db = get_db()
    if request.method == "POST":
        try:
            user_id = parse_int_field("user_id", minimum=1)
            delta = parse_int_field("delta", minimum=-100000, maximum=100000)
        except ValueError as exc:
            return str(exc), 400
        user = db.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
        if user is None:
            return "用户不存在", 400
        return adjust_user_points(user_id, delta, request.form.get("admin_note", ""), redirect_to="admin.users")
    users = db.execute("SELECT * FROM users ORDER BY id DESC").fetchall()
    return render_template("admin/users.html", users=users)


@bp.get("/users/export")
@admin_required
def export_users():
    db = get_db()
    users = db.execute("SELECT * FROM users ORDER BY id ASC").fetchall()
    output = StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["id", "email", "username", "role", "email_verified", "points", "created_at"])
    for user in users:
        writer.writerow([
            user["id"],
            user["email"],
            user["username"],
            user["role"],
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
@admin_required
def import_users_template():
    return Response(
        "email,password,username,role,points,email_verified\nuser@example.com,secret123,nickname,user,20,0\n",
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=huishi-users-import-template.csv"},
    )


@bp.post("/users/import")
@admin_required
def import_users():
    uploaded_file = request.files.get("file")
    if uploaded_file is None or not uploaded_file.filename:
        return "请上传 CSV 文件", 400
    try:
        content = uploaded_file.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        return "CSV 必须使用 UTF-8 编码", 400
    created = import_users_csv(content)
    return redirect(url_for("admin.users", imported=created))


@bp.post("/users/<int:user_id>/adjust")
@admin_required
def adjust_user(user_id: int):
    try:
        delta = parse_int_field("delta", minimum=-100000, maximum=100000)
    except ValueError as exc:
        return str(exc), 400
    return adjust_user_points(user_id, delta, request.form.get("admin_note", ""), redirect_to="admin.users")


@bp.post("/users/<int:user_id>/password")
@admin_required
def reset_user_password(user_id: int):
    password = request.form.get("password", "")
    if len(password) < 6:
        return "密码至少 6 位", 400
    db = get_db()
    user = db.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
    if user is None:
        return "用户不存在", 404
    db.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (generate_password_hash(password), user_id),
    )
    db.commit()
    return redirect(url_for("admin.users"))


@bp.post("/users/<int:user_id>/role")
@admin_required
def update_user_role(user_id: int):
    role = request.form.get("role", "")
    if role not in {"user", "admin"}:
        return "角色无效", 400
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if user is None:
        return "用户不存在", 404
    if user["role"] == "admin" and role != "admin":
        admin_count = db.execute("SELECT COUNT(*) AS value FROM users WHERE role = 'admin'").fetchone()["value"]
        if admin_count <= 1:
            return "至少保留一个管理员", 400
    db.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
    db.commit()
    return redirect(url_for("admin.users"))


@bp.get("/users/<int:user_id>/ledger")
@admin_required
def user_ledger(user_id: int):
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if user is None:
        return "用户不存在", 404
    ledger_limit = int(current_app.config.get("USER_LEDGER_LIMIT", 200))
    ledger = db.execute(
        f"""
        SELECT * FROM point_ledger
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT {ledger_limit}
        """,
        (user_id,),
    ).fetchall()
    records_limit = int(current_app.config.get("USER_RECORDS_LIMIT", 50))
    records = db.execute(
        f"""
        SELECT * FROM records
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT {records_limit}
        """,
        (user_id,),
    ).fetchall()
    return render_template("admin/user_ledger.html", user=user, ledger=ledger, records=records)


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
    adjust_points(user_id, delta, "admin_adjust", admin_note=note.strip())
    db.commit()
    return redirect(url_for(redirect_to))


def import_users_csv(content: str) -> int:
    db = get_db()
    reader = csv.DictReader(StringIO(content))
    required = {"email", "password", "username", "role", "points", "email_verified"}
    if reader.fieldnames is None or not required.issubset(set(reader.fieldnames)):
        raise ValueError("CSV 字段必须包含 email,password,username,role,points,email_verified")
    created = 0
    for row in reader:
        email = (row.get("email") or "").strip().lower()
        password = row.get("password") or ""
        username = (row.get("username") or "").strip() or (email.split("@", 1)[0] if email else "")
        role = (row.get("role") or "user").strip()
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
        db.execute(
            """
            INSERT INTO users (email, username, password_hash, role, email_verified, email_verification_token, points, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                email,
                username,
                generate_password_hash(password),
                role,
                email_verified,
                "" if email_verified else "",
                max(points, 0),
                utc_now(),
            ),
        )
        created += 1
    db.commit()
    return created


@bp.route("/packages", methods=("GET", "POST"))
@admin_required
def packages():
    db = get_db()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            return "套餐名称不能为空", 400
        try:
            price_cents = parse_price_cents(request.form.get("price"))
            points = parse_int_field("points", minimum=1)
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


@bp.get("/records")
@admin_required
def records():
    db = get_db()
    records_limit = int(current_app.config.get("ADMIN_RECORDS_LIMIT", 100))
    records = db.execute(
        f"""
        SELECT records.*, users.username
        FROM records
        JOIN users ON users.id = records.user_id
        ORDER BY records.id DESC
        LIMIT {records_limit}
        """
    ).fetchall()
    ledger_limit = int(current_app.config.get("ADMIN_LEDGER_LIMIT", 100))
    ledger = db.execute(
        f"""
        SELECT point_ledger.*, users.username
        FROM point_ledger
        JOIN users ON users.id = point_ledger.user_id
        ORDER BY point_ledger.id DESC
        LIMIT {ledger_limit}
        """
    ).fetchall()
    return render_template("admin/records.html", records=records, ledger=ledger)
