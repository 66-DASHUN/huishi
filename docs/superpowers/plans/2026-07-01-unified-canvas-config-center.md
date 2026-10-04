# 画布兼容接入与统一配置中心实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在保留 `infinite-canvas` 独立运行时的前提下，把画布能力统一纳入当前项目的后台配置中心、统一计费体系和统一资产流转入口，对用户表现为一个系统。

**Architecture:** 继续由 `huishihuabu` 负责账号、权限、配置、计费、资产和后台，由 `infinite-canvas` 负责画布内部交互。主改造点在当前 Flask 项目：新增统一后台菜单与配置中心路由，把现有 `/settings`、`/admin/pricing`、`/admin/packages` 收口到新的管理结构，同时保留 `/canvas` 独立页和现有资产桥接。由于当前工作目录不是 git 仓库，本计划用“测试通过的检查点”替代强制提交步骤；若后续补上 git，可按文中给出的提交命令执行。

**Tech Stack:** Flask、Jinja2、SQLite、原生 JavaScript、CSS、pytest、现有 `app_settings` / `pricing_rules` / `packages` / `records` 表。

---

## 文件结构与职责

- `huishi/routes_admin.py`
  - 新增统一配置中心总页与子页面路由
  - 承接旧 `/admin/pricing`、`/admin/packages` 兼容跳转
  - 承载新的配置中心表单提交流程
- `huishi/routes_workspace.py`
  - 将旧 `/settings` 改成兼容入口，跳转到新的后台配置页
  - 保留 `/canvas` 独立页与资产桥接
- `huishi/providers.py`
  - 继续作为画布配置读写入口
  - 如需新增 `canvas_enabled` 等开关，在这里扩展
- `templates/admin/layout.html`
  - 统一后台菜单入口
- `templates/admin/config_center.html`
  - 新增配置中心总页
- `templates/admin/config_settings.html`
  - 新增统一配置页，收纳原 `/settings` 的系统设置、Provider、画布、SMTP 等表单
- `templates/admin/config_billing.html`
  - 新增统一计费页，承载原 `/admin/pricing`
- `templates/admin/config_packages.html`
  - 新增统一套餐页，承载原 `/admin/packages`
- `templates/settings.html`
  - 旧页面保留兼容时仅用于过渡；最终只保留跳转或极薄包装
- `templates/canvas.html`
  - 保持画布独立页，继续使用 iframe + postMessage
- `templates/assets.html`
  - 保持“发送到画布”入口
- `static/js/assets.js`
  - 保持资产桥接逻辑
- `tests/test_settings_config_status.py`
  - 覆盖配置中心、旧入口兼容、画布配置页可见性
- `tests/test_package_defaults.py`
  - 覆盖统一后台菜单中套餐/计费入口存在
- `tests/test_workspace_generation_flow.py`
  - 覆盖 `/canvas` 独立页、导航顺序、画布嵌入地址与资产桥接入口

---

### Task 1: 新增统一后台菜单与配置中心总页

**Files:**
- Modify: `huishi/routes_admin.py`
- Modify: `templates/admin/layout.html`
- Create: `templates/admin/config_center.html`
- Test: `tests/test_settings_config_status.py`

- [ ] **Step 1: 写失败测试，锁定配置中心入口与总页路由**

```python
from pathlib import Path


def test_admin_layout_has_config_center_entry():
    template = Path("templates/admin/layout.html").read_text(encoding="utf-8")

    assert "配置中心" in template
    assert 'href="/admin/config"' in template


def test_admin_config_center_page_renders(tmp_path):
    from app import create_app
    from huishi.db import get_db, init_db

    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "test.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"
    with app.app_context():
        init_db()
        admin = get_db().execute("SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1").fetchone()

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = admin["id"]
        response = client.get("/admin/config")

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "配置中心" in body
    assert "/admin/config/settings" in body
    assert "/admin/config/billing" in body
    assert "/admin/config/packages" in body
```

- [ ] **Step 2: 运行测试，确认先失败**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_settings_config_status.py::test_admin_layout_has_config_center_entry tests/test_settings_config_status.py::test_admin_config_center_page_renders -v
```

Expected:

- 至少一个测试失败
- 原因是 `/admin/config` 路由或菜单入口尚不存在

- [ ] **Step 3: 在后台路由中新增配置中心总页**

```python
@bp.get("/config")
@admin_required
def config_center():
    return render_template(
        "admin/config_center.html",
        sections=[
            {"key": "settings", "label": "系统配置", "href": url_for("admin.config_settings")},
            {"key": "billing", "label": "计费规则", "href": url_for("admin.config_billing")},
            {"key": "packages", "label": "套餐说明", "href": url_for("admin.config_packages")},
        ],
    )
