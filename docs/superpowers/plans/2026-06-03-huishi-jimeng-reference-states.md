# 绘世即梦参考状态优化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 根据用户提供的四张即梦参考图，将绘世补齐为空白创作态、生成后作品态、参数浮层和资产库四个清晰体验状态。

**Architecture:** 继续使用现有 Flask + Jinja + vanilla JS + CSS，不引入新前端框架。把工作台和资产库共享的左侧导航抽成局部模板；工作台根据 `current_record` 渲染空白态或作品态；历史页升级为资产库网格页，仍复用现有 `records` 数据，不新增数据库表。前端 JS 只增强现有参数、搜索、筛选和生成状态，不改变 `/generate`、`/api/estimate`、计费和上传校验协议。

**Tech Stack:** Python 3, Flask, SQLite, Jinja2, vanilla JavaScript, CSS, pytest, in-app browser visual verification.

---

## Reference Mapping

- 图一：即梦深色生成后状态。要提取的是布局逻辑，不是必须全黑：左侧 rail + 会话栏、顶部筛选、作品流、操作按钮、长提示词、参数浮层、底部紧凑生成条。
- 图二：当前项目状态。已经具备基础结构，但作品图与输入器发生遮挡，顶部筛选和左栏视觉不够贴近，资产库入口还只是历史页链接。
- 图三：即梦空白生成态。核心是浅色大画布、中央欢迎语、居中输入卡、顶部仅保留资产库入口，左侧栏是浅色体系。
- 图四：即梦资产库。核心是同一套左 rail、顶部资源类型 tabs、二级筛选、右侧搜索/批量/同步操作、日期分组和高密度图片网格。

## File Structure

- Create: `D:\AI\绘世\templates\partials\studio_nav.html`
  - Shared left rail + conversation sidebar for workspace and assets pages.
- Modify: `D:\AI\绘世\templates\workspace.html`
  - Render empty creation state and generated state with different chrome and composer placement.
- Modify: `D:\AI\绘世\templates\history.html`
  - Replace simple history list with asset library page.
- Modify: `D:\AI\绘世\static\css\site.css`
  - Add shared studio layout, workspace state styles, parameter popover, and asset grid styles.
- Modify: `D:\AI\绘世\static\js\workspace.js`
  - Improve state switching, parameter popover, dimension display, composer layout classes, and action handlers.
- Create: `D:\AI\绘世\static\js\assets.js`
  - Client-side asset search, tab/filter active states, favorite-only filtering.
- Modify: `D:\AI\绘世\huishi\routes_workspace.py`
  - Pass asset counts and optional grouped records to templates if needed.
- Modify: `D:\AI\绘世\tests\test_auth_records.py`
  - Add/adjust workspace empty/generated state contract tests.
- Modify: `D:\AI\绘世\tests\test_routes.py`
  - Add asset library rendering and JSON contract assertions.

## Task 1: Shared Studio Navigation

**Files:**
- Create: `D:\AI\绘世\templates\partials\studio_nav.html`
- Modify: `D:\AI\绘世\templates\workspace.html`
- Modify: `D:\AI\绘世\templates\history.html`
- Modify: `D:\AI\绘世\tests\test_auth_records.py`

- [ ] **Step 1: Add failing shared navigation test**

Append to `D:\AI\绘世\tests\test_auth_records.py`:

```python
def test_workspace_and_assets_share_studio_navigation(client):
    client.post("/register", data={"username": "sharednav", "password": "secret123"}, follow_redirects=True)

    workspace = client.get("/workspace").get_data(as_text=True)
    assets = client.get("/history").get_data(as_text=True)

    for text in (workspace, assets):
        assert 'aria-label="主导航"' in text
        assert "灵感" in text
        assert "生成" in text
        assert "资产" in text
        assert "开启创作" in text
        assert "默认创作" in text
```

- [ ] **Step 2: Verify the test fails**

Run:

```powershell
python -m pytest tests/test_auth_records.py::test_workspace_and_assets_share_studio_navigation -v
```

Expected: FAIL because `/history` still uses `simple-page` and does not render the studio navigation.

- [ ] **Step 3: Create shared partial**

