# 绘世即梦式工作台优化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将绘世工作台优化为更接近即梦截图的沉浸式创作界面，保留现有生成、计费、历史、收藏、删除和邮箱验证业务能力。

**Architecture:** 以现有 Flask + Jinja + vanilla JS 为主，不引入新的前端框架。后端继续提供记录列表、估价和异步生成 JSON；前端重构 `workspace.html` 的信息架构，增强 `workspace.js` 的参数选择、上传预览、回填再生成和生成结果插入逻辑；`site.css` 只针对工作台区域新增一套可切换的 studio 视觉主题，默认采用明暗混合的「雾白画布 + 暗色工具栏」方案，避免影响首页、管理后台和账户页。

**Tech Stack:** Python 3, Flask, SQLite, Jinja2, vanilla JavaScript, CSS, pytest, browser visual verification.

---

## 参考范围

- 以用户提供的即梦截图为主：左侧窄图标栏 + 会话栏、顶部悬浮筛选、居中作品流、底部悬浮输入器、参数浮层、比例/分辨率/尺寸控件、重新编辑/再次生成等操作。
- 公开资料仅用于确认常见参数方向：比例、分辨率、画布调整、参考图/图生图、风格与模型入口。第一轮不实现复杂画布编辑、遮罩、图层、动作/视频能力。
- 当前项目已经支持：登录、邮箱验证、点数计费、`/api/estimate`、异步 `/generate`、参考图上传、历史记录、详情、收藏、删除、后台配置。

## 修改清单

### 主要修改

- Modify: `D:\AI\绘世\templates\workspace.html`
  - 重构为即梦式三层布局：左侧 app rail、会话/资产侧栏、主创作流。
  - 将当前大画布改为作品流区域：顶部保留最新图，下面展示最近生成缩略卡。
  - 将生成表单改为底部悬浮 composer：提示词、多模式、模型、比例、清晰度、尺寸、数量、参考图、估价、提交按钮。
  - 增加可访问的按钮文本、`aria-live` 状态、隐藏 input，用 JS 同步参数。

- Modify: `D:\AI\绘世\static\css\site.css`
  - 新增/替换 `.studio-*`、`.creation-*`、`.composer-*` 工作台样式。
  - 保持 8px 或更小圆角，采用「可选择主题」而非固定深色：默认推荐明亮主画布、暗色工具栏、青绿色行动色。
  - 增加桌面、平板、手机断点，保证底部 composer 不遮挡内容，文字不溢出。

- Modify: `D:\AI\绘世\static\js\workspace.js`
  - 从 select 为主改为按钮/弹层驱动，并继续提交现有后端字段。
  - 增加比例按钮、分辨率按钮、宽高展示、参考图上传预览、估价刷新防抖、生成中状态、结果插入、再生成回填。
  - 保留当前 `SIZE_MATRIX` 和 `/api/estimate` 协议。

- Modify: `D:\AI\绘世\huishi\routes_workspace.py`
  - 视需要扩展 `serialize_record()`，让前端插入卡片时拿到 `ratio`、`mode_label`、`created_at` 等显示字段。
  - 不改变扣费、余额验证、上传校验和邮箱验证流程。

### 测试修改

- Modify: `D:\AI\绘世\tests\test_auth_records.py`
  - 更新工作台渲染断言，覆盖即梦式新结构和旧业务入口仍存在。

- Modify: `D:\AI\绘世\tests\test_routes.py`
  - 增加工作台登录后关键控件/筛选入口/资产入口渲染测试。

- Optional Create: `D:\AI\绘世\tests\test_workspace_ui_contract.py`
  - 如测试拆分更清晰，新建专门文件检查模板 contract。

### 不修改

- `D:\AI\绘世\huishi\billing.py`：计费规则不变。
- `D:\AI\绘世\huishi\image_api.py`：图像 API 调用不变。
- `D:\AI\绘世\templates\history.html` 和 `D:\AI\绘世\templates\image_detail.html`：第一轮只通过工作台入口链接它们，不重做页面。
- 数据库 schema：第一轮不增加项目/会话表，先用现有 `records` 实现“默认创作/最近记录”。

## Task 1: Baseline And Workspace Contract Tests

**Files:**
- Modify: `D:\AI\绘世\tests\test_auth_records.py`
- Optional Create: `D:\AI\绘世\tests\test_workspace_ui_contract.py`

- [ ] **Step 1: Add workspace contract assertions**

Modify `test_logged_in_user_can_view_workspace` in `D:\AI\绘世\tests\test_auth_records.py` so it checks both existing business behavior and the new UI contract:

```python
def test_logged_in_user_can_view_workspace(client):
    client.post("/register", data={"username": "carol", "password": "secret123"}, follow_redirects=True)
    response = client.get("/workspace")
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "开启创作" in text
    assert "默认创作" in text
    assert "最近" in text
    assert "图片生成" in text
    assert "预计消耗" in text
    assert "选择比例" in text
    assert "选择分辨率" in text
    assert "资产库" in text
    assert "composer-controls" in text
    assert "Base URL" not in text
    assert "API Key" not in text
```

- [ ] **Step 2: Add existing-record rendering contract**

Append this test to `D:\AI\绘世\tests\test_auth_records.py`:

