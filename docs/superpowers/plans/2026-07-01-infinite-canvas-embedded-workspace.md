# 无尽画布工作台嵌入实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**目标：** 把 `infinite-canvas` 以完整画布面板的形式嵌入到现有 Flask 工作台里，同时不削弱画布原有能力。

**架构：** 保持 `infinite-canvas` 作为独立的 Next.js 应用，只通过 `iframe` 挂载到 Flask 工作台中。Flask 负责工作台外壳、画布地址配置和安全头；嵌入的画布继续保留自己的路由、持久化和状态管理。只做一个很轻量的桥接，用来处理尺寸和打开上下文，确保画布行为和原应用一致。

**技术栈：** Flask、Jinja2、原生 JS、CSS、Next.js `iframe` 嵌入、pytest。

---

### 任务 1：增加工作台画布嵌入路由和配置

**Files:**
- 修改：`D:/AI/huishihuabu/huishi/config.py`
- 修改：`D:/AI/huishihuabu/app.py`
- 修改：`D:/AI/huishihuabu/huishi/routes_workspace.py`
- 测试：`D:/AI/huishihuabu/tests/test_workspace_generation_flow.py`

- [ ] **步骤 1：先写失败测试**

```python
def test_workspace_renders_embedded_canvas_frame(app):
    app.config["CANVAS_APP_URL"] = "http://127.0.0.1:3000"
    with app.app_context():
        user_id = create_user()

    with app.test_client() as client:
        login(client, user_id)
        response = client.get("/workspace?canvas=1")

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'data-workspace-pane="canvas"' in html
    assert '<iframe' in html
    assert 'http://127.0.0.1:3000/canvas' in html
```

- [ ] **步骤 2：运行测试，确认它先失败**

运行：`python -m pytest tests/test_workspace_generation_flow.py::test_workspace_renders_embedded_canvas_frame -v`
预期：失败，因为 `/workspace?canvas=1` 和画布嵌入标记还不存在。

- [ ] **步骤 3：写最小实现**

```python
# huishi/config.py
class Config:
    CANVAS_APP_URL = os.environ.get("HUISHI_CANVAS_APP_URL", "http://127.0.0.1:3000")

# huishi/routes_workspace.py
@bp.get("/workspace")
@login_required
def workspace():
    canvas_app_url = str(current_app.config.get("CANVAS_APP_URL") or "").rstrip("/")
    canvas_embed_url = f"{canvas_app_url}/canvas" if canvas_app_url else ""
    return render_template(
        "workspace.html",
        canvas_app_url=canvas_app_url,
        canvas_embed_url=canvas_embed_url,
        canvas_mode=request.args.get("canvas") == "1",
        # existing context stays unchanged
    )

# app.py
app.config["CANVAS_APP_URL"] = os.environ.get("HUISHI_CANVAS_APP_URL", app.config.get("CANVAS_APP_URL", "http://127.0.0.1:3000"))
```

- [ ] **步骤 4：运行测试，确认通过**

运行：`python -m pytest tests/test_workspace_generation_flow.py::test_workspace_renders_embedded_canvas_frame -v`
预期：通过，页面能渲染 iframe 且包含配置的地址。

- [ ] **步骤 5：提交**

```bash
git add D:/AI/huishihuabu/huishi/config.py D:/AI/huishihuabu/app.py D:/AI/huishihuabu/huishi/routes_workspace.py D:/AI/huishihuabu/tests/test_workspace_generation_flow.py
git commit -m "feat: add embedded canvas workspace route"
```

### 任务 2：把工作台模板改成左右分栏的工作台/画布外壳

**Files:**
- 修改：`D:/AI/huishihuabu/templates/workspace.html`
- 修改：`D:/AI/huishihuabu/templates/partials/studio_nav.html`
- 修改：`D:/AI/huishihuabu/static/css/site.css`
- 测试：`D:/AI/huishihuabu/tests/test_workspace_generation_flow.py`

- [ ] **步骤 1：先写失败测试**

