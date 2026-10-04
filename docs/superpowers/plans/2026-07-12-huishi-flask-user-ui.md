# 绘世 Flask 用户端 UI 优化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用统一主题和组件语言优化 Flask 工作台、资产、提示词入口、认证辅助页、账户和计费页面，同时保持现有业务结构。

**Architecture:** `site.css` 负责通用组件，工作台结构继续由现有 Jinja 模板和 `workspace.js` 驱动。只添加必要的语义类名和状态属性，不重写生成、对话、筛选、计费或 CSRF 逻辑。

**Tech Stack:** Flask/Jinja2、原生 CSS/JS、pytest。

---

### Task 1: 锁定用户端结构契约

**Files:**
- Create: `tests/test_user_ui_structure.py`
- Read: `templates/workspace.html`, `templates/assets.html`, `templates/asset_detail.html`, `templates/prompts.html`, `templates/account.html`, `templates/account_api_key.html`, `templates/pricing.html`

- [ ] **Step 1: 写结构测试**

```python
from pathlib import Path


def text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_workspace_keeps_two_navigation_layers_and_composer():
    page = text("templates/workspace.html")
    nav = text("templates/partials/studio_nav.html")
    assert 'class="studio-rail"' in nav
    assert 'class="studio-sidebar"' in nav
    assert 'id="composer"' in page
    assert 'class="creation-stream"' in page


def test_asset_detail_does_not_mount_studio_navigation():
    page = text("templates/asset_detail.html")
    assert "partials/studio_nav.html" not in page
    assert 'class="detail-image"' in page
    assert 'class="detail-panel"' in page


def test_prompts_remains_an_iframe_boundary():
    page = text("templates/prompts.html")
    assert "prompts_embed_url" in page
    assert 'class="canvas-frame"' in page


def test_account_pages_use_top_navigation_not_studio_rail():
    for path in ("templates/account.html", "templates/account_api_key.html", "templates/pricing.html"):
        page = text(path)
        assert 'class="simple-nav"' in page
        assert "partials/studio_nav.html" not in page
```

- [ ] **Step 2: 运行测试**

Run: `ssh huishi-vm "cd /opt/huishi && .venv/bin/python -m pytest tests/test_user_ui_structure.py -q"`  
Expected: 现有结构保护项 PASS；后续改造必须持续通过。

### Task 2: 优化工作台双侧栏与结果流

**Files:**
- Modify: `templates/partials/studio_nav.html`
- Modify: `templates/workspace.html`
- Modify: `static/css/site.css`
- Modify only if state hooks are missing: `static/js/workspace.js`
- Test: `tests/test_workspace_generation_flow.py`, `tests/test_workspace_composer_copy.py`

- [ ] **Step 1: 添加语义主题选择器，不改变 DOM 顺序**

```css
.studio-shell { background: var(--color-bg); color: var(--color-text); }
.studio-rail,
.studio-sidebar { background: var(--color-surface); border-color: var(--color-border); }
.rail-nav-item.is-active,
.dialogue-link.active { background: var(--color-primary-soft); color: var(--color-primary); }
```

- [ ] **Step 2: 统一输入区和结果操作**

```css
.composer,
.creation-item { border-radius: var(--radius-panel); }
.composer { background: var(--color-surface); border: 1px solid var(--color-border); }
.creation-action-group button { border-radius: var(--radius-control); }
```

- [ ] **Step 3: 为任务状态增加属性**

模板和 JS 使用现有 `is-generating`、失败详情和 `aria-live`，补充 `data-task-state="queued|running|success|failed|refunded"`，不建立第二套状态机。

- [ ] **Step 4: 运行工作台回归测试**

Run: `ssh huishi-vm "cd /opt/huishi && .venv/bin/python -m pytest tests/test_workspace_generation_flow.py tests/test_workspace_composer_copy.py -q"`  
Expected: PASS。

### Task 3: 增加工作台响应式折叠

**Files:**
- Modify: `static/css/site.css`
- Modify: `templates/partials/studio_nav.html`
- Modify: `static/js/workspace.js`

- [ ] **Step 1: 添加对话侧栏切换按钮**

```html
<button type="button" class="conversation-toggle" data-conversation-toggle aria-controls="studio-conversations" aria-expanded="false">
  <span class="sr-only">打开历史对话</span>
</button>
```

- [ ] **Step 2: 给历史侧栏稳定 ID**

```html
<aside id="studio-conversations" class="studio-sidebar" aria-label="创作入口">
```

- [ ] **Step 3: 实现移动端状态**

```js
const toggle = document.querySelector("[data-conversation-toggle]");
const sidebar = document.querySelector("#studio-conversations");
toggle?.addEventListener("click", () => {
  const open = !sidebar?.classList.contains("is-open");
  sidebar?.classList.toggle("is-open", open);
  toggle.setAttribute("aria-expanded", String(open));
});
```

- [ ] **Step 4: CSS 只在窄屏变为抽屉**

```css
@media (max-width: 760px) {
  .studio-sidebar { position: fixed; inset: 0 auto 0 var(--studio-rail-width); transform: translateX(-100%); }
  .studio-sidebar.is-open { transform: translateX(0); }
}
```

### Task 4: 优化资产库真实数据边界

**Files:**
- Modify: `templates/assets.html`
- Modify: `static/css/site.css`
- Modify: `static/js/assets.js`
- Test: `tests/test_asset_detail_actions.py`, `tests/test_image_optimization.py`