```python
def test_workspace_shows_latest_record_and_recent_list(client, app):
    from huishi.db import get_db, utc_now

    client.post("/register", data={"username": "studio-records", "password": "secret123"}, follow_redirects=True)
    with app.app_context():
        db = get_db()
        user_id = db.execute("SELECT id FROM users WHERE username = 'studio-records'").fetchone()["id"]
        db.execute(
            """
            INSERT INTO records
            (user_id, prompt, image_path, mode, resolution, actual_size, quality, output_format, count, model_source, elapsed_seconds, points_charged, favorite, created_at)
            VALUES (?, '主视觉图', '/static/uploads/main.png', 'text', '2K', '2560x1440', 'auto', 'png', 1, 'demo', 1.2, 2, 0, ?)
            """,
            (user_id, utc_now()),
        )
        db.execute(
            """
            INSERT INTO records
            (user_id, prompt, image_path, mode, resolution, actual_size, quality, output_format, count, model_source, elapsed_seconds, points_charged, favorite, created_at)
            VALUES (?, '最近缩略图', '/static/uploads/recent.png', 'reference', '1K', '864x1536', 'auto', 'png', 1, 'demo', 1.2, 2, 0, ?)
            """,
            (user_id, utc_now()),
        )
        db.commit()

    response = client.get("/workspace")
    text = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "主视觉图" in text or "最近缩略图" in text
    assert "重新编辑" in text
    assert "再次生成" in text
    assert "查看参数" in text
```

- [ ] **Step 3: Run tests to verify they fail before implementation**

Run:

```powershell
python -m pytest tests/test_auth_records.py::test_logged_in_user_can_view_workspace tests/test_auth_records.py::test_workspace_shows_latest_record_and_recent_list -v
```

Expected: FAIL because the current template does not yet contain `开启创作`, `资产库`, `选择比例`, `重新编辑`, or `再次生成`.

## Task 2: Workspace Template Restructure

**Files:**
- Modify: `D:\AI\绘世\templates\workspace.html`

- [ ] **Step 1: Replace the current `studio-shell` markup**

Replace the content inside `{% block content %}` in `D:\AI\绘世\templates\workspace.html` with:

