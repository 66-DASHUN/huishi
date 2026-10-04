# 绘世后台与统一业务流水 UI 优化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将后台管理统一为同色主题高密度界面，并把生成记录与计费流水合并为可筛选、可审计的业务流水视图。

**Architecture:** 后台布局继续由 `admin/layout.html` 提供，页面复用现有权限和分页工具。新增只读的规范化业务事件 DTO，在 `routes_admin.py` 组合现有生成记录与积分流水，不迁移数据库或改变交易写入。

**Tech Stack:** Flask/Jinja2、SQLite/PostgreSQL、原生 CSS/JS、pytest。

---

### Task 1: 锁定后台主题与布局契约

**Files:**
- Create: `tests/test_admin_ui_structure.py`
- Read: `templates/admin/layout.html`, `static/css/site.css`

- [ ] **Step 1: 写失败测试**

```python
from pathlib import Path


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_admin_layout_uses_shared_theme_and_navigation():
    layout = read("templates/admin/layout.html")
    assert "data-theme-toggle" in layout
    assert "运行总览" in layout
    assert "业务流水" in layout


def test_admin_css_does_not_force_a_black_sidebar():
    css = read("static/css/site.css")
    assert ".admin-console-sidebar{background:#" not in css.replace(" ", "")
    assert "var(--color-surface)" in css
```

- [ ] **Step 2: 运行并确认失败**

Run: `ssh huishi-vm "cd /opt/huishi && .venv/bin/python -m pytest tests/test_admin_ui_structure.py -q"`  
Expected: FAIL，导航仍为“记录与流水”或缺主题入口。

### Task 2: 统一后台布局和主题

**Files:**
- Modify: `templates/admin/layout.html`
- Modify: `static/css/site.css`
- Modify: `static/js/theme.js`

- [ ] **Step 1: 导航改名并添加主题选择**

```html
<a href="/admin/records" {% if request.endpoint in ["admin.records", "admin.user_ledger"] %}aria-current="page"{% endif %}>业务流水</a>
<div class="admin-theme-control" aria-label="主题">
  <button type="button" data-theme-option="system">跟随系统</button>
  <button type="button" data-theme-option="light">瓷白</button>
  <button type="button" data-theme-option="dark">曜黑</button>
</div>
```

- [ ] **Step 2: 侧栏和内容使用同一主题层级**

```css
.admin-console-sidebar,
.admin-console-topbar { background: var(--color-surface); border-color: var(--color-border); }
.admin-console-main { background: var(--color-bg); }
.admin-console-sidebar a[aria-current="page"] { background: var(--color-primary-soft); color: var(--color-primary); }
```

- [ ] **Step 3: 运行布局测试**

Run: `ssh huishi-vm "cd /opt/huishi && .venv/bin/python -m pytest tests/test_admin_ui_structure.py -q"`  
Expected: PASS。

### Task 3: 定义业务事件 DTO 组合函数

**Files:**
- Create: `huishi/admin_activity.py`
- Create: `tests/test_admin_activity.py`
- Read: `huishi/records.py`, `huishi/billing.py`, `huishi/db_backend.py`

- [ ] **Step 1: 写 DTO 测试**

```python
from huishi.admin_activity import merge_activity_rows


def test_generation_and_charge_merge_into_one_event():
    records = [{"id": 10, "user_id": 2, "username": "mira", "prompt": "scene", "mode": "text", "resolution": "2K", "actual_size": "2560x1440", "model_source": "gpt-image-2", "created_at": "2026-07-12T10:00:00"}]
    ledger = [{"id": 90, "user_id": 2, "username": "mira", "delta": -2, "reason": "generation", "record_id": 10, "created_at": "2026-07-12T10:00:01"}]
    rows = merge_activity_rows(records, ledger)
    assert len(rows) == 1
    assert rows[0]["event_type"] == "image_generation"
    assert rows[0]["points_delta"] == -2
    assert rows[0]["record_id"] == 10
    assert rows[0]["ledger_id"] == 90


def test_reward_without_record_remains_visible():
    rows = merge_activity_rows([], [{"id": 91, "user_id": 2, "username": "mira", "delta": 100, "reason": "invite_reward", "record_id": None, "created_at": "2026-07-12T11:00:00"}])
    assert rows[0]["event_type"] == "invite_reward"
    assert rows[0]["record_id"] is None


def test_refund_is_not_duplicated_with_failed_record():
    records = [{"id": 11, "user_id": 2, "username": "mira", "prompt": "scene", "mode": "text", "resolution": "4K", "actual_size": "3840x2160", "model_source": "gpt-image-2", "status": "failed", "created_at": "2026-07-12T12:00:00"}]
    ledger = [{"id": 92, "user_id": 2, "username": "mira", "delta": 6, "reason": "generation_refund", "record_id": 11, "created_at": "2026-07-12T12:00:03"}]
    rows = merge_activity_rows(records, ledger)
    assert len(rows) == 1
    assert rows[0]["event_type"] == "generation_refund"
```