Create `D:\AI\绘世\templates\partials\studio_nav.html`:

```html
<aside class="studio-rail" aria-label="主导航">
  <a class="rail-logo" href="/" aria-label="绘世首页">绘</a>
  <nav class="rail-nav" aria-label="创作导航">
    <a class="{{ 'is-active' if active_nav == 'inspiration' else '' }}" href="/workspace"><span>灵感</span></a>
    <a class="{{ 'is-active' if active_nav == 'generate' else '' }}" href="/workspace"><span>生成</span></a>
    <a class="{{ 'is-active' if active_nav == 'assets' else '' }}" href="/history"><span>资产</span></a>
    <a class="{{ 'is-active' if active_nav == 'settings' else '' }}" href="/settings"><span>设置</span></a>
  </nav>
  <div class="rail-footer">
    <a href="/pricing">会员</a>
    <a href="/account">{{ g.user["points"] }} 点</a>
  </div>
</aside>

<aside class="studio-sidebar">
  <header class="sidebar-header">
    <strong>开启创作</strong>
    <a class="sidebar-icon-button" href="/workspace" aria-label="新对话">+</a>
  </header>
  <a class="conversation-entry is-pinned" href="/workspace">
    <span class="conversation-thumb">绘</span>
    <span>默认创作</span>
  </a>
  <div class="sidebar-section-title">最近</div>
  <nav class="work-folder-list" aria-label="最近创作">
    {% for record in records[:12] %}
    <a class="{{ 'active' if loop.first and active_nav != 'assets' else '' }}" href="/image/{{ record['id'] }}">
      <img src="{{ record['image_path'] }}" alt="">
      <span>{{ record["prompt"] }}</span>
    </a>
    {% else %}
    <span class="sidebar-empty">暂无创作记录</span>
    {% endfor %}
  </nav>
</aside>
```

- [ ] **Step 4: Use partial in workspace**

In `D:\AI\绘世\templates\workspace.html`, replace the current `studio-rail` and `studio-sidebar` blocks with:

```html
{% set active_nav = "generate" %}
{% include "partials/studio_nav.html" %}
```

- [ ] **Step 5: Use partial in history**

In `D:\AI\绘世\templates\history.html`, temporarily wrap the existing history content in `studio-shell`:

```html
<main class="studio-shell assets-shell" data-studio-theme="mist">
  {% set active_nav = "assets" %}
  {% include "partials/studio_nav.html" %}
  <section class="studio-main assets-main">
    ...
  </section>
</main>
```

- [ ] **Step 6: Verify shared navigation passes**

Run:

```powershell
python -m pytest tests/test_auth_records.py::test_workspace_and_assets_share_studio_navigation -v
```

Expected: PASS.

## Task 2: Empty Creation State Like Reference 图三

**Files:**
- Modify: `D:\AI\绘世\templates\workspace.html`
- Modify: `D:\AI\绘世\static\css\site.css`
- Modify: `D:\AI\绘世\tests\test_auth_records.py`

- [ ] **Step 1: Tighten empty-state contract test**

Update `test_empty_workspace_uses_centered_creation_card` in `D:\AI\绘世\tests\test_auth_records.py`:

```python
def test_empty_workspace_uses_centered_creation_card(client):
    client.post("/register", data={"username": "empty-studio", "password": "secret123"}, follow_redirects=True)
    response = client.get("/workspace")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "empty-creation-stage" in text
    assert "empty-composer-card" in text
    assert "你好，想创作什么？" in text
    assert "资产库" in text
    assert "studio-filterbar" not in text
    assert "生成后的图片会显示在这里" not in text
```

- [ ] **Step 2: Verify the test fails**

Run:

```powershell
python -m pytest tests/test_auth_records.py::test_empty_workspace_uses_centered_creation_card -v
```

Expected: FAIL because current empty state still renders the full filterbar.

- [ ] **Step 3: Split top chrome by state**

In `D:\AI\绘世\templates\workspace.html`, render only asset button for empty state:

```html
{% if current_record %}
<header class="studio-filterbar" aria-label="作品筛选">
  <button type="button" class="filter-search" aria-label="搜索">⌕</button>
  <button type="button">时间</button>
  <button type="button">生成模式</button>
  <button type="button">操作类型</button>
  <a href="/history">资产库</a>
</header>
{% else %}
<header class="empty-topbar">
  <a href="/history">资产库</a>
</header>
{% endif %}
```