```html
<main class="studio-shell">
  <aside class="studio-rail" aria-label="主导航">
    <a class="rail-logo" href="/" aria-label="绘世首页">绘</a>
    <nav class="rail-nav">
      <a class="is-active" href="/workspace"><span>灵感</span></a>
      <a href="/workspace"><span>生成</span></a>
      <a href="/history"><span>资产</span></a>
      <a href="/settings"><span>设置</span></a>
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
    <nav class="work-folder-list">
      {% for record in records[:6] %}
      <a class="{{ 'active' if loop.first else '' }}" href="/image/{{ record['id'] }}">
        <img src="{{ record['image_path'] }}" alt="">
        <span>{{ record["prompt"] }}</span>
      </a>
      {% else %}
      <span class="sidebar-empty">暂无创作记录</span>
      {% endfor %}
    </nav>
  </aside>

  <section class="studio-main">
    <header class="studio-filterbar" aria-label="作品筛选">
      <button type="button" class="filter-search" aria-label="搜索">⌕</button>
      <button type="button">时间</button>
      <button type="button">生成模式</button>
      <button type="button">操作类型</button>
      <a href="/history">资产库</a>
    </header>

    <section class="creation-stream" id="current-canvas" aria-live="polite">
      {% if current_record %}
      <article class="creation-item is-featured" data-record-id="{{ current_record['id'] }}">
        <div class="creation-actions">
          <button type="button" data-refill-record data-prompt="{{ current_record['prompt'] }}" data-mode="{{ current_record['mode'] }}" data-resolution="{{ current_record['resolution'] }}">重新编辑</button>
          <button type="button" data-regenerate-record data-prompt="{{ current_record['prompt'] }}" data-mode="{{ current_record['mode'] }}" data-resolution="{{ current_record['resolution'] }}">再次生成</button>
          <a href="/image/{{ current_record['id'] }}">查看参数</a>
        </div>
        <p class="creation-prompt">{{ current_record["prompt"] }}</p>
        <figure class="creation-image-wrap">
          <img id="current-image" src="{{ current_record['image_path'] }}" alt="{{ current_record['prompt'] }}">
        </figure>
        <footer class="creation-meta" id="current-meta">
          <span>{{ "图片生成" if current_record["mode"] == "text" else "参考图编辑" }}</span>
          <span>{{ current_record["resolution"] }}</span>
          <span>{{ current_record["actual_size"] }}</span>
          <span>{{ current_record["points_charged"] }} 点</span>
        </footer>
      </article>
      {% else %}
      <div class="canvas-empty" id="canvas-empty">
        <span>LIVE CANVAS</span>
        <strong>生成后的图片会显示在这里</strong>
      </div>
      {% endif %}

      <section class="recent-strip" aria-label="最近生成">
        {% for record in records[1:9] %}
        <a class="recent-card" href="/image/{{ record['id'] }}">
          <img src="{{ record['image_path'] }}" alt="{{ record['prompt'] }}">
          <span>{{ record["resolution"] }} · {{ record["actual_size"] }}</span>
        </a>
        {% endfor %}
      </section>
    </section>

    {% if g.user["email"] and not g.user["email_verified"] and g.user["role"] != "admin" %}
    <p class="generation-status is-error" id="generation-status" aria-live="polite">
      请先完成邮箱验证后再生成图片，<a href="/verify-email">去输入验证码</a>。
    </p>
    {% else %}
    <p class="generation-status" id="generation-status" aria-live="polite"></p>
    {% endif %}

    <form class="composer studio-composer" method="post" action="/generate" enctype="multipart/form-data">
      <textarea class="composer-prompt" name="prompt" rows="3" placeholder="输入你想生成的画面" required></textarea>
      <input type="hidden" name="mode" id="mode" value="text">
      <input type="hidden" name="ratio" id="ratio" value="9:16">
      <input type="hidden" name="resolution" id="resolution" value="2K">
      <input type="hidden" name="quality" id="quality" value="auto">
      <input type="hidden" name="output_format" id="output-format" value="png">

      <div class="composer-reference" id="reference-field">
        <label class="reference-drop">
          <span>+</span>
          <input name="reference_images" id="reference-images" type="file" accept="image/png,image/jpeg,image/webp" multiple>
        </label>
        <div class="reference-preview" id="reference-preview"></div>
      </div>

      <div class="composer-controls">
        <div class="segmented-control" data-field="mode" aria-label="生成模式">
          <button type="button" class="is-active" data-value="text">图片生成</button>
          <button type="button" data-value="reference">参考图编辑</button>
        </div>
        <button type="button" class="parameter-trigger" data-panel-trigger="ratio-panel">选择比例 <span id="ratio-label">9:16</span></button>
        <button type="button" class="parameter-trigger" data-panel-trigger="resolution-panel">选择分辨率 <span id="resolution-label">高清 2K</span></button>
        <label class="count-field"><span>数量</span><input name="count" type="number" min="1" max="8" value="1"></label>
        <div class="composer-meter"><span id="resolved-size">尺寸 1440x2560</span><strong id="estimate">预计消耗 - 点</strong></div>
        <button class="generate-button" type="submit">生成</button>
      </div>

      <div class="parameter-popover" id="ratio-panel" hidden>
        <span class="popover-title">选择比例</span>
        <div class="ratio-grid" data-field="ratio">
          <button type="button" data-value="auto">智能</button>
          <button type="button" data-value="21:9">21:9</button>
          <button type="button" data-value="16:9">16:9</button>
          <button type="button" data-value="3:2">3:2</button>
          <button type="button" data-value="4:3">4:3</button>
          <button type="button" data-value="1:1">1:1</button>
          <button type="button" data-value="3:4">3:4</button>
          <button type="button" data-value="2:3">2:3</button>
          <button type="button" class="is-active" data-value="9:16">9:16</button>
        </div>
      </div>

      <div class="parameter-popover" id="resolution-panel" hidden>
        <span class="popover-title">选择分辨率</span>
        <div class="resolution-grid" data-field="resolution">
          <button type="button" data-value="1K">标准 1K</button>
          <button type="button" class="is-active" data-value="2K">高清 2K</button>
          <button type="button" data-value="4K">超清 4K</button>
        </div>
      </div>
    </form>
  </section>
</main>
```

- [ ] **Step 2: Preserve script loading**

Keep the existing scripts block unchanged:

```html
{% block scripts %}
<script src="{{ url_for('static', filename='js/workspace.js') }}"></script>
{% endblock %}
```

- [ ] **Step 3: Run template tests**

Run:

```powershell
python -m pytest tests/test_auth_records.py::test_logged_in_user_can_view_workspace -v
```

Expected: template renders without Jinja errors; the test still may fail until CSS/JS terms are finalized.

## Task 3: Studio Theme, CSS Skin, And Responsive Layout

**Files:**
- Modify: `D:\AI\绘世\static\css\site.css`

- [ ] **Step 1: Choose the visual theme direction**

Use one of these three workspace themes before writing CSS:

```text
Recommended: Mist Canvas
- Light main canvas, dark left rail/sidebar, floating charcoal composer.
- Best fit for 绘世 because generated images stay visually prominent and the app still feels creation-focused.

Alternative: Night Studio
- Dark main canvas, dark rail/sidebar, high-contrast controls.
- Closest to the 即梦 screenshot, best for cinematic review but heavier visually.

Alternative: Paper Lab
- Warm light background, pale panels, graphite controls.
- Softer and friendlier, but less close to 即梦's professional tool feel.
```

Default to `Mist Canvas` unless the user explicitly chooses another option.

- [ ] **Step 2: Replace the existing workspace style block**

In `D:\AI\绘世\static\css\site.css`, replace the current `.studio-shell` through `.composer button:disabled` workspace block with:

