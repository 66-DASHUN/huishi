# Huishi Cinematic Homepage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the approved two-video cinematic homepage with a real prompt entry while keeping all homepage styling isolated from the rest of Huishi.

**Architecture:** Keep the existing React 18 entry and Tailwind build. Extend `FadingVideo` with rAF looping, store homepage prompt drafts in `sessionStorage`, and consume them once from the existing workspace composer. Use homepage-only CSS and fonts.

**Tech Stack:** Flask/Jinja, React 18, esbuild, Tailwind CSS, pytest contract tests

---

### Task 1: Lock the homepage media and typography contracts

**Files:**
- Modify: `tests/test_home_assets.py`
- Modify: `templates/home.html`

- [ ] **Step 1: Write failing contract tests**

Update the font test to require one Google Fonts request containing `Noto+Serif+SC` and `Noto+Sans+SC`. Update the media test to require:

```python
assert 'const CAPABILITIES_VIDEO = "/static/media/huishi-workflow.mp4"' in source
assert 'const CAPABILITIES_POSTER = "/static/media/huishi-workflow-poster.jpg"' in source
assert "loop" not in video_component
assert "requestAnimationFrame" in video_component
```

- [ ] **Step 2: Run tests and verify the old implementation fails**

Run: `pytest -q tests/test_home_assets.py`

Expected: failures for the old single-font, reused-video and native-loop contracts.

- [ ] **Step 3: Update the homepage font request**

Load only `Noto Serif SC` weights 500 and 600 plus `Noto Sans SC` weights 400, 500 and 600 in the homepage font block.

- [ ] **Step 4: Run the focused font test**

Run: `pytest -q tests/test_home_assets.py -k font`

Expected: PASS.

### Task 2: Implement rAF video looping and the second video

**Files:**
- Modify: `static/js/home.js`
- Test: `tests/test_home_assets.py`

- [ ] **Step 1: Replace the reused workflow constants**

Use:

```js
const CAPABILITIES_VIDEO = "/static/media/huishi-workflow.mp4";
const CAPABILITIES_POSTER = "/static/media/huishi-workflow-poster.jpg";
```

- [ ] **Step 2: Implement the `FadingVideo` state machine**

Use `FADE_MS = 500`, `FADE_OUT_LEAD = 0.55`, rAF cancellation, `loadeddata`, `timeupdate` and `ended` listeners. Remove the `loop` attribute and clear rAF plus the 100ms replay timer on unmount.

- [ ] **Step 3: Run focused media tests**

Run: `pytest -q tests/test_home_assets.py -k "media or video or workflow"`

Expected: PASS.

### Task 3: Add the real homepage prompt entry

**Files:**
- Modify: `static/js/home.js`
- Modify: `static/js/workspace.js`
- Modify: `tests/test_home_assets.py`
- Modify: `tests/test_workspace_composer_copy.py`

- [ ] **Step 1: Add failing prompt handoff tests**

Require both files to share the key:

```python
assert 'const HOME_PROMPT_DRAFT_KEY = "huishi.home.promptDraft"' in home_source
assert 'const HOME_PROMPT_DRAFT_KEY = "huishi.home.promptDraft"' in workspace_source
assert "sessionStorage.setItem(HOME_PROMPT_DRAFT_KEY" in home_source
assert "sessionStorage.removeItem(HOME_PROMPT_DRAFT_KEY)" in workspace_source
```

- [ ] **Step 2: Run the tests and verify failure**

Run: `pytest -q tests/test_home_assets.py tests/test_workspace_composer_copy.py`

Expected: failures for the missing prompt handoff.

- [ ] **Step 3: Implement prompt submission**

Add a controlled Hero input. On non-empty submit, save to `sessionStorage`. Authenticated users navigate to `/workspace?new=1`; unauthenticated users open the login modal with the safe next target `/workspace?new=1`.

- [ ] **Step 4: Consume the draft in workspace**

At workspace initialization, fill the existing `.composer-prompt` only when it is empty, dispatch an `input` event, then clear the key. Catch storage errors without blocking the page.

- [ ] **Step 5: Run prompt handoff tests**

Run: `pytest -q tests/test_home_assets.py tests/test_workspace_composer_copy.py`

Expected: PASS.

### Task 4: Apply the approved homepage composition

**Files:**
- Modify: `static/js/home.js`
- Modify: `static/css/home-tailwind.input.css`
- Modify: `tests/test_home_assets.py`

- [ ] **Step 1: Add failing content and isolation assertions**

Require `绘梦造世`, `让灵感在无限画布中持续显形`, `多图参考`, the three approved cards, and confirm `site.css` remains absent from the homepage response.

- [ ] **Step 2: Implement Hero and workflow markup**

Replace the old marketing CTA block with the controlled prompt form. Replace the capability card copy with the approved three-card content. Keep existing authentication modal behavior.

- [ ] **Step 3: Implement homepage-only styles**

Use `Noto Serif SC` only for `.hero-title` and workflow display headings. Add scoped liquid-glass styles for the homepage navigation, prompt entry and workflow cards. Do not add any rule to `site.css`.

- [ ] **Step 4: Run homepage tests**

Run: `pytest -q tests/test_home_assets.py tests/test_home_build_config.py`

Expected: PASS.

### Task 5: Build and verify homepage assets

**Files:**
- Modify generated: `static/js/home.compiled.js`
- Modify generated: `static/css/home-tailwind.css`

- [ ] **Step 1: Build homepage assets**

Run: `npm run build:home`

Expected: esbuild and Tailwind complete without errors.

- [ ] **Step 2: Verify asset and encoding budgets**

Run: `npm run verify:home`

Expected: encoding, build and asset checks pass.

- [ ] **Step 3: Run the complete homepage contract suite**

Run: `pytest -q tests/test_home_assets.py tests/test_home_build_config.py tests/test_home_password_toggle.py`

Expected: PASS.

