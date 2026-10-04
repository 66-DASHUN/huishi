# Performance Security Storage Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the Huishi app around Claude coordination timeout, storage cleanup scale, auth CSRF, SEO metadata, image loading, and generated-image compression.

**Architecture:** Keep changes focused in the Flask main app, storage sweeper, image saving path, and lightweight template/React entry points. Use configuration for destructive or operational limits, and keep dry-run/reporting behavior observable before deletion. Use tests to lock each behavior before implementation.

**Tech Stack:** Flask, Jinja templates, React UMD landing page, pytest, TypeScript MCP bridge, systemd deployment examples, optional Pillow image optimization.

---

### Task 1: Claude MCP Timeout

**Files:**
- Modify: `tools/claude-mcp/src/index.ts`
- Modify: `tools/claude-mcp/README.md`
- Modify: `.codex/config.toml`

- [x] Change the default `CLAUDE_MCP_TIMEOUT_MS` from `1200000` to `1800000`.
- [x] Rebuild `tools/claude-mcp/dist` with `npm run build`.
- [x] Verify with `rg "1800000|1200000" tools/claude-mcp .codex/config.toml`.
- [x] Record that Codex app's outer `tools/call` 300s timeout is separate from the bridge timeout if it still interrupts calls.
- [x] Add async Claude job tools (`*_async` + `claude_job_status`) so long reviews can return a job id before the outer `tools/call` timeout.

### Task 2: Storage Cleanup Scale

**Files:**
- Modify: `huishi/storage.py`
- Modify: `huishi/config.py`
- Modify: `app.py`
- Modify: `.env.example`
- Modify: `deploy/env.vm-staging.example`
- Modify: `deploy/vm-staging-bootstrap.sh`
- Modify: `tests/test_storage_sweeper.py`

- [x] Add a failing test proving a sweep reports when eligible deletions exceed the configured deletion limit.
- [x] Add `HUISHI_STORAGE_SWEEP_MAX_DELETE_FILES`, default `20000`, with `0` meaning unlimited.
- [x] Add `HUISHI_STORAGE_SWEEP_MIN_AGE_SECONDS`, default `300`, to protect in-flight generated files.
- [x] Add CLI `--max-delete-files`.
- [x] Add CLI `--min-age-seconds`.
- [x] Add result fields for `max_delete_files`, `delete_limit_reached`, `remaining_deletable_files`, and `min_age_seconds`.
- [x] Verify `pytest -q tests/test_storage_sweeper.py`.

### Task 3: Login CSRF

**Files:**
- Modify: `app.py`
- Modify: `templates/home.html`
- Modify: `static/js/home.js`
- Modify: `templates/forgot_password.html`
- Modify: `templates/verify_email.html`
- Add or modify: `tests/test_auth_csrf.py`

- [x] Add a failing test: POST `/login` without token returns 403 when CSRF testing is enabled.
- [x] Inject `window.__HUISHI_CSRF_TOKEN__` into the landing page.
- [x] Send `X-CSRF-Token` from landing auth fetches and include hidden `csrf_token` fields in auth forms.
- [x] Remove auth POST routes from `CSRF_EXEMPT_PATHS` when their forms can send tokens.
- [x] Verify targeted auth tests.

### Task 4: SEO Meta Description

**Files:**
- Modify: `templates/base.html`
- Modify: `templates/home.html`
- Add or modify: `tests/test_seo_metadata.py`

- [x] Add a failing test proving `/` renders a meta description.
- [x] Add a default `description` block in `base.html`.
- [x] Override homepage description with product-specific copy.
- [x] Verify targeted metadata tests.

### Task 5: Image Compression and Lazy Loading

**Files:**
- Modify: `requirements.txt`
- Modify: `huishi/image_api.py`
- Modify: `huishi/config.py`
- Modify: `.env.example`
- Modify: `deploy/env.vm-staging.example`
- Modify: `templates/asset_detail.html`
- Modify selected canvas TSX thumbnail `<img>` tags.
- Add or modify image tests.

- [x] Add Pillow dependency.
- [x] Add failing test proving PNG/JPEG bytes are optimized before saving when compression is enabled.
- [x] Implement `optimize_image_bytes` with safe fallback to original bytes on unsupported or invalid images.
- [x] Add `loading="lazy"` and `decoding="async"` to non-critical image thumbnails and detail images.
- [x] Verify Flask tests and Next build/typecheck where feasible.

### Task 6: Audit Report and Six-Dimension Review

**Files:**
- Add or modify: `docs/product/performance-security-audit.md`

- [x] Record prioritized findings across target, experience, content, conversion, performance, and data.
- [x] Mark fixed items with verification evidence and keep remaining work explicit.
- [x] Run Lighthouse or document the blocker and run an equivalent smoke/build verification.

### Additional Hardening From Review

- [x] Add PostgreSQL `SELECT ... FOR UPDATE` user-row lock before transactional generation reservation checks.
- [x] Add tests for PG lock SQL, lock/check ordering, and enqueue-failure task failure state.
- [x] Remove homepage `console.error` suppression after fixing React list keys.
- [x] Replace browser-side Babel with `npm run build:home` / `static/js/home.compiled.js`.
- [x] Replace Tailwind CDN with locally generated `static/css/home-tailwind.css`.
- [x] Add homepage video poster and compressed `shouyeshipin-home.mp4`.
- [x] Verify Lighthouse improved to Performance `0.71`, A11y/Best/SEO `1.00`, console errors `0`.