```css
.workspace-page {
  --studio-bg: #eef1f5;
  --studio-main: #f8fafc;
  --studio-rail: #12151b;
  --studio-sidebar: #181b22;
  --studio-panel: rgba(255,255,255,.86);
  --studio-floating: rgba(36,39,48,.94);
  --studio-text: #151922;
  --studio-invert: #f5f7fb;
  --studio-muted: #707784;
  --studio-line: rgba(21,25,34,.12);
  --studio-accent: #00c8d7;
}
.workspace-page[data-studio-theme="night"] {
  --studio-bg: #090a0e;
  --studio-main: #0b0c10;
  --studio-rail: #111217;
  --studio-sidebar: #15161c;
  --studio-panel: rgba(24,27,34,.88);
  --studio-floating: rgba(37,39,47,.92);
  --studio-text: #f5f7fb;
  --studio-invert: #f5f7fb;
  --studio-muted: #9ba3af;
  --studio-line: rgba(255,255,255,.1);
  --studio-accent: #2ee7ff;
}
.workspace-page[data-studio-theme="paper"] {
  --studio-bg: #f3efe7;
  --studio-main: #fbfaf7;
  --studio-rail: #25231f;
  --studio-sidebar: #fffaf0;
  --studio-panel: rgba(255,255,255,.9);
  --studio-floating: rgba(47,48,52,.94);
  --studio-text: #171717;
  --studio-invert: #fffaf0;
  --studio-muted: #776f64;
  --studio-line: rgba(23,23,23,.13);
  --studio-accent: #087443;
}
.studio-shell { min-height: 100vh; display: grid; grid-template-columns: 96px 300px minmax(0, 1fr); background: var(--studio-bg); color: var(--studio-text); }
.studio-rail { min-height: 100vh; display: grid; grid-template-rows: auto 1fr auto; gap: 22px; padding: 28px 14px; border-right: 1px solid rgba(255,255,255,.07); background: var(--studio-rail); color: var(--studio-invert); }
.rail-logo { width: 40px; height: 40px; display: grid; place-items: center; border-radius: 8px; background: linear-gradient(145deg, #36d7ff, #f4ff76); color: #070809; font-weight: 900; }
.rail-nav, .rail-footer { display: grid; gap: 10px; }
.rail-nav a, .rail-footer a { min-height: 56px; display: grid; place-items: center; gap: 4px; border-radius: 8px; color: rgba(245,247,251,.74); font-size: 12px; font-weight: 800; }
.rail-nav a.is-active, .rail-nav a:hover, .rail-footer a:hover { background: rgba(255,255,255,.08); color: #fff; }
.studio-sidebar { min-height: 100vh; padding: 28px 18px; border-right: 1px solid var(--studio-line); background: var(--studio-sidebar); color: var(--studio-invert); }
.sidebar-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 18px; }
.sidebar-header strong { font-size: 20px; }
.sidebar-icon-button { width: 40px; height: 40px; display: grid; place-items: center; border-radius: 8px; background: #242631; color: #fff; font-size: 24px; }
.conversation-entry { display: flex; align-items: center; gap: 12px; min-height: 50px; padding: 8px; border-radius: 8px; color: #fff; }
.conversation-entry.is-pinned { background: rgba(255,255,255,.05); }
.conversation-thumb { width: 40px; height: 40px; display: grid; place-items: center; border-radius: 8px; background: #fff; color: #111217; font-weight: 900; }
.sidebar-section-title { margin: 24px 0 10px; color: #7f8794; font-size: 13px; font-weight: 900; }
.work-folder-list { display: grid; gap: 6px; }
.work-folder-list a { display: grid; grid-template-columns: 40px minmax(0, 1fr); align-items: center; gap: 10px; min-height: 46px; padding: 6px 8px; border-radius: 8px; color: rgba(245,247,251,.72); }
.work-folder-list a.active, .work-folder-list a:hover { background: #242631; color: #fff; }
.work-folder-list img { width: 34px; height: 34px; object-fit: cover; border-radius: 6px; background: #2b2d35; }
.work-folder-list span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sidebar-empty { display: block; padding: 10px; color: #7f8794; font-size: 13px; }
.studio-main { min-width: 0; min-height: 100vh; position: relative; padding: 110px 7vw 220px; background: radial-gradient(circle at 52% 0%, rgba(0,200,215,.12), transparent 36%), var(--studio-main); overflow-x: hidden; }
.studio-filterbar { position: fixed; z-index: 12; top: 24px; right: 48px; display: flex; align-items: center; gap: 4px; padding: 6px; border: 1px solid rgba(255,255,255,.1); border-radius: 8px; background: rgba(28,30,38,.88); box-shadow: 0 18px 52px rgba(0,0,0,.28); backdrop-filter: blur(18px); }
.studio-filterbar button, .studio-filterbar a { min-height: 34px; display: inline-flex; align-items: center; justify-content: center; padding: 0 14px; border: 0; border-radius: 6px; background: transparent; color: #f5f7fb; font-weight: 800; cursor: pointer; }
.studio-filterbar button:hover, .studio-filterbar a:hover { background: rgba(255,255,255,.08); }
.filter-search { width: 38px; padding: 0 !important; font-size: 22px; }
.creation-stream { display: grid; gap: 26px; width: min(1120px, 100%); margin: 0 auto; }
.creation-item { display: grid; gap: 16px; }
.creation-actions { display: flex; flex-wrap: wrap; gap: 8px; }
.creation-actions button, .creation-actions a { min-height: 40px; display: inline-flex; align-items: center; padding: 0 14px; border: 0; border-radius: 8px; background: #20222b; color: #fff; font-weight: 900; cursor: pointer; }
.creation-actions a { background: #2a2d38; }
.creation-prompt { max-width: 980px; margin: 0; color: var(--studio-text); font-size: 18px; line-height: 1.8; font-weight: 800; }
.creation-image-wrap { margin: 0; display: grid; place-items: center; min-height: 420px; overflow: hidden; background: var(--studio-panel); border: 1px solid var(--studio-line); border-radius: 8px; box-shadow: 0 26px 90px rgba(21,25,34,.16); }
.creation-image-wrap img { width: 100%; max-height: min(74vh, 760px); object-fit: contain; background: #111217; }
.creation-meta { display: flex; flex-wrap: wrap; gap: 8px; color: #9ba3af; }
.creation-meta span { min-height: 30px; display: inline-flex; align-items: center; padding: 0 10px; border-radius: 6px; background: rgba(255,255,255,.06); font-size: 13px; font-weight: 800; }
.recent-strip { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 10px; }
.recent-card { overflow: hidden; border-radius: 8px; background: #15161c; color: #dfe4eb; }
.recent-card img { width: 100%; aspect-ratio: 1; object-fit: cover; display: block; background: #22242c; }
.recent-card span { display: block; padding: 8px; color: #9ba3af; font-size: 12px; }
.canvas-empty { min-height: 420px; display: grid; place-items: center; align-content: center; gap: 10px; border: 1px dashed rgba(255,255,255,.16); border-radius: 8px; color: #9ba3af; text-align: center; background: #111217; }
.canvas-empty strong { color: #f5f7fb; font-size: 24px; }
.generation-status { position: fixed; left: 440px; right: 48px; bottom: 182px; z-index: 10; min-height: 24px; margin: 0; color: #27d36f; font-size: 13px; font-weight: 800; pointer-events: none; }
.generation-status.is-error { color: #ff6b61; pointer-events: auto; }
.generation-status a { color: #ff8e86; text-decoration: underline; text-underline-offset: 3px; }
.composer { position: fixed; z-index: 20; left: 50%; bottom: 24px; transform: translateX(-50%); width: min(960px, calc(100vw - 440px)); display: grid; gap: 12px; padding: 16px; border: 1px solid rgba(255,255,255,.1); border-radius: 8px; background: var(--studio-floating); box-shadow: 0 28px 92px rgba(0,0,0,.32); backdrop-filter: blur(22px); }
.composer-prompt { width: 100%; min-height: 78px; resize: vertical; padding: 14px; border: 0; border-radius: 8px; background: transparent; color: #fff; outline: 0; font-size: 16px; line-height: 1.7; }
.composer-prompt::placeholder { color: #9ba3af; }
.composer-reference { display: none; grid-template-columns: 76px minmax(0, 1fr); gap: 10px; }
.composer-reference.is-visible { display: grid; }
.reference-drop { width: 76px; height: 76px; display: grid; place-items: center; border-radius: 8px; background: #30333d; color: #b8c0cc; cursor: pointer; }
.reference-drop input { display: none; }
.reference-drop span { font-size: 28px; }
.reference-preview { display: flex; gap: 8px; overflow: hidden; }
.reference-preview img { width: 76px; height: 76px; object-fit: cover; border-radius: 8px; background: #22242c; }
.composer-controls { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.segmented-control { display: inline-flex; gap: 4px; padding: 4px; border-radius: 8px; background: #20222a; }
.segmented-control button, .parameter-trigger, .count-field, .composer-meter, .generate-button { min-height: 44px; border: 0; border-radius: 8px; background: #20222a; color: #eef2f7; font-weight: 900; }
.segmented-control button { padding: 0 12px; cursor: pointer; }
.segmented-control button.is-active { background: #303541; color: var(--studio-accent); }
.parameter-trigger { display: inline-flex; align-items: center; gap: 8px; padding: 0 12px; cursor: pointer; }
.parameter-trigger span { color: var(--studio-accent); }
.count-field { display: inline-grid; grid-template-columns: auto 58px; align-items: center; gap: 8px; padding: 0 10px; color: #9ba3af; font-size: 12px; }
.count-field input { width: 58px; height: 32px; border: 0; border-radius: 6px; background: #30333d; color: #fff; text-align: center; }
.composer-meter { display: grid; align-content: center; gap: 2px; min-width: 150px; padding: 0 12px; color: #9ba3af; font-size: 12px; }
.composer-meter strong { color: #fff; font-size: 13px; white-space: nowrap; }
.generate-button { margin-left: auto; min-width: 54px; padding: 0 16px; background: #f4f7fb; color: #111217; cursor: pointer; }
.generate-button:disabled { opacity: .62; cursor: wait; }
.parameter-popover { position: absolute; right: 96px; bottom: 100%; width: min(540px, calc(100vw - 36px)); margin-bottom: 12px; padding: 18px; border: 1px solid rgba(255,255,255,.08); border-radius: 8px; background: #1b1d24; box-shadow: 0 24px 84px rgba(0,0,0,.42); }
.popover-title { display: block; margin-bottom: 12px; color: #9ba3af; font-size: 13px; font-weight: 900; }
.ratio-grid, .resolution-grid { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 8px; }
.ratio-grid button, .resolution-grid button { min-height: 56px; border: 0; border-radius: 8px; background: #262934; color: #f5f7fb; font-weight: 900; cursor: pointer; }
.ratio-grid button.is-active, .resolution-grid button.is-active { background: #353b49; color: var(--studio-accent); }
```

