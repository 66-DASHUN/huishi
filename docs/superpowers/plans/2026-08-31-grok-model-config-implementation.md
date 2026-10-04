# Grok 与新增生图模型配置 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不影响现有渠道和图片资源的前提下，完成 Grok/Nano Banana 模型配置、独立计费、系统配置页布局优化和管理员新增用户。

**Architecture:** 以 `huishi.providers.IMAGE_MODEL_CATALOG` 作为协议驱动的唯一模型元数据源，模板和 JavaScript 从该目录生成选择器与能力提示；数据库启动迁移负责旧 Grok ID 和价格规则的幂等兼容。管理员用户创建复用现有权限、审计、哈希和事务模式。

**Tech Stack:** Flask、Jinja2、SQLite/PostgreSQL、Werkzeug password hashing、原生 JavaScript/CSS、pytest、Docker Compose/SSH 部署。

---

## 文件与职责映射

- `huishi/providers.py`：官方模型目录、显示名称、默认 URL、能力元数据、模型/协议规范化。
- `huishi/image_api.py`：按协议和模型能力路由 Grok、Nano Banana、OpenAI 兼容请求。
- `huishi/routes_workspace.py`：Provider 表单解析和服务端模型/分辨率校验。
- `huishi/db.py`：启动迁移、默认计费规则、旧 Grok 记录合并。
- `huishi/routes_admin.py`：系统配置、价格规则和管理员用户创建路由。
- `templates/admin/_config_settings_panels.html`：Provider 和系统配置表格/对话框。
- `templates/admin/config_billing.html`：模型×分辨率价格表。
- `templates/admin/users.html`：用户列表和新增用户表单。
- `static/js/settings.js`：协议/模型联动、默认 URL/分辨率和自定义 ID 展开。
- `static/css/site.css`：配置页、价格表和新增用户表单的响应式布局。
- `tests/test_image_provider_formats.py`、`tests/test_generation_billing.py`、`tests/test_settings_config_status.py`、`tests/test_admin_ui_structure.py`：现有回归覆盖。
- 新增 `tests/test_grok_model_config.py`、`tests/test_model_migrations.py`、`tests/test_admin_create_user.py`：本次行为的独立测试。

## Task 1: 建立协议驱动的模型目录和 Provider 校验

**Files:**
- Modify: `huishi/providers.py`
- Modify: `huishi/routes_workspace.py:277-304`
- Modify: `huishi/image_api.py:576-704`
- Test: `tests/test_grok_model_config.py`
- Test: `tests/test_image_provider_formats.py`

- [ ] **Step 1: Write failing catalog tests**

```python
def test_grok_catalog_exposes_only_imagine_2():
    from huishi.providers import image_model_options, image_model_label

    assert image_model_options("grok") == [
        {"id": "grok-imagine-image-2.0", "label": "grok-imagine 2.0"}
    ]
    assert image_model_label("grok-imagine-image-2.0") == "grok-imagine 2.0"


def test_banana_catalog_keeps_two_official_models():
    from huishi.providers import image_model_options

    assert image_model_options("banana") == [
        {"id": "gemini-3.1-flash-image", "label": "Nano Banana 2"},
        {"id": "gemini-3-pro-image", "label": "Nano Banana Pro"},
    ]
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run: `pytest -q tests/test_grok_model_config.py tests/test_image_provider_formats.py`

Expected: FAIL because the current Grok catalog still exposes two non-official IDs and no complete model capability metadata exists.

- [ ] **Step 3: Implement the catalog metadata**

Replace the Grok catalog tuple with one entry and add a metadata mapping keyed by model ID. Keep custom IDs accepted only when the explicit custom-model path is used. The metadata must expose `default_base_url`, `resolutions`, `generate_path`, and `edit_path` for Grok and Banana.

```python
IMAGE_MODEL_CATALOG["grok"] = (
    {"id": "grok-imagine-image-2.0", "label": "grok-imagine 2.0"},
)
IMAGE_MODEL_METADATA = {
    "grok-imagine-image-2.0": {
        "api_format": "grok",
        "default_base_url": "https://api.x.ai/v1",
        "resolutions": ("1K", "2K"),
        "generate_path": "/v1/images/generations",
        "edit_path": "/v1/images/edits",
    },
    "gemini-3.1-flash-image": {
        "api_format": "banana",
        "default_base_url": "https://generativelanguage.googleapis.com",
        "resolutions": ("1K", "2K", "4K"),
        "generate_path": "/v1beta/interactions",
    },
    "gemini-3-pro-image": {
        "api_format": "banana",
        "default_base_url": "https://generativelanguage.googleapis.com",
        "resolutions": ("1K", "2K", "4K"),
        "generate_path": "/v1beta/interactions",
    },
}
```

Add helpers with these stable signatures and concrete behavior:

```python
def image_model_metadata(model: object, api_format: object = "openai") -> dict[str, object]:
    normalized_model = str(model or "").strip()
    normalized_format = str(api_format or "openai").strip().lower()
    for option in IMAGE_MODEL_CATALOG.get(normalized_format, ()):
        if option["id"] == normalized_model:
            return dict(IMAGE_MODEL_METADATA.get(normalized_model, {}))
    return {}


