# Huishi Luminous Home Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a bright, cinematic Huishi home page using the two supplied local videos while preserving all existing navigation and authentication behavior.

**Architecture:** Keep the existing Flask template plus bundled React entry point. Add web-optimized local media and posters, express the visual system in the Tailwind input layer, and refactor the two React sections from repeated glass cards into semantic hero and capability rails. Validate media contracts with Python tests and rendered behavior with the browser.

**Tech Stack:** Flask/Jinja, React 18, Tailwind CSS 3, esbuild, pytest, FFmpeg, in-app browser automation.

---

### Task 1: Lock The Media And Visual Contracts

**Files:**
- Modify: `tests/test_home_assets.py`
- Modify: `tests/test_asset_budget.py`
- Modify: `tools/check_asset_budget.py`

- [ ] Add failing tests asserting that `home.js` references `/static/media/huishi-workflow.mp4` and both local posters, contains no `cloudfront.net`, uses the luminous hero/workflow class contracts, and avoids the former `liquid-glass` card grid.
- [ ] Add the workflow video and two posters to the shared asset-budget expectations with explicit byte limits.
- [ ] Run `./.venv/bin/python -m pytest tests/test_home_assets.py tests/test_asset_budget.py -q` and confirm failure because the new local workflow assets and class contracts do not exist.

### Task 2: Prepare The Supplied Videos

**Files:**
- Replace: `static/media/shouyeshipin-home.mp4`
- Replace: `static/media/shouyeshipin-poster.jpg`
- Create: `static/media/huishi-workflow.mp4`
- Create: `static/media/huishi-workflow-poster.jpg`

- [ ] Encode the supplied hero video to H.264/yuv420p with `faststart`, preserving 1280x720/24fps and keeping it below 3.2 MB.
- [ ] Encode the supplied workflow video to H.264/yuv420p with `faststart`, preserving 1920x1080/24fps and keeping it below 4.5 MB.
- [ ] Generate representative local JPEG posters from the supplied files with the same aspect ratios.
- [ ] Verify media dimensions, duration, codecs, pixel format, and byte limits with `ffprobe` and `stat`.

### Task 3: Implement The Luminous Layout

**Files:**
- Modify: `static/js/home.js`
- Modify: `static/css/home-tailwind.input.css`
- Modify: `templates/home.html`

- [ ] Replace the remote workflow constant with local video/poster constants.
- [ ] Update `FadingVideo` so reduced-motion users retain poster imagery and no content is gated on animation.
- [ ] Refactor `Navbar`, `Hero`, hero utility entries, `Capabilities`, and the authentication modal to the approved luminous layout while preserving existing URLs and event handlers.
- [ ] Add named design tokens, localized video overlays, focus-visible states, responsive layout rules, touch targets, and reduced-motion handling to the Tailwind input layer.
- [ ] Update the home font/theme metadata and static asset version identifiers.

### Task 4: Build And Pass Focused Tests

**Files:**
- Regenerate: `static/js/home.compiled.js`
- Regenerate: `static/css/home-tailwind.css`

- [ ] Run `npm run build:home` and confirm both bundles are generated successfully.
- [ ] Run `./.venv/bin/python -m pytest tests/test_home_assets.py tests/test_asset_budget.py tests/test_home_build_config.py tests/test_home_password_toggle.py tests/test_seo_metadata.py -q` and confirm all focused tests pass.
- [ ] Run `npm run verify:home` and confirm encoding, bundles, and asset budgets pass.

### Task 5: Render And Audit The Experience

**Files:**
- Inspect: deployed page at `https://huishi.local/`

- [ ] Restart only the Huishi service if source changes are not visible, then reload the browser page.
- [ ] Capture and inspect desktop hero/workflow screenshots at 1440x900.
- [ ] Capture and inspect mobile hero/workflow screenshots at 375x812.
- [ ] Verify video sources, computed overlay values, focus visibility, motion reduction, horizontal overflow, and console errors.
- [ ] Exercise login/register modal switching, Escape close, navigation links, and primary actions without submitting credentials.

### Task 6: Final Regression And Review

**Files:**
- Review all changed home files and generated assets.

- [ ] Run the complete project test suite with `npm test`.
- [ ] Run the Impeccable detector over the changed home source and resolve actionable findings.
- [ ] Ask local Claude to review the final diff-equivalent file changes and test evidence; resolve all BLOCKER and SHOULD_FIX findings.
- [ ] Perform a requirement-by-requirement completion audit against the design specification before reporting completion.