- [ ] **Step 4: Refine empty composer markup**

Keep the same form, but ensure it has these classes when empty:

```html
<form class="composer studio-composer {{ 'is-empty-card empty-composer-card' if not current_record else '' }}" ...>
```

- [ ] **Step 5: Add empty topbar CSS**

Append to the studio CSS block in `D:\AI\绘世\static\css\site.css`:

```css
.empty-topbar {
  position: fixed;
  z-index: 12;
  top: 24px;
  right: 48px;
}
.empty-topbar a {
  min-height: 44px;
  display: inline-flex;
  align-items: center;
  padding: 0 16px;
  border: 1px solid var(--studio-line);
  border-radius: 8px;
  background: rgba(255,255,255,.78);
  color: var(--studio-text);
  font-weight: 900;
  box-shadow: 0 16px 42px rgba(21,25,34,.08);
}
```

- [ ] **Step 6: Verify empty state**

Run:

```powershell
python -m pytest tests/test_auth_records.py::test_empty_workspace_uses_centered_creation_card -v
```

Expected: PASS.

## Task 3: Generated Workspace State Like Reference 图一/图二

**Files:**
- Modify: `D:\AI\绘世\templates\workspace.html`
- Modify: `D:\AI\绘世\static\css\site.css`
- Modify: `D:\AI\绘世\static\js\workspace.js`
- Modify: `D:\AI\绘世\tests\test_auth_records.py`

- [ ] **Step 1: Add generated-state contract test**

Append to `D:\AI\绘世\tests\test_auth_records.py`:

```python
def test_generated_workspace_uses_output_state_contract(client, app):
    from huishi.db import get_db, utc_now

    client.post("/register", data={"username": "output-state", "password": "secret123"}, follow_redirects=True)
    with app.app_context():
        db = get_db()
        user_id = db.execute("SELECT id FROM users WHERE username = 'output-state'").fetchone()["id"]
        db.execute(
            """
            INSERT INTO records
            (user_id, prompt, image_path, mode, resolution, actual_size, quality, output_format, count, model_source, elapsed_seconds, points_charged, favorite, created_at)
            VALUES (?, '生成后作品态测试', '/static/uploads/output.png', 'text', '2K', '1440x2560', 'auto', 'png', 1, 'demo', 1.2, 2, 0, ?)
            """,
            (user_id, utc_now()),
        )
        db.commit()

    text = client.get("/workspace").get_data(as_text=True)
    assert "creation-stream" in text
    assert "creation-actions" in text
    assert "重新编辑" in text
    assert "再次生成" in text
    assert "output-composer" in text
    assert "empty-composer-card" not in text
```

- [ ] **Step 2: Verify the test fails**

Run:

```powershell
python -m pytest tests/test_auth_records.py::test_generated_workspace_uses_output_state_contract -v
```

Expected: FAIL because composer does not yet have `output-composer`.

- [ ] **Step 3: Add output composer class**

In `D:\AI\绘世\templates\workspace.html`, change form class to:

```html
<form class="composer studio-composer {{ 'is-empty-card empty-composer-card' if not current_record else 'output-composer' }}" method="post" action="/generate" enctype="multipart/form-data">
```

- [ ] **Step 4: Improve generated image layout CSS**

In `D:\AI\绘世\static\css\site.css`, refine generated state:

```css
.output-composer {
  width: min(980px, calc(100vw - 460px));
}
.creation-stream {
  padding-bottom: 40px;
}
.creation-item.is-featured {
  align-items: start;
}
.creation-image-wrap {
  width: min(1120px, 100%);
  justify-self: center;
}
.creation-actions {
  position: sticky;
  top: 92px;
  z-index: 8;
}
```

- [ ] **Step 5: Ensure JS removes empty and applies output class**

In `D:\AI\绘世\static\js\workspace.js`, update the success branch:

```javascript
form.classList.remove("is-empty-card", "empty-composer-card");
form.classList.add("output-composer");
```

- [ ] **Step 6: Verify generated state**

