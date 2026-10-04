# 画布接入与统一配置中心实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**目标：** 在现有 Flask 项目里新增独立画布页和左侧“画布”入口，同时把画布相关配置统一到现有管理后台的配置中心里，并兼容现有资产、计费和管理页面。

**架构：** 画布仍保持为独立应用形态，由 `/canvas` 作为入口页承载；现有工作台只负责提供按钮、资产导入入口和配置数据。所有画布连接信息、Agent/MCP、本地启动参数、默认模板都存入数据库并由管理员在配置中心修改。计费规则继续沿用现有按分辨率/模式扣积分逻辑，但在统一配置中心里提供同一组管理入口和跳转。

**技术栈：** Flask、Jinja2、SQLite、原生 JS、CSS、pytest、现有 `app_settings` / `pricing_rules` / `packages` 表。

---

### 任务 1：新增左侧“画布”按钮和独立画布页

**Files:**
- 修改：`D:/AI/huishihuabu/templates/partials/studio_nav.html`
- 修改：`D:/AI/huishihuabu/app.py`
- 修改：`D:/AI/huishihuabu/huishi/routes_workspace.py`
- 新增：`D:/AI/huishihuabu/templates/canvas.html`
- 修改：`D:/AI/huishihuabu/static/css/site.css`
- 测试：`D:/AI/huishihuabu/tests/test_workspace_generation_flow.py`

- [ ] **步骤 1：先写失败测试**

```python
def test_workspace_nav_has_canvas_button_before_assets():
    template = Path("templates/partials/studio_nav.html").read_text(encoding="utf-8")
    assert template.index("画布") < template.index("资产")


def test_canvas_route_renders_canvas_shell(app):
    with app.app_context():
        user_id = create_user()

    with app.test_client() as client:
        login(client, user_id)
        response = client.get("/canvas")

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'data-canvas-shell' in html
    assert '<iframe' in html
```

- [ ] **步骤 2：运行测试，确认它先失败**

运行：`python -m pytest tests/test_workspace_generation_flow.py::test_workspace_nav_has_canvas_button_before_assets tests/test_workspace_generation_flow.py::test_canvas_route_renders_canvas_shell -v`
预期：失败，因为按钮和 `/canvas` 页面还不存在。

- [ ] **步骤 3：写最小实现**

```html
<!-- templates/partials/studio_nav.html -->
<nav class="rail-nav" aria-label="创作导航">
  <a class="rail-nav-item" href="/canvas" title="画布">画布</a>
  <a class="rail-nav-item" href="/workspace" title="生成">生成</a>
  <a class="rail-nav-item" href="/assets" title="资产">资产</a>
</nav>
```

```python
# huishi/routes_workspace.py
@bp.get("/canvas")
@login_required
def canvas_page():
    canvas_app_url = str(current_app.config.get("CANVAS_APP_URL") or "").rstrip("/")
    return render_template(
        "canvas.html",
        canvas_app_url=canvas_app_url,
        canvas_embed_url=f"{canvas_app_url}/canvas" if canvas_app_url else "",
    )
```

```html
<!-- templates/canvas.html -->
<main class="canvas-shell" data-canvas-shell>
  <header class="canvas-shell-header">
    <h1>画布</h1>
    <a href="/assets">从资产导入</a>
  </header>
  <iframe class="canvas-frame" src="{{ canvas_embed_url }}" title="画布"></iframe>
</main>
```

- [ ] **步骤 4：运行测试，确认通过**

运行：`python -m pytest tests/test_workspace_generation_flow.py::test_workspace_nav_has_canvas_button_before_assets tests/test_workspace_generation_flow.py::test_canvas_route_renders_canvas_shell -v`
预期：通过，左侧栏出现“画布”按钮且 `/canvas` 页面可打开。

- [ ] **步骤 5：提交**

```bash
git add D:/AI/huishihuabu/templates/partials/studio_nav.html D:/AI/huishihuabu/app.py D:/AI/huishihuabu/huishi/routes_workspace.py D:/AI/huishihuabu/templates/canvas.html D:/AI/huishihuabu/static/css/site.css D:/AI/huishihuabu/tests/test_workspace_generation_flow.py
git commit -m "feat: add canvas entry and canvas page"
```

### 任务 2：把画布配置统一到管理配置中心并保存在数据库

