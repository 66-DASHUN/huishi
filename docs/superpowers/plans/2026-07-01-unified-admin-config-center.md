# 统一后台配置中心实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**目标：** 把 API Key、Base URL、模型、SMTP、计费标准和套餐管理收拢到一个统一的后台配置中心，同时保留旧页面和旧路由兼容。

**架构：** 以现有 Flask 管理后台为基础，新增一个统一的“配置中心”入口页，把分散在 `/settings`、`/admin/pricing`、`/admin/packages` 的配置项集中展示和编辑。底层继续沿用当前数据库表与存储逻辑，只做视图层整合和提交路径收敛；旧路由保留跳转或重定向，避免现有链接失效。这样可以先统一管理体验，再决定以后是否进一步拆分数据模型。

**技术栈：** Flask、Jinja2、SQLite、原生 JS、CSS、pytest。

---

### 任务 1：梳理并暴露统一配置中心所需的后端数据

**Files:**
- 修改：`D:/AI/huishihuabu/huishi/routes_workspace.py`
- 修改：`D:/AI/huishihuabu/huishi/providers.py`
- 测试：`D:/AI/huishihuabu/tests/test_settings_config_status.py`
- 测试：`D:/AI/huishihuabu/tests/test_provider_scheduling.py`

- [ ] **步骤 1：先写失败测试**

```python
def test_settings_page_exposes_all_unified_config_sections(tmp_path):
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
    assert "统一配置中心" in body
    assert "生图配置" in body
    assert "提示词优化" in body
    assert "SMTP 验证" in body
    assert "计费规则" in body
    assert "套餐管理" in body
```

- [ ] **步骤 2：运行测试，确认它先失败**

运行：`python -m pytest tests/test_settings_config_status.py::test_settings_page_exposes_all_unified_config_sections -v`
预期：失败，因为页面还没有统一配置中心的结构。

- [ ] **步骤 3：写最小实现**

```python
# huishi/routes_workspace.py
@bp.get("/settings")
@admin_required
def settings():
    db = get_db()
    settings_values = get_app_settings()
    image_providers = provider_store.list_providers("image")
    prompt_providers = provider_store.list_providers("prompt")
    pricing_rules = db.execute("SELECT * FROM pricing_rules ORDER BY mode, resolution").fetchall()
    packages = db.execute("SELECT * FROM packages ORDER BY id DESC").fetchall()
    return render_template(
        "settings.html",
        image_providers=image_providers,
        prompt_providers=prompt_providers,
        pricing_rules=pricing_rules,
        packages=packages,
        # existing settings context stays intact
    )
```

```python
# huishi/providers.py
def settings_config_snapshot() -> dict[str, object]:
    return {
        "image_providers": list_providers("image"),
        "prompt_providers": list_providers("prompt"),
        "settings": get_app_settings(),
    }
```

- [ ] **步骤 4：运行测试，确认通过**

运行：`python -m pytest tests/test_settings_config_status.py::test_settings_page_exposes_all_unified_config_sections -v`
预期：通过，页面能拿到统一配置中心所需的数据。

- [ ] **步骤 5：提交**

```bash
git add D:/AI/huishihuabu/huishi/routes_workspace.py D:/AI/huishihuabu/huishi/providers.py D:/AI/huishihuabu/tests/test_settings_config_status.py
git commit -m "feat: expose unified config center data"
```

### 任务 2：把设置页改造成统一配置中心

**Files:**
- 修改：`D:/AI/huishihuabu/templates/settings.html`
- 修改：`D:/AI/huishihuabu/static/css/site.css`
- 修改：`D:/AI/huishihuabu/static/js/settings.js`
- 测试：`D:/AI/huishihuabu/tests/test_settings_config_status.py`

- [ ] **步骤 1：先写失败测试**

```python
def test_settings_page_uses_unified_config_center_navigation(tmp_path):
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
    assert 'href="#section-image"' in body
    assert 'href="#section-prompt"' in body
    assert 'href="#section-smtp"' in body
    assert 'href="#section-billing"' in body
    assert 'href="#section-packages"' in body
```

- [ ] **步骤 2：运行测试，确认它先失败**

运行：`python -m pytest tests/test_settings_config_status.py::test_settings_page_uses_unified_config_center_navigation -v`
预期：失败，因为设置页还没有统一导航锚点。

- [ ] **步骤 3：写最小实现**

```html
<!-- templates/settings.html -->
<header class="page-hero settings-console-hero">
  <div class="settings-hero-head">
    <div>
      <span>统一配置中心</span>
      <h1>配置中心</h1>
    </div>
    <nav class="settings-hero-actions">
      <a href="#section-image">生图</a>
      <a href="#section-prompt">提示词</a>
      <a href="#section-smtp">SMTP</a>
      <a href="#section-billing">计费</a>
      <a href="#section-packages">套餐</a>
    </nav>
  </div>
</header>
```

```javascript
// static/js/settings.js
document.querySelectorAll(".settings-hero-actions a").forEach((link) => {
  link.addEventListener("click", () => {
    // keep anchor navigation but make the page feel deliberate
    document.documentElement.classList.add("is-jumping-to-section");
  });
});
```

- [ ] **步骤 4：运行测试，确认通过**

运行：`python -m pytest tests/test_settings_config_status.py::test_settings_page_uses_unified_config_center_navigation -v`
预期：通过，统一导航已出现。

- [ ] **步骤 5：提交**

```bash
git add D:/AI/huishihuabu/templates/settings.html D:/AI/huishihuabu/static/css/site.css D:/AI/huishihuabu/static/js/settings.js D:/AI/huishihuabu/tests/test_settings_config_status.py
git commit -m "feat: unify admin configuration center"
```

### 任务 3：把计费规则和套餐管理并入同一配置中心页面

