# AI Creation Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a clean AI creation workbench flow with `/workspace`, `/assets`, `/assets/<id>`, recharge wording, role-aware navigation, asset continuation, prompt optimization, batch asset operations, and white/black workspace themes.

**Architecture:** Keep the existing Flask + Jinja + vanilla JS structure. Add small backend helpers for asset filtering, continuation seeds, prompt optimization, app-level settings, and zip downloads while preserving existing generation, billing, auth, upload validation, and pricing behavior.

**Tech Stack:** Flask, SQLite, Jinja templates, vanilla JavaScript, CSS, pytest, stdlib `zipfile`, OpenAI-compatible Python SDK.

---

## Scope Notes

This plan implements the approved design in three working stages:

1. Product structure: routes, navigation, recharge wording, admin-only settings.
2. Creation loop: assets, details, edit-again, regenerate, generation task and failure cards.
3. Enhancements: theme toggle, advanced filters, batch operations, zip download, prompt optimization.

The project directory is not currently a git repository. Treat each task's "Checkpoint" as a manual review point. If a git repository is initialized before implementation, replace each checkpoint with a normal commit.

Reference-image regenerate has one data constraint: old reference records do not contain the original uploaded reference files. New reference generations will persist reference source paths. Existing reference records without source paths must refuse direct regenerate before charging points and offer edit-again instead.

---

## File Structure

### Backend

- Modify `D:\AI\绘世\app.py`
  - Redirect logged-in users from `/` to `/workspace`.
- Modify `D:\AI\绘世\huishi\db.py`
  - Add `ratio` and `reference_paths` columns to `records`.
  - Add an `app_settings` table for admin-global Prompt optimization settings.
  - Add migration helpers for existing databases.
- Modify `D:\AI\绘世\huishi\records.py`
  - Add record listing filters.
  - Add continuation seed helpers.
  - Add bulk record selection helpers.
  - Update `create_record()` to persist `ratio` and reference source paths.
- Modify `D:\AI\绘世\huishi\routes_workspace.py`
  - Replace `/history` with `/assets`.
  - Replace `/image/<id>` with `/assets/<id>`.
  - Add bulk asset routes.
  - Add asset regenerate route.
  - Make `/settings` admin-only.
  - Add `/api/prompt/optimize`.
  - Update generation to save ratio and reference paths.
- Create `D:\AI\绘世\huishi\prompt_api.py`
  - OpenAI-compatible text prompt optimization helper.
- Modify `D:\AI\绘世\huishi\image_api.py`
  - Add helper for local reference file reconstruction only if routes need it; do not change public image generation behavior.

### Templates

- Modify `D:\AI\绘世\templates\partials\studio_nav.html`
  - Remove inspiration and membership wording.
  - Use `/assets`.
  - Show settings/admin only to admins.
  - Add theme toggle button.
- Rename or replace `D:\AI\绘世\templates\history.html` with `D:\AI\绘世\templates\assets.html`
  - Single image asset library.
  - Search, quick filters, advanced filter drawer, batch mode.
- Modify `D:\AI\绘世\templates\workspace.html`
  - Link assets to `/assets`.
  - Add edit seed hydration.
  - Add prompt optimize controls and modal.
  - Add generation task card and failure card containers.
- Rename or replace `D:\AI\绘世\templates\image_detail.html` with `D:\AI\绘世\templates\asset_detail.html`
  - Use `/assets/<id>`.
  - Add complete asset metadata and action forms.
- Modify `D:\AI\绘世\templates\settings.html`
  - Admin-only image API and Prompt optimization settings.
- Modify `D:\AI\绘世\templates\pricing.html`
  - Change user-facing copy from pricing/member language to recharge/integral language.

### Frontend

- Modify `D:\AI\绘世\static\js\workspace.js`
  - Hydrate edit seeds.
  - Add task card and failure card behavior.
  - Add regenerate confirmation and insufficient-points modal handling.
  - Add prompt optimization flow.
- Modify `D:\AI\绘世\static\js\assets.js`
  - Advanced filter drawer.
  - Batch selection.
  - Bulk delete/favorite/download requests.
- Create `D:\AI\绘世\static\js\theme.js`
  - White/black theme toggle persisted to localStorage.
- Modify `D:\AI\绘世\static\css\site.css`
  - Asset library, asset detail, modals, task cards, failure cards, filter drawer, batch mode, themes.

### Tests

- Modify `D:\AI\绘世\tests\test_auth_records.py`
  - Replace history tests with asset route tests.
  - Add admin-only settings tests.
  - Add edit-again seed tests.
  - Add asset detail action tests.
  - Add prompt optimization settings and API tests.
  - Add bulk operation tests.
- Modify `D:\AI\绘世\tests\test_routes.py`
  - Add logged-in `/` redirect test.
  - Update pricing/recharge assertions.
  - Add insufficient-balance JSON assertion if not already covered enough.

---

## Task 1: Database And Record Model Support

**Files:**
- Modify: `D:\AI\绘世\huishi\db.py`
- Modify: `D:\AI\绘世\huishi\records.py`
- Test: `D:\AI\绘世\tests\test_auth_records.py`

- [ ] **Step 1: Write failing tests for record ratio, reference paths, and app settings migration**

Add these tests near the existing record/settings tests in `tests/test_auth_records.py`:

```python
def test_records_store_ratio_and_reference_paths(client, app):
    from huishi.records import create_record, get_record_for_user
    from huishi.db import get_db

    client.post("/register", data={"username": "ratio-user", "password": "secret123"}, follow_redirects=True)
    with app.app_context():
        db = get_db()
        user_id = db.execute("SELECT id FROM users WHERE username = 'ratio-user'").fetchone()["id"]
        record_id = create_record(
            user_id=user_id,
            prompt="ratio prompt",
            image_path="/static/uploads/ratio.png",
            mode="text",
            ratio="9:16",
            resolution="2K",
            actual_size="1440x2560",
            quality="auto",
            output_format="png",
            count=1,
            model_source="test",
            elapsed_seconds=0.2,
            points_charged=2,
            reference_paths=["/static/uploads/ref-a.png"],
        )
        db.commit()
        record = get_record_for_user(record_id, user_id)

    assert record["ratio"] == "9:16"
    assert "/static/uploads/ref-a.png" in record["reference_paths"]


def test_app_settings_table_exists(client, app):
    client.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=True)
    with app.app_context():
        from huishi.db import get_db

        get_db().execute(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES ('prompt_model', 'gpt-4.1-mini', '2026-06-04T00:00:00+00:00')
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """
        )
        saved = get_db().execute("SELECT value FROM app_settings WHERE key = 'prompt_model'").fetchone()

    assert saved["value"] == "gpt-4.1-mini"
```

- [ ] **Step 2: Run the new tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_auth_records.py::test_records_store_ratio_and_reference_paths tests/test_auth_records.py::test_app_settings_table_exists -v
```

Expected: both tests fail because `ratio`, `reference_paths`, or `app_settings` do not exist.

- [ ] **Step 3: Add schema and migration support**

In `huishi/db.py`, update the `records` table definition inside `SCHEMA`:

```sql
  ratio TEXT NOT NULL DEFAULT '16:9',
  reference_paths TEXT NOT NULL DEFAULT '[]',
```

Place `ratio` after `mode`, and `reference_paths` after `points_charged`.

Add this table to `SCHEMA`:

```sql
CREATE TABLE IF NOT EXISTS app_settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL
);
```

Update `init_db()`:

```python
def init_db() -> None:
    db = get_db()
    db.executescript(SCHEMA)
    migrate_users_table(db)
    migrate_records_table(db)
    seed_defaults(db)
    db.commit()
```

Add:

```python
def migrate_records_table(db: sqlite3.Connection) -> None:
    columns = {row["name"] for row in db.execute("PRAGMA table_info(records)").fetchall()}
    migrations = {
        "ratio": "ALTER TABLE records ADD COLUMN ratio TEXT NOT NULL DEFAULT '16:9'",
        "reference_paths": "ALTER TABLE records ADD COLUMN reference_paths TEXT NOT NULL DEFAULT '[]'",
    }
    for column, statement in migrations.items():
        if column not in columns:
            db.execute(statement)
```

- [ ] **Step 4: Update record creation and helpers**

In `huishi/records.py`, import JSON:

```python
import json
```

Update `create_record()` signature:

```python
def create_record(
    *,
    user_id: int,
    prompt: str,
    image_path: str,
    mode: str,
    ratio: str,
    resolution: str,
    actual_size: str,
    quality: str,
    output_format: str,
    count: int,
    model_source: str,
    elapsed_seconds: float,
    points_charged: int,
    reference_paths: list[str] | None = None,
) -> int:
```

Update the insert statement:

```python
        INSERT INTO records
        (user_id, prompt, image_path, mode, ratio, resolution, actual_size, quality, output_format, count, model_source, elapsed_seconds, points_charged, reference_paths, favorite, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
```

Update values:

```python
            user_id,
            prompt,
            image_path,
            mode,
            ratio,
            resolution,
            actual_size,
            quality,
            output_format,
            count,
            model_source,
            elapsed_seconds,
            points_charged,
            json.dumps(reference_paths or [], ensure_ascii=False),
            utc_now(),
```

Add helper functions:

```python
def parse_reference_paths(record) -> list[str]:
    try:
        value = json.loads(record["reference_paths"] or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str)]


def infer_ratio_from_size(actual_size: str) -> str:
    try:
        width_raw, height_raw = actual_size.lower().split("x", 1)
        width = int(width_raw)
        height = int(height_raw)
    except (AttributeError, ValueError):
        return "16:9"
    known = {
        (1024, 1024): "1:1",
        (2048, 2048): "1:1",
        (1536, 864): "16:9",
        (2560, 1440): "16:9",
        (3840, 2160): "16:9",
        (864, 1536): "9:16",
        (1440, 2560): "9:16",
        (2160, 3840): "9:16",
        (1536, 1024): "3:2",
        (2160, 1440): "3:2",
        (1024, 1536): "2:3",
        (1440, 2160): "2:3",
    }
    return known.get((width, height), "16:9")


def record_generation_seed(record) -> dict[str, object]:
    return {
        "id": record["id"],
        "prompt": record["prompt"],
        "mode": record["mode"],
        "ratio": record["ratio"] or infer_ratio_from_size(record["actual_size"]),
        "resolution": record["resolution"],
        "quality": record["quality"],
        "output_format": record["output_format"],
        "count": record["count"],
        "reference_paths": parse_reference_paths(record),
    }
```

- [ ] **Step 5: Update generation route call sites**

In `huishi/routes_workspace.py`, update `create_record(...)` in `generate()` to pass:

```python
        ratio=ratio,
        reference_paths=[],