**Files:**
- 修改：`D:/AI/huishihuabu/huishi/providers.py`
- 修改：`D:/AI/huishihuabu/huishi/routes_workspace.py`
- 修改：`D:/AI/huishihuabu/templates/settings.html`
- 修改：`D:/AI/huishihuabu/static/js/settings.js`
- 修改：`D:/AI/huishihuabu/static/css/site.css`
- 测试：`D:/AI/huishihuabu/tests/test_settings_config_status.py`

- [ ] **步骤 1：先写失败测试**

```python
def test_settings_page_shows_canvas_config_section(tmp_path):
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
        response = client.get("/settings")

    body = response.get_data(as_text=True)
    assert "画布配置" in body
    assert "画布应用地址" in body
    assert "Agent/MCP" in body
    assert "本地启动参数" in body
    assert "默认模板" in body
```

- [ ] **步骤 2：运行测试，确认它先失败**

运行：`python -m pytest tests/test_settings_config_status.py::test_settings_page_shows_canvas_config_section -v`
预期：失败，因为设置页还没有画布配置区。

- [ ] **步骤 3：写最小实现**

```python
# huishi/providers.py
def get_canvas_settings() -> dict[str, str]:
    return get_app_settings(
        "canvas_app_url",
        "canvas_agent_url",
        "canvas_agent_token",
        "canvas_local_start_cmd",
        "canvas_default_template",
    )

def save_canvas_setting(key: str, value: str) -> None:
    if key not in {"canvas_app_url", "canvas_agent_url", "canvas_agent_token", "canvas_local_start_cmd", "canvas_default_template"}:
        raise ValueError("unsupported canvas setting")
    save_app_setting(key, value)
```

```python
# huishi/routes_workspace.py
@bp.route("/settings", methods=("GET", "POST"))
@admin_required
def settings():
    settings_values = get_app_settings()
    canvas_settings = provider_store.get_canvas_settings()
    if request.method == "POST":
        provider_store.save_canvas_setting("canvas_app_url", request.form.get("canvas_app_url", "").strip())
        provider_store.save_canvas_setting("canvas_agent_url", request.form.get("canvas_agent_url", "").strip())
        provider_store.save_canvas_setting("canvas_agent_token", request.form.get("canvas_agent_token", "").strip())
        provider_store.save_canvas_setting("canvas_local_start_cmd", request.form.get("canvas_local_start_cmd", "").strip())
        provider_store.save_canvas_setting("canvas_default_template", request.form.get("canvas_default_template", "").strip())
        get_db().commit()
        return redirect(url_for("workspace.settings"))
    return render_template("settings.html", canvas_settings=canvas_settings, settings_values=settings_values)
```

```html
<!-- templates/settings.html -->
<details class="settings-panel" id="settings-canvas" open>
  <summary class="settings-panel-head">
    <span class="settings-panel-title"><strong>画布配置</strong></span>
  </summary>
  <div class="settings-panel-body">
    <label><span>画布应用地址</span><input name="canvas_app_url" value="{{ canvas_settings.get('canvas_app_url', '') }}"></label>
    <label><span>Agent/MCP 地址</span><input name="canvas_agent_url" value="{{ canvas_settings.get('canvas_agent_url', '') }}"></label>
    <label><span>Agent Token</span><input name="canvas_agent_token" type="password" value=""></label>
    <label><span>本地启动参数</span><textarea name="canvas_local_start_cmd">{{ canvas_settings.get('canvas_local_start_cmd', '') }}</textarea></label>
    <label><span>默认模板</span><textarea name="canvas_default_template">{{ canvas_settings.get('canvas_default_template', '') }}</textarea></label>
  </div>
</details>
```

- [ ] **步骤 4：运行测试，确认通过**

运行：`python -m pytest tests/test_settings_config_status.py::test_settings_page_shows_canvas_config_section -v`
预期：通过，画布配置能从数据库读写并显示在管理页。

- [ ] **步骤 5：提交**

```bash
git add D:/AI/huishihuabu/huishi/providers.py D:/AI/huishihuabu/huishi/routes_workspace.py D:/AI/huishihuabu/templates/settings.html D:/AI/huishihuabu/static/js/settings.js D:/AI/huishihuabu/static/css/site.css D:/AI/huishihuabu/tests/test_settings_config_status.py
git commit -m "feat: add canvas config center"
```

### 任务 3：打通资产库到画布的手动导入