```python
def test_workspace_template_exposes_canvas_split_layout():
    template = Path("templates/workspace.html").read_text(encoding="utf-8")
    assert 'data-workspace-shell' in template
    assert 'data-workspace-pane="canvas"' in template
    assert 'data-workspace-pane="generation"' in template
    assert 'iframe' in template
```

- [ ] **步骤 2：运行测试，确认它先失败**

运行：`python -m pytest tests/test_workspace_generation_flow.py::test_workspace_template_exposes_canvas_split_layout -v`
预期：失败，因为模板还没有分栏外壳。

- [ ] **步骤 3：写最小实现**

```html
<!-- workspace.html -->
<main class="studio-shell studio-shell--embedded" data-studio-theme="mist">
  {% include "partials/studio_nav.html" %}
  <section class="workspace-split-shell" data-workspace-shell>
    <section class="workspace-pane workspace-pane--generation" data-workspace-pane="generation">
      <!-- existing generation UI -->
    </section>
    <section class="workspace-pane workspace-pane--canvas" data-workspace-pane="canvas">
      <header class="canvas-embed-header">
        <strong>无限画布</strong>
        <a href="{{ canvas_app_url }}/canvas" target="_blank" rel="noopener">在新窗口打开</a>
      </header>
      <iframe
        class="canvas-embed-frame"
        src="{{ canvas_embed_url }}"
        title="无限画布"
        loading="lazy"
        referrerpolicy="no-referrer"
      ></iframe>
    </section>
  </section>
</main>
```

- [ ] **步骤 4：运行测试，确认通过**

运行：`python -m pytest tests/test_workspace_generation_flow.py::test_workspace_template_exposes_canvas_split_layout -v`
预期：通过，分栏外壳和 iframe 标记都存在。

- [ ] **步骤 5：提交**

```bash
git add D:/AI/huishihuabu/templates/workspace.html D:/AI/huishihuabu/templates/partials/studio_nav.html D:/AI/huishihuabu/static/css/site.css D:/AI/huishihuabu/tests/test_workspace_generation_flow.py
git commit -m "feat: embed canvas in workspace layout"
```

### 任务 3：让嵌入画布能完整自适应尺寸

**Files:**
- 修改：`D:/AI/huishihuabu/static/css/site.css`
- 修改：`D:/AI/huishihuabu/static/js/workspace.js`
- 测试：`D:/AI/huishihuabu/tests/test_workspace_generation_flow.py`

- [ ] **步骤 1：先写失败测试**

```python
def test_workspace_canvas_embed_resizes_with_shell():
    css = Path("static/css/site.css").read_text(encoding="utf-8")
    assert ".workspace-split-shell" in css
    assert ".canvas-embed-frame" in css
    source = Path("static/js/workspace.js").read_text(encoding="utf-8")
    assert "ResizeObserver" in source
```

- [ ] **步骤 2：运行测试，确认它先失败**

运行：`python -m pytest tests/test_workspace_generation_flow.py::test_workspace_canvas_embed_resizes_with_shell -v`
预期：失败，因为还没有分栏尺寸 CSS 和 iframe 高度桥接。

- [ ] **步骤 3：写最小实现**

```css
/* site.css */
.workspace-split-shell {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(360px, .8fr);
  gap: 16px;
  height: calc(100dvh - 24px);
}
.workspace-pane {
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}
.canvas-embed-frame {
  width: 100%;
  height: 100%;
  border: 0;
  border-radius: 18px;
}
```

```javascript
// workspace.js
const canvasPane = document.querySelector('[data-workspace-pane="canvas"]');
const canvasFrame = document.querySelector(".canvas-embed-frame");
if (canvasPane && canvasFrame && "ResizeObserver" in window) {
  const observer = new ResizeObserver(() => {
    canvasFrame.style.height = `${canvasPane.clientHeight - 48}px`;
  });
  observer.observe(canvasPane);
}
```

- [ ] **步骤 4：运行测试，确认通过**

