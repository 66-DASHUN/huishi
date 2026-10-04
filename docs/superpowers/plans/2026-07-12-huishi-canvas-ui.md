# 绘世画布子应用 UI 优化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Next.js 画布子应用同步到全站主题与组件语言，同时完整保留节点画布和三栏创作结构。

**Architecture:** 通过 `use-theme-store`、`app-theme.ts`、`canvas-theme.ts` 和 `globals.css` 映射语义令牌。主站嵌入模式复用现有 host bridge 同步主题；独立模式保留本地主题。页面私有样式继续放在组件/Tailwind 中。

**Tech Stack:** Next.js 16、React 19、TypeScript、Ant Design 6、Tailwind 4、Zustand、Motion。

**Verification Constraint:** 根据 `infinite-canvas/AGENTS.md`，Codex 不执行 `bun test`、`bun run typecheck` 或 `bun run build`；计划列出命令供用户执行。

---

### Task 1: 扩展画布主题类型

**Files:**
- Modify: `infinite-canvas/web/src/stores/use-theme-store.ts`
- Modify: `infinite-canvas/web/src/lib/app-theme.ts`
- Modify: `infinite-canvas/web/src/lib/canvas-theme.ts`
- Create: `infinite-canvas/web/src/stores/use-theme-store.test.ts`

- [ ] **Step 1: 写主题解析测试**

```ts
import { describe, expect, test } from "bun:test";
import { resolveTheme } from "./use-theme-store";

describe("resolveTheme", () => {
  test("keeps explicit themes", () => {
    expect(resolveTheme("light", true)).toBe("light");
    expect(resolveTheme("dark", false)).toBe("dark");
  });
  test("resolves system from media state", () => {
    expect(resolveTheme("system", true)).toBe("dark");
    expect(resolveTheme("system", false)).toBe("light");
  });
});
```

- [ ] **Step 2: 将 store 拆分为偏好和有效主题**

```ts
export type ThemePreference = "system" | "light" | "dark";
export type ResolvedTheme = "light" | "dark";

export function resolveTheme(preference: ThemePreference, systemDark: boolean): ResolvedTheme {
  return preference === "system" ? (systemDark ? "dark" : "light") : preference;
}

type ThemeStore = {
  preference: ThemePreference;
  resolvedTheme: ResolvedTheme;
  setPreference: (preference: ThemePreference) => void;
  applyHostTheme: (preference: ThemePreference, resolvedTheme: ResolvedTheme) => void;
};
```

- [ ] **Step 3: 用确认后的中性/钴蓝令牌更新 Ant Design**

```ts
token: {
  colorPrimary: dark ? "oklch(70% 0.15 265)" : "oklch(57% 0.24 265)",
  borderRadius: 6,
  borderRadiusLG: 8,
  boxShadow: dark ? "none" : "0 4px 12px rgb(16 24 40 / 6%)",
}
```

- [ ] **Step 4: 更新 `canvasThemes`**

将旧暖灰 `#f4f2ed`、`#181715` 映射为规范中的中性瓷白/曜黑表面，保留所有键名以避免组件调用方变化。

### Task 2: 实现安全的 host 主题桥接

**Files:**
- Modify: `templates/canvas.html`
- Modify: `static/js/theme.js`
- Modify: `infinite-canvas/web/src/app/(user)/canvas/lib/host-canvas-session.ts`
- Modify: `infinite-canvas/web/src/app/(user)/canvas/components/canvas-host-session-guard.tsx`
- Test: `tests/test_canvas_embed_mode_contract.py`
- Create: `infinite-canvas/web/src/app/(user)/canvas/lib/host-theme-message.test.ts`

- [ ] **Step 1: Flask 端消息函数**

```js
function postThemeToCanvas(frame) {
  const url = new URL(frame.src, window.location.href);
  frame.contentWindow?.postMessage({
    type: "huishi-theme-change",
    preference: document.documentElement.dataset.themePreference,
    resolvedTheme: document.documentElement.dataset.theme,
  }, url.origin);
}
```

- [ ] **Step 2: 在 iframe load/ready 和主题变化时发送**