**Files:**
- 修改：`D:/AI/huishihuabu/huishi/routes_workspace.py`
- 修改：`D:/AI/huishihuabu/templates/assets.html`
- 修改：`D:/AI/huishihuabu/static/js/assets.js`
- 修改：`D:/AI/huishihuabu/templates/canvas.html`
- 修改：`D:/AI/huishihuabu/static/js/workspace.js`
- 测试：`D:/AI/huishihuabu/tests/test_asset_detail_actions.py`
- 测试：`D:/AI/huishihuabu/tests/test_workspace_generation_flow.py`

- [ ] **步骤 1：先写失败测试**

```python
def test_assets_page_has_send_to_canvas_action():
    template = Path("templates/assets.html").read_text(encoding="utf-8")
    assert "发送到画布" in template


def test_canvas_page_accepts_asset_payload():
    source = Path("templates/canvas.html").read_text(encoding="utf-8")
    assert "data-canvas-import" in source
    assert "拖拽" in source
```

- [ ] **步骤 2：运行测试，确认它先失败**

运行：`python -m pytest tests/test_asset_detail_actions.py::test_assets_page_has_send_to_canvas_action tests/test_workspace_generation_flow.py::test_canvas_page_accepts_asset_payload -v`
预期：失败，因为资产页和画布页还没有导入入口。

- [ ] **步骤 3：写最小实现**

```html
<!-- templates/assets.html -->
<button type="button" data-send-to-canvas>发送到画布</button>
<button type="button" data-open-canvas>在画布中打开</button>
```

```javascript
// static/js/assets.js
document.querySelectorAll("[data-send-to-canvas]").forEach((button) => {
  button.addEventListener("click", () => {
    const payload = collectSelectedAssetUrls();
    sessionStorage.setItem("huishi.canvas.import", JSON.stringify(payload));
    window.open("/canvas", "_blank", "noopener");
  });
});
```

```html
<!-- templates/canvas.html -->
<section class="canvas-import-panel" data-canvas-import>
  <p>把资产拖到这里，或点击“导入资产”。</p>
  <button type="button" data-import-from-storage>导入资产</button>
</section>
```

```javascript
// static/js/workspace.js
function importAssetsIntoCanvas() {
  const raw = sessionStorage.getItem("huishi.canvas.import");
  if (!raw) return;
  const assets = JSON.parse(raw);
  sessionStorage.removeItem("huishi.canvas.import");
  // forward assets into canvas bootstrap state
}
```

- [ ] **步骤 4：运行测试，确认通过**

运行：`python -m pytest tests/test_asset_detail_actions.py::test_assets_page_has_send_to_canvas_action tests/test_workspace_generation_flow.py::test_canvas_page_accepts_asset_payload -v`
预期：通过，资产页能把素材手动送到画布，画布页能接收。

- [ ] **步骤 5：提交**

```bash
git add D:/AI/huishihuabu/huishi/routes_workspace.py D:/AI/huishihuabu/templates/assets.html D:/AI/huishihuabu/static/js/assets.js D:/AI/huishihuabu/templates/canvas.html D:/AI/huishihuabu/static/js/workspace.js D:/AI/huishihuabu/tests/test_asset_detail_actions.py D:/AI/huishihuabu/tests/test_workspace_generation_flow.py
git commit -m "feat: bridge assets to canvas"
```

### 任务 4：把计费标准和套餐管理收进统一管理菜单，并保留旧入口兼容

**Files:**
- 修改：`D:/AI/huishihuabu/templates/admin/layout.html`
- 新增：`D:/AI/huishihuabu/templates/admin/config_center.html`
- 修改：`D:/AI/huishihuabu/huishi/routes_admin.py`
- 修改：`D:/AI/huishihuabu/templates/admin/pricing.html`
- 修改：`D:/AI/huishihuabu/templates/admin/packages.html`
- 测试：`D:/AI/huishihuabu/tests/test_settings_config_status.py`
- 测试：`D:/AI/huishihuabu/tests/test_package_defaults.py`

- [ ] **步骤 1：先写失败测试**

```python
def test_admin_menu_has_config_center_and_legacy_redirects():
    layout = Path("templates/admin/layout.html").read_text(encoding="utf-8")
    assert "配置中心" in layout
    assert 'href="/admin/config"' in layout


def test_pricing_and_packages_redirect_to_config_center(tmp_path):
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
        pricing = client.get("/admin/pricing", follow_redirects=False)
        packages = client.get("/admin/packages", follow_redirects=False)

    assert pricing.status_code in {200, 302}
    assert packages.status_code in {200, 302}
```