```

This minimal value will be replaced with real persisted reference paths in a later task.

- [ ] **Step 6: Run tests**

Run:

```powershell
python -m pytest tests/test_auth_records.py::test_records_store_ratio_and_reference_paths tests/test_auth_records.py::test_app_settings_table_exists -v
```

Expected: both tests pass.

- [ ] **Checkpoint**

Record that database migrations and record helpers are complete. If using git, commit with:

```powershell
git add huishi/db.py huishi/records.py huishi/routes_workspace.py tests/test_auth_records.py
git commit -m "feat: add asset record metadata"
```

---

## Task 2: Product Routes, Navigation, Recharge Copy, And Admin Settings Access

**Files:**
- Modify: `D:\AI\绘世\app.py`
- Modify: `D:\AI\绘世\huishi\routes_workspace.py`
- Modify: `D:\AI\绘世\templates\partials\studio_nav.html`
- Modify: `D:\AI\绘世\templates\settings.html`
- Modify: `D:\AI\绘世\templates\pricing.html`
- Test: `D:\AI\绘世\tests\test_auth_records.py`
- Test: `D:\AI\绘世\tests\test_routes.py`

- [ ] **Step 1: Write failing route and navigation tests**

Replace the existing shared navigation/history assertions with:

```python
def test_workspace_and_assets_share_clean_studio_navigation(client):
    client.post("/register", data={"username": "sharednav", "password": "secret123"}, follow_redirects=True)

    workspace = client.get("/workspace").get_data(as_text=True)
    assets = client.get("/assets").get_data(as_text=True)

    for text in (workspace, assets):
        assert 'aria-label="主导航"' in text
        assert "生成" in text
        assert "资产" in text
        assert "充值" in text
        assert "账号" in text
        assert "灵感" not in text
        assert "会员" not in text
        assert "设置" not in text
        assert "/history" not in text


def test_admin_navigation_shows_management_and_settings(client):
    client.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=True)

    text = client.get("/workspace").get_data(as_text=True)

    assert "管理" in text
    assert "设置" in text
    assert "/settings" in text


def test_history_route_is_not_an_asset_entry(client):
    client.post("/register", data={"username": "nohistory", "password": "secret123"}, follow_redirects=True)

    response = client.get("/history")

    assert response.status_code == 404


def test_regular_user_cannot_access_settings(client):
    client.post("/register", data={"username": "nosettings", "password": "secret123"}, follow_redirects=True)

    response = client.get("/settings")

    assert response.status_code == 403
