# Huishi Canvas Experience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every canvas tool reachable at 390px while preserving the existing desktop workflow and adding complete loading, empty, failure, and narrow-screen Agent behavior.

**Architecture:** Keep the current canvas store and editor. Extract tool metadata and appearance controls, render a five-action mobile dock plus a More sheet below `md`, and retain the existing desktop dock above `md`. Use CSS breakpoints for presentation and a small viewport hook only for behavior that changes Agent panel mode.

**Tech Stack:** Next.js 16, React 19, TypeScript, Ant Design 6, Tailwind 4, Zustand, Lucide, Bun test runner.

---

### Task 1: Establish a Bun Test Entry Point and Tool Model

**Files:**
- Modify: `infinite-canvas/web/package.json`
- Create: `infinite-canvas/web/src/app/(user)/canvas/components/canvas-toolbar-tools.ts`
- Create: `infinite-canvas/web/src/app/(user)/canvas/components/canvas-toolbar-tools.test.ts`

- [ ] **Step 1: Add a failing tool-partition test**

```typescript
import { describe, expect, test } from "bun:test";
import { MOBILE_PRIMARY_TOOL_IDS, MOBILE_MORE_TOOL_IDS } from "./canvas-toolbar-tools";

describe("mobile canvas tools", () => {
    test("keeps five primary actions and exposes every secondary action", () => {
        expect(MOBILE_PRIMARY_TOOL_IDS).toEqual(["hand", "text", "image", "upload", "more"]);
        expect(MOBILE_MORE_TOOL_IDS).toEqual(["undo", "redo", "video", "audio", "config", "assets", "appearance", "shortcuts", "clear"]);
        expect(new Set([...MOBILE_PRIMARY_TOOL_IDS, ...MOBILE_MORE_TOOL_IDS]).size).toBe(14);
    });
});
```

- [ ] **Step 2: Add `"test": "bun test"` and verify the test fails**

Run: `cd infinite-canvas/web && bun test src/app/'(user)'/canvas/components/canvas-toolbar-tools.test.ts`

Expected: fail because `canvas-toolbar-tools.ts` is missing.

- [ ] **Step 3: Implement typed tool metadata**

```typescript
export type CanvasToolId = "hand" | "undo" | "redo" | "text" | "image" | "video" | "audio" | "config" | "upload" | "assets" | "appearance" | "shortcuts" | "clear" | "more";

export const MOBILE_PRIMARY_TOOL_IDS = ["hand", "text", "image", "upload", "more"] as const satisfies readonly CanvasToolId[];
export const MOBILE_MORE_TOOL_IDS = ["undo", "redo", "video", "audio", "config", "assets", "appearance", "shortcuts", "clear"] as const satisfies readonly CanvasToolId[];
export const DESKTOP_TOOL_IDS = ["hand", "undo", "redo", "text", "image", "video", "audio", "config", "upload", "assets", "appearance", "clear"] as const satisfies readonly CanvasToolId[];
```

- [ ] **Step 4: Verify the model test passes**

Run: `cd infinite-canvas/web && bun test src/app/'(user)'/canvas/components/canvas-toolbar-tools.test.ts`

Expected: 1 test passes.

### Task 2: Extract the Shared Appearance Panel

**Files:**
- Create: `infinite-canvas/web/src/app/(user)/canvas/components/canvas-appearance-panel.tsx`
- Modify: `infinite-canvas/web/src/app/(user)/canvas/components/canvas-toolbar.tsx`
- Modify: `infinite-canvas/web/src/app/(user)/canvas/components/canvas-toolbar-tools.test.ts`

- [ ] **Step 1: Add a failing source-contract test**

```typescript
test("desktop toolbar delegates appearance controls", async () => {
    const source = await Bun.file(new URL("./canvas-toolbar.tsx", import.meta.url)).text();
    expect(source).toContain("<CanvasAppearancePanel");
    expect(source).not.toContain("<Segmented");
});
```

- [ ] **Step 2: Verify the contract fails**

Run: `cd infinite-canvas/web && bun test src/app/'(user)'/canvas/components/canvas-toolbar-tools.test.ts`

Expected: fail because appearance markup is still inline.

- [ ] **Step 3: Move appearance controls into a focused component**

```typescript
export function CanvasAppearancePanel({ backgroundMode, showImageInfo, onBackgroundModeChange, onShowImageInfoChange, onClose }: Props) {
    return (
        <section aria-label="画布外观" className="grid gap-3">
            <Segmented block value={backgroundMode} onChange={(value) => onBackgroundModeChange(value as CanvasBackgroundMode)} options={BACKGROUND_OPTIONS} />
            <div className="flex items-center justify-between gap-3">
                <span>图片信息</span>
                <Switch size="small" checked={showImageInfo} onChange={onShowImageInfoChange} />
            </div>
            {onClose ? <Button type="text" onClick={onClose}>完成</Button> : null}
        </section>
    );
}
```

Reuse `canvasThemes`; do not hard-code a separate mobile palette.

