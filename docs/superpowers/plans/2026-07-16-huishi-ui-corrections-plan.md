# Huishi UI Corrections Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the settings menu hierarchical and compact, center and shorten canvas controls, repair the three admin configuration pages, and deploy the requested video sources.

**Architecture:** Preserve existing Flask, vanilla theme and Next.js component boundaries. Use native disclosure for Theme, a responsive full-width canvas Rail, admin-scoped CSS, redirects for the removed overview, and the existing homepage video constants.

**Tech Stack:** Flask/Jinja, vanilla JavaScript, CSS, Next.js, React, TypeScript, Ant Design, Tailwind CSS, pytest, Bun

---

### Task 1: Compact Hierarchical Theme Menu

**Files:**
- Modify: `templates/partials/theme_options.html`
- Modify: `static/js/theme.js`
- Modify: `static/css/site.css`
- Test: `tests/test_ui_theme_contract.py`
- Test: `tests/test_user_ui_structure.py`

- [ ] Add failing assertions for a `theme-menu` disclosure, three nested `data-theme-option` buttons and a panel width no greater than 180px.
- [ ] Run the focused pytest files and verify the current segmented implementation fails.
- [ ] Replace the segmented group with an inline details/summary hierarchy while preserving `aria-pressed` and theme values.
- [ ] Update the current theme label in `updateThemeControls()` and apply compact scoped styles.
- [ ] Re-run the focused tests.

### Task 2: Center And Shorten Canvas Controls

**Files:**
- Modify: `infinite-canvas/web/src/app/(user)/canvas/components/canvas-toolbar.tsx`
- Modify: `infinite-canvas/web/src/app/(user)/canvas/components/canvas-zoom-controls.tsx`
- Modify: `infinite-canvas/web/src/app/(user)/canvas/[id]/canvas-client-page.tsx`
- Test: `infinite-canvas/web/src/app/(user)/canvas/components/canvas-surface-contract.test.ts`
- Test: `infinite-canvas/web/src/app/(user)/canvas/components/canvas-toolbar-tools.test.ts`

- [ ] Add failing source contracts for a wide-screen full-canvas centered toolbar, a More menu, `agentOpen` state and neutral toolbar accents.
- [ ] Run focused Bun tests and confirm failure.
- [ ] Pass `assistantOpen` into `CanvasToolbar`, render the Agent button active when open, and keep the Rail inside the flexing canvas section.
- [ ] Use a centered wide-screen Rail with left-pinned zoom controls and a two-column medium fallback.
- [ ] Keep primary commands visible and move low-frequency commands into an Ant Design popover/dropdown opened by a More icon.
- [ ] Replace toolbar active and range colors with canvas neutral tokens.
- [ ] Re-run Bun tests and TypeScript validation.

### Task 3: Repair Admin Configuration

**Files:**
- Modify: `huishi/routes_admin.py`
- Modify: `templates/admin/layout.html`
- Modify: `static/css/site.css`
- Modify: `tests/test_settings_config_status.py`
- Modify: `tests/test_requested_regressions.py`

- [ ] Change tests to require `/admin/config` to redirect to `/admin/config/settings`, remove Configuration Overview and retain exactly three children.
- [ ] Add CSS contract assertions for admin-scoped configuration shells, editor cards and responsive forms.
- [ ] Run focused pytest files and confirm the old overview and broken styles fail.
- [ ] Redirect `config_center()`, remove the overview nav item and point the parent link to System Configuration.
- [ ] Add final `.admin-console-page` rules for headers, summaries, settings panels, provider rows, billing cards and package forms.
- [ ] Re-run configuration and admin tests.

### Task 4: Deploy Requested Media

**Files:**
- Replace: `static/media/shouyeshipin-home.mp4`
- Replace: `static/media/huishi-workflow.mp4`
- Modify: `tools/check_asset_budget.py`
- Test: `tests/test_home_assets.py`

- [ ] Add source-hash/size contracts for the explicitly requested media.
- [ ] Run the media and asset checks and confirm the existing optimized files fail the new contract.
- [ ] Copy the two requested source files to the deployed media paths.
- [ ] Update only the two video byte budgets to match the approved source sizes.
- [ ] Re-run homepage tests, encoding and asset checks.

### Task 5: Build, Restart And Verify

**Files:**
- Modify: `infinite-canvas/docs/content/docs/progress/pending-test.mdx`

- [ ] Build homepage JavaScript and CSS.
- [ ] Run the complete Python suite, all Bun tests and TypeScript.
- [ ] Run the root Next.js production build.
- [ ] Restart `huishi.service` and `huishi-canvas.service`.
- [ ] Verify homepage, admin and canvas return HTTP 200.
- [ ] Capture desktop screenshots for the settings menu, canvas Agent closed/open states and all three configuration pages in light and dark themes.
- [ ] Verify deployed media hashes match the user sources.
- [ ] Ask Claude for a final read-only review and resolve BLOCKER or SHOULD_FIX findings.

## Completion Record

- Completed on 2026-07-16 against `huishi-vm:/opt/huishi`.
- Python: `379 passed, 60 skipped`.
- Canvas: `38 passed`; TypeScript passed.
- Homepage encoding, build and asset-budget checks passed.
- Next.js production build passed and standalone assets were prepared.
- `huishi.service` and `huishi-canvas.service` restarted and returned active.
- Playwright verified desktop and mobile video playback, the 176px hierarchical theme menu, both Agent panel states, and all three admin configuration pages in light and dark themes.
- Claude final review: no BLOCKER and no SHOULD_FIX findings.
