# Huishi Performance and Maintainability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the documented verification commands real, reduce first-load assets, remove confirmed dead media safely, and split high-risk canvas responsibilities without changing user behavior.

**Architecture:** Add lightweight repository-owned verification scripts, compile the existing React homepage in production/minified mode, enforce asset budgets, lazy-load heavy canvas features, and extract pure canvas logic one responsibility at a time. No framework replacement or broad dependency upgrade is included.

**Tech Stack:** Python, pytest, Node/npm, esbuild, Tailwind, Next.js, Bun, TypeScript.

---

### Task 1: Add Real Encoding and Verification Commands

**Files:**
- Create: `tools/check_encoding.py`
- Create: `tests/test_check_encoding.py`
- Modify: `package.json`
- Modify: `README.md`

- [ ] **Step 1: Write failing encoding scanner tests**

```python
def test_find_encoding_errors_reports_invalid_utf8(tmp_path):
    (tmp_path / "good.py").write_text("绘世", encoding="utf-8")
    (tmp_path / "bad.txt").write_bytes(b"\xff\xfe")
    errors = find_encoding_errors(tmp_path)
    assert errors == ["bad.txt: invalid UTF-8"]


def test_find_encoding_errors_skips_generated_directories(tmp_path):
    generated = tmp_path / "node_modules" / "bad.js"
    generated.parent.mkdir()
    generated.write_bytes(b"\xff")
    assert find_encoding_errors(tmp_path) == []
```

- [ ] **Step 2: Verify the tests fail because the scanner is missing**

Run: `.venv/bin/python -m pytest -q tests/test_check_encoding.py`

Expected: import failure.

- [ ] **Step 3: Implement deterministic UTF-8 scanning**

```python
TEXT_SUFFIXES = {".py", ".html", ".js", ".mjs", ".ts", ".tsx", ".json", ".css", ".md", ".yml", ".yaml", ".toml", ".ini", ".service", ".timer", ".sh", ".ps1"}
SKIP_PARTS = {".git", ".next", ".venv", "node_modules", "__pycache__", ".pytest_cache", "static/uploads"}

def find_encoding_errors(root: Path) -> list[str]:
    errors = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES or any(part in SKIP_PARTS for part in relative.parts):
            continue
        try:
            path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            errors.append(f"{relative.as_posix()}: invalid UTF-8")
    return errors
```

- [ ] **Step 4: Add truthful npm scripts**

```json
{
  "scripts": {
    "test": "python -m pytest -q",
    "check:encoding": "python tools/check_encoding.py",
    "verify:home": "npm run check:encoding && npm run build:home"
  }
}
```

Preserve all existing build scripts.

- [ ] **Step 5: Verify scanner and command existence**

Run: `.venv/bin/python -m pytest -q tests/test_check_encoding.py`

Run: `npm run check:encoding`

Expected: tests pass and scanner exits 0.

### Task 2: Produce a Minified Production Homepage Bundle

**Files:**
- Modify: `package.json`
- Modify: `tests/test_seo_metadata.py`
- Create: `tests/test_home_build_config.py`

- [ ] **Step 1: Write a failing build-script contract test**

```python
def test_home_build_uses_production_minification():
    package = json.loads(Path("package.json").read_text(encoding="utf-8"))
    command = package["scripts"]["build:home:js"]
    assert "--minify" in command
    assert '--define:process.env.NODE_ENV=\"production\"' in command
```

- [ ] **Step 2: Verify the contract fails**

Run: `.venv/bin/python -m pytest -q tests/test_home_build_config.py`

Expected: fail because the current esbuild command is unminified.

- [ ] **Step 3: Update the existing esbuild command**

```json
"build:home:js": "esbuild static/js/home.js --bundle --minify --define:process.env.NODE_ENV=\"production\" --loader:.js=jsx --jsx-factory=React.createElement --jsx-fragment=React.Fragment --format=iife --outfile=static/js/home.compiled.js"
```

- [ ] **Step 4: Build and measure**

Run: `npm run build:home:js`

Expected: exit 0 and `static/js/home.compiled.js` is materially below the audited 1,100,793 bytes.

- [ ] **Step 5: Verify homepage behavior and metadata tests**

Run: `.venv/bin/python -m pytest -q tests/test_home_password_toggle.py tests/test_auth_csrf.py tests/test_seo_metadata.py tests/test_home_build_config.py`

Expected: all selected tests pass.

### Task 3: Stop Loading Global CSS on the Homepage

**Files:**
- Modify: `templates/base.html`
- Modify: `templates/home.html`
- Modify: `static/css/home-tailwind.input.css`
- Modify: `tailwind.home.config.js`
- Create: `tests/test_home_assets.py`

- [ ] **Step 1: Write a failing homepage asset test**

```python
def test_home_does_not_load_global_site_css(client):
    body = client.get("/").get_data(as_text=True)
    assert "css/home-tailwind.css" in body
    assert "css/site.css" not in body
```