运行：`python -m pytest tests/test_workspace_generation_flow.py::test_workspace_canvas_embed_resizes_with_shell -v`
预期：通过，分栏布局 CSS 和尺寸桥接都存在。

- [ ] **步骤 5：提交**

```bash
git add D:/AI/huishihuabu/static/css/site.css D:/AI/huishihuabu/static/js/workspace.js D:/AI/huishihuabu/tests/test_workspace_generation_flow.py
git commit -m "feat: size embedded canvas within workspace"
```

### 任务 4：确保生产环境允许 iframe 嵌入

**Files:**
- 修改：`D:/AI/huishihuabu/app.py`
- 修改：`D:/AI/huishihuabu/huishi/routes_workspace.py`
- 测试：`D:/AI/huishihuabu/tests/test_workspace_generation_flow.py`

- [ ] **步骤 1：先写失败测试**

```python
def test_workspace_allows_canvas_frame_sources(app):
    app.config["CANVAS_APP_URL"] = "http://127.0.0.1:3000"
    with app.app_context():
        user_id = create_user()

    with app.test_client() as client:
        login(client, user_id)
        response = client.get("/workspace?canvas=1")

    assert response.status_code == 200
    assert "frame-ancestors" in response.headers.get("Content-Security-Policy", "")
```

- [ ] **步骤 2：运行测试，确认它先失败**

运行：`python -m pytest tests/test_workspace_generation_flow.py::test_workspace_allows_canvas_frame_sources -v`
预期：失败，因为 CSP 还没有包含画布主机。

- [ ] **步骤 3：写最小实现**

```python
# app.py
canvas_origin = urlsplit(str(app.config.get("CANVAS_APP_URL") or "")).scheme + "://" + urlsplit(str(app.config.get("CANVAS_APP_URL") or "")).netloc
response.headers.setdefault(
    "Content-Security-Policy",
    f"default-src 'self'; frame-src 'self' {canvas_origin}; frame-ancestors 'self'; ..."
)

# huishi/routes_workspace.py
@app.after_request
def add_workspace_frame_headers(response):
    if request.path == "/workspace":
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    return response
```

- [ ] **步骤 4：运行测试，确认通过**

运行：`python -m pytest tests/test_workspace_generation_flow.py::test_workspace_allows_canvas_frame_sources -v`
预期：通过，CSP 允许 iframe。

- [ ] **步骤 5：提交**

```bash
git add D:/AI/huishihuabu/app.py D:/AI/huishihuabu/huishi/routes_workspace.py D:/AI/huishihuabu/tests/test_workspace_generation_flow.py
git commit -m "feat: allow embedded canvas framing"
```

### 任务 5：端到端验证嵌入式工作台

**Files:**
- 仅测试：`D:/AI/huishihuabu/tests/test_workspace_generation_flow.py`

- [ ] **步骤 1：写端到端冒烟测试**

```python
def test_workspace_canvas_embed_smoke(app):
    app.config["CANVAS_APP_URL"] = "http://127.0.0.1:3000"
    with app.app_context():
        user_id = create_user()

    with app.test_client() as client:
        login(client, user_id)
        response = client.get("/workspace?canvas=1")

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "无限画布" in html
    assert "iframe" in html
    assert "/workspace" in html
```

- [ ] **步骤 2：运行冒烟测试和工作台相关测试**

运行：`python -m pytest tests/test_workspace_generation_flow.py -v`
预期：所有工作台测试通过，包括新增的画布嵌入测试。

- [ ] **步骤 3：提交**

```bash
git add D:/AI/huishihuabu/tests/test_workspace_generation_flow.py
git commit -m "test: cover embedded canvas workspace flow"
```

**自检清单**
- 嵌入式画布仍然通过 `iframe` 隔离，`infinite-canvas` 保持独立。
- Flask 负责外壳布局、路由配置和安全头。
- 工作台原有生成 UI 仍然能渲染，并且保持可测试。
- 没有任何任务去重写画布内部逻辑或持久化方案。