复用现有 `huishi-canvas-ready`/ping 监听，不新增并行握手机制。

- [ ] **Step 3: 画布端定义解析函数**

```ts
export function parseHostThemeMessage(data: unknown) {
  if (!data || typeof data !== "object") return null;
  const value = data as Record<string, unknown>;
  if (value.type !== "huishi-theme-change") return null;
  if (!["system", "light", "dark"].includes(String(value.preference))) return null;
  if (!["light", "dark"].includes(String(value.resolvedTheme))) return null;
  return value as { type: "huishi-theme-change"; preference: ThemePreference; resolvedTheme: ResolvedTheme };
}
```

- [ ] **Step 4: 只接受父窗口和允许 origin**

```ts
if (event.source !== window.parent) return;
if (event.origin !== hostOrigin) return;
const message = parseHostThemeMessage(event.data);
if (message) applyHostTheme(message.preference, message.resolvedTheme);
```

- [ ] **Step 5: 运行 Flask bridge 测试**

Run: `ssh huishi-vm "cd /opt/huishi && .venv/bin/python -m pytest tests/test_canvas_embed_mode_contract.py -q"`  
Expected: PASS。

### Task 3: 更新全局基础样式和顶部导航

**Files:**
- Modify: `infinite-canvas/web/src/app/globals.css`
- Modify: `infinite-canvas/web/src/components/layout/app-providers.tsx`
- Modify: `infinite-canvas/web/src/components/layout/app-top-nav.tsx`
- Modify: `infinite-canvas/web/src/components/layout/user-status-actions.tsx`

- [ ] **Step 1: 用语义变量替换暖灰和纯黑默认值**

```css
:root {
  --background: oklch(98% 0.004 250);
  --foreground: oklch(22% 0.008 250);
  --card: oklch(100% 0 0);
  --border: oklch(91.5% 0.008 250);
  --primary: oklch(57% 0.24 265);
}
.dark {
  --background: oklch(15% 0.006 250);
  --foreground: oklch(96% 0.003 250);
  --card: oklch(20% 0.008 250);
  --border: oklch(30% 0.012 250);
  --primary: oklch(70% 0.15 265);
}
```

- [ ] **Step 2: 顶部导航保持现有链接和嵌入隐藏逻辑**

只修改颜色、字体、选中态、主题选择菜单；`navigationTools` 路由不变。

- [ ] **Step 3: 三态主题菜单**

```tsx
<Segmented
  options={[{ label: "跟随系统", value: "system" }, { label: "瓷白", value: "light" }, { label: "曜黑", value: "dark" }]}
  value={preference}
  onChange={(value) => setPreference(value as ThemePreference)}
/>
```

### Task 4: 保持无限画布结构并换肤

**Files:**
- Modify: `infinite-canvas/web/src/app/(user)/canvas/components/canvas-toolbar.tsx`
- Modify: `infinite-canvas/web/src/app/(user)/canvas/components/canvas-node.tsx`
- Modify: `infinite-canvas/web/src/app/(user)/canvas/components/canvas-node-hover-toolbar.tsx`
- Modify: `infinite-canvas/web/src/app/(user)/canvas/components/canvas-zoom-controls.tsx`
- Modify: `infinite-canvas/web/src/app/(user)/canvas/components/canvas-mini-map.tsx`
- Modify: `infinite-canvas/web/src/app/(user)/canvas/components/canvas-assistant-panel.tsx`

- [ ] **Step 1: 保留组件树和现有 store**

不得移动 `InfiniteCanvas`、`CanvasToolbar`、`CanvasZoomControls`、`Minimap` 或 `CanvasAssistantPanel` 的挂载位置。

- [ ] **Step 2: 使用 `canvasThemes` 语义键**

```tsx
const dockStyle = {
  background: theme.toolbar.panel,
  borderColor: theme.toolbar.border,
  color: theme.toolbar.item,
  boxShadow: colorTheme === "dark" ? "none" : "0 4px 12px rgb(16 24 40 / 6%)",
};
```

- [ ] **Step 3: 保持已有移动端工具栏**

