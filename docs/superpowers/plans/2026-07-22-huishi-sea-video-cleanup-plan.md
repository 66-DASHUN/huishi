# Huishi Sea Video Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the person-containing hero media with a physically trimmed sea-only file and remove the adjacent `绘世` navbar wordmark.

**Architecture:** Keep the existing two-section React page and rAF-driven `FadingVideo` component. Produce one immutable hero media asset from the validated local source, update the homepage asset contract, and verify the deployed result over SSH and Playwright.

**Tech Stack:** React, Babel build, Python pytest, FFmpeg/FFprobe, Playwright, systemd, SSH

---

### Task 1: Lock the Requested Homepage Contract

**Files:**
- Modify: `tests/test_home_assets.py`
- Modify: `tests/test_requested_regressions.py`
- Modify: `tests/test_asset_budget.py`
- Modify: `tools/check_asset_budget.py`

- [ ] Add assertions for `shouyeshipin-sea.mp4`, the absence of `home-brand-name`, and the new binary digest.
- [ ] Change both asset budget maps from `shouyeshipin-home.mp4` to `shouyeshipin-sea.mp4`.
- [ ] Upload only the test and budget files to `/opt/huishi`.
- [ ] Run `pytest tests/test_home_assets.py tests/test_asset_budget.py tests/test_requested_regressions.py -q` and confirm failures point to the old hero filename and visible wordmark.

### Task 2: Produce the Sea-Only Hero Asset

**Files:**
- Create: `static/media/shouyeshipin-sea.mp4`

- [ ] Run FFmpeg against the verified source hash `a41ae34355ddac463b796eaaea7837785305efdadc3a9a2bd0a1a506065d9053` with `-t 8.7`, H.264, `yuv420p`, fast-start metadata, and no audio.
- [ ] Use FFprobe to confirm the duration is approximately 8.7 seconds, codec is H.264, and the file contains no audio stream.
- [ ] Extract frames across the resulting duration and visually confirm every frame is sea, sky, cloud, or wave with no crystal or human outline.
- [ ] Record the final SHA-256 digest in `tests/test_home_assets.py`.

### Task 3: Update the Homepage Source and Cache Version

**Files:**
- Modify: `static/js/home.js`
- Modify: `templates/home.html`

- [ ] Change `HERO_VIDEO` to `/static/media/shouyeshipin-sea.mp4`.
- [ ] Delete `<span className="home-brand-name">绘世</span>` while preserving the circular `绘` mark and accessible link label.
- [ ] Bump the two homepage asset query strings from `20260715-home-video-4` to `20260722-sea-video-1`.
- [ ] Upload the source, template, and new media file to `/opt/huishi`.
- [ ] Run the focused pytest command and confirm it passes.

### Task 4: Build, Verify, and Restart

**Files:**
- Generated: `static/js/home.compiled.js`

- [ ] Run the repository's homepage verification/build command `bun run verify:home`.
- [ ] Run the complete Python test suite with `pytest -q`.
- [ ] Restart `huishi.service` and confirm it is active.
- [ ] Request `/` locally on the VM and confirm HTTP 200.

### Task 5: Browser and Claude Review

**Files:**
- Create temporary Playwright screenshots and sampled hero frames outside the application tree.

- [ ] Verify desktop and mobile render exactly two video elements and no `.home-brand-name` element.
- [ ] Seek through the complete hero video and capture representative frames, confirming no crystal, person, or luminous human outline.
- [ ] Check page overflow and browser console errors.
- [ ] Give the final screenshots and evidence to local Claude for the requested high-weight visual review.