def default_image_base_url(api_format: object, model: object = "") -> str:
    metadata = image_model_metadata(model, api_format)
    if metadata.get("default_base_url"):
        return str(metadata["default_base_url"])
    return {
        "grok": "https://api.x.ai/v1",
        "gemini": "https://generativelanguage.googleapis.com",
        "banana": "https://generativelanguage.googleapis.com",
    }.get(str(api_format or "openai").strip().lower(), "")


def supported_image_resolutions(api_format: object, model: object = "") -> tuple[str, ...]:
    metadata = image_model_metadata(model, api_format)
    if metadata.get("resolutions"):
        return tuple(str(value) for value in metadata["resolutions"])
    return tuple(DEFAULT_IMAGE_PROVIDER_RESOLUTIONS)
```

- [ ] **Step 4: Enforce model and resolution rules in form parsing**

In `parse_provider_form`, normalize the posted model, reject a known model paired with the wrong protocol, and intersect posted resolutions with `supported_image_resolutions`. For Grok, reject a request that has only unsupported resolutions instead of silently enabling 4K. Preserve the explicit custom-model path and allow its posted resolution set unchanged except for the protocol-level safety limit.

- [ ] **Step 5: Route API calls through metadata without changing OpenAI behavior**

Keep the existing Grok generations/edits and Banana interactions serializers. Use metadata for default paths and capability checks, and retain current error redaction. Add tests asserting the exact URL suffixes and that Grok 4K returns a configuration error before an HTTP request.

- [ ] **Step 6: Run focused tests**

Run: `pytest -q tests/test_grok_model_config.py tests/test_image_provider_formats.py tests/test_image_api_reference_mode.py`

Expected: PASS, including all pre-existing OpenAI/Gemini behavior.

## Task 2: Provider configuration UI and system configuration layout

**Files:**
- Modify: `templates/admin/_config_settings_panels.html`
- Modify: `static/js/settings.js`
- Modify: `static/css/site.css`
- Test: `tests/test_settings_config_status.py`
- Test: `tests/test_admin_ui_structure.py`

- [ ] **Step 1: Add failing template/contract assertions**

```python
def test_provider_form_uses_model_select_and_custom_id_toggle(client, login_admin):
    response = client.get("/admin/config/settings")
    body = response.get_data(as_text=True)
    assert 'data-model-select' in body
    assert 'data-custom-model-toggle' in body
    assert 'grok-imagine 2.0' in body
    assert 'grok-imagine-image-2.0' in body