Run:

```powershell
python -m pytest tests/test_auth_records.py::test_generated_workspace_uses_output_state_contract -v
```

Expected: PASS.

## Task 4: Parameter Popover Like Reference 图一

**Files:**
- Modify: `D:\AI\绘世\templates\workspace.html`
- Modify: `D:\AI\绘世\static\css\site.css`
- Modify: `D:\AI\绘世\static\js\workspace.js`
- Modify: `D:\AI\绘世\tests\test_auth_records.py`

- [ ] **Step 1: Add parameter popover contract test**

Append to `D:\AI\绘世\tests\test_auth_records.py`:

```python
def test_workspace_parameter_popover_contains_dimensions(client):
    client.post("/register", data={"username": "popover-user", "password": "secret123"}, follow_redirects=True)
    text = client.get("/workspace").get_data(as_text=True)

    assert "parameter-popover" in text
    assert "选择比例" in text
    assert "选择分辨率" in text
    assert "尺寸" in text
    assert 'id="width-display"' in text
    assert 'id="height-display"' in text
```

- [ ] **Step 2: Verify the test fails**

Run:

```powershell
python -m pytest tests/test_auth_records.py::test_workspace_parameter_popover_contains_dimensions -v
```

Expected: FAIL because current popover does not render separate W/H fields.

- [ ] **Step 3: Add dimension display markup**

Inside `#resolution-panel` in `D:\AI\绘世\templates\workspace.html`, after `.resolution-grid`, add:

```html
<div class="dimension-grid" aria-label="输出尺寸">
  <span>尺寸</span>
  <label>W <output id="width-display">1440</output></label>
  <label>H <output id="height-display">2560</output></label>
  <span>PX</span>
</div>
```

- [ ] **Step 4: Update JS dimension sync**

In `D:\AI\绘世\static\js\workspace.js`, add selectors:

```javascript
const widthDisplay = document.querySelector("#width-display");
const heightDisplay = document.querySelector("#height-display");
```

Then update `syncResolutionOptions()`:

```javascript
const [width, height] = size.split("x");
if (widthDisplay) widthDisplay.textContent = width;
if (heightDisplay) heightDisplay.textContent = height;
```

- [ ] **Step 5: Add dimension CSS**

Append:

```css
.dimension-grid {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  margin-top: 14px;
  color: #9ba3af;
  font-size: 13px;
  font-weight: 900;
}
.dimension-grid label {
  min-height: 48px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 0 14px;
  border-radius: 8px;
  background: #262934;
}
.dimension-grid output {
  color: #f5f7fb;
}
```

- [ ] **Step 6: Verify popover contract**

Run:

```powershell
python -m pytest tests/test_auth_records.py::test_workspace_parameter_popover_contains_dimensions -v
```

Expected: PASS.

## Task 5: Asset Library Like Reference 图四

**Files:**
- Modify: `D:\AI\绘世\templates\history.html`
- Create: `D:\AI\绘世\static\js\assets.js`
- Modify: `D:\AI\绘世\static\css\site.css`
- Modify: `D:\AI\绘世\tests\test_auth_records.py`

- [ ] **Step 1: Add asset library rendering test**

Append to `D:\AI\绘世\tests\test_auth_records.py`:

```python
def test_history_page_renders_asset_library(client, app):
    from huishi.db import get_db, utc_now

    client.post("/register", data={"username": "assetuser", "password": "secret123"}, follow_redirects=True)
    with app.app_context():
        db = get_db()
        user_id = db.execute("SELECT id FROM users WHERE username = 'assetuser'").fetchone()["id"]
        db.execute(
            """
            INSERT INTO records
            (user_id, prompt, image_path, mode, resolution, actual_size, quality, output_format, count, model_source, elapsed_seconds, points_charged, favorite, created_at)
            VALUES (?, '资产库图像', '/static/uploads/asset.png', 'text', '2K', '1440x2560', 'auto', 'png', 1, 'demo', 1.2, 2, 1, ?)
            """,
            (user_id, utc_now()),
        )
        db.commit()

    text = client.get("/history").get_data(as_text=True)
    assert "asset-library" in text
    assert "图片" in text
    assert "视频" in text
    assert "无限画布" in text
    assert "所有图片" in text
    assert "我的收藏" in text
    assert "批量操作" in text
    assert "同步到剪映" in text
    assert "资产库图像" in text
```