- [ ] **Step 3: Replace workspace media queries**

In the existing `@media (max-width: 1180px)` and `@media (max-width: 760px)` sections, replace workspace-specific lines with:

```css
@media (max-width: 1180px) {
  .studio-shell { grid-template-columns: 76px minmax(0, 1fr); }
  .studio-sidebar { display: none; }
  .studio-main { padding: 96px 22px 250px; }
  .composer { width: min(920px, calc(100vw - 44px)); }
  .generation-status { left: 22px; right: 22px; bottom: 206px; }
  .studio-filterbar { right: 22px; }
}

@media (max-width: 760px) {
  .studio-shell { grid-template-columns: 1fr; }
  .studio-rail { min-height: auto; position: sticky; top: 0; z-index: 30; grid-template-columns: auto 1fr auto; grid-template-rows: auto; align-items: center; padding: 8px 12px; }
  .rail-nav, .rail-footer { display: flex; align-items: center; gap: 4px; }
  .rail-nav a, .rail-footer a { min-height: 40px; padding: 0 9px; }
  .studio-main { padding: 86px 14px 340px; }
  .studio-filterbar { left: 14px; right: 14px; overflow-x: auto; }
  .creation-image-wrap { min-height: 320px; }
  .composer { left: 14px; right: 14px; bottom: 14px; transform: none; width: auto; }
  .composer-controls { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .segmented-control, .composer-meter, .generate-button, .composer-reference { grid-column: 1 / -1; }
  .parameter-trigger, .count-field, .generate-button { width: 100%; }
  .ratio-grid, .resolution-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .generation-status { left: 14px; right: 14px; bottom: 304px; }
}
```