```

In `tests/test_routes.py`, add:

```python
def test_logged_in_home_redirects_to_workspace(client):
    client.post("/register", data={"username": "homegoesworkspace", "password": "secret123"}, follow_redirects=True)

    response = client.get("/", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/workspace")


def test_recharge_page_uses_recharge_wording(client):
    response = client.get("/pricing")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "充值" in text
    assert "会员" not in text
```

- [ ] **Step 2: Run route tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_auth_records.py::test_workspace_and_assets_share_clean_studio_navigation tests/test_auth_records.py::test_admin_navigation_shows_management_and_settings tests/test_auth_records.py::test_history_route_is_not_an_asset_entry tests/test_auth_records.py::test_regular_user_cannot_access_settings tests/test_routes.py::test_logged_in_home_redirects_to_workspace tests/test_routes.py::test_recharge_page_uses_recharge_wording -v
```

Expected: failures because `/assets` is not the canonical route, `/history` still exists, settings are not admin-only, and navigation still contains old copy.

- [ ] **Step 3: Redirect logged-in users from home**

In `app.py`, ensure `redirect` and `url_for` are imported:

```python
from flask import Flask, abort, g, jsonify, redirect, render_template, send_from_directory, url_for
```

At the start of `home()`:

```python
        if g.user is not None:
            return redirect(url_for("workspace.workspace"))
```

- [ ] **Step 4: Replace `/history` with `/assets`**

In `huishi/routes_workspace.py`, remove the `/history` route and add:

```python
@bp.get("/assets")
@login_required
def assets():
    records = list_records_for_user(g.user["id"])
    return render_template("assets.html", records=records)
```

- [ ] **Step 5: Make settings admin-only**

At the top of `settings()` in `huishi/routes_workspace.py`, add:

```python
    if g.user["role"] != "admin":
        abort(403)
```

- [ ] **Step 6: Update navigation partial**

Replace `templates/partials/studio_nav.html` content with a clean version:

```jinja
<aside class="studio-rail" aria-label="主导航">
  <a class="rail-logo" href="/" aria-label="绘世首页">绘</a>
  <nav class="rail-nav" aria-label="创作导航">
    <a class="{{ 'is-active' if active_nav == 'generate' else '' }}" href="/workspace"><span>生成</span></a>
    <a class="{{ 'is-active' if active_nav == 'assets' else '' }}" href="/assets"><span>资产</span></a>
    <a class="{{ 'is-active' if active_nav == 'recharge' else '' }}" href="/pricing"><span>充值</span></a>
    <a class="{{ 'is-active' if active_nav == 'account' else '' }}" href="/account"><span>账号</span></a>
    {% if g.user["role"] == "admin" %}
    <a href="/admin/"><span>管理</span></a>
    <a class="{{ 'is-active' if active_nav == 'settings' else '' }}" href="/settings"><span>设置</span></a>
    {% endif %}
  </nav>
  <div class="rail-footer">
    <button class="theme-toggle" type="button" data-theme-toggle aria-label="切换黑白主题">◐</button>
    <a href="/account">{{ g.user["points"] }} 点</a>
  </div>
</aside>

<aside class="studio-sidebar">
  <header class="sidebar-header">
    <strong>开启创作</strong>
    <a class="sidebar-icon-button" href="/workspace" aria-label="新创作">+</a>
  </header>
  <a class="conversation-entry is-pinned" href="/workspace">
    <span class="conversation-thumb">绘</span>
    <span>默认创作</span>
  </a>
  <div class="sidebar-section-title">最近</div>
  <nav class="work-folder-list" aria-label="最近创作">
    {% for record in records[:12] %}
    <a class="{{ 'active' if loop.first and active_nav != 'assets' else '' }}" href="/assets/{{ record['id'] }}">
      <img src="{{ record['image_path'] }}" alt="">
      <span>{{ record["prompt"] }}</span>
    </a>
    {% else %}
    <span class="sidebar-empty">暂无创作记录</span>
    {% endfor %}
  </nav>
</aside>
```

- [ ] **Step 7: Create `assets.html` and remove old categories**

Create `templates/assets.html` from the current `history.html`, but use:

```jinja
{% extends "base.html" %}
{% block title %}资产库 - 绘世{% endblock %}
{% block body_class %}workspace-page{% endblock %}
{% block content %}
<main class="studio-shell assets-shell" data-studio-theme="workspace">
  {% set active_nav = "assets" %}
  {% include "partials/studio_nav.html" %}
  <section class="studio-main assets-main">
    <header class="asset-topbar">
      <h1>资产库</h1>
      <div class="asset-actions">
        <label class="asset-search"><span>⌕</span><input id="asset-search" type="search" placeholder="搜索提示词"></label>
        <button type="button" data-filter-open>筛选</button>
        <button type="button" data-batch-toggle>批量操作</button>
      </div>
    </header>
    <nav class="asset-subtabs" aria-label="图片筛选">
      <button type="button" class="is-active" data-quick-filter="all">全部</button>
      <button type="button" data-quick-filter="favorite">收藏</button>
    </nav>
    <section class="asset-date-group">
      <div class="asset-grid asset-library">
        {% for record in records %}
        <a class="asset-tile" href="/assets/{{ record['id'] }}" data-prompt="{{ record['prompt'] }}" data-resolution="{{ record['resolution'] }}" data-favorite="{{ record['favorite'] }}" data-mode="{{ record['mode'] }}" data-ratio="{{ record['ratio'] }}">
          <img src="{{ record['image_path'] }}" alt="{{ record['prompt'] }}">
          <span class="asset-tile-action">收藏 / 更多</span>
        </a>
        {% else %}
        <div class="empty-workspace">暂无图片资产</div>
        {% endfor %}
      </div>
    </section>
  </section>
</main>
{% endblock %}
{% block scripts %}
<script src="{{ url_for('static', filename='js/theme.js') }}"></script>
<script src="{{ url_for('static', filename='js/assets.js') }}"></script>
{% endblock %}
```

Remove or stop referencing `templates/history.html`.

- [ ] **Step 8: Update workspace and settings links**

In `templates/workspace.html`, replace:

```jinja
href="/history"
href="/image/{{ current_record['id'] }}"
href="/image/{{ record['id'] }}"
```

with:

```jinja
href="/assets"
href="/assets/{{ current_record['id'] }}"
href="/assets/{{ record['id'] }}"
```

In `templates/settings.html`, replace old simple nav with admin-safe links:

```jinja
<nav class="simple-nav"><a href="/workspace">工作台</a><a href="/assets">资产</a><a href="/account">账号</a></nav>
```

- [ ] **Step 9: Update pricing copy**

In `templates/pricing.html`, set:

```jinja
{% block title %}充值 - 绘世{% endblock %}
```

Change the hero text to include:

```jinja
<span>RECHARGE</span>
<h1>充值积分</h1>
<p>按清晰度和生成数量消耗积分。实际扣费以后端实时规则为准，管理员可在后台调整。</p>
```

- [ ] **Step 10: Run tests**

Run the route test command from Step 2 again.

Expected: all listed tests pass.

- [ ] **Checkpoint**

Review `/workspace`, `/assets`, `/pricing`, and `/settings` manually in the browser for link correctness.

---

## Task 3: Asset Detail Route And Asset Actions

**Files:**
- Modify: `D:\AI\绘世\huishi\routes_workspace.py`
- Create: `D:\AI\绘世\templates\asset_detail.html`
- Modify: `D:\AI\绘世\templates\workspace.html`
- Modify: `D:\AI\绘世\templates\assets.html`
- Test: `D:\AI\绘世\tests\test_auth_records.py`

- [ ] **Step 1: Write failing asset detail tests**

Add:

```python
def test_asset_detail_uses_asset_route_and_full_metadata(client, app):
    from huishi.db import get_db, utc_now

    client.post("/register", data={"username": "asset-detail-user", "password": "secret123"}, follow_redirects=True)
    with app.app_context():
        db = get_db()
        user_id = db.execute("SELECT id FROM users WHERE username = 'asset-detail-user'").fetchone()["id"]
        db.execute(
            """
            INSERT INTO records
            (user_id, prompt, image_path, mode, ratio, resolution, actual_size, quality, output_format, count, model_source, elapsed_seconds, points_charged, reference_paths, favorite, created_at)
            VALUES (?, '资产详情提示词', '/static/uploads/detail.png', 'text', '1:1', '2K', '2048x2048', 'auto', 'png', 1, 'demo', 1.2, 2, '[]', 0, ?)
            """,
            (user_id, utc_now()),
        )
        db.commit()

    response = client.get("/assets/1")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "资产详情提示词" in text
    assert "1:1" in text
    assert "2K" in text
    assert "2048x2048" in text
    assert "再次编辑" in text
    assert "再次生成" in text
    assert "/assets" in text


def test_old_image_detail_route_is_not_public_entry(client, app):
    from huishi.db import get_db, utc_now

    client.post("/register", data={"username": "old-image-route", "password": "secret123"}, follow_redirects=True)
    with app.app_context():
        db = get_db()
        user_id = db.execute("SELECT id FROM users WHERE username = 'old-image-route'").fetchone()["id"]
        db.execute(
            """
            INSERT INTO records
            (user_id, prompt, image_path, mode, ratio, resolution, actual_size, quality, output_format, count, model_source, elapsed_seconds, points_charged, reference_paths, favorite, created_at)
            VALUES (?, '旧详情路径', '/static/uploads/old.png', 'text', '16:9', '1K', '1536x864', 'auto', 'png', 1, 'demo', 1.2, 1, '[]', 0, ?)
            """,
            (user_id, utc_now()),
        )
        db.commit()

    assert client.get("/image/1").status_code == 404
```

- [ ] **Step 2: Run and verify failure**

Run:

```powershell
python -m pytest tests/test_auth_records.py::test_asset_detail_uses_asset_route_and_full_metadata tests/test_auth_records.py::test_old_image_detail_route_is_not_public_entry -v
```

Expected: failures until `/assets/<id>` exists and `/image/<id>` is removed.

- [ ] **Step 3: Replace detail route**

In `huishi/routes_workspace.py`, remove:

```python
@bp.get("/image/<int:record_id>")
```

Add:

```python
@bp.get("/assets/<int:record_id>")
@login_required
def asset_detail(record_id: int):
    record = get_record_for_user(record_id, g.user["id"], is_admin=g.user["role"] == "admin")
    if record is None:
        abort(404)
    return render_template("asset_detail.html", record=record)
```

- [ ] **Step 4: Update favorite and delete routes**

Change routes:

```python
@bp.post("/assets/<int:record_id>/favorite")
@login_required
def toggle_favorite(record_id: int):
    record = get_record_for_user(record_id, g.user["id"], is_admin=g.user["role"] == "admin")
    if record is None:
        abort(404)
    next_value = 0 if record["favorite"] else 1
    get_db().execute("UPDATE records SET favorite = ? WHERE id = ?", (next_value, record_id))
    get_db().commit()
    if wants_json():
        return jsonify({"ok": True, "favorite": next_value})
    return redirect(url_for("workspace.asset_detail", record_id=record_id))


@bp.post("/assets/<int:record_id>/delete")
@login_required
def delete_record(record_id: int):
    record = get_record_for_user(record_id, g.user["id"], is_admin=g.user["role"] == "admin")
    if record is None:
        abort(404)
    image_path = str(record["image_path"])
    get_db().execute("DELETE FROM records WHERE id = ?", (record_id,))
    get_db().commit()
    delete_local_upload(image_path)
    if wants_json():
        return jsonify({"ok": True})
    return redirect(url_for("workspace.assets"))
```

- [ ] **Step 5: Create asset detail template**

Create `templates/asset_detail.html`:

```jinja
{% extends "base.html" %}
{% block title %}资产详情 - 绘世{% endblock %}
{% block body_class %}workspace-page{% endblock %}
{% block content %}
<main class="detail-shell asset-detail-shell" data-studio-theme="workspace">
  <section class="detail-image"><img src="{{ record['image_path'] }}" alt="{{ record['prompt'] }}"></section>
  <aside class="detail-panel">
    <a href="/assets">返回资产库</a>
    <h1>资产详情</h1>
    <p>{{ record["prompt"] }}</p>
    <dl>
      <dt>模式</dt><dd>{{ "文生图" if record["mode"] == "text" else "参考图生成" }}</dd>
      <dt>比例</dt><dd>{{ record["ratio"] }}</dd>
      <dt>清晰度</dt><dd>{{ record["resolution"] }}</dd>
      <dt>实际尺寸</dt><dd>{{ record["actual_size"] }}</dd>
      <dt>格式</dt><dd>{{ record["output_format"] }}</dd>
      <dt>消耗积分</dt><dd>{{ record["points_charged"] }} 点</dd>
      <dt>生成时间</dt><dd>{{ record["created_at"] }}</dd>
      <dt>耗时</dt><dd>{{ "%.1f"|format(record["elapsed_seconds"]) }} 秒</dd>
    </dl>
    <div class="detail-actions">
      <a class="button-link" href="/workspace?edit_record={{ record['id'] }}">再次编辑</a>
      <button type="button" data-regenerate-asset="{{ record['id'] }}" data-cost="{{ record['points_charged'] }}">再次生成</button>
      <a href="{{ record['image_path'] }}" download>下载</a>
    </div>
    <form method="post" action="/assets/{{ record['id'] }}/favorite">
      <button type="submit">{{ "取消收藏" if record["favorite"] else "收藏" }}</button>
    </form>
    <form method="post" action="/assets/{{ record['id'] }}/delete" data-confirm-delete="删除后不可恢复，确认删除这张图片？">
      <button type="submit" class="danger-button">删除</button>
    </form>
  </aside>
</main>
{% endblock %}
{% block scripts %}
<script src="{{ url_for('static', filename='js/theme.js') }}"></script>
<script src="{{ url_for('static', filename='js/workspace.js') }}"></script>
{% endblock %}
```

- [ ] **Step 6: Run tests**

Run Step 2 command again.

Expected: both tests pass.

- [ ] **Checkpoint**

Open `/assets/<id>` for a test record and confirm it shows asset details, not the old image detail language.

---

## Task 4: Workspace Edit-Again Seeds

**Files:**
- Modify: `D:\AI\绘世\huishi\routes_workspace.py`
- Modify: `D:\AI\绘世\templates\workspace.html`
- Modify: `D:\AI\绘世\templates\assets.html`
- Modify: `D:\AI\绘世\static\js\workspace.js`
- Test: `D:\AI\绘世\tests\test_auth_records.py`

- [ ] **Step 1: Write failing edit seed test**

Add:

```python
def test_workspace_edit_record_prefills_original_prompt_and_parameters(client, app):
    from huishi.db import get_db, utc_now

    client.post("/register", data={"username": "editseed", "password": "secret123"}, follow_redirects=True)
    with app.app_context():
        db = get_db()
        user_id = db.execute("SELECT id FROM users WHERE username = 'editseed'").fetchone()["id"]
        db.execute(
            """
            INSERT INTO records
            (user_id, prompt, image_path, mode, ratio, resolution, actual_size, quality, output_format, count, model_source, elapsed_seconds, points_charged, reference_paths, favorite, created_at)
            VALUES (?, '继续编辑这张图', '/static/uploads/editseed.png', 'text', '3:2', '2K', '2160x1440', 'auto', 'webp', 2, 'demo', 1.2, 4, '[]', 0, ?)
            """,
            (user_id, utc_now()),
        )
        db.commit()

    response = client.get("/workspace?edit_record=1")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'data-edit-seed=' in text
    assert "继续编辑这张图" in text
    assert '"ratio": "3:2"' in text
    assert '"resolution": "2K"' in text
    assert '"count": 2' in text
```

- [ ] **Step 2: Run and verify failure**

Run:

```powershell
python -m pytest tests/test_auth_records.py::test_workspace_edit_record_prefills_original_prompt_and_parameters -v
```

Expected: failure because no edit seed is passed.

- [ ] **Step 3: Pass seed from route**

In `huishi/routes_workspace.py`, import:

```python
from huishi.records import create_record, get_record_for_user, list_records_for_user, record_generation_seed
```

Update `workspace()`:

```python
@bp.get("/workspace")
@login_required
def workspace():
    records = list_records_for_user(g.user["id"])
    current_record = records[0] if records else None
    edit_seed = None
    raw_edit_record = request.args.get("edit_record", "").strip()
    if raw_edit_record:
        try:
            edit_record_id = int(raw_edit_record)
        except ValueError:
            abort(404)
        edit_record = get_record_for_user(edit_record_id, g.user["id"], is_admin=g.user["role"] == "admin")
        if edit_record is None:
            abort(404)
        edit_seed = record_generation_seed(edit_record)
    return render_template(
        "workspace.html",
        records=records,
        current_record=current_record,
        edit_seed=edit_seed,
    )
```

- [ ] **Step 4: Add seed JSON to workspace template**

At the root `<main>` in `workspace.html`, add:

```jinja
data-edit-seed='{{ edit_seed|tojson if edit_seed else "" }}'
```

The opening tag becomes:

```jinja
<main class="studio-shell" data-studio-theme="workspace" data-edit-seed='{{ edit_seed|tojson if edit_seed else "" }}'>
```

Update composer values:

```jinja
<textarea class="composer-prompt" name="prompt" rows="3" placeholder="输入你想生成的画面" required>{{ edit_seed.prompt if edit_seed else "" }}</textarea>
<input type="hidden" name="mode" id="mode" value="{{ edit_seed.mode if edit_seed else 'text' }}">
<input type="hidden" name="ratio" id="ratio" value="{{ edit_seed.ratio if edit_seed else '9:16' }}">
<input type="hidden" name="resolution" id="resolution" value="{{ edit_seed.resolution if edit_seed else '2K' }}">
<input type="hidden" name="quality" id="quality" value="{{ edit_seed.quality if edit_seed else 'auto' }}">
<input type="hidden" name="output_format" id="output-format" value="{{ edit_seed.output_format if edit_seed else 'png' }}">
```

Update count:

```jinja
<label class="count-field"><span>数量</span><input name="count" type="number" min="1" max="8" value="{{ edit_seed.count if edit_seed else 1 }}"></label>
```

- [ ] **Step 5: Hydrate seed in JS**

In `static/js/workspace.js`, add:

```javascript
const studioShell = document.querySelector(".studio-shell");

function getEditSeed() {
  const raw = studioShell?.dataset.editSeed || "";
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch (error) {
    return null;
  }
}

function applySeedToComposer(seed) {
  if (!form || !seed) return;
  const promptInput = form.querySelector('[name="prompt"]');
  const countInput = form.querySelector('[name="count"]');
  if (promptInput) promptInput.value = seed.prompt || "";
  if (modeInput) modeInput.value = seed.mode || "text";
  if (ratioInput) ratioInput.value = seed.ratio || "9:16";
  if (resolutionInput) resolutionInput.value = seed.resolution || "2K";
  if (countInput) countInput.value = seed.count || 1;
  syncReferenceField();
  syncResolutionOptions();
  refreshEstimate();
}
```

Before final initialization ends:

```javascript
applySeedToComposer(getEditSeed());
```

- [ ] **Step 6: Update asset edit links**

In `assets.html`, ensure each card has:

```jinja
<a class="asset-edit-action" href="/workspace?edit_record={{ record['id'] }}">再次编辑</a>
```

If the whole card is already an anchor, place the edit action in an overlay container and use a button/link pattern that does not nest anchors.

- [ ] **Step 7: Run tests**

Run Step 2 command again.

Expected: test passes.

- [ ] **Checkpoint**

Open `/workspace?edit_record=<id>` and confirm the composer contains the original prompt, ratio, resolution, and count.

---

## Task 5: Asset Regenerate Endpoint And Confirmation Contract

**Files:**
- Modify: `D:\AI\绘世\huishi\routes_workspace.py`
- Modify: `D:\AI\绘世\huishi\records.py`
- Modify: `D:\AI\绘世\templates\asset_detail.html`
- Modify: `D:\AI\绘世\static\js\workspace.js`
- Test: `D:\AI\绘世\tests\test_auth_records.py`

- [ ] **Step 1: Write failing regenerate tests**

Add:

```python
def test_asset_regenerate_creates_new_record_after_balance_check(client, app, monkeypatch):
    from huishi.db import get_db, utc_now

    client.post("/register", data={"username": "regenuser", "password": "secret123"}, follow_redirects=True)
    with app.app_context():
        db = get_db()
        user_id = db.execute("SELECT id FROM users WHERE username = 'regenuser'").fetchone()["id"]
        db.execute("UPDATE users SET points = 20 WHERE id = ?", (user_id,))
        db.execute(
            """
            INSERT INTO records
            (user_id, prompt, image_path, mode, ratio, resolution, actual_size, quality, output_format, count, model_source, elapsed_seconds, points_charged, reference_paths, favorite, created_at)
            VALUES (?, '再次生成提示词', '/static/uploads/original.png', 'text', '16:9', '1K', '1536x864', 'auto', 'png', 1, 'demo', 1.2, 1, '[]', 0, ?)
            """,
            (user_id, utc_now()),
        )
        db.commit()

    def fake_generate_image(**kwargs):
        assert kwargs["prompt"] == "再次生成提示词"
        assert kwargs["ratio"] == "16:9"
        assert kwargs["resolution"] == "1K"
        return {
            "image_path": "/static/uploads/regenerated.png",
            "actual_size": "1536x864",
            "model_source": "fake",
            "elapsed_seconds": 0.1,
        }

    monkeypatch.setattr("huishi.routes_workspace.generate_image", fake_generate_image)
    response = client.post(
        "/assets/1/regenerate",
        headers={"X-Requested-With": "fetch", "Accept": "application/json"},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["record"]["prompt"] == "再次生成提示词"
    assert payload["balance"] == 19


def test_asset_regenerate_refuses_reference_without_saved_sources(client, app, monkeypatch):
    from huishi.db import get_db, utc_now

    client.post("/register", data={"username": "oldrefregen", "password": "secret123"}, follow_redirects=True)
    with app.app_context():
        db = get_db()
        user_id = db.execute("SELECT id FROM users WHERE username = 'oldrefregen'").fetchone()["id"]
        db.execute("UPDATE users SET points = 20 WHERE id = ?", (user_id,))
        db.execute(
            """
            INSERT INTO records
            (user_id, prompt, image_path, mode, ratio, resolution, actual_size, quality, output_format, count, model_source, elapsed_seconds, points_charged, reference_paths, favorite, created_at)
            VALUES (?, '旧参考图', '/static/uploads/ref.png', 'reference', '9:16', '1K', '864x1536', 'auto', 'png', 1, 'demo', 1.2, 2, '[]', 0, ?)
            """,
            (user_id, utc_now()),
        )
        db.commit()

    monkeypatch.setattr("huishi.routes_workspace.generate_image", lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not call API")))
    response = client.post(
        "/assets/1/regenerate",
        headers={"X-Requested-With": "fetch", "Accept": "application/json"},
    )

    assert response.status_code == 400
    assert "重新上传参考图" in response.get_json()["error"]
```

- [ ] **Step 2: Run and verify failure**

Run:

```powershell
python -m pytest tests/test_auth_records.py::test_asset_regenerate_creates_new_record_after_balance_check tests/test_auth_records.py::test_asset_regenerate_refuses_reference_without_saved_sources -v
```

Expected: failure because route does not exist.

- [ ] **Step 3: Add regenerate route**

In `huishi/routes_workspace.py`, add:

```python
@bp.post("/assets/<int:record_id>/regenerate")
@login_required
def regenerate_asset(record_id: int):
    record = get_record_for_user(record_id, g.user["id"], is_admin=g.user["role"] == "admin")
    if record is None:
        abort(404)
    seed = record_generation_seed(record)
    reference_paths = seed["reference_paths"]
    if seed["mode"] == "reference" and not reference_paths:
        return generation_error("旧参考图作品需要回到工作台重新上传参考图后再生成", 400)

    try:
        count = int(seed["count"])
        cost = calculate_cost(str(seed["mode"]), str(seed["resolution"]), count)
        require_balance(g.user["id"], cost)
    except ValueError as exc:
        return generation_error(str(exc), 400)

    try:
        result = generate_image(
            prompt=str(seed["prompt"]),
            mode=str(seed["mode"]),
            ratio=str(seed["ratio"]),
            resolution=str(seed["resolution"]),
            count=count,
            api_key=current_app.config.get("DEFAULT_API_KEY", ""),
            base_url=current_app.config.get("DEFAULT_BASE_URL", ""),
            quality=str(seed["quality"]),
            output_format=str(seed["output_format"]),
            reference_images=[],
        )
    except Exception as exc:
        return generation_error(f"生成失败：{exc}", 502)

    new_record_id = create_record(
        user_id=g.user["id"],
        prompt=str(seed["prompt"]),
        image_path=str(result["image_path"]),
        mode=str(seed["mode"]),
        ratio=str(seed["ratio"]),
        resolution=str(seed["resolution"]),
        actual_size=str(result["actual_size"]),
        quality=str(seed["quality"]),
        output_format=str(seed["output_format"]),
        count=count,
        model_source=str(result["model_source"]),
        elapsed_seconds=float(result["elapsed_seconds"]),
        points_charged=cost,
        reference_paths=list(reference_paths),
    )
    adjust_points(g.user["id"], -cost, "generation", record_id=new_record_id)
    get_db().commit()
    new_record = get_record_for_user(new_record_id, g.user["id"])
    return jsonify({"ok": True, "record": serialize_record(new_record), "balance": g.user["points"] - cost})
```

In this task, reference records with saved source paths are not reconstructed yet; Task 6 persists and reconstructs them.

- [ ] **Step 4: Add client-side confirmation contract**

In `static/js/workspace.js`, add:

```javascript
const REGENERATE_SKIP_KEY = "huishi.skipRegenerateConfirm";

function shouldConfirmRegenerate() {
  return localStorage.getItem(REGENERATE_SKIP_KEY) !== "1";
}

function setSkipRegenerateConfirm(skip) {
  localStorage.setItem(REGENERATE_SKIP_KEY, skip ? "1" : "0");
}

async function confirmRegenerate(cost) {
  if (!shouldConfirmRegenerate()) return true;
  const accepted = window.confirm(`再次生成预计消耗 ${cost || "-"} 点积分，确认继续？`);
  return accepted;
}

async function bindAssetRegenerateButtons() {
  document.querySelectorAll("[data-regenerate-asset]").forEach((button) => {
    button.addEventListener("click", async () => {
      const id = button.dataset.regenerateAsset;
      const cost = button.dataset.cost;
      if (!(await confirmRegenerate(cost))) return;
      const response = await fetch(`/assets/${id}/regenerate`, {
        method: "POST",
        headers: { "X-Requested-With": "fetch", "Accept": "application/json" },
      });
      const result = await response.json();
      if (!response.ok || !result.ok) {
        setStatus(result.error || "再次生成失败", true);
        return;
      }
      window.location.href = `/assets/${result.record.id}`;
    });
  });
}
```

Call:

```javascript
bindAssetRegenerateButtons();
```

This starts with `window.confirm`. Replace it with the designed custom modal in Task 10.

- [ ] **Step 5: Run tests**

Run Step 2 command again.

Expected: both tests pass.

- [ ] **Checkpoint**

Confirm `/assets/<id>` direct regenerate creates a new text record and refuses old reference records before charging.

---

## Task 6: Persist Reference Source Images For New Reference Generations

**Files:**
- Modify: `D:\AI\绘世\huishi\routes_workspace.py`
- Modify: `D:\AI\绘世\image_api.py`
- Test: `D:\AI\绘世\tests\test_routes.py`

- [ ] **Step 1: Write failing reference persistence test**

Add to `tests/test_routes.py`:

```python
def test_reference_generation_persists_reference_paths(client, app, monkeypatch):
    from io import BytesIO

    client.post("/register", data={"username": "persistref", "password": "secret123"}, follow_redirects=True)

    def fake_generate_image(**kwargs):
        references = kwargs["reference_images"]
        assert len(references) == 1
        return {
            "image_path": "/static/uploads/reference-result.png",
            "actual_size": "864x1536",
            "model_source": "fake",
            "elapsed_seconds": 0.1,
        }

    monkeypatch.setattr("huishi.routes_workspace.generate_image", fake_generate_image)
    response = client.post(
        "/generate",
        data={
            "prompt": "参考图保存",
            "mode": "reference",
            "resolution": "1K",
            "ratio": "9:16",
            "count": "1",
            "reference_images": (BytesIO(b"\x89PNG\r\n\x1a\nfake"), "ref.png"),
        },
        content_type="multipart/form-data",
        headers={"X-Requested-With": "fetch", "Accept": "application/json"},
    )

    assert response.status_code == 200
    with app.app_context():
        from huishi.db import get_db

        record = get_db().execute("SELECT * FROM records WHERE prompt = '参考图保存'").fetchone()
    assert record["ratio"] == "9:16"
    assert "/static/uploads/" in record["reference_paths"]
    assert "ref" in record["reference_paths"]
```

- [ ] **Step 2: Run and verify failure**

Run:

```powershell
python -m pytest tests/test_routes.py::test_reference_generation_persists_reference_paths -v
```

Expected: failure because `reference_paths` are saved as `[]`.

- [ ] **Step 3: Add reference persistence helper**

In `huishi/routes_workspace.py`, import:

```python
import secrets
from pathlib import Path
```

Add:

```python
def persist_reference_images(reference_images) -> list[str]:
    saved_paths: list[str] = []
    output_dir: Path = current_app.config["OUTPUT_DIR"]
    output_dir.mkdir(parents=True, exist_ok=True)
    for item in reference_images:
        suffix = Path(item.filename or "reference.png").suffix.lower() or ".png"
        filename = f"reference_{secrets.token_urlsafe(10)}{suffix}"
        target = output_dir / filename
        item.save(target)
        item.stream.seek(0)
        saved_paths.append(f"/static/uploads/{filename}")
    return saved_paths
```

- [ ] **Step 4: Save references during generation**

In `generate()`, before calling `generate_image(...)`:

```python
    reference_paths = persist_reference_images(reference_images) if reference_images else []
```

Pass to `create_record(...)`:

```python
        reference_paths=reference_paths,
```

- [ ] **Step 5: Run test**

Run Step 2 command again.

Expected: test passes.

- [ ] **Checkpoint**

Generate once with a reference image and confirm the record has source reference paths.

---

## Task 7: Prompt Optimization Settings And API

**Files:**
- Create: `D:\AI\绘世\huishi\prompt_api.py`
- Modify: `D:\AI\绘世\huishi\routes_workspace.py`
- Modify: `D:\AI\绘世\templates\settings.html`
- Test: `D:\AI\绘世\tests\test_auth_records.py`

- [ ] **Step 1: Write failing tests**

Add:

```python
def test_admin_can_save_prompt_optimization_settings(client, app):
    client.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=True)

    response = client.post(
        "/settings",
        data={
            "base_url": "https://image.example/v1",
            "api_key": "sk-image",
            "prompt_base_url": "https://text.example/v1",
            "prompt_api_key": "sk-text",
            "prompt_model": "gpt-4.1-mini",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "Prompt 优化" in text
    assert "https://text.example/v1" in text
    assert "sk-text" not in text

    with app.app_context():
        from huishi.db import get_db

        rows = {
            row["key"]: row["value"]
            for row in get_db().execute("SELECT key, value FROM app_settings").fetchall()
        }
    assert rows["prompt_base_url"] == "https://text.example/v1"
    assert rows["prompt_api_key"] == "sk-text"
    assert rows["prompt_model"] == "gpt-4.1-mini"


def test_prompt_optimize_reports_when_not_configured(client):
    client.post("/register", data={"username": "optuser", "password": "secret123"}, follow_redirects=True)

    response = client.post(
        "/api/prompt/optimize",
        json={"prompt": "一只猫", "style": "通用增强"},
        headers={"X-Requested-With": "fetch", "Accept": "application/json"},
    )

    assert response.status_code == 400
    assert "暂未启用 Prompt 优化" in response.get_json()["error"]


def test_prompt_optimize_calls_configured_provider(client, app, monkeypatch):
    client.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=True)
    client.post(
        "/settings",
        data={
            "base_url": "https://image.example/v1",
            "api_key": "sk-image",
            "prompt_base_url": "https://text.example/v1",
            "prompt_api_key": "sk-text",
            "prompt_model": "gpt-4.1-mini",
        },
        follow_redirects=True,
    )
    client.get("/logout")
    client.post("/register", data={"username": "optcall", "password": "secret123"}, follow_redirects=True)

    calls = {}

    def fake_optimize_prompt(**kwargs):
        calls.update(kwargs)
        return "优化后的猫，柔和光线，细腻毛发"

    monkeypatch.setattr("huishi.routes_workspace.optimize_prompt", fake_optimize_prompt)
    response = client.post(
        "/api/prompt/optimize",
        json={"prompt": "一只猫", "style": "写实摄影"},
        headers={"X-Requested-With": "fetch", "Accept": "application/json"},
    )

    assert response.status_code == 200
    assert response.get_json()["optimized_prompt"] == "优化后的猫，柔和光线，细腻毛发"
    assert calls["prompt"] == "一只猫"
    assert calls["style"] == "写实摄影"
    assert calls["model"] == "gpt-4.1-mini"
```

- [ ] **Step 2: Run and verify failure**

Run:

```powershell
python -m pytest tests/test_auth_records.py::test_admin_can_save_prompt_optimization_settings tests/test_auth_records.py::test_prompt_optimize_reports_when_not_configured tests/test_auth_records.py::test_prompt_optimize_calls_configured_provider -v
```

Expected: failures because settings and API do not exist.

- [ ] **Step 3: Add app setting helpers**

In `huishi/routes_workspace.py`, add:

```python
def get_app_settings() -> dict[str, str]:
    rows = get_db().execute("SELECT key, value FROM app_settings").fetchall()
    return {row["key"]: row["value"] for row in rows}


def save_app_setting(key: str, value: str) -> None:
    get_db().execute(
        """
        INSERT INTO app_settings (key, value, updated_at)
        VALUES (?, ?, datetime('now'))
        ON CONFLICT(key) DO UPDATE SET
          value = excluded.value,
          updated_at = excluded.updated_at
        """,
        (key, value),
    )
```

- [ ] **Step 4: Update admin settings route**

In POST branch of `settings()`, after image API settings save:

```python
        prompt_base_url = request.form.get("prompt_base_url", "").strip()
        if prompt_base_url and not is_http_url(prompt_base_url):
            return "Prompt 优化 Base URL 必须以 http:// 或 https:// 开头", 400
        prompt_model = request.form.get("prompt_model", "").strip()
        posted_prompt_api_key = request.form.get("prompt_api_key", "").strip()
        app_settings = get_app_settings()
        prompt_api_key = posted_prompt_api_key or app_settings.get("prompt_api_key", "")
        save_app_setting("prompt_base_url", prompt_base_url)
        save_app_setting("prompt_api_key", prompt_api_key)
        save_app_setting("prompt_model", prompt_model)
```

In GET render:

```python
    app_settings = get_app_settings()
    return render_template(
        "settings.html",
        settings=settings_row,
        app_settings=app_settings,
        default_base_url=current_app.config.get("DEFAULT_BASE_URL", ""),
        has_api_key=bool(settings_row and settings_row["api_key"]),
        has_prompt_api_key=bool(app_settings.get("prompt_api_key")),
    )
```

- [ ] **Step 5: Create prompt API helper**

Create `huishi/prompt_api.py`:

```python
from __future__ import annotations

from openai import OpenAI


STYLE_GUIDES = {
    "通用增强": "保留原意，补充主体、环境、构图、光线、质感和风格细节。",
    "写实摄影": "优化为写实摄影提示词，强调镜头、光线、景深、材质和真实感。",
    "插画二次元": "优化为插画或二次元风格提示词，强调角色、线条、色彩和画面氛围。",
    "商业设计": "优化为商业视觉设计提示词，强调产品、版式、背景、质感和可用性。",
    "电影感": "优化为电影画面提示词，强调镜头语言、光影、场景调度和情绪。",
    "极简产品图": "优化为极简产品图提示词，强调主体清晰、背景克制、材质和留白。",
}


def optimize_prompt(
    *,
    prompt: str,
    style: str,
    api_key: str,
    base_url: str,
    model: str,
) -> str:
    if not prompt.strip():
        raise ValueError("提示词不能为空")
    if not api_key or not base_url or not model:
        raise ValueError("暂未启用 Prompt 优化")
    guide = STYLE_GUIDES.get(style, STYLE_GUIDES["通用增强"])
    client = OpenAI(api_key=api_key, base_url=base_url)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "你是 AI 生图提示词优化助手。只输出优化后的提示词，不解释。",
            },
            {
                "role": "user",
                "content": f"优化风格：{style}\n优化要求：{guide}\n原提示词：{prompt}",
            },
        ],
        temperature=0.7,
    )
    content = response.choices[0].message.content if response.choices else ""
    optimized = (content or "").strip()
    if not optimized:
        raise RuntimeError("Prompt 优化接口没有返回内容")
    return optimized
```

- [ ] **Step 6: Add prompt optimize API route**

In `huishi/routes_workspace.py`, import:

```python
from huishi.prompt_api import optimize_prompt
```

Add:

```python
@bp.post("/api/prompt/optimize")
@login_required
def prompt_optimize():
    payload = request.get_json(silent=True) or {}
    prompt = str(payload.get("prompt", "")).strip()
    style = str(payload.get("style", "通用增强")).strip() or "通用增强"
    app_settings = get_app_settings()
    try:
        optimized = optimize_prompt(
            prompt=prompt,
            style=style,
            api_key=app_settings.get("prompt_api_key", ""),
            base_url=app_settings.get("prompt_base_url", ""),
            model=app_settings.get("prompt_model", ""),
        )
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "optimized_prompt": optimized})
```

- [ ] **Step 7: Update settings template**

In `templates/settings.html`, add below the image API fields:

```jinja
<section class="settings-section">
  <h2>Prompt 优化</h2>
  <label><span>Prompt 优化 API Base URL</span><input name="prompt_base_url" value="{{ app_settings.get('prompt_base_url', '') }}"></label>
  <label>
    <span>Prompt 优化 API Key{% if has_prompt_api_key %} · 已保存，留空则不修改{% endif %}</span>
    <input name="prompt_api_key" type="password" value="" placeholder="{{ '输入新 Key 可替换当前配置' if has_prompt_api_key else '请输入 Prompt 优化 API Key' }}">
  </label>
  <label><span>Prompt 优化模型名</span><input name="prompt_model" value="{{ app_settings.get('prompt_model', '') }}" placeholder="gpt-4.1-mini"></label>
</section>
```

- [ ] **Step 8: Run tests**

Run Step 2 command again.

Expected: all three tests pass.

- [ ] **Checkpoint**

Log in as admin, save Prompt optimization settings, log in as a normal user, and call the endpoint with a mocked provider in tests.

---

## Task 8: Prompt Optimization Frontend Flow

**Files:**
- Modify: `D:\AI\绘世\templates\workspace.html`
- Modify: `D:\AI\绘世\static\js\workspace.js`
- Modify: `D:\AI\绘世\static\css\site.css`
- Test: `D:\AI\绘世\tests\test_auth_records.py`

- [ ] **Step 1: Write failing markup test**

Add:

```python
def test_workspace_contains_prompt_optimization_controls(client):
    client.post("/register", data={"username": "prompt-ui", "password": "secret123"}, follow_redirects=True)

    text = client.get("/workspace").get_data(as_text=True)

    assert "优化提示词" in text
    assert 'id="prompt-style"' in text
    assert "通用增强" in text
    assert "写实摄影" in text
    assert "prompt-optimize-modal" in text
```

- [ ] **Step 2: Run and verify failure**

Run:

```powershell
python -m pytest tests/test_auth_records.py::test_workspace_contains_prompt_optimization_controls -v
```

Expected: failure because controls do not exist.

- [ ] **Step 3: Add workspace controls**

In `workspace.html`, between textarea and reference upload, add:

```jinja
<div class="prompt-tools">
  <select id="prompt-style" aria-label="Prompt 优化风格">
    <option>通用增强</option>
    <option>写实摄影</option>
    <option>插画二次元</option>
    <option>商业设计</option>
    <option>电影感</option>
    <option>极简产品图</option>
  </select>
  <button type="button" data-optimize-prompt>优化提示词</button>
</div>
<dialog class="prompt-optimize-modal" id="prompt-optimize-modal">
  <h2>优化提示词</h2>
  <label><span>原提示词</span><textarea id="prompt-original" readonly></textarea></label>
  <label><span>优化结果</span><textarea id="prompt-optimized"></textarea></label>
  <p class="generation-status" id="prompt-optimize-status" aria-live="polite"></p>
  <div class="modal-actions">
    <button type="button" data-use-optimized-prompt>使用优化结果</button>
    <button type="button" data-close-prompt-modal>取消</button>
  </div>
</dialog>
```

- [ ] **Step 4: Add frontend behavior**

In `workspace.js`, add constants:

```javascript
const promptStyle = document.querySelector("#prompt-style");
const optimizePromptButton = document.querySelector("[data-optimize-prompt]");
const promptOptimizeModal = document.querySelector("#prompt-optimize-modal");
const promptOriginal = document.querySelector("#prompt-original");
const promptOptimized = document.querySelector("#prompt-optimized");
const promptOptimizeStatus = document.querySelector("#prompt-optimize-status");
const useOptimizedPromptButton = document.querySelector("[data-use-optimized-prompt]");
const closePromptModalButton = document.querySelector("[data-close-prompt-modal]");
```

Add:

```javascript
function setPromptOptimizeStatus(message, isError = false) {
  if (!promptOptimizeStatus) return;
  promptOptimizeStatus.textContent = message || "";
  promptOptimizeStatus.classList.toggle("is-error", isError);
}

async function runPromptOptimization() {
  const promptInput = form?.querySelector('[name="prompt"]');
  const prompt = (promptInput?.value || "").trim();
  if (!prompt) {
    setStatus("请先输入提示词", true);
    return;
  }
  optimizePromptButton.disabled = true;
  optimizePromptButton.textContent = "优化中";
  setPromptOptimizeStatus("");
  try {
    const response = await fetch("/api/prompt/optimize", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Requested-With": "fetch",
        "Accept": "application/json",
      },
      body: JSON.stringify({ prompt, style: promptStyle?.value || "通用增强" }),
    });
    const result = await response.json();
    if (!response.ok || !result.ok) throw new Error(result.error || "优化失败");
    if (promptOriginal) promptOriginal.value = prompt;
    if (promptOptimized) promptOptimized.value = result.optimized_prompt;
    if (promptOptimizeModal?.showModal) promptOptimizeModal.showModal();
  } catch (error) {
    setStatus(error.message || "优化失败", true);
  } finally {
    optimizePromptButton.disabled = false;
    optimizePromptButton.textContent = "优化提示词";
  }
}

function useOptimizedPrompt() {
  const promptInput = form?.querySelector('[name="prompt"]');
  if (promptInput && promptOptimized?.value) promptInput.value = promptOptimized.value;
  promptOptimizeModal?.close();
  refreshEstimate();
}
```

Bind:

```javascript
if (optimizePromptButton) optimizePromptButton.addEventListener("click", runPromptOptimization);
if (useOptimizedPromptButton) useOptimizedPromptButton.addEventListener("click", useOptimizedPrompt);
if (closePromptModalButton) closePromptModalButton.addEventListener("click", () => promptOptimizeModal?.close());
```

- [ ] **Step 5: Add minimal CSS**

In `site.css`, add:

```css
.prompt-tools {
  display: flex;
  gap: 8px;
  align-items: center;
}

.prompt-tools select,
.prompt-tools button {
  min-height: 36px;
}

.prompt-optimize-modal {
  width: min(720px, calc(100vw - 32px));
  border: 0;
  border-radius: 8px;
  padding: 20px;
}

.prompt-optimize-modal textarea {
  width: 100%;
  min-height: 120px;
}
```

- [ ] **Step 6: Run tests**

Run Step 2 command again.

Expected: test passes.

- [ ] **Checkpoint**

Use a mocked Prompt optimization response in tests and manually confirm the modal lets the user accept or cancel the optimized prompt.

---

## Task 9: Generation Task Cards And Failure Cards

**Files:**
- Modify: `D:\AI\绘世\templates\workspace.html`
- Modify: `D:\AI\绘世\static\js\workspace.js`
- Modify: `D:\AI\绘世\static\css\site.css`
- Test: `D:\AI\绘世\tests\test_auth_records.py`

- [ ] **Step 1: Write failing markup test**

Add:

```python
def test_workspace_contains_generation_task_region(client):
    client.post("/register", data={"username": "taskregion", "password": "secret123"}, follow_redirects=True)

    text = client.get("/workspace").get_data(as_text=True)

    assert 'id="generation-task-region"' in text
    assert "generation-task-card" in text
```

- [ ] **Step 2: Run and verify failure**

Run:

```powershell
python -m pytest tests/test_auth_records.py::test_workspace_contains_generation_task_region -v
```

Expected: failure because task region does not exist.

- [ ] **Step 3: Add task region**

In `workspace.html`, inside the main studio section before `current-canvas`, add:

```jinja
<section id="generation-task-region" class="generation-task-region" aria-live="polite">
  <template id="generation-task-template">
    <article class="generation-task-card">
      <div class="task-spinner"></div>
      <strong>生成中</strong>
      <p data-task-prompt></p>
      <span data-task-params></span>
    </article>
  </template>
</section>
```

- [ ] **Step 4: Render task and failure cards**

In `workspace.js`, add:

```javascript
const taskRegion = document.querySelector("#generation-task-region");
const taskTemplate = document.querySelector("#generation-task-template");

function renderTaskCard(formData) {
  if (!taskRegion || !taskTemplate) return null;
  const clone = taskTemplate.content.cloneNode(true);
  const card = clone.querySelector(".generation-task-card");
  const prompt = formData.get("prompt") || "";
  const ratio = formData.get("ratio") || "";
  const resolution = formData.get("resolution") || "";
  clone.querySelector("[data-task-prompt]").textContent = String(prompt).slice(0, 80);
  clone.querySelector("[data-task-params]").textContent = `${ratio} · ${resolution}`;
  taskRegion.prepend(clone);
  return card;
}

function markTaskFailed(card, message) {
  if (!card) return;
  card.classList.add("is-failed");
  card.innerHTML = `
    <strong>生成失败</strong>
    <p>${message || "生成失败"}</p>
    <div class="task-actions">
      <button type="button" data-task-retry>重试</button>
      <button type="button" data-task-edit>重新编辑</button>
    </div>
  `;
  card.querySelector("[data-task-retry]")?.addEventListener("click", () => form?.requestSubmit());
  card.querySelector("[data-task-edit]")?.addEventListener("click", () => card.remove());
}
```

In `submitGeneration()`, before fetch:

```javascript
  const formData = new FormData(form);
  const taskCard = renderTaskCard(formData);
```

Use `formData` in fetch:

```javascript
      body: formData,
```

In catch:

```javascript
    markTaskFailed(taskCard, error.message || "生成失败");
```

In success:

```javascript
    taskCard?.remove();
```

- [ ] **Step 5: Add CSS**

In `site.css`:

```css
.generation-task-region {
  display: grid;
  gap: 10px;
}

.generation-task-card {
  border: 1px solid var(--studio-border, #d8dee8);
  border-radius: 8px;
  padding: 12px;
  background: var(--studio-surface, #fff);
}

.generation-task-card.is-failed {
  border-color: #e26d6d;
}

.task-spinner {
  width: 18px;
  height: 18px;
  border: 2px solid currentColor;
  border-right-color: transparent;
  border-radius: 999px;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
```

- [ ] **Step 6: Run tests**

Run Step 2 command again.

Expected: test passes.

- [ ] **Checkpoint**

Trigger a successful generation and a mocked failed generation to confirm cards are removed or marked failed correctly.

---

## Task 10: Theme Toggle And Workspace Theme Variables

**Files:**
- Create: `D:\AI\绘世\static\js\theme.js`
- Modify: `D:\AI\绘世\templates\workspace.html`
- Modify: `D:\AI\绘世\templates\assets.html`
- Modify: `D:\AI\绘世\templates\asset_detail.html`
- Modify: `D:\AI\绘世\templates\partials\studio_nav.html`
- Modify: `D:\AI\绘世\static\css\site.css`
- Test: `D:\AI\绘世\tests\test_auth_records.py`

- [ ] **Step 1: Write failing theme markup test**

Add:

```python
def test_workspace_related_pages_include_theme_toggle_script(client, app):
    from huishi.db import get_db, utc_now

    client.post("/register", data={"username": "theme-user", "password": "secret123"}, follow_redirects=True)
    with app.app_context():
        db = get_db()
        user_id = db.execute("SELECT id FROM users WHERE username = 'theme-user'").fetchone()["id"]
        db.execute(
            """
            INSERT INTO records
            (user_id, prompt, image_path, mode, ratio, resolution, actual_size, quality, output_format, count, model_source, elapsed_seconds, points_charged, reference_paths, favorite, created_at)
            VALUES (?, '主题测试', '/static/uploads/theme.png', 'text', '1:1', '1K', '1024x1024', 'auto', 'png', 1, 'demo', 1.2, 1, '[]', 0, ?)
            """,
            (user_id, utc_now()),
        )
        db.commit()

    for path in ("/workspace", "/assets", "/assets/1"):
        text = client.get(path).get_data(as_text=True)
        assert 'data-theme-toggle' in text
        assert "js/theme.js" in text
```

- [ ] **Step 2: Run and verify failure**

Run:

```powershell
python -m pytest tests/test_auth_records.py::test_workspace_related_pages_include_theme_toggle_script -v
```

Expected: failure until theme script is included everywhere.

- [ ] **Step 3: Create theme script**

Create `static/js/theme.js`:

```javascript
const THEME_KEY = "huishi.workspaceTheme";
const root = document.documentElement;

function applyTheme(theme) {
  const nextTheme = theme === "dark" ? "dark" : "light";
  root.dataset.workspaceTheme = nextTheme;
  document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
    button.textContent = nextTheme === "dark" ? "☀" : "◐";
    button.setAttribute("aria-label", nextTheme === "dark" ? "切换到白色主题" : "切换到黑色主题");
  });
}

function currentTheme() {
  return localStorage.getItem(THEME_KEY) === "dark" ? "dark" : "light";
}

applyTheme(currentTheme());

document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
  button.addEventListener("click", () => {
    const nextTheme = currentTheme() === "dark" ? "light" : "dark";
    localStorage.setItem(THEME_KEY, nextTheme);
    applyTheme(nextTheme);
  });
});
```

- [ ] **Step 4: Include script in workspace**

In `workspace.html` scripts block:

```jinja
<script src="{{ url_for('static', filename='js/theme.js') }}"></script>
<script src="{{ url_for('static', filename='js/workspace.js') }}"></script>
```

Ensure `assets.html` and `asset_detail.html` include `theme.js`.

- [ ] **Step 5: Add CSS variables**

In `site.css`, add:

```css
:root[data-workspace-theme="light"] {
  --studio-bg: #f6f7f9;
  --studio-surface: #ffffff;
  --studio-text: #18202f;
  --studio-muted: #657083;
  --studio-border: #dfe4ec;
}

:root[data-workspace-theme="dark"] {
  --studio-bg: #101319;
  --studio-surface: #181d26;
  --studio-text: #f4f7fb;
  --studio-muted: #a8b0bf;
  --studio-border: #303846;
}

.workspace-page .studio-shell,
.workspace-page .assets-shell,
.workspace-page .asset-detail-shell {
  background: var(--studio-bg);
  color: var(--studio-text);
}

.workspace-page .composer,
.workspace-page .asset-tile,
.workspace-page .detail-panel,
.workspace-page .parameter-popover {
  background: var(--studio-surface);
  color: var(--studio-text);
  border-color: var(--studio-border);
}
```

- [ ] **Step 6: Run tests**

Run Step 2 command again.

Expected: test passes.

- [ ] **Checkpoint**

Use the browser to toggle theme on `/workspace`, `/assets`, and `/assets/<id>`.

---

## Task 11: Advanced Asset Filters And Batch Operations

**Files:**
- Modify: `D:\AI\绘世\huishi\records.py`
- Modify: `D:\AI\绘世\huishi\routes_workspace.py`
- Modify: `D:\AI\绘世\templates\assets.html`
- Modify: `D:\AI\绘世\static\js\assets.js`
- Modify: `D:\AI\绘世\static\css\site.css`
- Test: `D:\AI\绘世\tests\test_auth_records.py`

- [ ] **Step 1: Write failing backend bulk tests**

Add:

```python
def test_bulk_favorite_and_delete_assets(client, app):
    from huishi.db import get_db, utc_now

    client.post("/register", data={"username": "bulkuser", "password": "secret123"}, follow_redirects=True)
    with app.app_context():
        db = get_db()
        user_id = db.execute("SELECT id FROM users WHERE username = 'bulkuser'").fetchone()["id"]
        for prompt in ("批量一", "批量二"):
            db.execute(
                """
                INSERT INTO records
                (user_id, prompt, image_path, mode, ratio, resolution, actual_size, quality, output_format, count, model_source, elapsed_seconds, points_charged, reference_paths, favorite, created_at)
                VALUES (?, ?, '/static/uploads/bulk.png', 'text', '1:1', '1K', '1024x1024', 'auto', 'png', 1, 'demo', 1.2, 1, '[]', 0, ?)
                """,
                (user_id, prompt, utc_now()),
            )
        db.commit()

    favorite = client.post(
        "/assets/bulk/favorite",
        json={"ids": [1, 2], "favorite": True},
        headers={"X-Requested-With": "fetch", "Accept": "application/json"},
    )
    assert favorite.status_code == 200
    assert favorite.get_json()["updated"] == 2

    delete = client.post(
        "/assets/bulk/delete",
        json={"ids": [1, 2]},
        headers={"X-Requested-With": "fetch", "Accept": "application/json"},
    )
    assert delete.status_code == 200
    assert delete.get_json()["deleted"] == 2


def test_assets_page_contains_filter_drawer_and_batch_controls(client):
    client.post("/register", data={"username": "filter-ui", "password": "secret123"}, follow_redirects=True)

    text = client.get("/assets").get_data(as_text=True)

    assert "asset-filter-drawer" in text
    assert "data-filter-mode" in text
    assert "data-filter-ratio" in text
    assert "data-batch-toggle" in text
    assert "data-bulk-download" in text
```

- [ ] **Step 2: Run and verify failure**

Run:

```powershell
python -m pytest tests/test_auth_records.py::test_bulk_favorite_and_delete_assets tests/test_auth_records.py::test_assets_page_contains_filter_drawer_and_batch_controls -v
```

Expected: failures until routes and markup exist.

- [ ] **Step 3: Add bulk routes**

In `huishi/routes_workspace.py`, add:

```python
def parse_asset_ids() -> list[int]:
    payload = request.get_json(silent=True) or {}
    raw_ids = payload.get("ids", [])
    ids: list[int] = []
    for raw_id in raw_ids:
        try:
            ids.append(int(raw_id))
        except (TypeError, ValueError):
            continue
    return sorted(set(ids))


@bp.post("/assets/bulk/favorite")
@login_required
def bulk_favorite_assets():
    ids = parse_asset_ids()
    payload = request.get_json(silent=True) or {}
    favorite = 1 if payload.get("favorite") else 0
    if not ids:
        return jsonify({"ok": False, "error": "请选择资产"}), 400
    placeholders = ",".join("?" for _ in ids)
    params = [favorite, *ids, g.user["id"]]
    cursor = get_db().execute(
        f"UPDATE records SET favorite = ? WHERE id IN ({placeholders}) AND user_id = ?",
        params,
    )
    get_db().commit()
    return jsonify({"ok": True, "updated": cursor.rowcount})


@bp.post("/assets/bulk/delete")
@login_required
def bulk_delete_assets():
    ids = parse_asset_ids()
    if not ids:
        return jsonify({"ok": False, "error": "请选择资产"}), 400
    placeholders = ",".join("?" for _ in ids)
    records = get_db().execute(
        f"SELECT * FROM records WHERE id IN ({placeholders}) AND user_id = ?",
        [*ids, g.user["id"]],
    ).fetchall()
    for record in records:
        delete_local_upload(str(record["image_path"]))
    get_db().execute(
        f"DELETE FROM records WHERE id IN ({placeholders}) AND user_id = ?",
        [*ids, g.user["id"]],
    )
    get_db().commit()
    return jsonify({"ok": True, "deleted": len(records)})
```

- [ ] **Step 4: Add filter drawer and batch controls**

In `assets.html`, add after quick tabs:

```jinja
<aside class="asset-filter-drawer" hidden>
  <label>模式
    <select data-filter-mode>
      <option value="">全部</option>
      <option value="text">文生图</option>
      <option value="reference">参考图生成</option>
    </select>
  </label>
  <label>时间
    <select data-filter-time>
      <option value="">全部</option>
      <option value="today">今天</option>
      <option value="7">最近 7 天</option>
      <option value="30">最近 30 天</option>
    </select>
  </label>
  <label>比例
    <select data-filter-ratio>
      <option value="">全部</option>
      <option>1:1</option>
      <option>16:9</option>
      <option>9:16</option>
      <option>3:2</option>
      <option>2:3</option>
    </select>
  </label>
  <label>清晰度
    <select data-filter-resolution>
      <option value="">全部</option>
      <option>1K</option>
      <option>2K</option>
      <option>4K</option>
    </select>
  </label>
  <div class="filter-actions">
    <button type="button" data-filter-reset>重置</button>
    <button type="button" data-filter-apply>应用</button>
  </div>
</aside>
<div class="asset-batchbar" hidden>
  <span data-selected-count>已选择 0 张</span>
  <button type="button" data-bulk-favorite>收藏</button>
  <button type="button" data-bulk-unfavorite>取消收藏</button>
  <button type="button" data-bulk-download>下载</button>
  <button type="button" data-bulk-delete>删除</button>
</div>
```

Add per tile:

```jinja
data-created-at="{{ record['created_at'] }}"
```

Add checkbox:

```jinja
<input class="asset-select" type="checkbox" value="{{ record['id'] }}" aria-label="选择资产">
```

- [ ] **Step 5: Add asset JS**

Replace `static/js/assets.js` with logic that keeps existing search and adds:

```javascript
const filterDrawer = document.querySelector(".asset-filter-drawer");
const batchBar = document.querySelector(".asset-batchbar");
const selectedCount = document.querySelector("[data-selected-count]");

function selectedIds() {
  return Array.from(document.querySelectorAll(".asset-select:checked")).map((item) => item.value);
}

function updateBatchBar() {
  const count = selectedIds().length;
  if (selectedCount) selectedCount.textContent = `已选择 ${count} 张`;
  if (batchBar) batchBar.hidden = count === 0;
}

function matchesTime(tile, value) {
  if (!value) return true;
  const created = new Date(tile.dataset.createdAt || "");
  if (Number.isNaN(created.getTime())) return true;
  const now = new Date();
  const days = value === "today" ? 1 : Number(value);
  const diff = now.getTime() - created.getTime();
  return diff <= days * 24 * 60 * 60 * 1000;
}

function applyAssetFilters(filter = document.querySelector("[data-quick-filter].is-active")?.dataset.quickFilter || "all") {
  const query = (assetSearch?.value || "").trim().toLowerCase();
  const mode = document.querySelector("[data-filter-mode]")?.value || "";
  const ratio = document.querySelector("[data-filter-ratio]")?.value || "";
  const resolution = document.querySelector("[data-filter-resolution]")?.value || "";
  const time = document.querySelector("[data-filter-time]")?.value || "";
  assetTiles.forEach((tile) => {
    const prompt = (tile.dataset.prompt || "").toLowerCase();
    const matchesSearch = !query || prompt.includes(query);
    const matchesQuick = filter === "all" || (filter === "favorite" && tile.dataset.favorite === "1");
    const matchesMode = !mode || tile.dataset.mode === mode;
    const matchesRatio = !ratio || tile.dataset.ratio === ratio;
    const matchesResolution = !resolution || tile.dataset.resolution === resolution;
    tile.classList.toggle("is-hidden", !(matchesSearch && matchesQuick && matchesMode && matchesRatio && matchesResolution && matchesTime(tile, time)));
  });
}

async function postBulk(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Requested-With": "fetch", "Accept": "application/json" },
    body: JSON.stringify(payload),
  });
  const result = await response.json();
  if (!response.ok || !result.ok) throw new Error(result.error || "批量操作失败");
  return result;
}
```

Bind controls:

```javascript
document.querySelector("[data-filter-open]")?.addEventListener("click", () => {
  if (filterDrawer) filterDrawer.hidden = !filterDrawer.hidden;
});
document.querySelector("[data-filter-apply]")?.addEventListener("click", () => applyAssetFilters());
document.querySelector("[data-filter-reset]")?.addEventListener("click", () => {
  document.querySelectorAll(".asset-filter-drawer select").forEach((select) => { select.value = ""; });
  applyAssetFilters();
});
document.querySelectorAll(".asset-select").forEach((input) => input.addEventListener("change", updateBatchBar));
document.querySelector("[data-bulk-favorite]")?.addEventListener("click", () => postBulk("/assets/bulk/favorite", { ids: selectedIds(), favorite: true }).then(() => location.reload()));
document.querySelector("[data-bulk-unfavorite]")?.addEventListener("click", () => postBulk("/assets/bulk/favorite", { ids: selectedIds(), favorite: false }).then(() => location.reload()));
document.querySelector("[data-bulk-delete]")?.addEventListener("click", () => {
  const ids = selectedIds();
  if (!ids.length || !confirm(`确认删除选中的 ${ids.length} 张图片？删除后不可恢复。`)) return;
  postBulk("/assets/bulk/delete", { ids }).then(() => location.reload());
});
```

- [ ] **Step 6: Run tests**

Run Step 2 command again.

Expected: tests pass.

- [ ] **Checkpoint**

In browser, select multiple assets, apply filters, and verify batch favorite/delete works.

---

## Task 12: Batch Zip Download

**Files:**
- Modify: `D:\AI\绘世\huishi\routes_workspace.py`
- Modify: `D:\AI\绘世\static\js\assets.js`
- Test: `D:\AI\绘世\tests\test_auth_records.py`

- [ ] **Step 1: Write failing zip test**

Add:

```python
def test_bulk_download_returns_zip_for_owned_assets(client, app, tmp_path):
    from huishi.db import get_db, utc_now

    upload_dir = app.config["OUTPUT_DIR"]
    upload_dir.mkdir(parents=True, exist_ok=True)
    (upload_dir / "zip-a.png").write_bytes(b"image-a")
    (upload_dir / "zip-b.png").write_bytes(b"image-b")

    client.post("/register", data={"username": "zipuser", "password": "secret123"}, follow_redirects=True)
    with app.app_context():
        db = get_db()
        user_id = db.execute("SELECT id FROM users WHERE username = 'zipuser'").fetchone()["id"]
        for filename in ("zip-a.png", "zip-b.png"):
            db.execute(
                """
                INSERT INTO records
                (user_id, prompt, image_path, mode, ratio, resolution, actual_size, quality, output_format, count, model_source, elapsed_seconds, points_charged, reference_paths, favorite, created_at)
                VALUES (?, ?, ?, 'text', '1:1', '1K', '1024x1024', 'auto', 'png', 1, 'demo', 1.2, 1, '[]', 0, ?)
                """,
                (user_id, filename, f"/static/uploads/{filename}", utc_now()),
            )
        db.commit()

    response = client.post(
        "/assets/bulk/download",
        json={"ids": [1, 2]},
        headers={"X-Requested-With": "fetch", "Accept": "application/zip"},
    )

    assert response.status_code == 200
    assert response.mimetype == "application/zip"
    assert response.headers["Content-Disposition"].startswith("attachment;")
    assert response.data.startswith(b"PK")
```

- [ ] **Step 2: Run and verify failure**

Run:

```powershell
python -m pytest tests/test_auth_records.py::test_bulk_download_returns_zip_for_owned_assets -v
```

Expected: failure because route does not exist.

- [ ] **Step 3: Add zip route**

In `huishi/routes_workspace.py`, import:

```python
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
from flask import send_file
```

Add:

```python
@bp.post("/assets/bulk/download")
@login_required
def bulk_download_assets():
    ids = parse_asset_ids()
    if not ids:
        return jsonify({"ok": False, "error": "请选择资产"}), 400
    placeholders = ",".join("?" for _ in ids)
    records = get_db().execute(
        f"SELECT * FROM records WHERE id IN ({placeholders}) AND user_id = ? ORDER BY id",
        [*ids, g.user["id"]],
    ).fetchall()
    memory = BytesIO()
    with ZipFile(memory, "w", ZIP_DEFLATED) as archive:
        for record in records:
            image_path = str(record["image_path"])
            if not image_path.startswith("/static/uploads/"):
                continue
            local_name = image_path.rsplit("/", 1)[-1]
            local_path = current_app.config["OUTPUT_DIR"] / local_name
            if local_path.exists():
                archive.write(local_path, arcname=local_name)
    memory.seek(0)
    return send_file(
        memory,
        mimetype="application/zip",
        as_attachment=True,
        download_name="huishi-assets.zip",
    )
```

- [ ] **Step 4: Wire download button**

In `assets.js`, add:

```javascript
document.querySelector("[data-bulk-download]")?.addEventListener("click", async () => {
  const ids = selectedIds();
  if (!ids.length) return;
  const response = await fetch("/assets/bulk/download", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Requested-With": "fetch", "Accept": "application/zip" },
    body: JSON.stringify({ ids }),
  });
  if (!response.ok) {
    alert("批量下载失败");
    return;
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `huishi-assets-${new Date().toISOString().slice(0, 10)}.zip`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
});
```

- [ ] **Step 5: Run test**

Run Step 2 command again.

Expected: test passes.

- [ ] **Checkpoint**

Select two assets in browser and confirm one zip file downloads.

---

## Task 13: Insufficient Points Modal And Regenerate Custom Confirmation

**Files:**
- Modify: `D:\AI\绘世\templates\workspace.html`
- Modify: `D:\AI\绘世\templates\asset_detail.html`
- Modify: `D:\AI\绘世\static\js\workspace.js`
- Modify: `D:\AI\绘世\static\css\site.css`
- Test: `D:\AI\绘世\tests\test_auth_records.py`

- [ ] **Step 1: Write failing modal markup test**

Add:

```python
def test_workspace_contains_points_and_regenerate_modals(client):
    client.post("/register", data={"username": "modaluser", "password": "secret123"}, follow_redirects=True)

    text = client.get("/workspace").get_data(as_text=True)

    assert "points-shortage-modal" in text
    assert "regenerate-confirm-modal" in text
    assert "去充值" in text
    assert "不再提示" in text
```

- [ ] **Step 2: Run and verify failure**

Run:

```powershell
python -m pytest tests/test_auth_records.py::test_workspace_contains_points_and_regenerate_modals -v
```

Expected: failure until modal markup exists.

- [ ] **Step 3: Add modal markup**

In `workspace.html`, add before closing `</main>`:

```jinja
<dialog id="points-shortage-modal" class="confirm-modal">
  <h2>积分不足</h2>
  <p data-shortage-message>当前积分不足，无法开始生成。</p>
  <div class="modal-actions">
    <a href="/pricing">去充值</a>
    <button type="button" data-close-shortage>取消</button>
  </div>
</dialog>

<dialog id="regenerate-confirm-modal" class="confirm-modal">
  <h2>再次生成</h2>
  <p data-regenerate-message>再次生成会消耗积分，确认继续？</p>
  <label><input type="checkbox" data-skip-regenerate-confirm> 不再提示</label>
  <div class="modal-actions">
    <button type="button" data-confirm-regenerate>确认生成</button>
    <button type="button" data-cancel-regenerate>取消</button>
  </div>
</dialog>
```

Add the same regenerate modal to `asset_detail.html`, or include a shared partial if one is created.

- [ ] **Step 4: Replace `window.confirm` with dialog**

In `workspace.js`, replace `confirmRegenerate()` with:

```javascript
const regenerateModal = document.querySelector("#regenerate-confirm-modal");
const regenerateMessage = document.querySelector("[data-regenerate-message]");
const confirmRegenerateButton = document.querySelector("[data-confirm-regenerate]");
const cancelRegenerateButton = document.querySelector("[data-cancel-regenerate]");
const skipRegenerateConfirm = document.querySelector("[data-skip-regenerate-confirm]");

function confirmRegenerate(cost) {
  if (!shouldConfirmRegenerate()) return Promise.resolve(true);
  if (!regenerateModal?.showModal) {
    return Promise.resolve(window.confirm(`再次生成预计消耗 ${cost || "-"} 点积分，确认继续？`));
  }
  if (regenerateMessage) regenerateMessage.textContent = `再次生成预计消耗 ${cost || "-"} 点积分，确认继续？`;
  regenerateModal.showModal();
  return new Promise((resolve) => {
    confirmRegenerateButton.onclick = () => {
      setSkipRegenerateConfirm(Boolean(skipRegenerateConfirm?.checked));
      regenerateModal.close();
      resolve(true);
    };
    cancelRegenerateButton.onclick = () => {
      regenerateModal.close();
      resolve(false);
    };
  });
}
```

In generation catch, if error contains insufficient points text from backend, open shortage modal:

```javascript
const shortageModal = document.querySelector("#points-shortage-modal");
const shortageMessage = document.querySelector("[data-shortage-message]");
document.querySelector("[data-close-shortage]")?.addEventListener("click", () => shortageModal?.close());

function showShortage(message) {
  if (shortageMessage) shortageMessage.textContent = message || "当前积分不足，无法开始生成。";
  if (shortageModal?.showModal) shortageModal.showModal();
}
```

In `catch`:

```javascript
    if ((error.message || "").includes("积分") || (error.message || "").includes("余额")) {
      showShortage(error.message);
    }
```

- [ ] **Step 5: Add CSS**

In `site.css`:

```css
.confirm-modal {
  width: min(420px, calc(100vw - 32px));
  border: 0;
  border-radius: 8px;
  padding: 20px;
  background: var(--studio-surface, #fff);
  color: var(--studio-text, #18202f);
}

.confirm-modal::backdrop {
  background: rgba(0, 0, 0, 0.45);
}
```

- [ ] **Step 6: Run tests**

Run Step 2 command again.

Expected: test passes.

- [ ] **Checkpoint**

Verify insufficient points opens the recharge modal and regenerate confirmation supports "不再提示".

---

## Task 14: Final Regression And Browser Verification

**Files:**
- No source files unless regressions are found.

- [ ] **Step 1: Run complete Python test suite**

Run:

```powershell
python -m pytest -v
```

Expected: all tests pass.

- [ ] **Step 2: Start or restart local service**

Run:

```powershell
cd D:\AI\绘世
$env:FLASK_DEBUG='0'
Start-Process -FilePath python -ArgumentList 'app.py' -WorkingDirectory 'D:\AI\绘世' -RedirectStandardOutput 'D:\AI\绘世\server.out.log' -RedirectStandardError 'D:\AI\绘世\server.err.log' -WindowStyle Hidden
```

If port 8000 is already used:

```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen
Stop-Process -Id <OwningProcess> -Force
```

Then run the start command again.

- [ ] **Step 3: Browser verify desktop pages**

Use the in-app browser:

- Open `http://127.0.0.1:8000/workspace`.
- Verify navigation shows 生成、资产、充值、账号.
- Verify no 灵感、会员、history text appears.
- Open `http://127.0.0.1:8000/assets`.
- Verify asset grid, search, filter drawer, batch controls.
- Open `http://127.0.0.1:8000/assets/1` for an existing asset.
- Verify detail actions and metadata.

- [ ] **Step 4: Browser verify mobile layout**

Set viewport to a mobile width such as 390x844.

Check:

- `document.documentElement.scrollWidth <= window.innerWidth`
- The asset grid does not overflow horizontally.
- The composer controls wrap cleanly.
- Theme toggle remains reachable.

- [ ] **Step 5: Browser verify core interactions**

Check:

- White/black theme toggle persists after reload.
- `/workspace?edit_record=<id>` pre-fills prompt and parameters.
- Prompt optimize displays disabled/configuration error when admin has not configured it.
- Batch delete asks for confirmation.
- Batch zip download returns a zip file.
- Regenerate confirmation appears unless "不再提示" was saved.

- [ ] **Checkpoint**

Record final test count and browser observations in the final response.

---

## Self-Review Checklist

- Spec coverage:
  - `/assets`, `/assets/<id>`, `/history` removal, clean nav, recharge copy: Tasks 2 and 3.
  - Admin-only settings and Prompt optimization config: Task 7.
  - Edit-again seed: Task 4.
  - Regenerate confirmation and no accidental charge: Tasks 5 and 13.
  - Generation task/failure cards: Task 9.
  - Theme toggle: Task 10.
  - Advanced filters, batch favorite/delete/download: Tasks 11 and 12.
  - Final verification: Task 14.
- Placeholder scan:
  - This plan contains no TBD, TODO, or unspecified implementation steps.
- Type consistency:
  - Record metadata uses `ratio` and `reference_paths`.
  - Prompt settings use `prompt_base_url`, `prompt_api_key`, and `prompt_model`.
  - Asset routes consistently use `/assets`.