```

- [ ] **Step 4: 更新后台菜单与总页模板**

```html
<!-- templates/admin/layout.html -->
<nav class="simple-nav">
  <a href="/admin/">管理总览</a>
  <a href="/admin/config">配置中心</a>
  <a href="/admin/users">用户管理</a>
  <a href="/admin/invites">邀请码管理</a>
  <a href="/admin/records">记录流水</a>
  <a href="/workspace">工作台</a>
</nav>
```

```html
<!-- templates/admin/config_center.html -->
{% extends "admin/layout.html" %}
{% block title %}配置中心 - 绘世{% endblock %}
{% block admin_content %}
<header class="page-hero">
  <span>Config Center</span>
  <h1>配置中心</h1>
  <p>统一管理系统配置、画布配置、计费规则与套餐说明。</p>
</header>
<section class="table-list">
  {% for section in sections %}
  <article class="admin-row">
    <strong>{{ section.label }}</strong>
    <a href="{{ section.href }}">进入</a>
  </article>
  {% endfor %}
</section>
{% endblock %}
```

- [ ] **Step 5: 重新运行测试，确认通过**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_settings_config_status.py::test_admin_layout_has_config_center_entry tests/test_settings_config_status.py::test_admin_config_center_page_renders -v
```

Expected:

- 2 passed

- [ ] **Step 6: 记录检查点**

```powershell
git add huishi/routes_admin.py templates/admin/layout.html templates/admin/config_center.html tests/test_settings_config_status.py
git commit -m "feat: add admin config center entrypoint"
```

如果 `git rev-parse --is-inside-work-tree` 返回非 0，则跳过提交，只保留“测试已通过”的检查点。

---

### Task 2: 抽出统一配置页并让旧 `/settings` 走兼容入口

**Files:**
- Modify: `huishi/routes_admin.py`
- Modify: `huishi/routes_workspace.py`
- Create: `templates/admin/config_settings.html`
- Modify: `templates/settings.html`
- Test: `tests/test_settings_config_status.py`

- [ ] **Step 1: 写失败测试，锁定新配置页与旧入口兼容行为**

```python
def test_admin_config_settings_page_shows_canvas_section(tmp_path):
    from app import create_app
    from huishi.db import get_db, init_db

    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "test.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"
    with app.app_context():
        init_db()
        admin = get_db().execute("SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1").fetchone()

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = admin["id"]
        response = client.get("/admin/config/settings")

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "画布配置" in body
    assert "画布应用地址" in body
    assert "Agent/MCP" in body


def test_legacy_settings_route_redirects_to_admin_config(tmp_path):
    from app import create_app
    from huishi.db import get_db, init_db

    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "test.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"
    with app.app_context():
        init_db()
        admin = get_db().execute("SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1").fetchone()

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = admin["id"]
        response = client.get("/settings", follow_redirects=False)

    assert response.status_code == 302
    assert "/admin/config/settings" in response.headers["Location"]
```

- [ ] **Step 2: 运行测试，确认先失败**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_settings_config_status.py::test_admin_config_settings_page_shows_canvas_section tests/test_settings_config_status.py::test_legacy_settings_route_redirects_to_admin_config -v
```

Expected:

- 新路由不存在或旧 `/settings` 仍直接渲染原页

- [ ] **Step 3: 在后台蓝图中新增统一配置页路由**

```python
@bp.route("/config/settings", methods=("GET", "POST"))
@admin_required
def config_settings():
    from huishi.routes_workspace import settings as legacy_settings

    return legacy_settings()
```

> 执行时不要直接长期保留这种“路由套路由”的最终实现。先用它跑通行为，再在同一任务中把 `routes_workspace.settings()` 里的上下文构建和保存逻辑抽到可复用 helper，例如 `build_settings_context()` 与 `handle_settings_submission()`，最终让 `routes_admin.py` 与 `routes_workspace.py` 共用 helper，而不是互相调用。

- [ ] **Step 4: 把旧 `/settings` 改成兼容跳转**

```python
@bp.route("/settings", methods=("GET", "POST"))
@login_required
def settings():
    if g.user["role"] != "admin":
        abort(403)
    return redirect(url_for("admin.config_settings"))
```

- [ ] **Step 5: 为后台配置页创建承载模板**

```html
<!-- templates/admin/config_settings.html -->
{% extends "admin/layout.html" %}
{% block title %}系统配置 - 绘世{% endblock %}
{% block admin_content %}
<header class="page-hero">
  <span>Settings</span>
  <h1>系统配置</h1>
  <p>统一管理 Provider、画布、SMTP 与告警邮箱配置。</p>