- [ ] **Step 4: Verify contract and typecheck**

Run: `cd infinite-canvas/web && bun test src/app/'(user)'/canvas/components/canvas-toolbar-tools.test.ts && bun run typecheck`

Expected: test and typecheck pass.

### Task 3: Add the Mobile Toolbar and More Sheet

**Files:**
- Create: `infinite-canvas/web/src/app/(user)/canvas/components/canvas-mobile-toolbar.tsx`
- Modify: `infinite-canvas/web/src/app/(user)/canvas/components/canvas-toolbar.tsx`
- Modify: `infinite-canvas/web/src/app/(user)/canvas/[id]/canvas-client-page.tsx`
- Modify: `infinite-canvas/web/src/app/(user)/canvas/components/canvas-toolbar-tools.test.ts`

- [ ] **Step 1: Add failing source and tool-accessibility tests**

```typescript
test("mobile toolbar has one fixed five-action dock and a labeled more sheet", async () => {
    const source = await Bun.file(new URL("./canvas-mobile-toolbar.tsx", import.meta.url)).text();
    expect(source).toContain('aria-label="画布常用工具"');
    expect(source).toContain('aria-label="更多工具"');
    expect(source).toContain('aria-expanded={moreOpen}');
    expect(source).toContain("grid-cols-5");
});
```

- [ ] **Step 2: Verify the test fails because the component is missing**

Run: `cd infinite-canvas/web && bun test src/app/'(user)'/canvas/components/canvas-toolbar-tools.test.ts`

Expected: file-not-found failure.

- [ ] **Step 3: Implement the five-action dock**

```typescript
<nav aria-label="画布常用工具" className="pointer-events-auto grid h-16 w-full grid-cols-5 border-t md:hidden" style={dockStyle}>
    <MobileToolButton label="选择" icon={<Hand />} onClick={onDeselect} />
    <MobileToolButton label="文字" icon={<Type />} onClick={onAddText} />
    <MobileToolButton label="图片" icon={<ImageIcon />} onClick={onAddImage} />
    <MobileToolButton label="上传" icon={<Upload />} onClick={onUpload} />
    <MobileToolButton label="更多" icon={<Ellipsis />} expanded={moreOpen} onClick={() => setMoreOpen((value) => !value)} />
</nav>
```

Render the desktop toolbar with `hidden md:flex`. The mobile dock spans `inset-x-0 bottom-0`; it must not inherit the desktop `left: 300px` offset.

- [ ] **Step 4: Implement the More sheet**

Use an Ant Design `Drawer` with `placement="bottom"`, `height="auto"`, `aria-label="更多工具"`, a two-column action grid, and actions for undo, redo, video, audio, config, assets, appearance, shortcuts, and clear. Undo/redo retain their disabled states. Close the sheet after invoking a normal action; keep it open while the appearance controls are active. Restore focus to the More button on close.

- [ ] **Step 5: Pass the existing callbacks without changing stores**

Add `onOpenShortcuts` to `CanvasToolbar` props and route all callbacks from `canvas-client-page.tsx`. Do not duplicate canvas state inside the toolbar.

- [ ] **Step 6: Verify tests and typecheck**

Run: `cd infinite-canvas/web && bun test && bun run typecheck`

Expected: all Bun tests and TypeScript pass.

### Task 4: Constrain Node Panels to the Viewport

**Files:**
- Modify: `infinite-canvas/web/src/app/(user)/canvas/components/canvas-node.tsx`
- Create: `infinite-canvas/web/src/app/(user)/canvas/utils/canvas-panel-layout.ts`
- Create: `infinite-canvas/web/src/app/(user)/canvas/utils/canvas-panel-layout.test.ts`

- [ ] **Step 1: Write failing panel width tests**

```typescript
import { expect, test } from "bun:test";
import { panelWidth } from "./canvas-panel-layout";

test("panel width preserves mobile gutters", () => {
    expect(panelWidth(390)).toBe(366);
    expect(panelWidth(768)).toBe(500);
});
```

- [ ] **Step 2: Verify the helper is missing**

Run: `cd infinite-canvas/web && bun test src/app/'(user)'/canvas/utils/canvas-panel-layout.test.ts`

Expected: import failure.

- [ ] **Step 3: Implement the pure constraint and apply matching CSS**

```typescript
export const panelWidth = (viewportWidth: number) => Math.min(500, Math.max(280, viewportWidth - 24));
```

Replace `w-[500px]` with `w-[min(500px,calc(100vw-24px))] max-w-[calc(100vw-24px)]`. Clamp translated left position so the panel remains inside 12px viewport gutters.

- [ ] **Step 4: Verify helper, typecheck, and source contract**

Run: `cd infinite-canvas/web && bun test && bun run typecheck`

Expected: all checks pass and no canvas panel retains an unconditional `w-[500px]`.

### Task 5: Make the Agent a Full-Width Mobile Drawer