- [ ] **Step 2: Verify the test fails because `base.html` always loads site CSS**

Run: `.venv/bin/python -m pytest -q tests/test_home_assets.py`

Expected: fail on `site.css` presence.

- [ ] **Step 3: Add an overridable stylesheet block**

```jinja2
{% block site_styles %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/site.css') }}">
{% endblock %}
```

Override `site_styles` in `home.html` with the homepage stylesheet only. Ensure Tailwind input includes the reset and every class used by home/auth components.

- [ ] **Step 4: Rebuild CSS and run homepage tests**

Run: `npm run build:home:css`

Run: `.venv/bin/python -m pytest -q tests/test_home_assets.py tests/test_home_password_toggle.py tests/test_auth_csrf.py tests/test_seo_metadata.py`

Expected: all selected tests pass and the homepage renders login/register states without `site.css`.

### Task 4: Add Asset Budgets and Remove Confirmed Dead Media

**Files:**
- Create: `tools/check_asset_budget.py`
- Create: `tests/test_asset_budget.py`
- Modify: `package.json`
- Delete after explicit approval: `static/media/shouyeshipin.mp4`

- [ ] **Step 1: Write failing budget and reference tests**

```python
def test_home_assets_fit_budget():
    failures = check_budgets(Path("."), {"static/js/home.compiled.js": 300_000, "static/css/home-tailwind.css": 40_000, "static/media/shouyeshipin-home.mp4": 3_200_000})
    assert failures == []


def test_legacy_video_is_not_referenced():
    references = find_references([Path("templates"), Path("static/js"), Path("static/css")], "shouyeshipin.mp4")
    assert references == []
```

- [ ] **Step 2: Verify the JS budget fails before minification or the scanner is missing**

Run: `.venv/bin/python -m pytest -q tests/test_asset_budget.py`

Expected: fail on missing module or oversized bundle.

- [ ] **Step 3: Implement budget and reference scanning**

The scanner reports actual bytes and configured limits, skips generated dependency directories, and exits 1 on any exceeded budget or unexpected reference.

- [ ] **Step 4: Add `check:assets` to package scripts**

Run: `npm run build:home && npm run check:assets`

Expected: both commands exit 0.

- [ ] **Step 5: Back up and remove the legacy video only after user approval**

Verify no source/template reference, create a code snapshot containing the file, then remove `static/media/shouyeshipin.mp4` and rerun the reference scanner.

Expected: active homepage continues using `shouyeshipin-home.mp4` and poster.

### Task 5: Lazy-Load Heavy Canvas Surfaces

**Files:**
- Modify: `infinite-canvas/web/src/app/(user)/canvas/[id]/canvas-client-page.tsx`
- Create: `infinite-canvas/web/src/app/(user)/canvas/utils/canvas-lazy-surfaces.test.ts`

- [ ] **Step 1: Add a failing dynamic-import source test**