- [ ] **Step 2: 运行并确认失败**

Run: `ssh huishi-vm "cd /opt/huishi && .venv/bin/python -m pytest tests/test_admin_activity.py -q"`  
Expected: FAIL，模块不存在。

- [ ] **Step 3: 实现纯组合函数**

```python
def merge_activity_rows(records, ledger_rows):
    ledger_by_record = {row["record_id"]: row for row in ledger_rows if row.get("record_id")}
    consumed_ledger_ids = set()
    events = []
    for record in records:
        ledger = ledger_by_record.get(record["id"])
        if ledger:
            consumed_ledger_ids.add(ledger["id"])
        events.append(build_record_event(record, ledger))
    for ledger in ledger_rows:
        if ledger["id"] not in consumed_ledger_ids:
            events.append(build_ledger_event(ledger))
    return sorted(events, key=lambda row: (row["occurred_at"], row["id"]), reverse=True)
```

`build_record_event` 和 `build_ledger_event` 必须返回规范中的全部 DTO 字段；未知 reason 映射为 `other`，不得丢弃。

- [ ] **Step 4: 运行 DTO 测试**

Run: `ssh huishi-vm "cd /opt/huishi && .venv/bin/python -m pytest tests/test_admin_activity.py -q"`  
Expected: PASS。

### Task 4: 建立服务端查询和分页

**Files:**
- Modify: `huishi/admin_activity.py`
- Modify: `huishi/routes_admin.py`
- Modify: `tests/test_admin_pagination.py`
- Modify: `tests/test_admin_console_experience.py`

- [ ] **Step 1: 写路由过滤测试**

```python
def test_business_activity_filters_by_user_event_and_date(admin_client):
    response = admin_client.get("/admin/records?user=mira&event_type=image_generation&from=2026-07-01&to=2026-07-31")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "业务流水" in body
    assert "mira" in body
```

- [ ] **Step 2: 将 `/admin/records` 改为统一查询**

路由解析 `q`、`user`、`event_type`、`mode`、`status`、`from`、`to`、`page`、`per_page`，调用：

```python
activity_page = query_activity_page(
    search=request.args.get("q", "").strip(),
    user=request.args.get("user", "").strip(),
    event_type=request.args.get("event_type", "").strip(),
    mode=request.args.get("mode", "").strip(),
    status=request.args.get("status", "").strip(),
    from_date=request.args.get("from", "").strip(),
    to_date=request.args.get("to", "").strip(),
    page=parse_positive_int(request.args.get("page"), default=1),
    per_page=parse_per_page(request.args.get("per_page")),
)
```

- [ ] **Step 3: PostgreSQL/SQLite 使用相同参数化过滤**

查询只能使用现有数据库边界 API，不在路由内拼接 SQL 字符串。分页总数与展示结果必须使用相同过滤条件。

- [ ] **Step 4: 运行分页和后台测试**

Run: `ssh huishi-vm "cd /opt/huishi && .venv/bin/python -m pytest tests/test_admin_activity.py tests/test_admin_pagination.py tests/test_admin_console_experience.py -q"`  
Expected: PASS。

### Task 5: 重做业务流水模板和详情抽屉

**Files:**
- Modify: `templates/admin/records.html`
- Modify: `static/js/admin.js`
- Modify: `static/css/site.css`
- Test: `tests/test_admin_console_experience.py`

- [ ] **Step 1: 用单表替换两个表**

```html
<table class="admin-data-table admin-activity-table">
  <thead><tr><th>时间</th><th>用户</th><th>事件</th><th>业务详情</th><th>积分</th><th>状态</th><th>关联记录</th><th>操作</th></tr></thead>
  <tbody>
    {% for event in events %}
    <tr data-activity-row data-activity='{{ event|tojson|forceescape }}'>
      <td><time>{{ event.occurred_at }}</time></td>
      <td>{{ event.username }}</td>
      <td><span class="admin-event-pill">{{ event.event_type }}</span></td>
      <td class="admin-record-prompt" title="{{ event.summary }}">{{ event.summary }}</td>
      <td>{{ "%+d"|format(event.points_delta) }} 点</td>
      <td>{{ event.status }}</td>
      <td>{% if event.record_id %}#{{ event.record_id }}{% else %}-{% endif %}</td>
      <td><button type="button" data-activity-open>查看</button></td>
    </tr>
    {% endfor %}
  </tbody>
</table>
```