```

- [ ] **Step 2: Run the UI tests and verify failure**

Run: `pytest -q tests/test_settings_config_status.py tests/test_admin_ui_structure.py`

Expected: FAIL because the form currently uses a free-text `input+datalist` model field and the settings page has no custom-ID disclosure contract.

- [ ] **Step 3: Replace model inputs with accessible selects**

For image Provider dialogs, render a `<select name="model" data-model-select>` from `image_model_catalog`, show the selected ID in a read-only `<code data-model-id>`, and add a checkbox `data-custom-model-toggle`. Render the text input only when the checkbox is enabled; keep its submitted name separate (`custom_model`) so the server can distinguish it from official selection.

- [ ] **Step 4: Add protocol-driven JavaScript behavior**

In `static/js/settings.js`, define a JSON-safe catalog object emitted by the template. On protocol/model changes:

```javascript
function syncProviderModel(form, restoreDefaults = false) {
  const protocol = form.querySelector("[data-model-protocol]")?.value || "openai";
  const modelSelect = form.querySelector("[data-model-select]");
  const modelId = form.querySelector("[data-model-id]");
  const baseUrl = form.querySelector("input[name='base_url']");
  const resolutionInputs = [...form.querySelectorAll("input[name='resolutions']")];
  const option = window.HUISHI_IMAGE_MODEL_CATALOG?.[protocol]?.find(
    (item) => item.id === modelSelect?.value,
  );
  if (modelId) modelId.textContent = modelSelect?.value || "自定义模型";
  if (baseUrl && (restoreDefaults || !baseUrl.value.trim())) {
    baseUrl.value = option?.default_base_url || "";
  }
  const supported = new Set(option?.resolutions || ["1K", "2K", "4K"]);
  resolutionInputs.forEach((input) => {
    const enabled = supported.has(input.value);
    input.disabled = !enabled;
    if (!enabled) input.checked = false;
  });
}
```

Ensure API Key values are never copied into the DOM. Existing custom Base URL remains unchanged after protocol/model changes.

- [ ] **Step 5: Restructure the settings page into compact sections**

Keep the existing routes and forms, but group them into the four approved sections. Use a single provider table for rows and dialogs for editing. Move billing links and system diagnostics out of the provider table. Preserve `settings-main-form`, CSRF fields, storage controls, admin entry, and existing `data-confirm` hooks.

- [ ] **Step 6: Add responsive CSS**

Scope new rules under `.admin-console-page` and the existing settings classes. Use a compact two-column form at `min-width: 900px`, one column below that, horizontal scrolling only for dense tables, and maintain light/dark variables. Do not remove legacy selectors used by unrelated console pages.

- [ ] **Step 7: Run UI and contract tests**

Run: `pytest -q tests/test_settings_config_status.py tests/test_admin_ui_structure.py tests/test_ui_theme_contract.py`

Expected: PASS in both configured themes; no existing management button or CSRF/action contract disappears.

## Task 3: Model-specific pricing and idempotent database migration

**Files:**
- Modify: `huishi/db.py:451-479, 700-735`
- Modify: `huishi/routes_admin.py:280-430`
- Modify: `templates/admin/config_billing.html`
- Modify: `huishi/billing.py`
- Test: `tests/test_generation_billing.py`
- Test: `tests/test_model_migrations.py`

- [ ] **Step 1: Write migration and pricing failure tests**

```python
def test_legacy_grok_ids_migrate_to_2_0_without_duplicate_rules(app):
    db = get_db()
    db.execute("INSERT INTO api_providers (provider_type,name,base_url,api_key,model,api_format,resolutions,priority,enabled,created_at,updated_at) VALUES ('image','legacy','https://x.test','key','grok-imagine-image','grok','[\"1K\",\"2K\"]',100,1,datetime('now'),datetime('now'))")
    db.commit()
    run_compatibility_migrations(db)
    run_compatibility_migrations(db)
    rows = db.execute("SELECT model FROM api_providers WHERE api_format='grok'").fetchall()
    assert [row["model"] for row in rows] == ["grok-imagine-image-2.0"]


def test_each_new_model_has_independent_pricing_rows(app):
    rows = get_db().execute("SELECT model,resolution FROM pricing_rules WHERE model IN ('grok-imagine-image-2.0','gemini-3.1-flash-image','gemini-3-pro-image')").fetchall()
    assert {tuple(row) for row in rows} >= {
        ("grok-imagine-image-2.0", "1K"), ("grok-imagine-image-2.0", "2K"),
        ("gemini-3.1-flash-image", "1K"), ("gemini-3.1-flash-image", "2K"), ("gemini-3.1-flash-image", "4K"),
        ("gemini-3-pro-image", "1K"), ("gemini-3-pro-image", "2K"), ("gemini-3-pro-image", "4K"),
    }