- [ ] **Step 2: Verify the test fails**

Run:

```powershell
python -m pytest tests/test_auth_records.py::test_history_page_renders_asset_library -v
```

Expected: FAIL because history page is still a simple page.

- [ ] **Step 3: Replace history template**

Replace `D:\AI\绘世\templates\history.html` content:

```html
{% extends "base.html" %}
{% block title %}资产库 - 绘世{% endblock %}
{% block body_class %}workspace-page{% endblock %}
{% block content %}
<main class="studio-shell assets-shell" data-studio-theme="mist">
  {% set active_nav = "assets" %}
  {% include "partials/studio_nav.html" %}
  <section class="studio-main assets-main">
    <header class="asset-topbar">
      <nav class="asset-tabs" aria-label="资产类型">
        <a class="is-active" href="/history">图片</a>
        <span>视频</span>
        <span>无限画布</span>
        <span>图片编辑器</span>
        <span>音频</span>
        <span>文档</span>
      </nav>
      <div class="asset-actions">
        <label><span>⌕</span><input id="asset-search" type="search" placeholder="搜索资产"></label>
        <button type="button">批量操作</button>
        <button type="button">同步到剪映</button>
      </div>
    </header>

    <nav class="asset-subtabs" aria-label="图片筛选">
      <button type="button" class="is-active" data-asset-filter="all">所有图片</button>
      <button type="button" data-asset-filter="2K">超清</button>
      <button type="button" data-asset-filter="favorite">我的收藏</button>
    </nav>

    <section class="asset-date-group">
      <h1>全部图片</h1>
      <div class="asset-grid asset-library">
        {% for record in records %}
        <a class="asset-tile" href="/image/{{ record['id'] }}" data-prompt="{{ record['prompt'] }}" data-resolution="{{ record['resolution'] }}" data-favorite="{{ record['favorite'] }}">
          <img src="{{ record['image_path'] }}" alt="{{ record['prompt'] }}">
          <span>{{ record["prompt"] }}</span>
        </a>
        {% else %}
        <div class="empty-workspace">暂无资产。</div>
        {% endfor %}
      </div>
    </section>
  </section>
</main>
{% endblock %}
{% block scripts %}
<script src="{{ url_for('static', filename='js/assets.js') }}"></script>
{% endblock %}
```

- [ ] **Step 4: Add asset CSS**

Append:

```css
.assets-main { padding: 32px 48px 80px; }
.asset-topbar { display: flex; align-items: center; justify-content: space-between; gap: 24px; margin-bottom: 28px; }
.asset-tabs { display: flex; flex-wrap: wrap; gap: 18px; align-items: center; }
.asset-tabs a, .asset-tabs span { min-height: 46px; display: inline-flex; align-items: center; padding: 0 18px; border-radius: 8px; color: var(--studio-text); font-weight: 900; }
.asset-tabs .is-active { background: rgba(21,25,34,.08); }
.asset-actions { display: flex; gap: 8px; align-items: center; }
.asset-actions label { min-height: 44px; display: inline-flex; align-items: center; gap: 8px; padding: 0 12px; border: 1px solid var(--studio-line); border-radius: 8px; background: rgba(255,255,255,.78); }
.asset-actions input { width: 180px; border: 0; outline: 0; background: transparent; }
.asset-actions button { min-height: 44px; border: 1px solid var(--studio-line); border-radius: 8px; background: rgba(255,255,255,.78); color: var(--studio-text); font-weight: 900; }
.asset-subtabs { display: flex; gap: 24px; margin-bottom: 36px; }
.asset-subtabs button { min-height: 34px; border: 0; background: transparent; color: var(--studio-muted); font-weight: 900; cursor: pointer; }
.asset-subtabs button.is-active { color: var(--studio-text); }
.asset-date-group h1 { margin: 0 0 18px; font-size: 32px; line-height: 1; }
.asset-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 3px; }
.asset-tile { position: relative; overflow: hidden; min-height: 150px; background: #dfe3e8; color: #fff; }
.asset-tile img { width: 100%; aspect-ratio: 1; display: block; object-fit: cover; }
.asset-tile span { position: absolute; left: 8px; right: 8px; bottom: 8px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 900; text-shadow: 0 2px 8px rgba(0,0,0,.6); }
.asset-tile.is-hidden { display: none; }
```

