# Huishi Canvas Surfaces Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align canvas project cards with the existing canvas theme and prevent the desktop bottom HUD and toolbar from colliding when Agent opens.

**Architecture:** Replace hardcoded stone card colors with the existing semantic Tailwind and canvas theme tokens. Keep the zoom HUD and action toolbar as separate surfaces inside one CSS grid Rail owned by `CanvasToolbar`, avoiding runtime collision measurements.

**Tech Stack:** Next.js, React 19, TypeScript, Tailwind CSS 4, Ant Design, Bun tests

---

### Task 1: Add source-level regression tests

**Files:**
- Create: `infinite-canvas/web/src/app/(user)/canvas/components/canvas-surface-contract.test.ts`

- [ ] **Step 1: Write failing card and Rail contracts**

```ts
import { expect, test } from "bun:test";

test("project card uses semantic theme surfaces", async () => {
    const source = await Bun.file(new URL("./canvas-project-card.tsx", import.meta.url)).text();
    expect(source).toContain("bg-card");
    expect(source).toContain("border-border");
    expect(source).not.toContain("#f1eee8");
    expect(source).not.toContain("stone-");
    expect(source).not.toContain("rounded-2xl");
});

test("desktop controls share one collision-free rail", async () => {
    const toolbar = await Bun.file(new URL("./canvas-toolbar.tsx", import.meta.url)).text();
    const zoom = await Bun.file(new URL("./canvas-zoom-controls.tsx", import.meta.url)).text();
    expect(toolbar).toContain("data-canvas-bottom-rail");
    expect(toolbar).toContain("grid-cols-[auto_minmax(0,1fr)]");
    expect(zoom).not.toContain("absolute bottom-5 left-5");
});
```

- [ ] **Step 2: Run tests and verify failure**

Run: `cd infinite-canvas/web && bun test src/app/'(user)'/canvas/components/canvas-surface-contract.test.ts`

Expected: both tests FAIL against the old card and independent absolute controls.

### Task 2: Theme the project card

**Files:**
- Modify: `infinite-canvas/web/src/app/(user)/canvas/components/canvas-project-card.tsx`

- [ ] **Step 1: Replace hardcoded surfaces**

Use `rounded-lg border border-border bg-card text-card-foreground p-4`. Use `text-muted-foreground` for metadata, `hover:border-primary/35` for hover, and `text-destructive` for delete.

- [ ] **Step 2: Add accessible action tooltips**

Wrap export, rename, save, cancel and delete buttons in Ant Design `Tooltip`. Preserve every `aria-label`, `stopPropagation`, rename flow and delete dialog.

- [ ] **Step 3: Make selection intent quiet**

Keep the checkbox in a stable slot and fade it to full opacity on `group-hover`, `group-focus-within` or selected state. Do not move content when its visibility changes.

- [ ] **Step 4: Run the focused card contract**

Run: `cd infinite-canvas/web && bun test src/app/'(user)'/canvas/components/canvas-surface-contract.test.ts`

Expected: the card contract passes.

### Task 3: Place both desktop controls in one Rail

**Files:**
- Modify: `infinite-canvas/web/src/app/(user)/canvas/components/canvas-toolbar.tsx`
- Modify: `infinite-canvas/web/src/app/(user)/canvas/components/canvas-zoom-controls.tsx`
- Modify: `infinite-canvas/web/src/app/(user)/canvas/[id]/canvas-client-page.tsx`

- [ ] **Step 1: Make `CanvasZoomControls` presentational**

Remove its absolute wrapper and return a 48px high, 8px radius themed HUD. Keep the shortcut Modal, slider behavior, minimap toggle and reset behavior unchanged.

- [ ] **Step 2: Add a `zoomControls` slot to `CanvasToolbar`**

Add `zoomControls: ReactNode` and render the desktop surfaces in:

```tsx
<div data-canvas-bottom-rail className="pointer-events-none absolute inset-x-4 bottom-4 z-[60] hidden min-w-0 grid-cols-[auto_minmax(0,1fr)] items-end gap-3 md:grid">
    <div className="pointer-events-auto min-w-0">{zoomControls}</div>
    <div className="pointer-events-none relative flex min-w-0 justify-center">...</div>
</div>
```

Keep `CanvasMobileToolbar` outside the desktop Rail.

- [ ] **Step 3: Pass the existing zoom control through the slot**

Remove the standalone `CanvasZoomControls` render in `canvas-client-page.tsx` and pass the same props through `zoomControls={<CanvasZoomControls ... />}`. Do not change viewport state.

- [ ] **Step 4: Run toolbar contracts**

Run: `cd infinite-canvas/web && bun test src/app/'(user)'/canvas/components/canvas-surface-contract.test.ts src/app/'(user)'/canvas/components/canvas-toolbar-tools.test.ts`

Expected: PASS.

### Task 4: Verify canvas compilation and behavior

**Files:**
- Verify only

- [ ] **Step 1: Run all Bun tests**

Run: `cd infinite-canvas/web && bun test`

Expected: PASS.

- [ ] **Step 2: Run TypeScript validation**

Run: `cd infinite-canvas/web && bun run typecheck`

Expected: no TypeScript errors.

- [ ] **Step 3: Build Next.js**

Run: `cd infinite-canvas/web && bun run build`

Expected: production build succeeds.