</header>
{% include "admin/_config_settings_panels.html" %}
{% endblock %}
```

> 执行时将当前 `templates/settings.html` 中的面板主体抽成可复用 partial `templates/admin/_config_settings_panels.html`，避免复制一整份大模板。

- [ ] **Step 6: 重新运行测试，确认通过**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_settings_config_status.py::test_admin_config_settings_page_shows_canvas_section tests/test_settings_config_status.py::test_legacy_settings_route_redirects_to_admin_config -v
```

Expected:

- 2 passed

- [ ] **Step 7: 记录检查点**

```powershell
git add huishi/routes_admin.py huishi/routes_workspace.py templates/admin/config_settings.html templates/settings.html tests/test_settings_config_status.py
git commit -m "feat: move settings into admin config center"
```

---

### Task 3: 把计费规则与套餐说明统一收口到配置中心子页面

**Files:**
- Modify: `huishi/routes_admin.py`
- Modify: `templates/admin/pricing.html`
- Modify: `templates/admin/packages.html`
- Create: `templates/admin/config_billing.html`
- Create: `templates/admin/config_packages.html`
- Test: `tests/test_settings_config_status.py`
- Test: `tests/test_package_defaults.py`

- [ ] **Step 1: 写失败测试，锁定新计费入口与旧入口兼容**

```python
def test_admin_config_billing_page_renders(tmp_path):
    from app import create_app
    from huishi.db import get_db, init_db

    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "test.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"
    with app.app_context():
        init_db()
        admin = get_db().execute("SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1").fetchone()

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = admin["id"]
        response = client.get("/admin/config/billing")

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "计费规则" in body
    assert "同时适用于工作台与画布" in body


def test_legacy_admin_pricing_and_packages_redirect_to_config_center(tmp_path):
    from app import create_app
    from huishi.db import get_db, init_db

    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "test.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"
    with app.app_context():
        init_db()
        admin = get_db().execute("SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1").fetchone()

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = admin["id"]
        pricing_response = client.get("/admin/pricing", follow_redirects=False)
        packages_response = client.get("/admin/packages", follow_redirects=False)

    assert pricing_response.status_code == 302
    assert "/admin/config/billing" in pricing_response.headers["Location"]
    assert packages_response.status_code == 302
    assert "/admin/config/packages" in packages_response.headers["Location"]
```

- [ ] **Step 2: 运行测试，确认先失败**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_settings_config_status.py::test_admin_config_billing_page_renders tests/test_settings_config_status.py::test_legacy_admin_pricing_and_packages_redirect_to_config_center -v
```

Expected:

- 旧 `/admin/pricing`、`/admin/packages` 仍直接渲染旧页面

- [ ] **Step 3: 新增 `/admin/config/billing` 与 `/admin/config/packages` 路由**

```python
@bp.route("/config/billing", methods=("GET", "POST"))
@admin_required
def config_billing():
    db = get_db()
    if request.method == "POST":
        points_per_image = parse_int_field("points_per_image", minimum=0)
        mode = request.form.get("mode", "")
        resolution = request.form.get("resolution", "")
        enabled = 1 if request.form.get("enabled") == "on" else 0
        db.execute(
            "UPDATE pricing_rules SET points_per_image = ?, enabled = ? WHERE mode = ? AND resolution = ?",
            (points_per_image, enabled, mode, resolution),
        )
        db.commit()
        return redirect(url_for("admin.config_billing"))
    rules = db.execute("SELECT * FROM pricing_rules ORDER BY mode, resolution").fetchall()
    return render_template("admin/config_billing.html", rules=rules)


@bp.route("/config/packages", methods=("GET", "POST"))
@admin_required
def config_packages():
    db = get_db()
    if request.method == "POST":
        ...
    packages = db.execute("SELECT * FROM packages ORDER BY id DESC").fetchall()
    return render_template("admin/config_packages.html", packages=packages)
```

- [ ] **Step 4: 把旧计费/套餐路由改成兼容跳转**

```python
@bp.route("/pricing", methods=("GET", "POST"))
@admin_required
def pricing():
    return redirect(url_for("admin.config_billing"))


@bp.route("/packages", methods=("GET", "POST"))
@admin_required
def packages():
    return redirect(url_for("admin.config_packages"))
```

- [ ] **Step 5: 为统一计费页补统一说明文案**

```html
<!-- templates/admin/config_billing.html -->
{% extends "admin/layout.html" %}
{% block title %}计费规则 - 绘世{% endblock %}
{% block admin_content %}
<header class="page-hero">
  <span>Billing</span>
  <h1>计费规则</h1>
  <p>当前积分规则同时适用于工作台与画布，管理员只维护一套规则。</p>
