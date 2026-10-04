# Huishi Settings And Admin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the clipped workspace settings menu and remove legacy console styles that make admin text invisible or inconsistent.

**Architecture:** Keep the existing Flask templates and vanilla theme script. Render theme choices as an inline segmented control, remove the legacy `console-page` body class from admin, and make all admin surfaces inherit a single scoped semantic token set.

**Tech Stack:** Flask, Jinja, CSS, vanilla JavaScript, pytest contract tests

---

### Task 1: Add failing settings and admin contracts

**Files:**
- Modify: `tests/test_ui_theme_contract.py`
- Modify: `tests/test_admin_ui_structure.py`
- Modify: `tests/test_user_ui_structure.py`

- [ ] **Step 1: Replace the nested theme-menu expectations**

Require a segmented group with three direct buttons:

```python
assert 'class="theme-segmented"' in options
assert 'role="group"' in options
assert options.count('data-theme-option=') == 3
assert "data-theme-menu-panel" not in options
```

- [ ] **Step 2: Add the admin isolation contract**

```python
assert "console-page admin-console-page" not in layout
assert "admin-console-page" in layout
admin_block = css[css.index(".admin-console-page {") :]
assert "Instrument Serif" not in admin_block
assert "var(--c-" not in admin_block
```

- [ ] **Step 3: Run focused tests and verify failure**

Run: `pytest -q tests/test_ui_theme_contract.py tests/test_admin_ui_structure.py tests/test_user_ui_structure.py`

Expected: failures for the nested menu and mixed admin body classes.

### Task 2: Redesign the settings menu

**Files:**
- Modify: `templates/partials/studio_nav.html`
- Modify: `templates/partials/theme_options.html`
- Modify: `static/js/theme.js`
- Modify: `static/css/site.css`

- [ ] **Step 1: Group the menu entries**

Add semantic groups for account, preference, admin and logout. Add inline Lucide-style SVGs. Keep the Jinja admin permission check exactly where it currently runs.

- [ ] **Step 2: Replace nested theme interaction**

Render three direct theme buttons with `data-theme-option`, `aria-pressed` and labels `浅色`, `深色`, `系统`. Remove menu trigger, menu panel and nested close logic from `theme.js`. Keep storage, system `matchMedia`, theme events and iframe synchronization unchanged.

- [ ] **Step 3: Scope the menu styles**

Set `.workspace-page .rail-settings-panel` to approximately 228px and style `.theme-segmented` as one inline segmented control. Add separators for admin and logout. Do not add naked element selectors.

- [ ] **Step 4: Run theme and navigation tests**

Run: `pytest -q tests/test_ui_theme_contract.py tests/test_user_ui_structure.py`

Expected: PASS.

### Task 3: Remove legacy admin style contamination

**Files:**
- Modify: `templates/admin/layout.html`
- Modify: `static/css/site.css`
- Modify: `tests/test_admin_ui_structure.py`

- [ ] **Step 1: Remove the legacy body class**

Change the body class block to:

```jinja2
{% block body_class %}admin-console-page{% endblock %}
```

- [ ] **Step 2: Normalize admin typography and colors**

Ensure `.admin-console-page` uses only `var(--font-ui)`, `--admin-ink`, `--admin-muted`, `--admin-canvas`, `--admin-surface` and `--admin-soft`. Remove admin-scoped `Instrument Serif` and `--c-*` dependencies. Keep status colors semantic.

- [ ] **Step 3: Normalize tables and forms**

Use 40px minimum table rows, sticky headers, tabular numerals, semantic input surfaces and one 8px radius scale. Preserve existing permissions, forms, confirmation attributes and drawer behavior.

- [ ] **Step 4: Run admin contracts**

Run: `pytest -q tests/test_admin_ui_structure.py tests/test_admin_console_experience.py tests/test_admin_delete_user_cascade.py`

Expected: PASS.

### Task 4: Verify Flask UI regressions

**Files:**
- Verify only

- [ ] **Step 1: Run focused UI tests**

Run: `pytest -q tests/test_ui_theme_contract.py tests/test_user_ui_structure.py tests/test_admin_ui_structure.py tests/test_admin_console_experience.py`

Expected: PASS.

- [ ] **Step 2: Run the full Python suite**

Run: `pytest -q`

Expected: PASS.

- [ ] **Step 3: Check encoding**

Run: `npm run check:encoding`

Expected: all tracked text files are valid UTF-8.