- [ ] **Step 4: Scan CSS for unintended one-note palette**

Run:

```powershell
Select-String -Path static\css\site.css -Pattern "--studio-bg|--studio-main|--studio-rail|--studio-accent"
```

Expected: theme variables appear in the workspace block only, while homepage/admin styles remain present.

## Task 4: Parameter Controls And Estimate JavaScript

**Files:**
- Modify: `D:\AI\绘世\static\js\workspace.js`

- [ ] **Step 1: Replace field selectors and size matrix**

At the top of `workspace.js`, replace selector setup and `SIZE_MATRIX` with:

```javascript
const form = document.querySelector(".composer");
const estimate = document.querySelector("#estimate");
const resolvedSize = document.querySelector("#resolved-size");
const ratioInput = document.querySelector("#ratio");
const resolutionInput = document.querySelector("#resolution");
const modeInput = document.querySelector("#mode");
const referenceField = document.querySelector("#reference-field");
const referenceImages = document.querySelector("#reference-images");
const referencePreview = document.querySelector("#reference-preview");
const statusLine = document.querySelector("#generation-status");
const currentCanvas = document.querySelector("#current-canvas");
const ratioLabel = document.querySelector("#ratio-label");
const resolutionLabel = document.querySelector("#resolution-label");

const SIZE_MATRIX = {
  "auto": { "1K": "1024x1024", "2K": "2048x2048" },
  "1:1": { "1K": "1024x1024", "2K": "2048x2048" },
  "21:9": { "1K": "1536x658", "2K": "2560x1097", "4K": "3840x1646" },
  "16:9": { "1K": "1536x864", "2K": "2560x1440", "4K": "3840x2160" },
  "9:16": { "1K": "864x1536", "2K": "1440x2560", "4K": "2160x3840" },
  "3:2": { "1K": "1536x1024", "2K": "2160x1440" },
  "2:3": { "1K": "1024x1536", "2K": "1440x2160" },
  "4:3": { "1K": "1536x1152", "2K": "2048x1536" },
  "3:4": { "1K": "1152x1536", "2K": "1536x2048" },
};

const RESOLUTION_LABELS = {
  "1K": "标准 1K",
  "2K": "高清 2K",
  "4K": "超清 4K",
};
```

- [ ] **Step 2: Replace resolution sync**

Replace `availableResolutions()` and `syncResolutionOptions()` with:

```javascript
function availableResolutions() {
  return Object.keys(SIZE_MATRIX[ratioInput?.value] || SIZE_MATRIX["9:16"]);
}

function syncResolutionOptions() {
  if (!ratioInput || !resolutionInput) return;
  const available = availableResolutions();
  if (!available.includes(resolutionInput.value)) {
    resolutionInput.value = available.includes("2K") ? "2K" : available[0];
  }
  const size = (SIZE_MATRIX[ratioInput.value] || SIZE_MATRIX["9:16"])[resolutionInput.value];
  if (resolvedSize) resolvedSize.textContent = `尺寸 ${size}`;
  if (ratioLabel) ratioLabel.textContent = ratioInput.value === "auto" ? "智能" : ratioInput.value;
  if (resolutionLabel) resolutionLabel.textContent = RESOLUTION_LABELS[resolutionInput.value] || resolutionInput.value;
  document.querySelectorAll('[data-field="resolution"] button').forEach((button) => {
    const enabled = available.includes(button.dataset.value);
    button.disabled = !enabled;
    button.classList.toggle("is-disabled", !enabled);
    button.classList.toggle("is-active", button.dataset.value === resolutionInput.value);
  });
  document.querySelectorAll('[data-field="ratio"] button').forEach((button) => {
    button.classList.toggle("is-active", button.dataset.value === ratioInput.value);
  });
}
```