- [ ] **步骤 2：运行测试，确认它先失败**

运行：`python -m pytest tests/test_settings_config_status.py::test_admin_menu_has_config_center_and_legacy_redirects tests/test_settings_config_status.py::test_pricing_and_packages_redirect_to_config_center -v`
预期：失败，因为统一后台菜单和旧入口兼容还没接上。

- [ ] **步骤 3：写最小实现**

```python
# huishi/routes_admin.py
@bp.get("/config")
@admin_required
def config_center():
    db = get_db()
    return render_template(
        "admin/config_center.html",
        rules=db.execute("SELECT * FROM pricing_rules ORDER BY mode, resolution").fetchall(),
        packages=db.execute("SELECT * FROM packages ORDER BY id DESC").fetchall(),
        canvas_settings=provider_store.get_canvas_settings(),
    )

@bp.get("/pricing")
@admin_required
def pricing():
    return redirect(url_for("admin.config_center", section="billing"))

@bp.get("/packages")
@admin_required
def packages():
    return redirect(url_for("admin.config_center", section="packages"))
```

```html
<!-- templates/admin/layout.html -->
<a href="/admin/config">配置中心</a>
<a href="/admin/config?section=billing">计费</a>
<a href="/admin/config?section=packages">套餐</a>
```

```html
<!-- templates/admin/config_center.html -->
<section class="config-center-shell">
  <nav class="config-center-nav">
    <a href="#canvas">画布配置</a>
    <a href="#billing">计费规则</a>
    <a href="#packages">套餐管理</a>
  </nav>
</section>
```

- [ ] **步骤 4：运行测试，确认通过**

运行：`python -m pytest tests/test_settings_config_status.py::test_admin_menu_has_config_center_and_legacy_redirects tests/test_settings_config_status.py::test_pricing_and_packages_redirect_to_config_center -v`
预期：通过，统一管理菜单可用，旧页面仍兼容。

- [ ] **步骤 5：提交**

```bash
git add D:/AI/huishihuabu/templates/admin/layout.html D:/AI/huishihuabu/templates/admin/config_center.html D:/AI/huishihuabu/huishi/routes_admin.py D:/AI/huishihuabu/templates/admin/pricing.html D:/AI/huishihuabu/templates/admin/packages.html D:/AI/huishihuabu/tests/test_settings_config_status.py D:/AI/huishihuabu/tests/test_package_defaults.py
git commit -m "feat: unify admin config and billing entrypoints"
```

### 任务 5：端到端验证画布、配置中心和资产桥接

**Files:**
- 测试：`D:/AI/huishihuabu/tests/test_workspace_generation_flow.py`
- 测试：`D:/AI/huishihuabu/tests/test_settings_config_status.py`
- 测试：`D:/AI/huishihuabu/tests/test_provider_scheduling.py`
- 测试：`D:/AI/huishihuabu/tests/test_package_defaults.py`

- [ ] **步骤 1：写端到端冒烟测试**

```python
def test_canvas_and_config_center_smoke(app):
    with app.app_context():
        user_id = create_user()

    with app.test_client() as client:
        login(client, user_id)
        canvas = client.get("/canvas")
        settings = client.get("/settings")
        config = client.get("/admin/config")

    assert canvas.status_code == 200
    assert settings.status_code in {200, 302}
    assert config.status_code in {200, 302}
```

- [ ] **步骤 2：运行目标测试套件**

运行：`python -m pytest tests/test_workspace_generation_flow.py tests/test_settings_config_status.py tests/test_provider_scheduling.py tests/test_package_defaults.py -v`
预期：全部通过，画布、配置中心和计费兼容都能工作。

- [ ] **步骤 3：提交**

```bash
git add D:/AI/huishihuabu/tests/test_workspace_generation_flow.py D:/AI/huishihuabu/tests/test_settings_config_status.py D:/AI/huishihuabu/tests/test_provider_scheduling.py D:/AI/huishihuabu/tests/test_package_defaults.py
git commit -m "test: cover canvas integration and unified config center"
```

**自检清单**
- 左侧栏新增“画布”按钮，并且在“资产”上方。
- `/canvas` 是独立入口，不会改坏现有工作台。
- 画布配置保存到数据库，由管理员在页面里修改。
- 资产可以手动送入画布，支持拖拽和点击。
- 计费标准沿用现有规则，但统一在管理菜单里可见、可编辑。
- 旧设置页和旧计费页保留兼容入口，不直接断链。