**Files:**
- Create: `infinite-canvas/web/src/app/(user)/canvas/hooks/use-canvas-viewport.ts`
- Modify: `infinite-canvas/web/src/app/(user)/canvas/components/canvas-assistant-panel.tsx`
- Modify: `infinite-canvas/web/src/app/(user)/canvas/[id]/canvas-client-page.tsx`
- Create: `infinite-canvas/web/src/app/(user)/canvas/hooks/use-canvas-viewport.test.ts`

- [ ] **Step 1: Write a failing breakpoint test for the pure snapshot function**

```typescript
test("canvas viewport switches to compact below md", () => {
    expect(canvasViewportSnapshot(390)).toEqual({ compact: true, agentWidth: 390 });
    expect(canvasViewportSnapshot(1280)).toEqual({ compact: false, agentWidth: 520 });
});
```

- [ ] **Step 2: Verify the helper is missing**

Run: `cd infinite-canvas/web && bun test src/app/'(user)'/canvas/hooks/use-canvas-viewport.test.ts`

Expected: import failure.

- [ ] **Step 3: Implement a single `matchMedia('(max-width: 767px)')` hook**

The hook subscribes to `change`, returns `{compact, viewportWidth}`, and removes its listener on cleanup. Its pure `canvasViewportSnapshot` function is testable without DOM.

- [ ] **Step 4: Render mobile Agent as an overlay**

At compact widths, use `position: absolute; inset: 0; width: 100%` and hide the resize handle. At desktop widths, retain the current resizable side panel. Closing the mobile Agent returns focus to the Agent button and restores the full canvas.

- [ ] **Step 5: Verify tests and typecheck**

Run: `cd infinite-canvas/web && bun test && bun run typecheck`

Expected: all checks pass.

### Task 6: Complete Canvas Status States

**Files:**
- Create: `infinite-canvas/web/src/app/(user)/canvas/components/canvas-status-screen.tsx`
- Modify: `infinite-canvas/web/src/app/(user)/canvas/components/canvas-host-session-guard.tsx`
- Modify: `infinite-canvas/web/src/app/(user)/canvas/[id]/canvas-client-page.tsx`
- Create: `infinite-canvas/web/src/app/(user)/canvas/components/canvas-status-screen.test.ts`

- [ ] **Step 1: Add a failing state-model test**

```typescript
test("every canvas status has a user action", () => {
    for (const status of ["session", "project", "offline", "error"] as const) {
        expect(CANVAS_STATUS_COPY[status].title).toBeTruthy();
        expect(CANVAS_STATUS_COPY[status].action).toBeTruthy();
    }
});
```

- [ ] **Step 2: Verify the status module is missing**

Run: `cd infinite-canvas/web && bun test src/app/'(user)'/canvas/components/canvas-status-screen.test.ts`

Expected: import failure.

- [ ] **Step 3: Implement restrained status surfaces**

Use centered text and one action, not decorative cards. Session validation shows a spinner and “正在连接画布”; project load offers retry; offline offers retry without discarding local canvas; fatal errors offer return to canvas list.

- [ ] **Step 4: Replace raw `会话校验中...` and refresh shells**

Ensure status components have `role="status"` for loading and `role="alert"` for failures. Preserve existing session verification behavior.

- [ ] **Step 5: Verify tests and typecheck**

Run: `cd infinite-canvas/web && bun test && bun run typecheck`

Expected: all checks pass.

### Task 7: Build, Deploy, and Visually Verify Canvas UX

**Files:**
- Modify: `infinite-canvas/docs/content/docs/progress/pending-test.mdx`
- Modify: `infinite-canvas/CHANGELOG.md`

- [ ] **Step 1: Run the complete frontend gate**

Run: `cd infinite-canvas/web && bun test && bun run typecheck && bun run format:check && bun run build`

Expected: all commands exit 0 with no TypeScript build suppression hiding errors. If `ignoreBuildErrors` remains enabled, the explicit typecheck is mandatory evidence.

- [ ] **Step 2: Build outside the active release and switch only after success**

Create a code snapshot first, build in the staged release directory, then update the active service directory and restart `huishi-canvas.service` after approval.

- [ ] **Step 3: Verify desktop behavior**

At 1280x720 and 1440x900 verify every existing desktop tool, hover label, undo/redo state, appearance panel, upload, assets, clear confirmation, Agent resizing, node panels, and no toolbar/Agent overlap.

- [ ] **Step 4: Verify mobile behavior**

At 390x844 and 768x1024 verify five primary tools fit without horizontal scrolling; every secondary tool is reachable from More; the sheet restores focus; node panels fit; Agent uses full width; no text or control overlaps.

- [ ] **Step 5: Verify host embed flow**

From Flask `/canvas`, verify session validation, credit display, generation estimate, generation request, asset import, and Agent online/local modes. Confirm browser console has no errors.

- [ ] **Step 6: Record visual evidence and close issues**

Capture desktop/mobile screenshots and record each discovered issue as found, assigned, fixed, retested, and closed before acceptance.