- [ ] **Step 1: 为图片提供加载和失败状态**

```html
<div class="asset-media" data-asset-media>
  <span class="asset-media-status" data-asset-media-status>加载中</span>
  <img src="{{ record['image_path'] }}" alt="{{ record['prompt'] }}" loading="lazy" decoding="async">
</div>
```

- [ ] **Step 2: 在 `assets.js` 处理 load/error**

```js
document.querySelectorAll("[data-asset-media] img").forEach((image) => {
  image.addEventListener("load", () => image.closest("[data-asset-media]")?.setAttribute("data-state", "ready"));
  image.addEventListener("error", () => image.closest("[data-asset-media]")?.setAttribute("data-state", "error"));
});
```

- [ ] **Step 3: 处理超长提示词**

```css
.asset-card-body strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.asset-media[data-state="error"] { background: var(--color-surface-subtle); }
.asset-media[data-state="error"] .asset-media-status { display: grid; }
```

- [ ] **Step 4: 运行资产回归测试**

Run: `ssh huishi-vm "cd /opt/huishi && .venv/bin/python -m pytest tests/test_asset_detail_actions.py tests/test_image_optimization.py -q"`  
Expected: PASS。

### Task 5: 优化资产详情与确认弹窗

**Files:**
- Modify: `templates/asset_detail.html`
- Modify: `static/css/site.css`
- Modify: `static/js/workspace.js`

- [ ] **Step 1: 保留分栏，仅替换主题样式**

```css
.asset-detail-shell { background: var(--color-bg); }
.detail-image { background: oklch(14% 0.005 250); }
.detail-panel { background: var(--color-surface); border-color: var(--color-border); }
.detail-prompt-card { background: var(--color-surface-subtle); border-radius: var(--radius-panel); }
```

- [ ] **Step 2: 统一 modal 状态**

确认弹窗使用现有 `<dialog>`，增加 `aria-describedby`，危险操作使用语义红色；不新增嵌套 modal。

- [ ] **Step 3: 浏览器验证来源返回**

从资产库和工作台分别进入详情，确认返回链接、再次编辑、收藏、下载、删除和再次生成保持原行为。

### Task 6: 优化提示词 iframe 壳与主题同步占位

**Files:**
- Modify: `templates/prompts.html`
- Modify: `static/css/site.css`
- Modify: `templates/canvas.html`
- Test: `tests/test_canvas_embed_mode_contract.py`, `tests/test_settings_config_status.py`

- [ ] **Step 1: 保留 iframe 并增加状态容器**

```html
<div class="canvas-frame-wrap" data-embed-state="loading">
  <div class="embed-status" role="status">提示词库加载中</div>
  <iframe class="canvas-frame" src="{{ prompts_embed_url }}" title="提示词库" loading="eager"></iframe>
</div>
```

- [ ] **Step 2: 将已配置和未配置状态使用同一视觉组件**

`canvas-empty-state` 和 `embed-status` 使用语义表面、单一主操作和明确重试/配置入口。

- [ ] **Step 3: 运行 iframe 回归测试**

Run: `ssh huishi-vm "cd /opt/huishi && .venv/bin/python -m pytest tests/test_canvas_embed_mode_contract.py tests/test_settings_config_status.py -q"`  
Expected: PASS。

### Task 7: 优化账户、API Key、价格与认证辅助页

**Files:**
- Modify: `templates/account.html`
- Modify: `templates/account_api_key.html`
- Modify: `templates/pricing.html`
- Modify: `templates/forgot_password.html`
- Modify: `templates/verify_email.html`
- Modify: `static/css/site.css`
- Test: `tests/test_account_experience.py`, `tests/test_user_key_global_toggle.py`, `tests/test_auth_transactions.py`

- [ ] **Step 1: 统一顶部导航和页面标题**

保留 `simple-nav`，不引入 `studio-rail`。标题使用无衬线，面板改用语义令牌。

- [ ] **Step 2: API Key 危险区保持独立**

```css
.danger-zone { border: 1px solid color-mix(in oklch, var(--color-danger) 35%, var(--color-border)); }
.btn-danger { color: var(--color-danger); }
```

- [ ] **Step 3: 验证码表单覆盖发送和错误状态**

保留 CSRF、字段名和现有路由；添加 `aria-live` 反馈区和禁用状态样式。

- [ ] **Step 4: 运行账户与认证测试**

Run: `ssh huishi-vm "cd /opt/huishi && .venv/bin/python -m pytest tests/test_account_experience.py tests/test_user_key_global_toggle.py tests/test_auth_transactions.py -q"`  
Expected: PASS。

### Task 8: Flask 用户端浏览器回归

**Files:**
- No source changes unless defects are found.

- [ ] **Step 1: 检查瓷白、曜黑和 system**

页面：工作台、资产库、资产详情、提示词、账户、API Key、价格、重置密码、邮箱验证。

- [ ] **Step 2: 检查真实数据边界**

使用现有缺图记录、长提示词和长对话名；页面壳不得横向溢出。

- [ ] **Step 3: 检查移动端**

`390x844` 和 `320x568`：对话抽屉可用、输入区不遮挡结果、资产筛选可达。

- [ ] **Step 4: 运行允许的主站测试**

Run: `ssh huishi-vm "cd /opt/huishi && npm test"`  
Expected: 全部 Flask 测试 PASS。
