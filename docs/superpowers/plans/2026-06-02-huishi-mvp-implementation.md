# 绘世 MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first usable version of 「绘世」 with a dynamic landing page, white generation workspace, image detail page, user accounts, configurable point billing, and a basic admin backend.

**Architecture:** Create a Flask application in the current project directory. Use SQLite for persistent data, server-rendered Jinja templates for pages, and small JavaScript modules for workspace interactions. Keep the reference project `D:\AI\image2` as a guide for image API payload shape and 1K/2K/4K size mapping, but do not copy its UI.

**Tech Stack:** Python 3, Flask, SQLite, Werkzeug password hashing, requests/OpenAI-compatible image API calls, Jinja2 templates, vanilla CSS and JavaScript, pytest.

---

## File Structure

- `requirements.txt`: Python dependencies.
- `app.py`: Flask app factory, route registration, CLI init command.
- `huishi/__init__.py`: package marker.
- `huishi/config.py`: environment defaults and filesystem paths.
- `huishi/db.py`: SQLite connection, schema creation, seed data.
- `huishi/auth.py`: login, register, logout, current user, role guards.
- `huishi/billing.py`: pricing lookup, estimated cost, balance checks, point ledger.
- `huishi/records.py`: generated image record helpers.
- `huishi/image_api.py`: image generation client adapted from the reference project behavior.
- `huishi/routes_public.py`: home, pricing, account routes.
- `huishi/routes_workspace.py`: workspace, image detail, generation, record actions.
- `huishi/routes_admin.py`: admin dashboard, users, pricing, packages, records.
- `templates/base.html`: shared document shell.
- `templates/home.html`: dynamic dark landing page.
- `templates/workspace.html`: white generation workspace.
- `templates/image_detail.html`: image detail page.
- `templates/pricing.html`: user-facing pricing page.
- `templates/account.html`: user account page.
- `templates/auth_login.html`: login form.
- `templates/auth_register.html`: registration form.
- `templates/admin/*.html`: admin pages.
- `static/css/site.css`: global, home, workspace, detail, admin styles.
- `static/js/home.js`: hero parallax and scroll motion.
- `static/js/workspace.js`: pricing estimate, submit state, copy config helpers.
- `static/uploads/.gitkeep`: generated output directory marker.
- `tests/conftest.py`: test app and temporary database fixtures.
- `tests/test_billing.py`: billing rule tests.
- `tests/test_auth_records.py`: user ownership and record tests.
- `tests/test_routes.py`: page and admin access tests.

## Task 1: Project Skeleton And App Factory

**Files:**
- Create: `D:\AI\绘世\requirements.txt`
- Create: `D:\AI\绘世\app.py`
- Create: `D:\AI\绘世\huishi\__init__.py`
- Create: `D:\AI\绘世\huishi\config.py`
- Create: `D:\AI\绘世\templates\base.html`
- Create: `D:\AI\绘世\static\css\site.css`
- Create: `D:\AI\绘世\tests\conftest.py`
- Create: `D:\AI\绘世\tests\test_routes.py`

- [ ] **Step 1: Write dependency file**

Create `requirements.txt`:

```txt
Flask==3.0.3
requests==2.32.3
openai==1.82.0
pytest==8.3.5
```

- [ ] **Step 2: Write the initial route test**

Create `tests/conftest.py`:

```python
import os
import tempfile

import pytest

from app import create_app


@pytest.fixture()
def app():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["HUISHI_DATABASE"] = os.path.join(tmp, "test.sqlite3")
        os.environ["HUISHI_OUTPUT_DIR"] = os.path.join(tmp, "output")
        os.environ["HUISHI_SECRET_KEY"] = "test-secret"
        flask_app = create_app(testing=True)
        yield flask_app


@pytest.fixture()
def client(app):
    return app.test_client()
```

Create `tests/test_routes.py`:

```python
def test_home_page_renders(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "绘世" in response.get_data(as_text=True)
    assert "造境" in response.get_data(as_text=True)
```

- [ ] **Step 3: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/test_routes.py::test_home_page_renders -v
```

Expected: FAIL because `app.py` or `create_app` does not exist.

- [ ] **Step 4: Implement minimal Flask app factory**

Create `huishi/__init__.py`:

```python
"""绘世 application package."""
```

Create `huishi/config.py`:

```python
from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


class Config:
    SECRET_KEY = os.environ.get("HUISHI_SECRET_KEY", "dev-change-me")
    DATABASE = Path(os.environ.get("HUISHI_DATABASE", BASE_DIR / "data" / "huishi.sqlite3"))
    OUTPUT_DIR = Path(os.environ.get("HUISHI_OUTPUT_DIR", BASE_DIR / "static" / "uploads"))
    DEFAULT_BASE_URL = os.environ.get("BASE_URL", "https://qa.dashun9527.com")
    DEFAULT_GENERATION_PATH = os.environ.get("GENERATION_PATH", "/v1/images/generations")
    DEFAULT_EDIT_PATH = os.environ.get("EDIT_PATH", "/v1/images/edits")
    DEFAULT_API_KEY = os.environ.get("API_KEY", "")
```

Create `app.py`:

```python
from __future__ import annotations

from flask import Flask, render_template

from huishi.config import Config


def create_app(*, testing: bool = False) -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    app.config["TESTING"] = testing
    app.config["OUTPUT_DIR"].mkdir(parents=True, exist_ok=True)
    app.config["DATABASE"].parent.mkdir(parents=True, exist_ok=True)

    @app.get("/")
    def home():
        return render_template("home.html")

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
```

Create `templates/base.html`:

```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{% block title %}绘世{% endblock %}</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='css/site.css') }}">
    {% block head %}{% endblock %}
  </head>
  <body class="{% block body_class %}{% endblock %}">
    {% block content %}{% endblock %}
    {% block scripts %}{% endblock %}
  </body>
</html>
```

Create `templates/home.html`:

```html
{% extends "base.html" %}
{% block title %}绘世 - AI 视觉创作空间{% endblock %}
{% block body_class %}home-page{% endblock %}
{% block content %}
<main class="home-shell">
  <nav class="home-nav">
    <a class="brand" href="/">绘世</a>
    <div class="home-nav-links">
      <a href="#about">关于绘世</a>
      <a href="#contact">联系我们</a>
      <a href="/pricing">计费</a>
      <a class="home-nav-cta" href="/workspace">开始使用</a>
    </div>
  </nav>
  <section class="hero-stage">
    <div class="light-path path-a"></div>
    <div class="light-path path-b"></div>
    <div class="hero-copy">
      <p class="hero-kicker">AI IMAGE CREATION SPACE</p>
      <h1><span>造境</span><span>显影</span><span>成世</span></h1>
      <p class="hero-subtitle">把提示词、参考图和参数变成可复用的视觉资产。</p>
      <a class="hero-button" href="/workspace">进入工作台</a>
    </div>
    <div class="floating-card card-one"></div>
    <div class="floating-card card-two"></div>
    <div class="floating-card card-three"></div>
  </section>
  <section id="about" class="dark-section">
    <p class="section-label">关于绘世</p>
    <h2>为创作者准备的 AI 图像生成工作台</h2>
    <div class="feature-grid">
      <article><h3>灵感图库</h3><p>沉淀可复用的提示词与作品方向。</p></article>
      <article><h3>局部重绘</h3><p>围绕参考图进行更精准的画面修改。</p></article>
      <article><h3>参数调校</h3><p>按 1K、2K、4K 管理清晰度与成本。</p></article>
      <article><h3>Agent 助手</h3><p>把生成任务拆解为更清晰的创作步骤。</p></article>
    </div>
  </section>
  <section id="contact" class="dark-section contact-section">
    <div>
      <p class="section-label">关于我们</p>
      <h2>我们希望让每一次生成都能被管理、复用和延展。</h2>
    </div>
    <div class="contact-card">
      <p>联系我们</p>
      <a href="mailto:support@huishi.local">support@huishi.local</a>
    </div>
  </section>
