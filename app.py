from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path

from flask import Flask, abort, g, jsonify, redirect, render_template, request, send_from_directory, session, url_for

from huishi.auth import bp as auth_bp, login_required
from huishi.config import Config
from huishi.db import close_db, get_db, init_db
from huishi.routes_admin import bp as admin_bp
from huishi.routes_workspace import bp as workspace_bp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("huishi")


def create_app(*, testing: bool = False) -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    app.config["SECRET_KEY"] = os.environ.get("HUISHI_SECRET_KEY", app.config["SECRET_KEY"])
    app.config["ADMIN_PASSWORD"] = os.environ.get("HUISHI_ADMIN_PASSWORD", app.config["ADMIN_PASSWORD"])
    app.config["DATABASE"] = Path(os.environ.get("HUISHI_DATABASE", app.config["DATABASE"]))
    app.config["OUTPUT_DIR"] = Path(os.environ.get("HUISHI_OUTPUT_DIR", app.config["OUTPUT_DIR"]))
    app.config["TESTING"] = testing
    app.config["OUTPUT_DIR"].mkdir(parents=True, exist_ok=True)
    app.config["DATABASE"].parent.mkdir(parents=True, exist_ok=True)
    app.teardown_appcontext(close_db)

    with app.app_context():
        init_db()

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(workspace_bp)

    CSRF_EXEMPT_METHODS = {"GET", "HEAD", "OPTIONS"}
    CSRF_EXEMPT_PATHS = {"/login", "/register", "/logout", "/verify-email", "/verify-email-link"}

    @app.before_request
    def csrf_protect():
        if app.config.get("TESTING"):
            return
        if request.method in CSRF_EXEMPT_METHODS:
            return
        if request.path in CSRF_EXEMPT_PATHS or request.path.startswith("/admin/users/import"):
            return
        if request.path.startswith("/static/") or request.path.startswith("/assets/"):
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
        return {"csrf_token": token}

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return response

    @app.get("/")
    def home():
        dist_index = Path(app.root_path) / "dist" / "index.html"
        if dist_index.exists():
            try:
                return send_from_directory(dist_index.parent, dist_index.name)
            except FileNotFoundError:
                pass
        return render_template("home.html")

    @app.get("/assets/<path:filename>")
    def vite_assets(filename: str):
        try:
            return send_from_directory(Path(app.root_path) / "dist" / "assets", filename)
        except FileNotFoundError:
            abort(404)

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
        ledger = get_db().execute(
            "SELECT * FROM point_ledger WHERE user_id = ? ORDER BY id DESC LIMIT 20",
            (g.user["id"],),
        ).fetchall()
        return render_template("account.html", user=g.user, ledger=ledger)

    @app.get("/pricing")
    def pricing():
        db = get_db()
        rules = db.execute(
            "SELECT * FROM pricing_rules WHERE enabled = 1 AND mode = 'text' ORDER BY resolution"
        ).fetchall()
        return render_template("pricing.html", rules=rules, user=g.user)

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=8000, debug=os.environ.get("FLASK_DEBUG", "1") == "1")