```typescript
test("heavy canvas surfaces are dynamically imported", async () => {
    const source = await Bun.file(new URL("../[id]/canvas-client-page.tsx", import.meta.url)).text();
    for (const name of ["CanvasAssistantPanel", "AssetPickerModal", "PromptSelectDialog"]) {
        expect(source).toContain(`dynamic(() => import(`);
        expect(source).toContain(name);
    }
});
```

- [ ] **Step 2: Verify the test fails on static imports**

Run: `cd infinite-canvas/web && bun test src/app/'(user)'/canvas/utils/canvas-lazy-surfaces.test.ts`

Expected: fail because surfaces are statically imported.

- [ ] **Step 3: Replace static imports with named dynamic imports**

```typescript
const CanvasAssistantPanel = dynamic(() => import("../components/canvas-assistant-panel").then((module) => module.CanvasAssistantPanel), { ssr: false });
const AssetPickerModal = dynamic(() => import("../components/asset-picker-modal").then((module) => module.AssetPickerModal), { ssr: false });
const PromptSelectDialog = dynamic(() => import("@/components/prompts/prompt-select-dialog").then((module) => module.PromptSelectDialog), { ssr: false });
```

Only mount each surface when open so its chunk is not requested on an empty canvas.

- [ ] **Step 4: Verify tests, typecheck, and build**

Run: `cd infinite-canvas/web && bun test && bun run typecheck && bun run build`

Expected: all checks pass and build output shows separate chunks for the three surfaces.

### Task 6: Extract Canvas Agent Lifecycle

**Files:**
- Create: `infinite-canvas/web/src/app/(user)/canvas/hooks/use-canvas-agent-lifecycle.ts`
- Create: `infinite-canvas/web/src/app/(user)/canvas/hooks/use-canvas-agent-lifecycle.test.ts`
- Modify: `infinite-canvas/web/src/app/(user)/canvas/[id]/canvas-client-page.tsx`

- [ ] **Step 1: Write a failing reducer test**

```typescript
test("agent close transitions through closing before unmount", () => {
    const open = reduceAgentLifecycle(INITIAL_AGENT_LIFECYCLE, { type: "open", mode: "online" });
    const closing = reduceAgentLifecycle(open, { type: "close" });
    const closed = reduceAgentLifecycle(closing, { type: "animation-complete" });
    expect(closing).toMatchObject({ mounted: true, collapsed: true, closing: true });
    expect(closed).toEqual(INITIAL_AGENT_LIFECYCLE);
});
```

- [ ] **Step 2: Verify reducer test fails on missing hook**

Run: `cd infinite-canvas/web && bun test src/app/'(user)'/canvas/hooks/use-canvas-agent-lifecycle.test.ts`

Expected: import failure.

- [ ] **Step 3: Implement reducer plus timer ownership in the hook**

The hook exposes `mounted`, `collapsed`, `closing`, `mode`, `openAgent`, `closeAgent`, and `toggleAgent`. It clears the close timer on unmount and re-open.

- [ ] **Step 4: Replace inline lifecycle state without changing panel props**

Remove `agentCloseTimerRef`, `assistantMounted`, `assistantCollapsed`, `assistantClosing`, `openAgent`, and `closeAgent` from `canvas-client-page.tsx`; consume the hook instead.

- [ ] **Step 5: Verify behavior tests and typecheck**

Run: `cd infinite-canvas/web && bun test && bun run typecheck`

Expected: all checks pass.

### Task 7: Extract Canvas Asset Insertion

**Files:**
- Create: `infinite-canvas/web/src/app/(user)/canvas/utils/canvas-asset-insertion.ts`
- Create: `infinite-canvas/web/src/app/(user)/canvas/utils/canvas-asset-insertion.test.ts`
- Modify: `infinite-canvas/web/src/app/(user)/canvas/[id]/canvas-client-page.tsx`

- [ ] **Step 1: Write failing pure conversion tests**

```typescript
test("video asset preserves aspect ratio and centers in viewport", () => {
    const node = assetToCanvasNode(videoAsset, { x: 500, y: 400 });
    expect(node.type).toBe(CanvasNodeType.Video);
    expect(node.metadata.naturalWidth).toBe(videoAsset.width);
    expect(node.position.x + node.width / 2).toBe(500);
    expect(node.position.y + node.height / 2).toBe(400);
});
```

- [ ] **Step 2: Verify the helper is missing**

Run: `cd infinite-canvas/web && bun test src/app/'(user)'/canvas/utils/canvas-asset-insertion.test.ts`

Expected: import failure.

- [ ] **Step 3: Extract text, image, video, and audio node construction**

Pure functions receive an asset plus target canvas point and return node data. React state updates and storage upload remain in the page/hook boundary.

- [ ] **Step 4: Verify tests and typecheck**

Run: `cd infinite-canvas/web && bun test && bun run typecheck`

Expected: all checks pass and insertion behavior is unchanged.

### Task 8: Add Bundle Reporting and Final Verification

**Files:**
- Create: `infinite-canvas/web/scripts/report-bundle.mjs`
- Modify: `infinite-canvas/web/package.json`
- Modify: `docs/product/performance-security-audit.md`

- [ ] **Step 1: Implement a deterministic chunk report**

The script scans `.next/static/chunks`, reports total JS/CSS bytes and the 20 largest files, and supports `--json` for before/after comparison. It does not require another package.

- [ ] **Step 2: Add `report:bundle` and run the full frontend gate**

Run: `cd infinite-canvas/web && bun test && bun run typecheck && bun run format:check && bun run build && bun run report:bundle --json`

Expected: all commands exit 0 and a report is stored with the deployment evidence.

- [ ] **Step 3: Run the root verification gate in an isolated environment**

Run: `npm run check:encoding && npm run build:home && npm run check:assets && env -u DATABASE_URL -u HUISHI_TEST_DATABASE_URL -u HUISHI_REQUIRE_POSTGRES -u HUISHI_TEST_REQUIRE_POSTGRES HUISHI_ENV=test HUISHI_DATABASE=/tmp/huishi-pytest.sqlite3 HUISHI_OUTPUT_DIR=/tmp/huishi-pytest-uploads .venv/bin/python -m pytest -q`

Expected: every command exits 0; tests use temporary databases and uploads.

- [ ] **Step 4: Run browser performance and visual checks**

Measure homepage LCP, transferred bytes, console errors, accessibility, SEO, and the canvas editor at desktop/mobile viewports. Compare with the audited baseline: Performance 0.71, LCP about 4.4s, homepage transfer about 3.3 MB.

- [ ] **Step 5: Accept only measured improvements without functional regressions**

Homepage bundle and unused CSS must decrease, old media must be absent only after approval, canvas heavy surfaces must load on demand, and login/register/generation/assets/canvas/admin smoke flows must still pass.
