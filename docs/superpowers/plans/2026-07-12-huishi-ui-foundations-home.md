# 绘世主题基础与首页优化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立 Flask 主站语义主题系统，并将首页与认证模态框更新为确认后的视觉语言。

**Architecture:** 在 `site.css` 定义全站令牌，在 `theme.js` 管理 `system/light/dark` 偏好；首页保留独立 Tailwind 构建和现有视频/rAF 逻辑，只替换字体、玻璃、层级与响应式样式。

**Tech Stack:** Jinja2、React 18、Tailwind 3、原生 CSS/JS、pytest。

---

### Task 1: 建立 Flask 主题契约测试

**Files:**
- Create: `tests/test_ui_theme_contract.py`
- Read: `templates/base.html`, `static/js/theme.js`, `static/css/site.css`

- [ ] **Step 1: 写失败测试**

```python
from pathlib import Path


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_base_exposes_theme_before_styles_render():
    base = read("templates/base.html")
    assert "data-theme" in base
    assert "color-scheme" in base


def test_theme_script_supports_system_light_and_dark():
    source = read("static/js/theme.js")
    for value in ('"system"', '"light"', '"dark"'):
        assert value in source
    assert "matchMedia" in source


def test_site_css_defines_semantic_theme_tokens():
    css = read("static/css/site.css")
    for token in ("--color-bg", "--color-surface", "--color-text", "--color-primary"):
        assert token in css
```

- [ ] **Step 2: 运行并确认失败**

Run: `ssh huishi-vm "cd /opt/huishi && .venv/bin/python -m pytest tests/test_ui_theme_contract.py -q"`  
Expected: FAIL，缺少 `system` 和语义令牌。

### Task 2: 实现三态主题脚本

**Files:**
- Modify: `static/js/theme.js`
- Modify: `templates/base.html`

- [ ] **Step 1: 在文档根节点提前设置主题**

```html
<script>
  (() => {
    const preference = localStorage.getItem("huishi.theme") || "system";
    const resolved = preference === "system"
      ? (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light")
      : preference;
    document.documentElement.dataset.theme = resolved;
    document.documentElement.dataset.themePreference = preference;
  })();
</script>
```

- [ ] **Step 2: 替换固定 console 暗色逻辑**

```js
const THEME_KEY = "huishi.theme";
const VALUES = new Set(["system", "light", "dark"]);

function resolveTheme(preference) {
  if (preference === "system") {
    return matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  return preference === "dark" ? "dark" : "light";
}

function applyTheme(preference) {
  const next = VALUES.has(preference) ? preference : "system";
  document.documentElement.dataset.themePreference = next;
  document.documentElement.dataset.theme = resolveTheme(next);
  document.documentElement.style.colorScheme = resolveTheme(next);
}
```

- [ ] **Step 3: 让 `[data-theme-option]` 选择主题并监听系统变化**

```js
document.querySelectorAll("[data-theme-option]").forEach((button) => {
  button.addEventListener("click", () => {
    const value = button.dataset.themeOption;
    if (!VALUES.has(value)) return;
    localStorage.setItem(THEME_KEY, value);
    applyTheme(value);
  });
});

matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
  if ((localStorage.getItem(THEME_KEY) || "system") === "system") applyTheme("system");
});
```

- [ ] **Step 4: 运行主题契约测试**

Run: `ssh huishi-vm "cd /opt/huishi && .venv/bin/python -m pytest tests/test_ui_theme_contract.py -q"`  
Expected: PASS。

### Task 3: 定义全站语义令牌

**Files:**
- Modify: `static/css/site.css`

- [ ] **Step 1: 添加字体与主题原始令牌**

```css
:root {
  --font-ui: "Noto Sans SC", "Microsoft YaHei UI", "PingFang SC", sans-serif;
  --radius-control: 6px;
  --radius-panel: 8px;
  --radius-dialog: 10px;
  --color-primary: oklch(57% 0.24 265);
  --color-primary-soft: oklch(95% 0.035 265);
}

:root[data-theme="light"] {
  --color-bg: oklch(98% 0.004 250);
  --color-surface: oklch(100% 0 0);
  --color-surface-subtle: oklch(95.5% 0.006 250);
  --color-border: oklch(91.5% 0.008 250);
  --color-text: oklch(22% 0.008 250);
  --color-text-muted: oklch(53% 0.015 250);
}

:root[data-theme="dark"] {
  --color-bg: oklch(15% 0.006 250);
  --color-surface: oklch(20% 0.008 250);
  --color-surface-subtle: oklch(25% 0.01 250);
  --color-border: oklch(30% 0.012 250);
  --color-text: oklch(96% 0.003 250);
  --color-text-muted: oklch(72% 0.012 250);
  --color-primary: oklch(70% 0.15 265);
  --color-primary-soft: oklch(27% 0.07 265);
}
```

- [ ] **Step 2: 将 body、表单和焦点样式改为语义令牌**

```css
body { background: var(--color-bg); color: var(--color-text); font-family: var(--font-ui); }
:where(a, button, input, textarea, select):focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}
```

- [ ] **Step 3: 检查旧固定主题选择器**