- [ ] **Step 3: Add segmented controls and popovers**

Append these functions before `refreshEstimate()`:

```javascript
function closeParameterPanels(exceptId = "") {
  document.querySelectorAll(".parameter-popover").forEach((panel) => {
    if (panel.id !== exceptId) panel.hidden = true;
  });
}

function bindParameterControls() {
  document.querySelectorAll("[data-panel-trigger]").forEach((button) => {
    button.addEventListener("click", () => {
      const panel = document.querySelector(`#${button.dataset.panelTrigger}`);
      if (!panel) return;
      const willOpen = panel.hidden;
      closeParameterPanels(panel.id);
      panel.hidden = !willOpen;
    });
  });

  document.querySelectorAll("[data-field] button[data-value]").forEach((button) => {
    button.addEventListener("click", () => {
      const group = button.closest("[data-field]");
      const field = group?.dataset.field;
      const input = field ? document.querySelector(`#${field}`) : null;
      if (!input || button.disabled) return;
      input.value = button.dataset.value || input.value;
      group.querySelectorAll("button").forEach((item) => item.classList.remove("is-active"));
      button.classList.add("is-active");
      syncReferenceField();
      syncResolutionOptions();
      refreshEstimate();
    });
  });

  document.addEventListener("click", (event) => {
    if (!event.target.closest(".parameter-popover") && !event.target.closest("[data-panel-trigger]")) {
      closeParameterPanels();
    }
  });
}
```

- [ ] **Step 4: Replace reference-field sync and upload preview**

Replace `syncReferenceField()` with:

```javascript
function syncReferenceField() {
  if (!modeInput || !referenceField) return;
  const needsReference = modeInput.value === "reference";
  referenceField.classList.toggle("is-visible", needsReference);
  if (referenceImages) referenceImages.required = needsReference;
}

function renderReferencePreview() {
  if (!referenceImages || !referencePreview) return;
  referencePreview.innerHTML = "";
  Array.from(referenceImages.files || []).slice(0, 5).forEach((file) => {
    const image = document.createElement("img");
    image.alt = file.name;
    image.src = URL.createObjectURL(file);
    image.addEventListener("load", () => URL.revokeObjectURL(image.src), { once: true });
    referencePreview.appendChild(image);
  });
}
```

- [ ] **Step 5: Preserve estimate and submit behavior**

Keep `setStatus()` and `refreshEstimate()` mostly unchanged, but ensure `refreshEstimate()` calls the new sync helpers:

```javascript
async function refreshEstimate() {
  if (!form || !estimate) return;
  syncResolutionOptions();
  syncReferenceField();
  const params = new URLSearchParams(new FormData(form));
  try {
    const response = await fetch(`/api/estimate?${params.toString()}`);
    const result = await response.json();
    estimate.textContent = result.ok ? `预计消耗 ${result.cost} 点` : result.error;
  } catch (error) {
    estimate.textContent = "估价失败";
  }
}
```

- [ ] **Step 6: Replace `renderCurrentRecord()`**

Replace `renderCurrentRecord(record)` with:

```javascript
function renderCurrentRecord(record) {
  if (!currentCanvas || !record) return;
  const modeLabel = record.mode === "reference" ? "参考图编辑" : "图片生成";
  currentCanvas.innerHTML = `
    <article class="creation-item is-featured" data-record-id="${record.id}">
      <div class="creation-actions">
        <button type="button" data-refill-record data-prompt="" data-mode="${record.mode}" data-resolution="${record.resolution}">重新编辑</button>
        <button type="button" data-regenerate-record data-prompt="" data-mode="${record.mode}" data-resolution="${record.resolution}">再次生成</button>
        <a href="/image/${record.id}">查看参数</a>
      </div>
      <p class="creation-prompt"></p>
      <figure class="creation-image-wrap">
        <img id="current-image" src="${record.image_path}" alt="">
      </figure>
      <footer class="creation-meta" id="current-meta">
        <span>${modeLabel}</span>
        <span>${record.resolution}</span>
        <span>${record.actual_size}</span>
        <span>${record.points_charged} 点</span>
      </footer>
    </article>
  `;
  currentCanvas.querySelector(".creation-prompt").textContent = record.prompt;
  currentCanvas.querySelector("img").alt = record.prompt;
  currentCanvas.querySelectorAll("[data-prompt]").forEach((button) => {
    button.dataset.prompt = record.prompt;
  });
  bindRecordActionButtons();
}
```

- [ ] **Step 7: Add record action binding**

Append before initialization:

```javascript
function applyRecordToComposer(button, submitImmediately = false) {
  if (!form || !button) return;
  const prompt = button.dataset.prompt || "";
  const promptInput = form.querySelector('[name="prompt"]');
  if (promptInput) promptInput.value = prompt;
  if (modeInput && button.dataset.mode) modeInput.value = button.dataset.mode;
  if (resolutionInput && button.dataset.resolution) resolutionInput.value = button.dataset.resolution;
  syncReferenceField();
  syncResolutionOptions();
  refreshEstimate();
  if (submitImmediately) form.requestSubmit();
}