不得用桌面工具栏硬缩放替代 `CanvasMobileToolbar`。

- [ ] **Step 4: 检查画布状态文件**

源码级确认 `canvas-status-screen.tsx` 覆盖 loading、offline、missing 和 retry 文案。

### Task 5: 优化生图和视频三栏工作台

**Files:**
- Modify: `infinite-canvas/web/src/app/(user)/image/page.tsx`
- Modify: `infinite-canvas/web/src/app/(user)/video/page.tsx`
- Modify: `infinite-canvas/web/src/components/image-settings-panel.tsx`
- Modify: `infinite-canvas/web/src/components/video-settings-panel.tsx`
- Modify: `infinite-canvas/web/src/app/globals.css`

- [ ] **Step 1: 保留三栏 DOM**

记录栏、参数栏和结果栏不得合并，也不得仅为增加属性而抽取新组件。直接在
`src/app/(user)/image/page.tsx` 和 `src/app/(user)/video/page.tsx` 的现有 DOM 上增加稳定属性：

精确变更如下：

- 给包含现有 `LogPanel` 的 `<aside>` 增加 `data-workbench-column="history"`。
- 给现有两栏 `<section>` 的第一个子 `<div>`（`GenerationSettings` 所在栏）增加
  `data-workbench-column="settings"`。
- 给同一 `<section>` 的第二个子 `<div>`（结果卡片所在栏）增加
  `data-workbench-column="results"`。

保留这些节点的全部现有 `className` 和子组件；只增加三个属性，不替换
`LogPanel`、`GenerationSettings` 或结果卡片组件。

- [ ] **Step 2: 统一栏位表面和滚动**

```css
[data-workbench-column] { min-width: 0; background: var(--card); border: 1px solid var(--border); border-radius: 8px; }
[data-workbench-column="settings"] { overflow-y: auto; }
```

- [ ] **Step 3: 移动端使用分段切换**

小于 `768px` 使用 `Segmented` 在记录、参数、结果间切换，三个面板仍保持挂载以保留状态。

- [ ] **Step 4: 统一空、加载、失败和结果状态**

复用 Ant Design `Empty`、`Skeleton`、`Alert`；不在结果面板中央只放 spinner。

### Task 6: 优化素材、项目列表和画布设置

**Files:**
- Modify: `infinite-canvas/web/src/app/(user)/assets/page.tsx`
- Modify: `infinite-canvas/web/src/app/(user)/canvas/page.tsx`
- Modify: `infinite-canvas/web/src/app/(user)/settings/page.tsx`
- Modify: `infinite-canvas/web/src/app/(user)/canvas/components/canvas-project-card.tsx`

- [ ] **Step 1: 素材卡覆盖媒体类型和损坏资源**

图片、视频、音频使用同一卡片骨架；加载失败显示文件类型、名称和移除/重试操作。

- [ ] **Step 2: 项目列表保留本地存储说明**

空状态必须明确“项目保存在此浏览器”，不承诺云同步。

- [ ] **Step 3: 设置页只呈现现有能力**

保留 API、模型、主题、存储和连接配置；不新增主站账户或通知功能。

### Task 7: 源码和浏览器验证

**Files:**
- No source changes unless defects are found.

- [ ] **Step 1: 源码检查结构**

Run: `ssh huishi-vm "cd /opt/huishi/infinite-canvas/web && grep -R -n 'data-workbench-column' 'src/app/(user)/image' 'src/app/(user)/video'"`  
Expected: image/video 各包含 history、settings、results。

- [ ] **Step 2: 浏览器检查独立页面**

页面：`/canvas`、`/image`、`/video`、`/assets`、`/settings`。检查瓷白/曜黑、三栏、节点画布和移动分段。

- [ ] **Step 3: 浏览器检查主站 iframe**

检查 `/canvas` 与 `/prompts` 嵌入：主题一致、ready 后无闪烁、来源校验不阻断合法消息。

- [ ] **Step 4: 向用户报告未执行验证**

用户运行：

```bash
cd /opt/huishi/infinite-canvas/web
bun test
bun run typecheck
bun run build
```

Codex 不在未授权情况下执行这些命令。