</header>
{% for rule in rules %}
<form method="post" class="admin-row">
  <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
  <input type="hidden" name="mode" value="{{ rule['mode'] }}">
  <input type="hidden" name="resolution" value="{{ rule['resolution'] }}">
  <strong>{{ rule["mode"] }} {{ rule["resolution"] }}</strong>
  <input name="points_per_image" type="number" min="0" value="{{ rule['points_per_image'] }}">
  <label><input name="enabled" type="checkbox" {% if rule["enabled"] %}checked{% endif %}> 启用</label>
  <button type="submit">保存</button>
</form>
{% endfor %}
{% endblock %}
```

- [ ] **Step 6: 重新运行测试，确认通过**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_settings_config_status.py::test_admin_config_billing_page_renders tests/test_settings_config_status.py::test_legacy_admin_pricing_and_packages_redirect_to_config_center tests/test_package_defaults.py -v
```

Expected:

- 相关测试全部通过
- 默认套餐测试无回归

- [ ] **Step 7: 记录检查点**

```powershell
git add huishi/routes_admin.py templates/admin/config_billing.html templates/admin/config_packages.html templates/admin/pricing.html templates/admin/packages.html tests/test_settings_config_status.py tests/test_package_defaults.py
git commit -m "feat: unify billing and packages under config center"
```

---

### Task 4: 加固画布配置保存逻辑，并在统一后台中暴露正确状态

**Files:**
- Modify: `huishi/providers.py`
- Modify: `huishi/routes_admin.py`
- Modify: `huishi/routes_workspace.py`
- Modify: `tests/test_settings_config_status.py`
- Modify: `tests/test_workspace_generation_flow.py`

- [ ] **Step 1: 写失败测试，锁定画布地址校验与独立页回归**

```python
def test_canvas_app_url_rejects_non_http_value(tmp_path):
    from app import create_app
    from huishi.db import get_db, init_db

    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "test.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"
    with app.app_context():
        init_db()
        admin = get_db().execute("SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1").fetchone()

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = admin["id"]
        response = client.post(
            "/admin/config/settings",
            data={"csrf_token": "test", "canvas_app_url": "api.deepseek.com"},
        )

    assert response.status_code == 400


def test_canvas_page_still_renders_embedded_shell(app):
    app.config["CANVAS_APP_URL"] = "http://127.0.0.1:3000"
    with app.app_context():
        user_id = create_user()

    with app.test_client() as client:
        login(client, user_id)
        response = client.get("/canvas")

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "data-canvas-shell" in html
    assert "http://127.0.0.1:3000/canvas" in html
```

- [ ] **Step 2: 运行测试，确认先失败**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_settings_config_status.py::test_canvas_app_url_rejects_non_http_value tests/test_workspace_generation_flow.py::test_canvas_page_still_renders_embedded_shell -v
```

Expected:

- 非法 `canvas_app_url` 目前可能被保存

- [ ] **Step 3: 在画布配置保存逻辑里补 URL 校验**

```python
canvas_app_url = request.form.get("canvas_app_url", "").strip()
if canvas_app_url and not is_http_url(canvas_app_url):
    return "画布应用地址必须以 http:// 或 https:// 开头", 400

canvas_agent_url = request.form.get("canvas_agent_url", "").strip()
if canvas_agent_url and not is_http_url(canvas_agent_url):
    return "Agent/MCP 地址必须以 http:// 或 https:// 开头", 400
```

- [ ] **Step 4: 在配置页显示当前画布状态与入口**

```html
<article>
  <span>画布</span>
  <strong>{{ canvas_settings.get('canvas_app_url', '') or current_app.config.get('CANVAS_APP_URL', '') or '未配置' }}</strong>
  <small>资产导入与独立画布页都依赖这里的地址。</small>
</article>
```

- [ ] **Step 5: 重新运行测试，确认通过**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_settings_config_status.py::test_canvas_app_url_rejects_non_http_value tests/test_workspace_generation_flow.py::test_canvas_page_still_renders_embedded_shell tests/test_settings_config_status.py -q
```

Expected:

- 非法地址被 400 拒绝
- `/canvas` 独立页仍保持正常

- [ ] **Step 6: 记录检查点**

```powershell
git add huishi/providers.py huishi/routes_admin.py huishi/routes_workspace.py tests/test_settings_config_status.py tests/test_workspace_generation_flow.py
git commit -m "fix: harden canvas config validation"
```

---

### Task 5: 保持资产到画布桥接与统一入口的回归覆盖