- [ ] **Step 2: 详情抽屉使用安全 JSON 数据**

`admin.js` 读取 `dataset.activity` 并通过 `textContent` 渲染提示词、参数和计费关联；不得使用 `innerHTML` 注入用户提示词。

- [ ] **Step 3: 表格横向滚动且页面不溢出**

```css
.admin-table-wrap { max-width: 100%; overflow-x: auto; }
.admin-activity-table { min-width: 70rem; }
.admin-record-prompt { max-width: 28rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
```

- [ ] **Step 4: 更新模板测试**

```python
assert body.count("生成记录") == 0
assert body.count("积分流水") == 0
assert "业务流水" in body
assert "data-activity-row" in body
```

### Task 6: 将用户流水改为统一视图的用户筛选版

**Files:**
- Modify: `huishi/routes_admin.py`
- Modify: `templates/admin/user_ledger.html`
- Test: `tests/test_admin_console_experience.py`

- [ ] **Step 1: 保留余额调整表单**

用户页继续支持充值/扣费；下方不再分别显示积分和生成两个表。

- [ ] **Step 2: 复用业务流水局部模板**

Create: `templates/admin/_activity_table.html`，`records.html` 与 `user_ledger.html` 传入相同 `events`、`pagination` 和抽屉数据。

- [ ] **Step 3: 用户路由固定 `user_id` 过滤**

忽略查询字符串中试图覆盖的其他用户 ID，避免越权或串数据。

- [ ] **Step 4: 运行权限和用户流水测试**

Run: `ssh huishi-vm "cd /opt/huishi && .venv/bin/python -m pytest tests/test_admin_console_experience.py tests/test_admin_audit.py -q"`  
Expected: PASS。

### Task 7: 优化其他后台页面真实边界

**Files:**
- Modify: `templates/admin/dashboard.html`
- Modify: `templates/admin/users.html`
- Modify: `templates/admin/invites.html`
- Modify: `templates/admin/config_billing.html`
- Modify: `templates/admin/config_packages.html`
- Modify: `templates/admin/config_center.html`
- Modify: `templates/admin/config_settings.html`
- Modify: `templates/admin/audit.html`
- Modify: `static/css/site.css`

- [ ] **Step 1: 用户表处理长值**

用户、最近使用时间和注册时间使用截断容器与 `title`；操作列保持可达，横向滚动限制在表格容器。

- [ ] **Step 2: 导入控件使用明确按钮**

视觉隐藏原生 file input，通过关联 `<label for>` 触发，显示已选文件名；保留原始表单提交。

- [ ] **Step 3: 健康状态使用统一 badge**

`ok`、`warning`、`failed`、`unknown` 同时使用图标/文字/颜色，不能只靠小圆点。

- [ ] **Step 4: 配置卡和表单使用统一控件高度**

字段、开关、按钮和状态 badge 遵循全站令牌；不把每个配置区做成嵌套卡片。

### Task 8: 后台回归与浏览器验证

**Files:**
- No source changes unless defects are found.

- [ ] **Step 1: 运行后台测试**

Run: `ssh huishi-vm "cd /opt/huishi && .venv/bin/python -m pytest tests/test_admin_activity.py tests/test_admin_console_experience.py tests/test_admin_pagination.py tests/test_admin_audit.py tests/test_admin_delete_user_cascade.py -q"`  
Expected: PASS。

- [ ] **Step 2: 浏览器验证 10 个后台页面**

运行总览、用户、用户业务流水、全站业务流水、邀请码、计费、套餐、配置中心、系统配置、审计日志。

- [ ] **Step 3: 检查同色主题和数据边界**

瓷白主题无固定黑色侧栏；曜黑主题全部区域一致。使用长用户名、长时间戳、长提示词和失败/退款事件。

- [ ] **Step 4: 检查 390px 与桌面**

移动端侧栏可折叠；表格内部可横向滚动；页面 body 不产生水平滚动条。

- [ ] **Step 5: 报告修改但不提交**

Run: `ssh huishi-vm "cd /opt/huishi && git status --short 2>/dev/null || true"`  
Expected: 报告工作树状态；不执行 commit。