</main>
{% endblock %}
```

Create `static/css/site.css`:

```css
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body { margin: 0; font-family: "Microsoft YaHei", "PingFang SC", sans-serif; color: #f7fbff; background: #050708; }
a { color: inherit; text-decoration: none; }
.home-shell { min-height: 100vh; background: #050708; overflow: hidden; }
.home-nav { position: fixed; z-index: 20; top: 24px; left: 36px; right: 36px; display: flex; align-items: center; justify-content: space-between; }
.brand { font-weight: 900; letter-spacing: 0; }
.home-nav-links { display: flex; align-items: center; gap: 10px; padding: 8px; border: 1px solid rgba(255,255,255,.12); border-radius: 999px; background: rgba(10,14,18,.58); backdrop-filter: blur(18px); }
.home-nav-links a { padding: 9px 14px; color: rgba(255,255,255,.76); font-size: 14px; }
.home-nav-cta { color: #050708 !important; background: #fff; border-radius: 999px; }
.hero-stage { position: relative; min-height: 100vh; padding: 150px 6vw 80px; display: flex; align-items: center; background: radial-gradient(circle at 72% 24%, rgba(91,205,255,.18), transparent 30%), #050708; }
.hero-copy { position: relative; z-index: 3; max-width: 980px; }
.hero-kicker { color: rgba(178,238,255,.74); font-size: 13px; letter-spacing: .14em; }
.hero-copy h1 { margin: 0; display: grid; gap: 0; font-size: clamp(86px, 15vw, 230px); line-height: .82; letter-spacing: 0; }
.hero-copy h1 span:nth-child(2) { margin-left: 22vw; }
.hero-copy h1 span:nth-child(3) { margin-left: 8vw; }
.hero-subtitle { max-width: 420px; color: rgba(255,255,255,.72); font-size: 18px; line-height: 1.7; }
.hero-button { display: inline-flex; margin-top: 22px; padding: 15px 22px; border-radius: 999px; background: #fff; color: #050708; font-weight: 800; }
.light-path { position: absolute; left: -10vw; width: 130vw; height: 2px; background: linear-gradient(90deg, transparent, rgba(136,226,255,.95), transparent); box-shadow: 0 0 22px rgba(136,226,255,.75); transform-origin: center; }
.path-a { top: 34%; transform: rotate(7deg); }
.path-b { top: 64%; transform: rotate(-12deg); opacity: .7; }
.floating-card { position: absolute; width: 190px; height: 250px; border: 1px solid rgba(255,255,255,.18); border-radius: 8px; background: linear-gradient(135deg, rgba(255,255,255,.18), rgba(55,173,207,.16)); box-shadow: 0 22px 80px rgba(0,0,0,.45); }
.card-one { right: 14vw; top: 24vh; }
.card-two { right: 30vw; bottom: 10vh; width: 150px; height: 200px; }
.card-three { right: 5vw; bottom: 22vh; width: 130px; height: 170px; }
.dark-section { min-height: 82vh; padding: 120px 9vw; border-top: 1px solid rgba(255,255,255,.08); background: linear-gradient(180deg, #050708, #080d10); }
.section-label { color: rgba(155,224,255,.72); font-size: 13px; letter-spacing: .12em; }
.dark-section h2 { max-width: 760px; margin: 0 0 34px; font-size: clamp(32px, 5vw, 72px); line-height: 1.05; letter-spacing: 0; }
.feature-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 18px; }
.feature-grid article, .contact-card { padding: 28px; border: 1px solid rgba(255,255,255,.1); border-radius: 8px; background: rgba(255,255,255,.045); }
.feature-grid p, .contact-card p { color: rgba(255,255,255,.62); line-height: 1.7; }
.contact-section { display: grid; grid-template-columns: 1.2fr .8fr; gap: 48px; align-items: center; }
@media (max-width: 860px) {
  .home-nav { left: 16px; right: 16px; }
  .home-nav-links a:not(.home-nav-cta) { display: none; }
  .hero-copy h1 { font-size: clamp(72px, 24vw, 132px); }
  .hero-copy h1 span:nth-child(2), .hero-copy h1 span:nth-child(3) { margin-left: 0; }
  .feature-grid, .contact-section { grid-template-columns: 1fr; }
  .floating-card { opacity: .38; }
}
```

- [ ] **Step 5: Run test to verify it passes**

Run:

```powershell
python -m pytest tests/test_routes.py::test_home_page_renders -v
```

Expected: PASS.

## Task 2: SQLite Schema, Seeds, And Billing Rules

**Files:**
- Create: `D:\AI\绘世\huishi\db.py`
- Create: `D:\AI\绘世\huishi\billing.py`
- Modify: `D:\AI\绘世\app.py`
- Create: `D:\AI\绘世\tests\test_billing.py`

- [ ] **Step 1: Write billing tests**

Create `tests/test_billing.py`:

```python
from huishi import billing
from huishi.db import get_db


def test_default_text_generation_2k_costs_two_points(app):
    with app.app_context():
        cost = billing.calculate_cost("text", "2K", 1)
        assert cost == 2


def test_default_reference_edit_4k_costs_eight_points(app):
    with app.app_context():
        cost = billing.calculate_cost("reference", "4K", 1)
        assert cost == 8


def test_cost_multiplies_by_count(app):
    with app.app_context():
        cost = billing.calculate_cost("text", "1K", 3)
        assert cost == 3


def test_disabled_pricing_rule_rejects_generation(app):
    with app.app_context():
        db = get_db()
        db.execute(
            "UPDATE pricing_rules SET enabled = 0 WHERE mode = ? AND resolution = ?",
            ("text", "4K"),
        )
        db.commit()
        try:
            billing.calculate_cost("text", "4K", 1)
        except ValueError as exc:
            assert "未启用" in str(exc)
        else:
            raise AssertionError("disabled pricing rule should raise ValueError")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_billing.py -v
```

Expected: FAIL because `huishi.db` and `huishi.billing` do not exist.

- [ ] **Step 3: Implement database schema and seeds**

Create `huishi/db.py`:

```python
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from flask import current_app, g
from werkzeug.security import generate_password_hash


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'user',
  points INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pricing_rules (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  mode TEXT NOT NULL,
  resolution TEXT NOT NULL,
  points_per_image INTEGER NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  UNIQUE(mode, resolution)
);

CREATE TABLE IF NOT EXISTS packages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  price_cents INTEGER NOT NULL,
  points INTEGER NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  enabled INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS records (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  prompt TEXT NOT NULL,
  image_path TEXT NOT NULL,
  mode TEXT NOT NULL,
  resolution TEXT NOT NULL,
  actual_size TEXT NOT NULL,
  quality TEXT NOT NULL,
  output_format TEXT NOT NULL,
  count INTEGER NOT NULL,
  model_source TEXT NOT NULL DEFAULT '',
  elapsed_seconds REAL NOT NULL DEFAULT 0,
  points_charged INTEGER NOT NULL DEFAULT 0,
  favorite INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS point_ledger (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  delta INTEGER NOT NULL,
  reason TEXT NOT NULL,
  record_id INTEGER,
  admin_note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  FOREIGN KEY(user_id) REFERENCES users(id),
  FOREIGN KEY(record_id) REFERENCES records(id)
);
"""


DEFAULT_PRICING = [
    ("text", "1K", 1),
    ("text", "2K", 2),
    ("text", "4K", 4),
    ("reference", "1K", 2),
    ("reference", "2K", 4),
    ("reference", "4K", 8),
]


DEFAULT_PACKAGES = [
    ("入门包", 990, 100, "适合体验绘世的基础创作。"),
    ("创作包", 3990, 500, "适合持续生成和调试作品。"),
    ("专业包", 8990, 1200, "适合高频创作和 4K 输出。"),
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        db = sqlite3.connect(current_app.config["DATABASE"])
        db.row_factory = sqlite3.Row
        g.db = db
    return g.db


def close_db(_: object = None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    db = get_db()
    db.executescript(SCHEMA)
    seed_defaults(db)
    db.commit()


def seed_defaults(db: sqlite3.Connection) -> None:
    for mode, resolution, points in DEFAULT_PRICING:
        db.execute(
            """
            INSERT OR IGNORE INTO pricing_rules (mode, resolution, points_per_image, enabled)
            VALUES (?, ?, ?, 1)
            """,
            (mode, resolution, points),
        )
    for name, price_cents, points, description in DEFAULT_PACKAGES:
        db.execute(
            """
            INSERT OR IGNORE INTO packages (name, price_cents, points, description, enabled)
            VALUES (?, ?, ?, ?, 1)
            """,
            (name, price_cents, points, description),
        )
    db.execute(
        """
        INSERT OR IGNORE INTO users (username, password_hash, role, points, created_at)
        VALUES (?, ?, 'admin', 1000, ?)
        """,
        ("admin", generate_password_hash("admin123"), utc_now()),
    )
```

- [ ] **Step 4: Implement billing helpers**

Create `huishi/billing.py`:

```python
from __future__ import annotations

from huishi.db import get_db, utc_now


def calculate_cost(mode: str, resolution: str, count: int) -> int:
    if count < 1:
        raise ValueError("生成数量必须大于 0")
    db = get_db()
    row = db.execute(
        """
        SELECT points_per_image, enabled
        FROM pricing_rules
        WHERE mode = ? AND resolution = ?
        """,
        (mode, resolution),
    ).fetchone()
    if row is None:
        raise ValueError("未找到计费规则")
    if not row["enabled"]:
        raise ValueError(f"{resolution} 当前未启用")
    return int(row["points_per_image"]) * int(count)


def require_balance(user_id: int, required_points: int) -> None:
    row = get_db().execute("SELECT points FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise ValueError("用户不存在")
    if int(row["points"]) < required_points:
        raise ValueError("积分余额不足")


def adjust_points(user_id: int, delta: int, reason: str, *, record_id: int | None = None, admin_note: str = "") -> None:
    db = get_db()
    db.execute("UPDATE users SET points = points + ? WHERE id = ?", (delta, user_id))
    db.execute(
        """
        INSERT INTO point_ledger (user_id, delta, reason, record_id, admin_note, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (user_id, delta, reason, record_id, admin_note, utc_now()),
    )
```

- [ ] **Step 5: Wire database initialization into the app**

Modify `app.py` to initialize and close the database:

```python
from __future__ import annotations

from flask import Flask, render_template

from huishi.config import Config
from huishi.db import close_db, init_db


def create_app(*, testing: bool = False) -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    app.config["TESTING"] = testing
    app.config["OUTPUT_DIR"].mkdir(parents=True, exist_ok=True)
    app.config["DATABASE"].parent.mkdir(parents=True, exist_ok=True)

    with app.app_context():
        init_db()

    app.teardown_appcontext(close_db)

    @app.get("/")
    def home():
        return render_template("home.html")

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
```

- [ ] **Step 6: Run billing tests**

Run:

```powershell
python -m pytest tests/test_billing.py -v
```

Expected: PASS.

## Task 3: Authentication And User Context

**Files:**
- Create: `D:\AI\绘世\huishi\auth.py`
- Create: `D:\AI\绘世\templates\auth_login.html`
- Create: `D:\AI\绘世\templates\auth_register.html`
- Modify: `D:\AI\绘世\templates\base.html`
- Modify: `D:\AI\绘世\app.py`
- Create: `D:\AI\绘世\tests\test_auth_records.py`

- [ ] **Step 1: Write auth tests**

Create `tests/test_auth_records.py`:

```python
def test_user_can_register_login_and_view_account(client):
    response = client.post(
        "/register",
        data={"username": "alice", "password": "secret123"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "alice" in response.get_data(as_text=True)

    client.get("/logout")

    response = client.post(
        "/login",
        data={"username": "alice", "password": "secret123"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "账户中心" in response.get_data(as_text=True)


def test_workspace_requires_login(client):
    response = client.get("/workspace", follow_redirects=False)
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
```

- [ ] **Step 2: Run auth tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_auth_records.py -v
```

Expected: FAIL because auth routes do not exist.

- [ ] **Step 3: Implement auth helpers and routes**

Create `huishi/auth.py`:

```python
from __future__ import annotations

from functools import wraps
from typing import Callable

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from huishi.db import get_db, utc_now

bp = Blueprint("auth", __name__)


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
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if len(username) < 2 or len(password) < 6:
            flash("用户名至少 2 位，密码至少 6 位")
        else:
            db = get_db()
            try:
                cursor = db.execute(
                    """
                    INSERT INTO users (username, password_hash, role, points, created_at)
                    VALUES (?, ?, 'user', 20, ?)
                    """,
                    (username, generate_password_hash(password), utc_now()),
                )
                db.execute(
                    """
                    INSERT INTO point_ledger (user_id, delta, reason, admin_note, created_at)
                    VALUES (?, 20, 'register_bonus', '新用户赠送', ?)
                    """,
                    (cursor.lastrowid, utc_now()),
                )
                db.commit()
            except Exception:
                flash("用户名已存在")
            else:
                session.clear()
                session["user_id"] = cursor.lastrowid
                return redirect(url_for("account"))
    return render_template("auth_register.html")


@bp.route("/login", methods=("GET", "POST"))
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = get_db().execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if user is None or not check_password_hash(user["password_hash"], password):
            flash("用户名或密码错误")
        else:
            session.clear()
            session["user_id"] = user["id"]
            return redirect(request.args.get("next") or url_for("account"))
    return render_template("auth_login.html")


@bp.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))
```

- [ ] **Step 4: Create auth templates**

Create `templates/auth_login.html`:

```html
{% extends "base.html" %}
{% block title %}登录 - 绘世{% endblock %}
{% block body_class %}auth-page{% endblock %}
{% block content %}
<main class="auth-panel">
  <a class="auth-brand" href="/">绘世</a>
  <h1>登录</h1>
  {% for message in get_flashed_messages() %}<p class="form-error">{{ message }}</p>{% endfor %}
  <form method="post" class="auth-form">
    <input name="username" placeholder="用户名" required>
    <input name="password" placeholder="密码" type="password" required>
    <button type="submit">进入绘世</button>
  </form>
  <a href="/register">创建账号</a>
</main>
{% endblock %}
```

Create `templates/auth_register.html`:

```html
{% extends "base.html" %}
{% block title %}注册 - 绘世{% endblock %}
{% block body_class %}auth-page{% endblock %}
{% block content %}
<main class="auth-panel">
  <a class="auth-brand" href="/">绘世</a>
  <h1>创建账号</h1>
  {% for message in get_flashed_messages() %}<p class="form-error">{{ message }}</p>{% endfor %}
  <form method="post" class="auth-form">
    <input name="username" placeholder="用户名" required>
    <input name="password" placeholder="密码，至少 6 位" type="password" required>
    <button type="submit">注册并领取 20 点</button>
  </form>
  <a href="/login">已有账号，去登录</a>
</main>
{% endblock %}
```

- [ ] **Step 5: Add account route and register blueprint**

Modify `app.py`:

```python
from __future__ import annotations

from flask import Flask, g, render_template

from huishi.auth import bp as auth_bp, login_required
from huishi.config import Config
from huishi.db import close_db, init_db


def create_app(*, testing: bool = False) -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    app.config["TESTING"] = testing
    app.config["OUTPUT_DIR"].mkdir(parents=True, exist_ok=True)
    app.config["DATABASE"].parent.mkdir(parents=True, exist_ok=True)

    with app.app_context():
        init_db()

    app.teardown_appcontext(close_db)
    app.register_blueprint(auth_bp)

    @app.get("/")
    def home():
        return render_template("home.html")

    @app.get("/account")
    @login_required
    def account():
        return render_template("account.html", user=g.user)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
```

Create `templates/account.html`:

```html
{% extends "base.html" %}
{% block title %}账户中心 - 绘世{% endblock %}
{% block body_class %}workspace-page{% endblock %}
{% block content %}
<main class="simple-page">
  <nav class="simple-nav"><a href="/">绘世</a><a href="/workspace">工作台</a><a href="/logout">退出</a></nav>
  <h1>账户中心</h1>
  <p>{{ user["username"] }}，当前余额 {{ user["points"] }} 点。</p>
</main>
{% endblock %}
```

- [ ] **Step 6: Add auth CSS**

Append to `static/css/site.css`:

```css
.auth-page, .workspace-page { background: #f5f6f8; color: #111; }
.auth-panel { width: min(420px, calc(100vw - 32px)); margin: 12vh auto; padding: 28px; border: 1px solid #e5e7eb; border-radius: 8px; background: #fff; box-shadow: 0 18px 60px rgba(17,24,39,.08); }
.auth-brand { font-weight: 900; }
.auth-form { display: grid; gap: 12px; }
.auth-form input { height: 46px; padding: 0 14px; border: 1px solid #d9dde5; border-radius: 8px; }
.auth-form button { height: 46px; border: 0; border-radius: 8px; background: #050708; color: #fff; font-weight: 800; }
.form-error { color: #b42318; }
.simple-page { width: min(1080px, calc(100vw - 32px)); margin: 0 auto; padding: 32px 0; }
.simple-nav { display: flex; gap: 18px; margin-bottom: 40px; }
```

- [ ] **Step 7: Run auth tests**

Run:

```powershell
python -m pytest tests/test_auth_records.py -v
```

Expected: PASS for registration/login, FAIL for workspace route until Task 5 adds it. Temporarily mark `test_workspace_requires_login` as expected fail only if executing strictly task-by-task.

## Task 4: Admin Pricing And Package Management

**Files:**
- Create: `D:\AI\绘世\huishi\routes_admin.py`
- Create: `D:\AI\绘世\templates\admin\layout.html`
- Create: `D:\AI\绘世\templates\admin\pricing.html`
- Create: `D:\AI\绘世\templates\admin\users.html`
- Create: `D:\AI\绘世\templates\admin\packages.html`
- Modify: `D:\AI\绘世\app.py`
- Modify: `D:\AI\绘世\tests\test_routes.py`

- [ ] **Step 1: Add admin tests**

Append to `tests/test_routes.py`:

```python
def login_admin(client):
    return client.post(
        "/login",
        data={"username": "admin", "password": "admin123"},
        follow_redirects=True,
    )


def test_admin_can_update_pricing_rule(client):
    login_admin(client)
    response = client.post(
        "/admin/pricing",
        data={"mode": "text", "resolution": "2K", "points_per_image": "3", "enabled": "on"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "3 点/张" in response.get_data(as_text=True)


def test_non_admin_cannot_access_admin(client):
    client.post("/register", data={"username": "bob", "password": "secret123"}, follow_redirects=True)
    response = client.get("/admin/pricing")
    assert response.status_code == 403
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_routes.py::test_admin_can_update_pricing_rule tests/test_routes.py::test_non_admin_cannot_access_admin -v
```

Expected: FAIL because admin routes do not exist.

- [ ] **Step 3: Implement admin routes**

Create `huishi/routes_admin.py`:

```python
from __future__ import annotations

from flask import Blueprint, redirect, render_template, request, url_for

from huishi.auth import admin_required
from huishi.billing import adjust_points
from huishi.db import get_db

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.get("/")
@admin_required
def index():
    return redirect(url_for("admin.pricing"))


@bp.route("/pricing", methods=("GET", "POST"))
@admin_required
def pricing():
    db = get_db()
    if request.method == "POST":
        enabled = 1 if request.form.get("enabled") == "on" else 0
        db.execute(
            """
            UPDATE pricing_rules
            SET points_per_image = ?, enabled = ?
            WHERE mode = ? AND resolution = ?
            """,
            (
                int(request.form["points_per_image"]),
                enabled,
                request.form["mode"],
                request.form["resolution"],
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
        user_id = int(request.form["user_id"])
        delta = int(request.form["delta"])
        note = request.form.get("admin_note", "")
        adjust_points(user_id, delta, "admin_adjust", admin_note=note)
        db.commit()
        return redirect(url_for("admin.users"))
    users = db.execute("SELECT * FROM users ORDER BY id DESC").fetchall()
    return render_template("admin/users.html", users=users)


@bp.route("/packages", methods=("GET", "POST"))
@admin_required
def packages():
    db = get_db()
    if request.method == "POST":
        enabled = 1 if request.form.get("enabled") == "on" else 0
        db.execute(
            """
            INSERT INTO packages (name, price_cents, points, description, enabled)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                request.form["name"],
                int(float(request.form["price"]) * 100),
                int(request.form["points"]),
                request.form.get("description", ""),
                enabled,
            ),
        )
        db.commit()
        return redirect(url_for("admin.packages"))
    packages = db.execute("SELECT * FROM packages ORDER BY id DESC").fetchall()
    return render_template("admin/packages.html", packages=packages)
```

- [ ] **Step 4: Create admin templates**

Create `templates/admin/layout.html`:

```html
{% extends "base.html" %}
{% block body_class %}workspace-page{% endblock %}
{% block content %}
<main class="simple-page">
  <nav class="simple-nav">
    <a href="/admin/pricing">计费设置</a>
    <a href="/admin/users">用户管理</a>
    <a href="/admin/packages">套餐管理</a>
    <a href="/workspace">工作台</a>
  </nav>
  {% block admin_content %}{% endblock %}
</main>
{% endblock %}
```

Create `templates/admin/pricing.html`:

```html
{% extends "admin/layout.html" %}
{% block title %}计费设置 - 绘世{% endblock %}
{% block admin_content %}
<h1>计费设置</h1>
<div class="table-list">
  {% for rule in rules %}
  <form method="post" class="admin-row">
    <input type="hidden" name="mode" value="{{ rule['mode'] }}">
    <input type="hidden" name="resolution" value="{{ rule['resolution'] }}">
    <strong>{{ "文生图" if rule["mode"] == "text" else "参考图编辑" }} {{ rule["resolution"] }}</strong>
    <input name="points_per_image" type="number" min="0" value="{{ rule['points_per_image'] }}">
    <label><input name="enabled" type="checkbox" {% if rule["enabled"] %}checked{% endif %}> 启用</label>
    <button type="submit">保存</button>
    <span>{{ rule["points_per_image"] }} 点/张</span>
  </form>
  {% endfor %}
</div>
{% endblock %}
```

Create `templates/admin/users.html`:

```html
{% extends "admin/layout.html" %}
{% block title %}用户管理 - 绘世{% endblock %}
{% block admin_content %}
<h1>用户管理</h1>
<div class="table-list">
  {% for user in users %}
  <form method="post" class="admin-row">
    <input type="hidden" name="user_id" value="{{ user['id'] }}">
    <strong>{{ user["username"] }}</strong>
    <span>{{ user["role"] }}</span>
    <span>{{ user["points"] }} 点</span>
    <input name="delta" type="number" placeholder="加点或扣点">
    <input name="admin_note" placeholder="备注">
    <button type="submit">调整</button>
  </form>
  {% endfor %}
</div>
{% endblock %}
```

Create `templates/admin/packages.html`:

```html
{% extends "admin/layout.html" %}
{% block title %}套餐管理 - 绘世{% endblock %}
{% block admin_content %}
<h1>套餐管理</h1>
<form method="post" class="admin-row">
  <input name="name" placeholder="套餐名称" required>
  <input name="price" type="number" step="0.01" placeholder="价格" required>
  <input name="points" type="number" placeholder="点数" required>
  <input name="description" placeholder="描述">
  <label><input name="enabled" type="checkbox" checked> 启用</label>
  <button type="submit">新增</button>
</form>
<div class="table-list">
  {% for package in packages %}
  <div class="admin-row">
    <strong>{{ package["name"] }}</strong>
    <span>{{ "%.2f"|format(package["price_cents"] / 100) }} 元</span>
    <span>{{ package["points"] }} 点</span>
    <span>{{ "启用" if package["enabled"] else "停用" }}</span>
  </div>
  {% endfor %}
</div>
{% endblock %}
```

- [ ] **Step 5: Register admin blueprint and add admin CSS**

Modify `app.py` to import and register `admin_bp`:

```python
from huishi.routes_admin import bp as admin_bp

# inside create_app after auth blueprint:
app.register_blueprint(admin_bp)
```

Append to `static/css/site.css`:

```css
.table-list { display: grid; gap: 10px; }
.admin-row { display: grid; grid-template-columns: 1.2fr repeat(5, minmax(90px, 1fr)); gap: 10px; align-items: center; padding: 12px; border: 1px solid #e5e7eb; border-radius: 8px; background: #fff; }
.admin-row input { height: 38px; padding: 0 10px; border: 1px solid #d9dde5; border-radius: 8px; }
.admin-row button { height: 38px; border: 0; border-radius: 8px; color: #fff; background: #050708; }
```

- [ ] **Step 6: Run admin tests**

Run:

```powershell
python -m pytest tests/test_routes.py::test_admin_can_update_pricing_rule tests/test_routes.py::test_non_admin_cannot_access_admin -v
```

Expected: PASS.

## Task 5: Workspace, Pricing API, Records, And Detail Page

**Files:**
- Create: `D:\AI\绘世\huishi\records.py`
- Create: `D:\AI\绘世\huishi\routes_workspace.py`
- Create: `D:\AI\绘世\templates\workspace.html`
- Create: `D:\AI\绘世\templates\image_detail.html`
- Create: `D:\AI\绘世\static\js\workspace.js`
- Modify: `D:\AI\绘世\app.py`
- Modify: `D:\AI\绘世\tests\test_auth_records.py`

- [ ] **Step 1: Add workspace and ownership tests**

Append to `tests/test_auth_records.py`:

```python
from huishi.db import get_db, utc_now


def test_logged_in_user_can_view_workspace(client):
    client.post("/register", data={"username": "carol", "password": "secret123"}, follow_redirects=True)
    response = client.get("/workspace")
    assert response.status_code == 200
    assert "预计消耗" in response.get_data(as_text=True)


def test_image_detail_requires_record_owner(client, app):
    client.post("/register", data={"username": "owner", "password": "secret123"}, follow_redirects=True)
    with app.app_context():
        db = get_db()
        owner_id = db.execute("SELECT id FROM users WHERE username = 'owner'").fetchone()["id"]
        cursor = db.execute(
            """
            INSERT INTO records
            (user_id, prompt, image_path, mode, resolution, actual_size, quality, output_format, count, model_source, elapsed_seconds, points_charged, favorite, created_at)
            VALUES (?, '测试提示词', '/static/uploads/demo.png', 'text', '1K', '1024x1024', 'auto', 'png', 1, 'demo', 1.2, 1, 0, ?)
            """,
            (owner_id, utc_now()),
        )
        db.commit()
        record_id = cursor.lastrowid
    response = client.get(f"/image/{record_id}")
    assert response.status_code == 200
    assert "测试提示词" in response.get_data(as_text=True)

    client.get("/logout")
    client.post("/register", data={"username": "other", "password": "secret123"}, follow_redirects=True)
    response = client.get(f"/image/{record_id}")
    assert response.status_code == 404
```

- [ ] **Step 2: Run workspace tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_auth_records.py::test_logged_in_user_can_view_workspace tests/test_auth_records.py::test_image_detail_requires_record_owner -v
```

Expected: FAIL because workspace routes do not exist.

- [ ] **Step 3: Implement record helpers**

Create `huishi/records.py`:

```python
from __future__ import annotations

from huishi.db import get_db, utc_now


def list_records_for_user(user_id: int):
    return get_db().execute(
        "SELECT * FROM records WHERE user_id = ? ORDER BY id DESC",
        (user_id,),
    ).fetchall()


def get_record_for_user(record_id: int, user_id: int, *, is_admin: bool = False):
    if is_admin:
        return get_db().execute("SELECT * FROM records WHERE id = ?", (record_id,)).fetchone()
    return get_db().execute(
        "SELECT * FROM records WHERE id = ? AND user_id = ?",
        (record_id, user_id),
    ).fetchone()


def create_record(
    *,
    user_id: int,
    prompt: str,
    image_path: str,
    mode: str,
    resolution: str,
    actual_size: str,
    quality: str,
    output_format: str,
    count: int,
    model_source: str,
    elapsed_seconds: float,
    points_charged: int,
) -> int:
    cursor = get_db().execute(
        """
        INSERT INTO records
        (user_id, prompt, image_path, mode, resolution, actual_size, quality, output_format, count, model_source, elapsed_seconds, points_charged, favorite, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
        """,
        (
            user_id,
            prompt,
            image_path,
            mode,
            resolution,
            actual_size,
            quality,
            output_format,
            count,
            model_source,
            elapsed_seconds,
            points_charged,
            utc_now(),
        ),
    )
    return int(cursor.lastrowid)
```

- [ ] **Step 4: Implement workspace routes**

Create `huishi/routes_workspace.py`:

```python
from __future__ import annotations

from flask import Blueprint, abort, g, jsonify, render_template, request

from huishi.auth import login_required
from huishi.billing import calculate_cost
from huishi.db import get_db
from huishi.records import get_record_for_user, list_records_for_user

bp = Blueprint("workspace", __name__)


@bp.get("/workspace")
@login_required
def workspace():
    records = list_records_for_user(g.user["id"])
    rules = get_db().execute("SELECT * FROM pricing_rules ORDER BY mode, resolution").fetchall()
    return render_template("workspace.html", records=records, rules=rules)


@bp.get("/api/estimate")
@login_required
def estimate():
    mode = request.args.get("mode", "text")
    resolution = request.args.get("resolution", "1K")
    count = int(request.args.get("count", "1"))
    try:
        cost = calculate_cost(mode, resolution, count)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "cost": cost, "balance": g.user["points"]})


@bp.get("/image/<int:record_id>")
@login_required
def image_detail(record_id: int):
    record = get_record_for_user(record_id, g.user["id"], is_admin=g.user["role"] == "admin")
    if record is None:
        abort(404)
    return render_template("image_detail.html", record=record)
```

- [ ] **Step 5: Create workspace templates**

Create `templates/workspace.html`:

```html
{% extends "base.html" %}
{% block title %}工作台 - 绘世{% endblock %}
{% block body_class %}workspace-page{% endblock %}
{% block content %}
<main class="workspace-shell">
  <header class="workspace-topbar">
    <a class="workspace-brand" href="/">绘世</a>
    <nav><a href="/pricing">计费</a><a href="/account">余额 {{ g.user["points"] }} 点</a></nav>
  </header>
  <section class="workspace-tools">
    <button>全部状态</button>
    <button>收藏</button>
    <input placeholder="搜索提示词、参数...">
  </section>
  <section class="record-grid">
    {% for record in records %}
    <a class="record-card" href="/image/{{ record['id'] }}">
      <img src="{{ record['image_path'] }}" alt="{{ record['prompt'] }}">
      <div><strong>{{ record["prompt"] }}</strong><span>{{ record["resolution"] }} · {{ record["points_charged"] }} 点</span></div>
    </a>
    {% else %}
    <div class="empty-workspace">还没有生成记录。</div>
    {% endfor %}
  </section>
  <form class="composer" method="post" action="/generate">
    <input name="prompt" placeholder="输入你想生成的画面" required>
    <select name="mode"><option value="text">文生图</option><option value="reference">参考图编辑</option></select>
    <select name="resolution"><option>1K</option><option>2K</option><option>4K</option></select>
    <input name="count" type="number" min="1" max="8" value="1">
    <span id="estimate">预计消耗 - 点</span>
    <button type="submit">生成</button>
  </form>
</main>
{% endblock %}
{% block scripts %}
<script src="{{ url_for('static', filename='js/workspace.js') }}"></script>
{% endblock %}
```

Create `templates/image_detail.html`:

```html
{% extends "base.html" %}
{% block title %}图片详情 - 绘世{% endblock %}
{% block body_class %}workspace-page{% endblock %}
{% block content %}
<main class="detail-shell">
  <section class="detail-image"><img src="{{ record['image_path'] }}" alt="{{ record['prompt'] }}"></section>
  <aside class="detail-panel">
    <a href="/workspace">返回工作台</a>
    <h1>输入内容</h1>
    <p>{{ record["prompt"] }}</p>
    <dl>
      <dt>模式</dt><dd>{{ "文生图" if record["mode"] == "text" else "参考图编辑" }}</dd>
      <dt>尺寸等级</dt><dd>{{ record["resolution"] }}</dd>
      <dt>实际尺寸</dt><dd>{{ record["actual_size"] }}</dd>
      <dt>格式</dt><dd>{{ record["output_format"] }}</dd>
      <dt>消耗</dt><dd>{{ record["points_charged"] }} 点</dd>
      <dt>耗时</dt><dd>{{ "%.1f"|format(record["elapsed_seconds"]) }} 秒</dd>
    </dl>
    <button>复制配置</button>
    <a href="{{ record['image_path'] }}" download>下载图片</a>
  </aside>
</main>
{% endblock %}
```

- [ ] **Step 6: Create workspace JavaScript and CSS**

Create `static/js/workspace.js`:

```javascript
const form = document.querySelector(".composer");
const estimate = document.querySelector("#estimate");

async function refreshEstimate() {
  if (!form || !estimate) return;
  const params = new URLSearchParams(new FormData(form));
  const response = await fetch(`/api/estimate?${params.toString()}`);
  const result = await response.json();
  estimate.textContent = result.ok ? `预计消耗 ${result.cost} 点` : result.error;
}

if (form) {
  form.addEventListener("change", refreshEstimate);
  refreshEstimate();
}
```

Append to `static/css/site.css`:

```css
.workspace-shell { min-height: 100vh; padding: 24px 32px 132px; }
.workspace-topbar { height: 56px; display: flex; align-items: center; justify-content: space-between; }
.workspace-brand { font-weight: 900; }
.workspace-topbar nav { display: flex; gap: 16px; }
.workspace-tools { display: grid; grid-template-columns: auto auto minmax(240px, 1fr); gap: 12px; margin: 24px 0; }
.workspace-tools button, .workspace-tools input { height: 42px; border: 1px solid #e5e7eb; border-radius: 8px; background: #fff; padding: 0 14px; }
.record-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 16px; }
.record-card { overflow: hidden; display: grid; grid-template-columns: 120px 1fr; gap: 12px; align-items: center; border: 1px solid #e5e7eb; border-radius: 8px; background: #fff; color: #111; }
.record-card img { width: 120px; height: 120px; object-fit: cover; background: #eef1f5; }
.record-card div { display: grid; gap: 8px; padding-right: 12px; }
.record-card span { color: #6b7280; font-size: 13px; }
.empty-workspace { padding: 40px; border: 1px dashed #d9dde5; border-radius: 8px; color: #6b7280; }
.composer { position: fixed; left: 50%; bottom: 24px; transform: translateX(-50%); width: min(980px, calc(100vw - 32px)); display: grid; grid-template-columns: minmax(240px, 1fr) 120px 90px 80px 120px 90px; gap: 10px; padding: 14px; border: 1px solid #e5e7eb; border-radius: 8px; background: rgba(255,255,255,.94); box-shadow: 0 18px 60px rgba(17,24,39,.14); backdrop-filter: blur(18px); }
.composer input, .composer select, .composer button { min-width: 0; height: 42px; border: 1px solid #d9dde5; border-radius: 8px; padding: 0 12px; }
.composer button { border: 0; background: #050708; color: #fff; font-weight: 800; }
.detail-shell { min-height: 100vh; display: grid; grid-template-columns: minmax(0, 1fr) 420px; gap: 32px; padding: 28px; }
.detail-image { display: grid; place-items: center; border-radius: 8px; background: #fff; }
.detail-image img { max-width: 100%; max-height: calc(100vh - 56px); object-fit: contain; }
.detail-panel { padding: 24px; border-radius: 8px; background: #fff; }
.detail-panel dl { display: grid; grid-template-columns: 100px 1fr; gap: 12px; }
.detail-panel dt { color: #6b7280; }
```

- [ ] **Step 7: Register workspace blueprint and run tests**

Modify `app.py`:

```python
from huishi.routes_workspace import bp as workspace_bp

# inside create_app after admin blueprint:
app.register_blueprint(workspace_bp)
```

Run:

```powershell
python -m pytest tests/test_auth_records.py -v
```

Expected: PASS.

## Task 6: Image Generation Endpoint With Balance Deduction

**Files:**
- Create: `D:\AI\绘世\huishi\image_api.py`
- Modify: `D:\AI\绘世\huishi\routes_workspace.py`
- Modify: `D:\AI\绘世\tests\test_billing.py`

- [ ] **Step 1: Add a generation billing test using a fake image client**

Append to `tests/test_billing.py`:

```python
def test_successful_generation_creates_record_and_deducts_points(client, app, monkeypatch):
    client.post("/register", data={"username": "genuser", "password": "secret123"}, follow_redirects=True)

    def fake_generate_image(**kwargs):
        return {
            "image_path": "/static/uploads/fake.png",
            "actual_size": "1024x1024",
            "model_source": "fake",
            "elapsed_seconds": 0.1,
        }

    monkeypatch.setattr("huishi.routes_workspace.generate_image", fake_generate_image)
    response = client.post(
        "/generate",
        data={"prompt": "一座发光的城市", "mode": "text", "resolution": "1K", "count": "1"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "一座发光的城市" in text
    assert "19 点" in text
```

- [ ] **Step 2: Run generation test to verify it fails**

Run:

```powershell
python -m pytest tests/test_billing.py::test_successful_generation_creates_record_and_deducts_points -v
```

Expected: FAIL because `/generate` route is missing.

- [ ] **Step 3: Implement image API adapter**

Create `huishi/image_api.py`:

```python
from __future__ import annotations

import time
from pathlib import Path

from flask import current_app


SIZE_MAP = {
    "1K": "1024x1024",
    "2K": "2048x2048",
    "4K": "3840x2160",
}


def generate_image(*, prompt: str, mode: str, resolution: str, count: int) -> dict[str, object]:
    started = time.monotonic()
    output_dir: Path = current_app.config["OUTPUT_DIR"]
    output_dir.mkdir(parents=True, exist_ok=True)
    size = SIZE_MAP.get(resolution, "1024x1024")

    placeholder = output_dir / "demo-generated.svg"
    placeholder.write_text(
        f"""<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024">
<rect width="1024" height="1024" fill="#050708"/>
<text x="80" y="480" fill="#ffffff" font-size="56">绘世</text>
<text x="80" y="560" fill="#8ee7ff" font-size="34">{prompt[:18]}</text>
</svg>""",
        encoding="utf-8",
    )
    return {
        "image_path": "/static/uploads/demo-generated.svg",
        "actual_size": size,
        "model_source": "local-placeholder",
        "elapsed_seconds": time.monotonic() - started,
    }
```

- [ ] **Step 4: Implement `/generate` route**

Append to `huishi/routes_workspace.py`:

```python
from flask import redirect, url_for

from huishi.billing import adjust_points, require_balance
from huishi.image_api import generate_image
from huishi.records import create_record


@bp.post("/generate")
@login_required
def generate():
    prompt = request.form.get("prompt", "").strip()
    mode = request.form.get("mode", "text")
    resolution = request.form.get("resolution", "1K")
    count = int(request.form.get("count", "1"))
    if not prompt:
        return ("提示词不能为空", 400)

    cost = calculate_cost(mode, resolution, count)
    require_balance(g.user["id"], cost)
    result = generate_image(prompt=prompt, mode=mode, resolution=resolution, count=count)
    record_id = create_record(
        user_id=g.user["id"],
        prompt=prompt,
        image_path=str(result["image_path"]),
        mode=mode,
        resolution=resolution,
        actual_size=str(result["actual_size"]),
        quality="auto",
        output_format="png",
        count=count,
        model_source=str(result["model_source"]),
        elapsed_seconds=float(result["elapsed_seconds"]),
        points_charged=cost,
    )
    adjust_points(g.user["id"], -cost, "generation", record_id=record_id)
    get_db().commit()
    return redirect(url_for("workspace.workspace"))
```

- [ ] **Step 5: Run generation test**

Run:

```powershell
python -m pytest tests/test_billing.py::test_successful_generation_creates_record_and_deducts_points -v
```

Expected: PASS.

## Task 7: Pricing Page And Account Ledger

**Files:**
- Create: `D:\AI\绘世\templates\pricing.html`
- Modify: `D:\AI\绘世\templates\account.html`
- Modify: `D:\AI\绘世\app.py`
- Modify: `D:\AI\绘世\tests\test_routes.py`

- [ ] **Step 1: Add pricing page test**

Append to `tests/test_routes.py`:

```python
def test_pricing_page_shows_resolution_rules(client):
    response = client.get("/pricing")
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "1K" in text
    assert "2K" in text
    assert "4K" in text
```

- [ ] **Step 2: Run pricing test to verify it fails**

Run:

```powershell
python -m pytest tests/test_routes.py::test_pricing_page_shows_resolution_rules -v
```

Expected: FAIL because `/pricing` route or template is missing.

- [ ] **Step 3: Implement pricing route and page**

Modify `app.py` to import `get_db` and add route:

```python
from huishi.db import close_db, get_db, init_db

@app.get("/pricing")
def pricing():
    db = get_db()
    rules = db.execute("SELECT * FROM pricing_rules WHERE enabled = 1 ORDER BY mode, resolution").fetchall()
    packages = db.execute("SELECT * FROM packages WHERE enabled = 1 ORDER BY points").fetchall()
    return render_template("pricing.html", rules=rules, packages=packages)
```

Create `templates/pricing.html`:

```html
{% extends "base.html" %}
{% block title %}计费 - 绘世{% endblock %}
{% block body_class %}workspace-page{% endblock %}
{% block content %}
<main class="simple-page">
  <nav class="simple-nav"><a href="/">绘世</a><a href="/workspace">工作台</a></nav>
  <h1>计费标准</h1>
  <p>积分消耗由管理员配置，生成时以后端实时计算为准。</p>
  <section class="pricing-grid">
    {% for rule in rules %}
    <article>
      <strong>{{ "文生图" if rule["mode"] == "text" else "参考图编辑" }} {{ rule["resolution"] }}</strong>
      <p>{{ rule["points_per_image"] }} 点/张</p>
    </article>
    {% endfor %}
  </section>
  <h2>套餐</h2>
  <section class="pricing-grid">
    {% for package in packages %}
    <article>
      <strong>{{ package["name"] }}</strong>
      <p>{{ package["points"] }} 点 · {{ "%.2f"|format(package["price_cents"] / 100) }} 元</p>
      <span>{{ package["description"] }}</span>
    </article>
    {% endfor %}
  </section>
</main>
{% endblock %}
```

Append to `static/css/site.css`:

```css
.pricing-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; margin: 18px 0 38px; }
.pricing-grid article { padding: 20px; border: 1px solid #e5e7eb; border-radius: 8px; background: #fff; }
.pricing-grid p { font-size: 24px; font-weight: 900; }
.pricing-grid span { color: #6b7280; }
```

- [ ] **Step 4: Expand account ledger**

Modify `templates/account.html`:

```html
{% extends "base.html" %}
{% block title %}账户中心 - 绘世{% endblock %}
{% block body_class %}workspace-page{% endblock %}
{% block content %}
<main class="simple-page">
  <nav class="simple-nav"><a href="/">绘世</a><a href="/workspace">工作台</a><a href="/pricing">计费</a><a href="/logout">退出</a></nav>
  <h1>账户中心</h1>
  <p>{{ user["username"] }}，当前余额 {{ user["points"] }} 点。</p>
  <h2>最近流水</h2>
  <div class="table-list">
    {% for item in ledger %}
    <div class="admin-row">
      <strong>{{ item["reason"] }}</strong>
      <span>{{ item["delta"] }} 点</span>
      <span>{{ item["created_at"] }}</span>
      <span>{{ item["admin_note"] }}</span>
    </div>
    {% else %}
    <p>暂无流水。</p>
    {% endfor %}
  </div>
</main>
{% endblock %}
```

Modify `account()` route in `app.py`:

```python
@app.get("/account")
@login_required
def account():
    ledger = get_db().execute(
        "SELECT * FROM point_ledger WHERE user_id = ? ORDER BY id DESC LIMIT 20",
        (g.user["id"],),
    ).fetchall()
    return render_template("account.html", user=g.user, ledger=ledger)
```

- [ ] **Step 5: Run pricing test**

Run:

```powershell
python -m pytest tests/test_routes.py::test_pricing_page_shows_resolution_rules -v
```

Expected: PASS.

## Task 8: Visual Polish, Responsive Checks, And Local Run

**Files:**
- Modify: `D:\AI\绘世\static\css\site.css`
- Create: `D:\AI\绘世\static\js\home.js`
- Modify: `D:\AI\绘世\templates\home.html`
- Create: `D:\AI\绘世\.gitignore`
- Create: `D:\AI\绘世\README.md`

- [ ] **Step 1: Add home motion JavaScript**

Create `static/js/home.js`:

```javascript
const stage = document.querySelector(".hero-stage");
const cards = document.querySelectorAll(".floating-card");

if (stage) {
  stage.addEventListener("pointermove", (event) => {
    const x = event.clientX / window.innerWidth - 0.5;
    const y = event.clientY / window.innerHeight - 0.5;
    cards.forEach((card, index) => {
      const strength = (index + 1) * 12;
      card.style.transform = `translate(${x * strength}px, ${y * strength}px)`;
    });
  });
}
```

Modify `templates/home.html` to load the script:

```html
{% block scripts %}
<script src="{{ url_for('static', filename='js/home.js') }}"></script>
{% endblock %}
```

- [ ] **Step 2: Add project docs and ignore file**

Create `.gitignore`:

```gitignore
.venv/
__pycache__/
.pytest_cache/
data/
static/uploads/*
!static/uploads/.gitkeep
*.pyc
```

Create `README.md`:

```markdown
# 绘世

面向用户使用的 AI 图像创作网站，包含动态首页、生成工作台、图片详情、用户积分和管理员计费配置。

## 启动

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

默认地址：`http://127.0.0.1:8000`

默认管理员：`admin / admin123`
```

Create `static/uploads/.gitkeep` as an empty file.

- [ ] **Step 3: Run the full test suite**

Run:

```powershell
python -m pytest -v
```

Expected: all tests PASS.

- [ ] **Step 4: Start the local server**

Run:

```powershell
python app.py
```

Expected: server listens on `http://127.0.0.1:8000`.

- [ ] **Step 5: Browser verification**

Open `http://127.0.0.1:8000` and verify:

- Home hero shows `造境 / 显影 / 成世`.
- Scrolling reveals 关于绘世 and 联系我们.
- Register creates a user with 20 points.
- Workspace shows estimated cost for 1K / 2K / 4K.
- Admin can change pricing under `/admin/pricing`.
- Pricing page reflects the changed pricing.
- Generating a placeholder image deducts points and creates a detail page.

## Self-Review Notes

- Spec coverage: The plan covers the dynamic home page, workspace, detail page, pricing page, account page, admin pricing/users/packages, user auth, SQLite persistence, configurable 1K/2K/4K billing, balance checks, ledger writes, and record ownership.
- Scope decision: Online payments and production OAuth are intentionally excluded from this MVP, matching the approved design.
- Implementation note: Task 6 initially uses a local placeholder image generator so the product flow can be tested without spending image API credits. After the MVP passes, replace `huishi/image_api.py` internals with the OpenAI-compatible call behavior from `D:\AI\image2`.