- [ ] **Step 5: Add asset JS**

Create `D:\AI\绘世\static\js\assets.js`:

```javascript
const assetSearch = document.querySelector("#asset-search");
const assetTiles = Array.from(document.querySelectorAll(".asset-tile"));
const filterButtons = document.querySelectorAll("[data-asset-filter]");

function applyAssetFilters(filter = document.querySelector("[data-asset-filter].is-active")?.dataset.assetFilter || "all") {
  const query = (assetSearch?.value || "").trim().toLowerCase();
  assetTiles.forEach((tile) => {
    const prompt = (tile.dataset.prompt || "").toLowerCase();
    const matchesSearch = !query || prompt.includes(query);
    const matchesFilter =
      filter === "all" ||
      (filter === "favorite" && tile.dataset.favorite === "1") ||
      tile.dataset.resolution === filter;
    tile.classList.toggle("is-hidden", !matchesSearch || !matchesFilter);
  });
}

filterButtons.forEach((button) => {
  button.addEventListener("click", () => {
    filterButtons.forEach((item) => item.classList.remove("is-active"));
    button.classList.add("is-active");
    applyAssetFilters(button.dataset.assetFilter);
  });
});

if (assetSearch) {
  assetSearch.addEventListener("input", () => applyAssetFilters());
}
```

- [ ] **Step 6: Verify asset page**

Run:

```powershell
python -m pytest tests/test_auth_records.py::test_history_page_renders_asset_library -v
```

Expected: PASS.

## Task 6: Responsive And Visual Verification

**Files:**
- Modify only if verification exposes layout defects.

- [ ] **Step 1: Run full regression**

Run:

```powershell
python -m pytest -v
```

Expected: all tests PASS.

- [ ] **Step 2: Browser-check empty workspace**

In the browser, use a new user or clear records, then open:

```text
http://127.0.0.1:8000/workspace
```

Verify:

- Left rail/sidebar matches 图三.
- Top right only shows `资产库`, not the full generated-state filterbar.
- Center shows `你好，想创作什么？`.
- Composer is centered in a white card and does not overlap the greeting.
- Search/filters do not appear in empty state.

- [ ] **Step 3: Browser-check generated workspace**

Use a user with records and open:

```text
http://127.0.0.1:8000/workspace
```

Verify:

- Top right filterbar appears like 图一/图二.
- `重新编辑` and `再次生成` sit above the prompt.
- Generated image is not hidden by composer at initial viewport.
- Composer is fixed at bottom and remains within viewport width.
- Ratio popover shows ratio, resolution, W/H dimension fields.

- [ ] **Step 4: Browser-check asset library**

Open:

```text
http://127.0.0.1:8000/history
```

Verify:

- Shared left navigation appears.
- Top tabs match 图四: 图片、视频、无限画布、图片编辑器、音频、文档.
- Search, 批量操作, 同步到剪映 appear on the right.
- Image tiles form a dense grid, no card-style history list.
- `我的收藏` filter hides non-favorites.

- [ ] **Step 5: Browser-check mobile**

Set mobile viewport around `390x844` and verify:

- No horizontal overflow.
- Rail collapses into compact top bar.
- Composer controls fit without text clipping.
- Asset grid stays scrollable and does not overlap top controls.

## Self-Review Notes

- Spec coverage: The plan maps all four reference images to concrete states and pages.
- Scope boundary: It does not add new asset types, true project folders, video generation, infinite canvas, or external sync behavior. Those labels are UI categories only until the backend exists.
- Placeholder scan: No task uses TBD/TODO placeholders.
- Type consistency: Template IDs/classes match JS selectors: `#ratio`, `#resolution`, `#width-display`, `#height-display`, `.asset-tile`, `#asset-search`.
- Repository note: `D:\AI\绘世` is not currently a git repository, so commit steps are omitted.
