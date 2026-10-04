# Reference Thumbnail Hover Close Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make uploaded reference thumbnails enlarge as a whole on hover and make the delete control a true round white close button at the image's upper-right corner.

**Architecture:** This is a CSS-only UI correction with one focused regression test. `static/css/site.css` owns the visual behavior; `tests/test_workspace_composer_copy.py` locks the expected CSS contract; `templates/base.html` bumps the static CSS version so browsers fetch the new rules.

**Tech Stack:** Flask/Jinja templates, plain CSS, pytest.

---

### Task 1: Lock The Visual Contract

**Files:**
- Modify: `tests/test_workspace_composer_copy.py`

- [ ] **Step 1: Write the failing test**

Update `test_reference_material_add_card_keeps_empty_and_uploaded_states_separate` so it asserts the close button is forced square/round and thumbnail hover scales the full tile:

```python
    assert "inline-size: 18px;" in css
    assert "block-size: 18px;" in css
    assert "min-width: 18px;" in css
    assert "min-height: 18px;" in css
    assert "max-width: 18px;" in css
    assert "max-height: 18px;" in css
    assert "aspect-ratio: 1;" in css
    assert "border-radius: 50%;" in css
    assert ".reference-material-tile:hover" in css
    assert "scale(1.24)" in css
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
@'
import pytest, sys
sys.exit(pytest.main(['-q','tests/test_workspace_composer_copy.py']))
'@ | .\.venv\Scripts\python.exe -
```

Expected: `test_reference_material_add_card_keeps_empty_and_uploaded_states_separate` fails because `inline-size: 18px;`, `aspect-ratio: 1;`, or `scale(1.24)` is missing.

### Task 2: Force A Round Close Button And Full Tile Scale

**Files:**
- Modify: `static/css/site.css`

- [ ] **Step 1: Implement the CSS correction**

In the `.reference-material-tile:hover` rule, scale the full tile more strongly:

```css
.reference-material-tile:hover {
  box-shadow: 0 18px 42px color-mix(in srgb, var(--studio-soft-shadow) 96%, transparent);
  transform: rotate(calc((var(--stack-index, 0) - 1) * -5deg)) scale(1.24);
  z-index: 60;
}
```

In the expanded-stack hover rule, scale the tile as a whole:

```css
.reference-material-stack:hover .reference-material-tile:hover,
.reference-material-stack.is-expanded .reference-material-tile:hover {
  transform: scale(1.24);
  z-index: 60;
}
```

Replace the `.reference-remove` sizing block with square constraints that cannot be stretched by generic button rules:

```css
.reference-remove {
  position: absolute;
  top: -7px;
  right: -7px;
  inline-size: 18px;
  block-size: 18px;
  width: 18px;
  height: 18px;
  min-width: 18px;
  min-height: 18px;
  max-width: 18px;
  max-height: 18px;
  aspect-ratio: 1;
  padding: 0;
  border: 1px solid rgba(31, 42, 29, .12);
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: rgba(255, 255, 255, .98);
  color: #1f2a1d;
  font-size: 0;
  line-height: 0;
  z-index: 70;
  opacity: 0;
  pointer-events: none;
  cursor: pointer;
  box-sizing: border-box;
  appearance: none;
  transition: opacity .14s ease, transform .14s ease, background-color .14s ease, box-shadow .14s ease;
}
```

Keep the pseudo-element X centered inside the round button:

```css
.reference-remove::before,
.reference-remove::after {
  content: "";
  position: absolute;
  width: 8px;
  height: 1.5px;
  border-radius: 999px;
  background: currentColor;
}
```

Mirror the same square constraints under `.workspace-page .reference-remove` so the workspace theme cannot stretch the button.

- [ ] **Step 2: Run tests**

Run:

```powershell
@'
import pytest, sys
sys.exit(pytest.main(['-q','tests/test_workspace_composer_copy.py','tests/test_workspace_generation_flow.py']))
'@ | .\.venv\Scripts\python.exe -
```

Expected: all tests pass.

### Task 3: Bust CSS Cache And Restart

**Files:**
- Modify: `templates/base.html`

- [ ] **Step 1: Bump the stylesheet version**

Change the CSS include to:

```html
<link rel="stylesheet" href="{{ url_for('static', filename='css/site.css', v='20260617-reference-round-close-1') }}">
```

- [ ] **Step 2: Restart the Flask service**

Run:

```powershell
$procs = Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python' -and $_.CommandLine -match 'app\.py' }
foreach ($p in $procs) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 2
$python = Join-Path (Get-Location) '.venv\Scripts\python.exe'
Start-Process -FilePath $python -ArgumentList 'app.py' -WorkingDirectory (Get-Location) -WindowStyle Hidden
Start-Sleep -Seconds 4
```

- [ ] **Step 3: Verify the new CSS version is served**

Run:

```powershell
$html = (Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/workspace?new=1 -TimeoutSec 10).Content
if ($html -match '20260617-reference-round-close-1') { 'css-version-ok' } else { 'css-version-missing' }
```

Expected: `css-version-ok`.

---

## Self-Review

- Spec coverage: Task 2 enlarges the whole `.reference-material-tile` on hover and forces `.reference-remove` into a round white button.
- Placeholder scan: no placeholders remain.
- Type consistency: selectors match existing CSS and test file names.