Run: `ssh huishi-vm "cd /opt/huishi && grep -nE 'workspaceTheme|fixedConsoleTheme|#f4efe4|#13161a' static/css/site.css static/js/theme.js"`  
Expected: 主题逻辑中无旧固定值；遗留业务色需逐项迁移而非批量删除。

### Task 4: 更新首页字体和模板资源

**Files:**
- Modify: `templates/home.html`
- Modify: `tailwind.home.config.js`
- Test: `tests/test_home_assets.py`

- [ ] **Step 1: 更新失败测试**

```python
def test_home_uses_single_modern_sans_font_family():
    home = Path("templates/home.html").read_text(encoding="utf-8")
    config = Path("tailwind.home.config.js").read_text(encoding="utf-8")
    assert "Noto+Sans+SC" in home
    assert "Instrument+Serif" not in home
    assert 'heading: ["Noto Sans SC"' in config
```

- [ ] **Step 2: 运行并确认失败**

Run: `ssh huishi-vm "cd /opt/huishi && .venv/bin/python -m pytest tests/test_home_assets.py::test_home_uses_single_modern_sans_font_family -q"`  
Expected: FAIL。

- [ ] **Step 3: 更新 Google Fonts 和 Tailwind 字体**

```js
fontFamily: {
  heading: ["Noto Sans SC", "Microsoft YaHei UI", "sans-serif"],
  body: ["Noto Sans SC", "Microsoft YaHei UI", "sans-serif"],
}
```

模板只请求 `Noto Sans SC:wght@300;400;500;600;700`。

### Task 5: 重构首页视觉而不改变视频契约

**Files:**
- Modify: `static/css/home-tailwind.input.css`
- Modify: `static/js/home.js`
- Test: `tests/test_home_assets.py`, `tests/test_seo_metadata.py`

- [ ] **Step 1: 添加结构保护测试**

```python
def test_home_keeps_existing_video_and_two_sections():
    source = Path("static/js/home.js").read_text(encoding="utf-8")
    assert 'const HERO_VIDEO = "/static/media/shouyeshipin-home.mp4"' in source
    assert 'id="hero"' in source
    assert 'id="capabilities"' in source
    assert "hero-luminous-overlay" not in source
```

- [ ] **Step 2: 运行测试确认当前保护项差异**

Run: `ssh huishi-vm "cd /opt/huishi && .venv/bin/python -m pytest tests/test_home_assets.py -q"`  
Expected: 至少新断言 FAIL。

- [ ] **Step 3: 将首页标题改为无衬线并使用局部玻璃承托**

```css
.hero-copy {
  max-width: 46rem;
  padding: 1.25rem;
  border-radius: var(--radius-panel);
  background: rgba(7, 17, 26, 0.14);
  backdrop-filter: blur(8px);
}
.hero-title { font-family: var(--font-ui); font-style: normal; letter-spacing: -0.03em; }
```

不得添加覆盖全屏的暗色层；保持 `FadingVideo` 的 rAF 逻辑。

- [ ] **Step 4: 更新首页文案**

```jsx
<BlurText text="绘梦造世" className="hero-title" as="h1" />
<p className="hero-subtitle">从一句灵感，到一整个可继续生长的视觉世界。</p>
```

- [ ] **Step 5: 保留登录/注册业务逻辑，只替换视觉类名**

认证 modal 的字段、CSRF、`NEXT_URL`、密码显隐和错误处理不得改动。

### Task 6: 补齐首页与认证状态

**Files:**
- Modify: `static/js/home.js`
- Modify: `static/css/home-tailwind.input.css`
- Test: `tests/test_home_password_toggle.py`, `tests/test_auth_csrf.py`

- [ ] **Step 1: 为提交状态增加稳定属性**

```jsx
<form aria-busy={submitting ? "true" : "false"} data-auth-state={error ? "error" : submitting ? "loading" : "idle"}>
```

- [ ] **Step 2: 定义 loading、error、disabled 和 focus-visible 样式**

```css
.auth-submit[disabled] { opacity: .55; cursor: wait; }
.auth-error { color: var(--color-danger); }
@media (prefers-reduced-motion: reduce) { .home-page * { animation-duration: .01ms !important; } }
```

- [ ] **Step 3: 运行认证回归测试**

Run: `ssh huishi-vm "cd /opt/huishi && .venv/bin/python -m pytest tests/test_home_password_toggle.py tests/test_auth_csrf.py -q"`  
Expected: PASS。

### Task 7: 构建和浏览器验证首页

**Files:**
- Generated: `static/js/home.compiled.js`, `static/css/home-tailwind.css`

- [ ] **Step 1: 构建首页资源**

Run: `ssh huishi-vm "cd /opt/huishi && npm run verify:home"`  
Expected: encoding、build 和 asset budget 全部 PASS。

- [ ] **Step 2: 桌面浏览器检查**

检查 `1440x900` 与 `1280x720`：视频可见、文字可读、无全屏遮罩、下一屏有提示。

- [ ] **Step 3: 移动浏览器检查**

检查 `390x844` 与 `320x568`：导航折叠、标题不溢出、CTA 可点击、登录 modal 不超屏。

- [ ] **Step 4: 记录未提交状态**

Run: `ssh huishi-vm "cd /opt/huishi && git status --short 2>/dev/null || true"`  
Expected: 报告修改文件；不执行 commit。