**Files:**
- Modify: `templates/assets.html`
- Modify: `static/js/assets.js`
- Modify: `templates/canvas.html`
- Test: `tests/test_workspace_generation_flow.py`

- [ ] **Step 1: 写失败测试，锁定“发送到画布”与桥接握手标记**

```python
from pathlib import Path


def test_assets_template_has_send_to_canvas_button():
    template = Path("templates/assets.html").read_text(encoding="utf-8")
    assert "发送到画布" in template


def test_canvas_template_has_bridge_handshake():
    template = Path("templates/canvas.html").read_text(encoding="utf-8")
    assert "huishi-canvas-import" in template
    assert "huishi-canvas-ready" in template
    assert "huishi-canvas-ping" in template
```

- [ ] **Step 2: 运行测试，确认当前行为被锁定**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_workspace_generation_flow.py::test_assets_template_has_send_to_canvas_button tests/test_workspace_generation_flow.py::test_canvas_template_has_bridge_handshake -v
```

Expected:

- 如测试名不存在则先补到文件中
- 测试应对现有行为给出清晰保护

- [ ] **Step 3: 若名称或文案调整，保持 DOM 钩子不变**

```javascript
const canvasBridgeKey = "huishi.canvas.bridge";
const canvasBridgeTarget = "/canvas?mode=new";

sessionStorage.setItem(canvasBridgeKey, JSON.stringify({ type: "huishi-canvas-bridge", assets }));
window.location.href = canvasBridgeTarget;
```

```javascript
frame.contentWindow.postMessage({ type: "huishi-canvas-import", payload }, "*");
if ((event.data || {}).type !== "huishi-canvas-ready") return;
frame.contentWindow.postMessage({ type: "huishi-canvas-ping" }, "*");
```

- [ ] **Step 4: 运行工作台相关回归测试**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_workspace_generation_flow.py -q
```

Expected:

- 工作台、画布页、导航顺序和桥接相关测试全部通过

- [ ] **Step 5: 记录检查点**

```powershell
git add templates/assets.html static/js/assets.js templates/canvas.html tests/test_workspace_generation_flow.py
git commit -m "test: lock asset to canvas bridge behavior"
```

---

### Task 6: 全量回归与交付核对

**Files:**
- Test only: `tests/test_settings_config_status.py`
- Test only: `tests/test_package_defaults.py`
- Test only: `tests/test_workspace_generation_flow.py`

- [ ] **Step 1: 运行目标测试集**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_settings_config_status.py tests/test_package_defaults.py tests/test_workspace_generation_flow.py -q
```

Expected:

- 全部通过
- 不出现新增失败

- [ ] **Step 2: 做人工检查清单**

逐项确认：

- `/admin/config` 可打开
- `/admin/config/settings` 可编辑 Provider、画布、SMTP
- `/admin/config/billing` 明确说明“一套规则同时适用于工作台与画布”
- `/admin/config/packages` 可维护套餐说明
- `/settings` 会跳到新的后台配置页
- `/admin/pricing` 和 `/admin/packages` 会跳到新的配置中心子页
- `/canvas` 仍然是独立页
- `/assets` 仍然有“发送到画布”

- [ ] **Step 3: 记录最终检查点**

```powershell
git add huishi/routes_admin.py huishi/routes_workspace.py huishi/providers.py templates/admin/layout.html templates/admin/config_center.html templates/admin/config_settings.html templates/admin/config_billing.html templates/admin/config_packages.html templates/settings.html templates/canvas.html templates/assets.html static/js/assets.js tests/test_settings_config_status.py tests/test_package_defaults.py tests/test_workspace_generation_flow.py
git commit -m "feat: unify canvas config and billing management"
```

---

## 计划自检

### 设计覆盖检查

本计划覆盖了设计文档中的核心要求：

- 统一后台入口：Task 1
- 统一配置页与旧设置入口兼容：Task 2
- 统一计费与套餐说明：Task 3
- 画布配置统一管理并校验：Task 4
- 资产到画布桥接保留：Task 5
- 回归与验收：Task 6

### 占位符检查

已避免使用：

- “待定”
- “后续再补”
- “后续补充”
- “类似前面实现”

### 类型与命名一致性检查

计划中的关键标识保持一致：

- 配置路由：`/admin/config`
- 设置子页：`/admin/config/settings`
- 计费子页：`/admin/config/billing`
- 套餐子页：`/admin/config/packages`
- 画布桥接键：`huishi.canvas.bridge`
- 画布握手消息：`huishi-canvas-ping` / `huishi-canvas-ready` / `huishi-canvas-import`