```

- [ ] **Step 2: Run migration tests and verify failure**

Run: `pytest -q tests/test_model_migrations.py tests/test_generation_billing.py`

Expected: FAIL because the migration helper does not yet exist and the old catalog seeds obsolete Grok rows.

- [ ] **Step 3: Implement a transaction-safe compatibility migration**

Add `run_compatibility_migrations(db)` in `huishi/db.py`. Within one transaction, update only exact legacy Grok model IDs, preserve connection/priority/enabled fields, merge duplicate provider rows by retaining the newest target row and deleting only the duplicate legacy row, normalize resolutions to `1K/2K`, and rewrite exact legacy pricing rows to the 2.0 ID. Use the existing database backend abstraction so SQLite and PostgreSQL execute equivalent statements. Make the function safe to call repeatedly.

- [ ] **Step 4: Update default pricing seeding**

Build model IDs from the new catalog, insert independent rows for each supported resolution, and omit or disable Grok 4K. Never overwrite an existing `points_per_image` value. Ensure a manually edited target 2.0 rule wins over a migrated legacy rule.

- [ ] **Step 5: Keep billing lookup model-specific**

Verify `huishi.billing` resolves exact model+resolution first, then existing wildcard fallback. Add a test that a Banana Pro request and a Grok 2.0 request charge their own rows and that Grok 4K cannot reach billing.

- [ ] **Step 6: Simplify the pricing table UI**

Render one row per model/resolution with display labels from `image_model_label`, the real model ID in a secondary caption, points input, enabled checkbox, and one save action. Keep existing CSRF, permission and audit hooks.

- [ ] **Step 7: Run migration and billing tests**

Run: `pytest -q tests/test_model_migrations.py tests/test_generation_billing.py tests/test_admin_audit.py`

Expected: PASS; running initialization twice yields the same provider and pricing rows.

## Task 4: Administrator-created users

**Files:**
- Modify: `huishi/routes_admin.py:424-482`
- Modify: `templates/admin/users.html`
- Modify: `static/js/admin.js`
- Test: `tests/test_admin_create_user.py`
- Test: `tests/test_admin_audit.py`

- [ ] **Step 1: Write failing route and security tests**

```python
def test_admin_can_create_user_with_hashed_password_and_points(client, login_admin, app):
    response = client.post("/admin/users/create", data={
        "email": "new@example.com", "username": "new-user",
        "password": "StrongPass123!", "role": "user",
        "points": "25", "enabled": "1",
    })
    assert response.status_code == 302
    row = get_db().execute("SELECT * FROM users WHERE username='new-user'").fetchone()
    assert row["points"] == 25
    assert row["password_hash"] != "StrongPass123!"


def test_non_admin_cannot_create_user(client, login_user):
    response = client.post("/admin/users/create", data={"email":"x@example.com","username":"x","password":"StrongPass123!"})
    assert response.status_code in {302, 403}
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run: `pytest -q tests/test_admin_create_user.py tests/test_admin_audit.py`

Expected: FAIL because `/admin/users/create` is not implemented.

- [ ] **Step 3: Implement the protected create route**

Add `@bp.post("/users/create")` with `@permission_required("users.create")`. Validate normalized email/username uniqueness, password length (minimum 6, matching existing reset policy), role in `{"user", "admin"}`, non-negative integer points, and enabled status. Insert using `generate_password_hash(password)` and `utc_now()` in one transaction. Do not include the password in audit data; record a redacted `user.create` audit event.

- [ ] **Step 4: Add permission metadata without weakening existing roles**

Add `users.create` to the existing admin permission map, grant it to administrator roles only, and keep the “at least one administrator” safeguard for all role changes and deletes.

- [ ] **Step 5: Add the compact UI form**

Add an “新增用户” button to `templates/admin/users.html` visible only when `can("users.create")`. Use the existing dialog patterns, CSRF token, password input with no value binding, role select, enabled checkbox, and non-negative points input. Keep CSV import/export and user edit drawer unchanged.

- [ ] **Step 6: Run user and audit tests**

Run: `pytest -q tests/test_admin_create_user.py tests/test_admin_audit.py tests/test_admin_delete_user_cascade.py tests/test_auth_csrf.py`

Expected: PASS; password is hashed, duplicate identities return 400 without a partial row, and ordinary users cannot access the route.

## Task 5: Integrated verification and release handoff

**Files:**
- Inspect: all files listed above
- Test: entire `tests/` suite
- Deploy: `deploy/` scripts and `DEPLOY.md`

- [ ] **Step 1: Run formatting/static checks used by the repository**

Run: `pytest -q tests/test_check_encoding.py tests/test_code_snapshot.py tests/test_deploy_release_scripts.py`

Expected: PASS with no encoding or release-script regressions.

- [ ] **Step 2: Run the complete test suite locally**

Run: `pytest -q`

Expected: all tests pass; if an existing snapshot expects the old Grok catalog, update only the snapshot assertions that are covered by the approved design.

- [ ] **Step 3: Inspect the diff and migration SQL**

Run: `rg -n -i "api[_ -]?key|password|secret|bearer|BEGIN .*PRIVATE KEY" huishi templates static tests` and inspect every changed template/route plus the generated release file list. Confirm no API Key, password, database dump, or production credential is added to the release artifact. If a Git checkout is available for the implementation worktree, also run `git diff --check`.

- [ ] **Step 4: Build the release artifact locally**

Run the repository’s existing release command from `DEPLOY.md`; verify the artifact contains `huishi/providers.py`, `huishi/db.py`, `huishi/routes_admin.py`, `templates/admin/_config_settings_panels.html`, `templates/admin/users.html`, `static/js/settings.js`, and `static/css/site.css`.

- [ ] **Step 5: Request explicit deployment approval**

Before touching the VM, show the final diff summary, test output, backup/rollback point, and the exact SSH deployment command. Do not deploy or restart Docker services until the user explicitly approves the release operation.