**Files:**
- 修改：`D:/AI/huishihuabu/huishi/routes_admin.py`
- 修改：`D:/AI/huishihuabu/templates/admin/pricing.html`
- 修改：`D:/AI/huishihuabu/templates/admin/packages.html`
- 测试：`D:/AI/huishihuabu/tests/test_package_defaults.py`

- [ ] **步骤 1：先写失败测试**

```python
def test_admin_pricing_and_packages_have_shared_config_entrypoints():
    pricing = Path("templates/admin/pricing.html").read_text(encoding="utf-8")
    packages = Path("templates/admin/packages.html").read_text(encoding="utf-8")
    assert "配置中心" in pricing
    assert "配置中心" in packages
    assert 'href="/settings#section-billing"' in pricing or 'href="/admin/config#billing"' in pricing
    assert 'href="/settings#section-packages"' in packages or 'href="/admin/config#packages"' in packages
```

- [ ] **步骤 2：运行测试，确认它先失败**

运行：`python -m pytest tests/test_package_defaults.py::test_admin_pricing_and_packages_have_shared_config_entrypoints -v`
预期：失败，因为计费和套餐页还没有统一入口提示。

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
        providers=provider_store.list_providers(),
        settings_values=provider_store.get_app_settings(),
    )
```

```html
<!-- templates/admin/pricing.html -->
<a href="/admin/config#billing">返回统一配置中心</a>

<!-- templates/admin/packages.html -->
<a href="/admin/config#packages">返回统一配置中心</a>
```

- [ ] **步骤 4：运行测试，确认通过**

运行：`python -m pytest tests/test_package_defaults.py::test_admin_pricing_and_packages_have_shared_config_entrypoints -v`
预期：通过，旧页面指向统一入口。

- [ ] **步骤 5：提交**

```bash
git add D:/AI/huishihuabu/huishi/routes_admin.py D:/AI/huishihuabu/templates/admin/pricing.html D:/AI/huishihuabu/templates/admin/packages.html D:/AI/huishihuabu/tests/test_package_defaults.py
git commit -m "feat: add shared admin config entrypoints"
```

### 任务 4：保留旧设置页和旧计费页的兼容跳转

**Files:**
- 修改：`D:/AI/huishihuabu/huishi/routes_workspace.py`
- 修改：`D:/AI/huishihuabu/huishi/routes_admin.py`
- 测试：`D:/AI/huishihuabu/tests/test_settings_config_status.py`

- [ ] **步骤 1：先写失败测试**

```python
def test_legacy_settings_and_pricing_routes_redirect_to_unified_center(app):
    with app.app_context():
        user_id = create_user()

    with app.test_client() as client:
        login(client, user_id)
        settings_response = client.get("/settings", follow_redirects=False)
        pricing_response = client.get("/admin/pricing", follow_redirects=False)

    assert settings_response.status_code in {200, 302}
    assert pricing_response.status_code in {200, 302}
```

- [ ] **步骤 2：运行测试，确认它先失败**

运行：`python -m pytest tests/test_settings_config_status.py::test_legacy_settings_and_pricing_routes_redirect_to_unified_center -v`
预期：失败，因为旧路由还没处理统一入口跳转。

- [ ] **步骤 3：写最小实现**

```python
# huishi/routes_workspace.py
@bp.get("/settings")
@admin_required
def settings():
    if request.args.get("legacy") == "1":
        return render_template("settings.html", legacy_mode=True)
    return redirect(url_for("admin.config_center"))

# huishi/routes_admin.py
@bp.get("/pricing")
@admin_required
def pricing():
    return redirect(url_for("admin.config_center", section="billing"))

@bp.get("/packages")
@admin_required
def packages():
    return redirect(url_for("admin.config_center", section="packages"))
```

- [ ] **步骤 4：运行测试，确认通过**

运行：`python -m pytest tests/test_settings_config_status.py::test_legacy_settings_and_pricing_routes_redirect_to_unified_center -v`
预期：通过，旧入口可以跳转到统一配置中心。

- [ ] **步骤 5：提交**

```bash
git add D:/AI/huishihuabu/huishi/routes_workspace.py D:/AI/huishihuabu/huishi/routes_admin.py D:/AI/huishihuabu/tests/test_settings_config_status.py
git commit -m "feat: preserve legacy config routes"
```

### 任务 5：验证统一配置中心在页面、权限和保存逻辑上可用

**Files:**
- 测试：`D:/AI/huishihuabu/tests/test_settings_config_status.py`
- 测试：`D:/AI/huishihuabu/tests/test_provider_scheduling.py`

- [ ] **步骤 1：写端到端冒烟测试**

```python
def test_unified_config_center_smoke(tmp_path):
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
    assert "统一配置中心" in body
    assert "计费规则" in body
    assert "套餐管理" in body
```

- [ ] **步骤 2：运行统一测试套件**

运行：`python -m pytest tests/test_settings_config_status.py tests/test_provider_scheduling.py tests/test_package_defaults.py -v`
预期：全部通过，统一配置中心和旧逻辑都能工作。

- [ ] **步骤 3：提交**

```bash
git add D:/AI/huishihuabu/tests/test_settings_config_status.py D:/AI/huishihuabu/tests/test_provider_scheduling.py D:/AI/huishihuabu/tests/test_package_defaults.py
git commit -m "test: cover unified admin config center"
```

**自检清单**
- 所有 API / Base URL / 模型 / SMTP / 计费 / 套餐都能在一个入口里管理。
- 旧 `/settings`、`/admin/pricing`、`/admin/packages` 仍然可访问，不会把老链接直接弄坏。
- 后端仍然沿用现有数据表，迁移风险低。
- 页面结构统一，但不强制立刻重构数据模型。