function bindRecordActionButtons() {
  document.querySelectorAll("[data-refill-record]").forEach((button) => {
    button.onclick = () => applyRecordToComposer(button, false);
  });
  document.querySelectorAll("[data-regenerate-record]").forEach((button) => {
    button.onclick = () => applyRecordToComposer(button, true);
  });
}
```

- [ ] **Step 8: Update initialization block**

Replace the existing `if (form) { ... }` block with:

```javascript
if (form) {
  form.addEventListener("change", refreshEstimate);
  form.addEventListener("submit", submitGeneration);
  if (referenceImages) referenceImages.addEventListener("change", renderReferencePreview);
  bindParameterControls();
  bindRecordActionButtons();
  syncResolutionOptions();
  syncReferenceField();
  refreshEstimate();
}
```

- [ ] **Step 9: Run existing generation JSON test**

Run:

```powershell
python -m pytest tests/test_routes.py::test_workspace_generation_json_updates_current_canvas -v
```

Expected: PASS; JSON shape and async generation still work.

## Task 5: Route Serialization Compatibility

**Files:**
- Modify: `D:\AI\绘世\huishi\routes_workspace.py`
- Modify: `D:\AI\绘世\tests\test_routes.py`

- [ ] **Step 1: Add JSON contract assertions**

In `test_workspace_generation_json_updates_current_canvas`, add:

```python
    assert payload["record"]["mode"] == "text"
    assert payload["record"]["resolution"] == "1K"
    assert payload["record"]["actual_size"] == "1536x864"
    assert payload["record"]["points_charged"] > 0
```

- [ ] **Step 2: Keep serialization stable**

Confirm `serialize_record()` still includes these keys:

```python
def serialize_record(record) -> dict[str, object]:
    return {
        "id": record["id"],
        "prompt": record["prompt"],
        "image_path": record["image_path"],
        "mode": record["mode"],
        "resolution": record["resolution"],
        "actual_size": record["actual_size"],
        "quality": record["quality"],
        "output_format": record["output_format"],
        "count": record["count"],
        "model_source": record["model_source"],
        "elapsed_seconds": record["elapsed_seconds"],
        "points_charged": record["points_charged"],
        "favorite": record["favorite"],
        "created_at": record["created_at"],
    }
```

If the function already matches, make no code change.

- [ ] **Step 3: Run route tests**

Run:

```powershell
python -m pytest tests/test_routes.py::test_workspace_generation_json_updates_current_canvas tests/test_routes.py::test_generation_rejects_count_above_limit tests/test_routes.py::test_reference_generation_passes_uploaded_images -v
```

Expected: PASS.

## Task 6: Full Regression And Visual Verification

**Files:**
- No required file changes.
- Optional output: `D:\AI\绘世\screenshots\jimeng-workspace-desktop.png`
- Optional output: `D:\AI\绘世\screenshots\jimeng-workspace-mobile.png`

- [ ] **Step 1: Run the backend and template test suite**

Run:

```powershell
python -m pytest -v
```

Expected: all tests PASS.

- [ ] **Step 2: Start the local server**

Run:

```powershell
python app.py
```

Expected: Flask listens at `http://127.0.0.1:8000`.

- [ ] **Step 3: Browser-check desktop workspace**

Open `http://127.0.0.1:8000/workspace` after logging in.

Verify:

- Left side has app rail and recent/default creation sidebar.
- Top right has search/time/mode/type/asset controls.
- Main area shows empty state or latest work without overlap.
- Bottom composer stays fixed, readable, and not wider than viewport.
- Ratio popover opens and selecting `16:9`, `1:1`, `9:16` updates `尺寸`.
- Resolution popover disables unsupported combinations and updates `预计消耗`.
- Reference mode reveals upload tray and requires at least one file.

- [ ] **Step 4: Browser-check mobile workspace**

Open the same page at a mobile-width viewport.

Verify:

- Rail collapses to a compact top bar.
- Filter bar scrolls horizontally instead of overlapping.
- Composer stacks controls into two columns and all text fits.
- Status line does not cover the generate button.

- [ ] **Step 5: End-to-end generation check**

With a test user that has points, submit a short prompt:

```text
电影感室内人像，窗边自然光，高清真实
```

Expected:

- Submit button changes to `生成中`.
- On success, latest result appears in the stream.
- `重新编辑` fills the composer.
- `再次生成` submits the same prompt.
- `查看参数` opens the existing detail page.

## Self-Review Notes

- Spec coverage: Covers the screenshot's visible layout, top filters, left navigation, current/recent generation display, bottom composer, ratio/resolution parameter panel, reference image tray, estimate, async generation state, and record actions.
- Scope boundary: Does not implement true project folders, canvas layers, crop/extend, mask editing, video generation, image search, or asset tagging because current database and routes do not support them yet. Visual direction is selectable; the default is not fixed to dark mode.
- Placeholder scan: No implementation step depends on undefined files or undefined function names.
- Type consistency: JS field ids match the planned template: `mode`, `ratio`, `resolution`, `reference-images`, `reference-preview`, `estimate`, `resolved-size`, `current-canvas`.
- Repository note: `D:\AI\绘世` is not currently a git repository, so commit steps are intentionally omitted.
