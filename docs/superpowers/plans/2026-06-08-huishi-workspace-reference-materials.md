# Huishi Workspace Reference Materials Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the confirmed workspace reference-material flow, longest-edge billing, and homepage login behavior while keeping the current homepage visuals and copy.

**Architecture:** Reuse the existing Flask/Jinja/vanilla JS workspace. Centralize billing by output width/height in `huishi.billing`, keep `/generate` as the single backend entry point, and make `static/js/workspace.js` manage a browser-only reference-material stack that submits local files plus existing image references at generation time. Update tests to match the current product baseline instead of old homepage/navigation assumptions.

**Tech Stack:** Flask 3, SQLite, Jinja templates, vanilla JavaScript, Vite/React homepage, pytest, Vitest.

---

## File Structure

- Modify `huishi/billing.py`: add longest-edge tier helpers and make cost calculation support both tier labels and `WxH` sizes.
- Modify `huishi/routes_workspace.py`: accept `reference_paths`, auto-detect reference mode, load existing references, return reference data in serialized records, and soft-delete assets.
- Modify `huishi/records.py`: normalize `reference_paths`, exclude hidden assets from list pages, and include hidden records when fetched directly for history.
- Modify `huishi/db.py`: add `hidden` column migration to `records`.
- Modify `templates/workspace.html`: replace visible reference upload UI with a material stack near the prompt, keep hidden file input, add existing-reference hidden input and preview dialog hooks.
- Modify `static/js/workspace.js`: implement material stack state, drag/drop, click add, image preview, delete, generation payload, and blur-based estimate refresh.
- Modify `static/css/site.css`: style the material stack, expanded state, drag overlay, and remove old reference-upload affordance.
- Modify `src/App.tsx`: keep homepage look but change auth form targets and post-login behavior so successful login/register returns to homepage.
- Modify `src/App.test.tsx`: replace old homepage assertions with the new login baseline.
- Modify `tests/test_billing.py`, `tests/test_auth_records.py`, `tests/test_routes.py`: update backend expectations for same-price reference billing, longest-edge tiers, material-stack markup, reference path reuse, and soft delete.

The workspace JS file is already large. Keep the new material-stack code in clearly named functions inside `workspace.js` for this pass; do not split bundles unless the build system is also updated.

## Task 1: Longest-Edge Billing Helpers

**Files:**
- Modify: `huishi/billing.py`
- Test: `tests/test_billing.py`

- [ ] **Step 1: Add failing tests for tier inference and same-price reference cost**

Append these tests to `tests/test_billing.py`:

```python
def test_billing_tier_uses_longest_edge(app):
    from huishi.billing import tier_for_size

    assert tier_for_size("1536x864") == "1K"
    assert tier_for_size("2048x2048") == "2K"
    assert tier_for_size("3840x2160") == "4K"


def test_reference_and_text_custom_size_share_price(app):
    from huishi import billing

    with app.app_context():
        text_cost = billing.calculate_cost("text", "2048x2048", 1)
        reference_cost = billing.calculate_cost("reference", "2048x2048", 1)

    assert text_cost == 2
    assert reference_cost == text_cost


def test_size_above_4k_tier_is_rejected():
    from huishi.billing import tier_for_size

    with pytest.raises(ValueError, match="分辨率"):
        tier_for_size("5000x3000")
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_billing.py::test_billing_tier_uses_longest_edge tests/test_billing.py::test_reference_and_text_custom_size_share_price tests/test_billing.py::test_size_above_4k_tier_is_rejected -q --basetemp=.pytest-tmp-plan-billing
```

Expected: fails because `tier_for_size` does not exist or custom `WxH` lookup is not handled directly in `calculate_cost`.

- [ ] **Step 3: Implement billing helpers**

Update `huishi/billing.py` so the top of the file includes:

```python
import re

RESOLUTION_TIERS = (
    ("1K", 0, 1560),
    ("2K", 1561, 2440),
    ("4K", 2441, 4280),
)


def tier_for_size(size: str) -> str:
    match = re.fullmatch(r"(\d+)x(\d+)", (size or "").strip())
    if not match:
        return size
    width = int(match.group(1))
    height = int(match.group(2))
    if width < 1 or height < 1:
        raise ValueError("分辨率必须大于 0")
    longest_edge = max(width, height)
    for label, lower, upper in RESOLUTION_TIERS:
        if lower <= longest_edge <= upper:
            return label
    raise ValueError("分辨率超过 4K 上限，请降低分辨率")
```

Then change the beginning of `calculate_cost` to:

```python
def calculate_cost(mode: str, resolution: str, count: int) -> int:
    """Price every generation by output resolution tier; reference materials do not change unit price."""
    if count < 1:
        raise ValueError("生成数量必须大于 0")
    billing_resolution = tier_for_size(resolution)
    db = get_db()
    row = db.execute(
        """
        SELECT points_per_image, enabled
        FROM pricing_rules
        WHERE mode = 'text' AND resolution = ?
        """,
        (billing_resolution,),
    ).fetchone()
```

Keep the rest of the function logic, but ensure error strings are valid UTF-8 Chinese.

- [ ] **Step 4: Run focused billing tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_billing.py -q --basetemp=.pytest-tmp-plan-billing
```

Expected: all billing tests pass except any existing tests that still expect reference 4K to cost 8. Update that old expectation to `4`.

- [ ] **Step 5: Commit**

This directory is currently not a Git repository. If Git is initialized later, commit with:

```bash
git add huishi/billing.py tests/test_billing.py
git commit -m "feat: price generations by output size tier"
```

## Task 2: Records Support Hidden Assets and Reference Paths

**Files:**
- Modify: `huishi/db.py`
- Modify: `huishi/records.py`
- Test: `tests/test_auth_records.py`

- [ ] **Step 1: Add failing soft-delete test**

Append this test to `tests/test_auth_records.py` near asset delete tests:

```python
def test_asset_delete_hides_record_but_keeps_file_and_reference_history(client, app):
    client.post("/register", data={"username": "soft-delete-user", "password": "secret123"}, follow_redirects=True)
    with app.app_context():
        db = get_db()
        user = db.execute("SELECT id FROM users WHERE username = ?", ("soft-delete-user",)).fetchone()
        output_dir = app.config["OUTPUT_DIR"]
        output_dir.mkdir(parents=True, exist_ok=True)
        image_file = output_dir / "soft-delete.png"
        image_file.write_bytes(b"image")
        cursor = db.execute(
            """
            INSERT INTO records
            (user_id, prompt, image_path, image_paths, mode, ratio, resolution, actual_size, quality, output_format, count, model_source, elapsed_seconds, points_charged, reference_paths, favorite, created_at)
            VALUES (?, 'soft delete source', '/static/uploads/soft-delete.png', '["/static/uploads/soft-delete.png"]', 'text', '1:1', '1K', '1024x1024', 'auto', 'png', 1, 'demo', 1.2, 1, '[]', 0, ?)
            """,
            (user["id"], utc_now()),
        )
        record_id = cursor.lastrowid
        db.commit()

    response = client.post(f"/assets/{record_id}/delete", follow_redirects=False)

    assert response.status_code in {302, 200}
    with app.app_context():
        db = get_db()
        row = db.execute("SELECT hidden FROM records WHERE id = ?", (record_id,)).fetchone()
        assert row is not None
        assert row["hidden"] == 1
        assert (app.config["OUTPUT_DIR"] / "soft-delete.png").exists()
```

Ensure `get_db` and `utc_now` are imported in the test module; they already are in this file in current tests, otherwise add:

```python
from huishi.db import get_db, utc_now
```

- [ ] **Step 2: Run test to verify failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_auth_records.py::test_asset_delete_hides_record_but_keeps_file_and_reference_history -q --basetemp=.pytest-tmp-plan-records
```

Expected: fails because `hidden` column does not exist or delete hard-deletes the row/file.

- [ ] **Step 3: Add `hidden` column migration**

In `huishi/db.py`, add `hidden INTEGER NOT NULL DEFAULT 0` to the `records` schema after `favorite`, and add this migration entry in `migrate_records_table`:

```python
"hidden": "ALTER TABLE records ADD COLUMN hidden INTEGER NOT NULL DEFAULT 0",
```

- [ ] **Step 4: Update record listing helpers**

In `huishi/records.py`, change list queries to exclude hidden rows:

```python
"SELECT * FROM records WHERE user_id = ? AND hidden = 0 ORDER BY id DESC"
```

and:

```python
"SELECT * FROM records WHERE user_id = ? AND dialogue_id = ? AND hidden = 0 ORDER BY id DESC"
```

Do not change `get_record_for_user`; direct history/detail access must still find hidden rows for reference recovery.

In `normalize_record`, add:

```python
record["reference_paths"] = parse_reference_paths(record)
```

This keeps templates and JSON serialization from reparsing reference paths repeatedly.

- [ ] **Step 5: Soft-delete assets**

In `huishi/routes_workspace.py`, change `delete_record` from `DELETE FROM records` plus `delete_local_upload` to:

```python
get_db().execute("UPDATE records SET hidden = 1 WHERE id = ?", (record_id,))
get_db().commit()
```

Remove the local file deletion call from this route.

In `bulk_delete_assets`, change the hard delete loop and delete SQL to:

```python
cursor = get_db().execute(
    f"UPDATE records SET hidden = 1 WHERE id IN ({placeholders}) AND user_id = ?",
    [*ids, g.user["id"]],
)
get_db().commit()
return jsonify({"ok": True, "deleted": cursor.rowcount})
```

Keep `delete_local_upload` defined for any future internal cleanup, but do not call it for user deletes.

- [ ] **Step 6: Run focused records tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_auth_records.py::test_asset_delete_hides_record_but_keeps_file_and_reference_history -q --basetemp=.pytest-tmp-plan-records
```

Expected: pass.

- [ ] **Step 7: Commit**

If Git is initialized later:

```bash
git add huishi/db.py huishi/records.py huishi/routes_workspace.py tests/test_auth_records.py
git commit -m "feat: soft-delete assets and preserve reference history"
```

## Task 3: Backend Generation Accepts Material References

**Files:**
- Modify: `huishi/routes_workspace.py`
- Modify: `huishi/records.py`
- Test: `tests/test_auth_records.py`

- [ ] **Step 1: Add failing test for existing image reference reuse via `/generate`**

Append:

```python
def test_generate_accepts_existing_reference_paths_without_reupload(client, app, monkeypatch):
    client.post("/register", data={"username": "existing-ref-user", "password": "secret123"}, follow_redirects=True)
    calls = {}

    def fake_generate_image(**kwargs):
        calls["mode"] = kwargs["mode"]
        references = kwargs["reference_images"]
        calls["reference_names"] = [item.filename for item in references]
        calls["reference_bytes"] = [item.read() for item in references]
        return {
            "image_path": "/static/uploads/generated-existing-ref.png",
            "image_paths": ["/static/uploads/generated-existing-ref.png"],
            "actual_size": "1536x864",
            "model_source": "fake",
            "elapsed_seconds": 0.1,
        }

    monkeypatch.setattr("huishi.routes_workspace.generate_image", fake_generate_image)
    with app.app_context():
        db = get_db()
        user = db.execute("SELECT id FROM users WHERE username = ?", ("existing-ref-user",)).fetchone()
        db.execute("UPDATE users SET points = 20 WHERE id = ?", (user["id"],))
        output_dir = app.config["OUTPUT_DIR"]
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "source-ref.png").write_bytes(b"existing-reference")
        db.commit()

    response = client.post(
        "/generate",
        data={
            "prompt": "use existing reference",
            "ratio": "16:9",
            "width": "1536",
            "height": "864",
            "count": "1",
            "reference_paths": "/static/uploads/source-ref.png",
        },
        headers={"X-Requested-With": "fetch"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["record"]["mode"] == "reference"
    assert payload["record"]["reference_paths"] == ["/static/uploads/source-ref.png"]
    assert calls["mode"] == "reference"
    assert calls["reference_names"] == ["source-ref.png"]
    assert calls["reference_bytes"] == [b"existing-reference"]
```

- [ ] **Step 2: Run test to verify failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_auth_records.py::test_generate_accepts_existing_reference_paths_without_reupload -q --basetemp=.pytest-tmp-plan-generate
```

Expected: fails because `/generate` ignores `reference_paths` and serialized records do not include reference paths.

- [ ] **Step 3: Add helper for parsing posted reference paths**

In `huishi/routes_workspace.py`, add:

```python
def parse_reference_path_form_values() -> list[str]:
    raw_values = request.form.getlist("reference_paths")
    paths: list[str] = []
    for raw_value in raw_values:
        for item in str(raw_value or "").split(","):
            path = item.strip()
            if path and path.startswith("/static/uploads/") and path not in paths:
                paths.append(path)
    return paths
```

- [ ] **Step 4: Update `/generate` reference handling**

In `generate`, replace the current reference setup:

```python
reference_images = [item for item in request.files.getlist("reference_images") if item and item.filename]
```

with:

```python
uploaded_reference_images = [item for item in request.files.getlist("reference_images") if item and item.filename]
existing_reference_paths = parse_reference_path_form_values()
reference_images = list(uploaded_reference_images)
if existing_reference_paths:
    reference_images.extend(load_reference_images(existing_reference_paths))
mode = "reference" if reference_images else "text"
```

Keep `mode` validation but make it validate the derived mode:

```python
if mode not in ALLOWED_MODES:
    return generation_error("生成模式无效", 400)
```

Remove the old error that required uploaded files when mode was reference; existing paths now satisfy reference mode.

Change saving paths:

```python
saved_reference_paths = save_reference_images(uploaded_reference_images) if uploaded_reference_images else []
reference_paths = [*existing_reference_paths, *saved_reference_paths] if mode == "reference" else []
```

Pass `reference_paths` to `_finalize_generation`.

- [ ] **Step 5: Serialize reference paths**

In `serialize_record`, add:

```python
"reference_paths": record["reference_paths"],
```

Because Task 2 normalizes this field to a list.

- [ ] **Step 6: Run focused generation tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_auth_records.py::test_generate_accepts_existing_reference_paths_without_reupload tests/test_auth_records.py::test_asset_regenerate_reuses_saved_reference_sources -q --basetemp=.pytest-tmp-plan-generate
```

Expected: both pass, with existing regenerate behavior preserved.

- [ ] **Step 7: Commit**

If Git is initialized later:

```bash
git add huishi/routes_workspace.py huishi/records.py tests/test_auth_records.py
git commit -m "feat: submit existing images as reference materials"
```

## Task 4: Workspace Material Stack Markup

**Files:**
- Modify: `templates/workspace.html`
- Test: `tests/test_auth_records.py`

- [ ] **Step 1: Add failing markup test**

Append:

```python
def test_workspace_uses_material_stack_not_reference_upload_copy(client):
    client.post("/register", data={"username": "material-stack-user", "password": "secret123"}, follow_redirects=True)

    response = client.get("/workspace")
    text = response.get_data(as_text=True)

    assert 'class="reference-material-stack' in text
    assert 'data-reference-add' in text
    assert 'name="reference_images"' in text
    assert 'name="reference_paths"' in text
    assert "参考图上传" not in text
    assert "图生图" not in text
```

- [ ] **Step 2: Run test to verify failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_auth_records.py::test_workspace_uses_material_stack_not_reference_upload_copy -q --basetemp=.pytest-tmp-plan-markup
```

Expected: fails because current markup uses old `reference-preview`/clear button and lacks material stack class.

- [ ] **Step 3: Replace reference controls in template**

In `templates/workspace.html`, keep the file input but make it hidden and add existing path input:

```html
<input class="reference-input" name="reference_images" id="reference-images" type="file" accept="image/png,image/jpeg,image/webp" multiple hidden>
<input type="hidden" name="reference_paths" id="reference-paths" value="">
```

Replace this old block inside `.composer-controls`:

```html
<div class="reference-preview" id="reference-preview"></div>
<button type="button" class="reference-clear" data-clear-reference hidden aria-label="清空参考图">清空</button>
```

with:

```html
<div class="reference-material-stack is-empty" id="reference-material-stack" data-reference-stack>
  <button type="button" class="reference-add-card" data-reference-add aria-label="添加素材">+</button>
  <div class="reference-material-list" id="reference-preview" data-reference-list aria-label="参考素材"></div>
</div>
```

Add a reference preview dialog near the existing image preview modal:

```html
<dialog id="reference-preview-modal" class="image-preview-modal" aria-label="素材预览">
  <button type="button" class="image-preview-close" data-close-reference-preview aria-label="关闭预览">×</button>
  <img src="" alt="">
  <p data-reference-preview-caption></p>
</dialog>
```

- [ ] **Step 4: Run markup test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_auth_records.py::test_workspace_uses_material_stack_not_reference_upload_copy -q --basetemp=.pytest-tmp-plan-markup
```

Expected: pass.

- [ ] **Step 5: Commit**

If Git is initialized later:

```bash
git add templates/workspace.html tests/test_auth_records.py
git commit -m "feat: add workspace reference material stack markup"
```

## Task 5: Workspace Material Stack JavaScript

**Files:**
- Modify: `static/js/workspace.js`
- Test: add light DOM tests only if existing JS test harness exists; otherwise verify with browser in Task 10.

- [ ] **Step 1: Replace old reference state variables**

Near the top of `static/js/workspace.js`, add:

```javascript
const referenceStack = document.querySelector("[data-reference-stack]");
const referenceAddButton = document.querySelector("[data-reference-add]");
const referencePathsInput = document.querySelector("#reference-paths");
const referencePreviewModal = document.querySelector("#reference-preview-modal");
const referencePreviewImage = referencePreviewModal?.querySelector("img");
const referencePreviewCaption = referencePreviewModal?.querySelector("[data-reference-preview-caption]");
let referenceMaterials = [];
```

Keep `referenceImages` and `referencePreview` as the hidden file input and list container.

- [ ] **Step 2: Add material model helpers**

Add:

```javascript
function isImageFile(file) {
  return /^image\/(png|jpe?g|webp)$/i.test(file?.type || "");
}

function rebuildReferenceFileInput() {
  if (!referenceImages) return;
  const transfer = new DataTransfer();
  referenceMaterials
    .filter((item) => item.kind === "file" && item.file)
    .forEach((item) => transfer.items.add(item.file));
  referenceImages.files = transfer.files;
  if (referencePathsInput) {
    referencePathsInput.value = referenceMaterials
      .filter((item) => item.kind === "path" && item.path)
      .map((item) => item.path)
      .join(",");
  }
}

function addReferenceFiles(files) {
  const images = Array.from(files || []).filter(isImageFile);
  if (!images.length) return false;
  const maxRef = 16;
  images.forEach((file) => {
    if (referenceMaterials.length >= maxRef) return;
    referenceMaterials.push({
      id: `file-${crypto.randomUUID ? crypto.randomUUID() : Date.now()}-${referenceMaterials.length}`,
      kind: "file",
      file,
      src: URL.createObjectURL(file),
      name: file.name || "参考素材",
    });
  });
  renderReferenceMaterials();
  refreshEstimateOnBlur();
  return true;
}

function addReferencePath(path, name = "已生成图片") {
  if (!path || referenceMaterials.some((item) => item.path === path)) return false;
  if (referenceMaterials.length >= 16) {
    setStatus("参考素材已达到上限。", true);
    return false;
  }
  referenceMaterials.push({
    id: `path-${referenceMaterials.length}-${Date.now()}`,
    kind: "path",
    path,
    src: path,
    name,
  });
  renderReferenceMaterials();
  refreshEstimateOnBlur();
  return true;
}
```

- [ ] **Step 3: Render stack and preview**

Add:

```javascript
function renderReferenceMaterials() {
  if (!referencePreview || !referenceStack) return;
  referencePreview.innerHTML = "";
  referenceStack.classList.toggle("is-empty", referenceMaterials.length === 0);
  referenceStack.classList.toggle("has-materials", referenceMaterials.length > 0);
  referenceMaterials.forEach((item, index) => {
    const tile = document.createElement("button");
    tile.type = "button";
    tile.className = "reference-material-tile";
    tile.dataset.referenceId = item.id;
    tile.style.setProperty("--stack-index", String(index));
    tile.setAttribute("aria-label", `查看素材 ${item.name}`);
    tile.innerHTML = `
      <img alt="">
      <span class="reference-remove" data-reference-remove aria-label="删除素材">×</span>
    `;
    const image = tile.querySelector("img");
    image.src = item.src;
    image.alt = item.name;
    tile.addEventListener("click", (event) => {
      if (event.target.closest("[data-reference-remove]")) {
        removeReferenceMaterial(item.id);
        return;
      }
      openReferencePreview(item);
    });
    referencePreview.appendChild(tile);
  });
  rebuildReferenceFileInput();
  syncReferenceField();
}

function removeReferenceMaterial(id) {
  const removed = referenceMaterials.find((item) => item.id === id);
  referenceMaterials = referenceMaterials.filter((item) => item.id !== id);
  if (removed?.kind === "file" && removed.src) URL.revokeObjectURL(removed.src);
  renderReferenceMaterials();
  refreshEstimateOnBlur();
}

function openReferencePreview(item) {
  if (!referencePreviewModal || !referencePreviewImage) return;
  referencePreviewImage.src = item.src;
  referencePreviewImage.alt = item.name;
  if (referencePreviewCaption) referencePreviewCaption.textContent = item.name;
  if (referencePreviewModal.showModal) referencePreviewModal.showModal();
  else window.open(item.src, "_blank", "noopener");
}

function closeReferencePreview() {
  referencePreviewModal?.close();
  if (referencePreviewImage) referencePreviewImage.src = "";
  if (referencePreviewCaption) referencePreviewCaption.textContent = "";
}
```

- [ ] **Step 4: Replace old reference functions**

Change `syncReferenceField` to derive from `referenceMaterials.length` instead of `referenceImages.files.length`:

```javascript
const hasReference = referenceMaterials.length > 0;
modeInput.value = hasReference ? "reference" : "text";
form?.classList.toggle("has-reference", hasReference);
```

Remove references to `referenceField`, `referenceClearButton`, and old clear button behavior.

Replace `renderReferencePreview`, `setReferenceFiles`, and `clearReferenceImages` with wrappers:

```javascript
function renderReferencePreview() {
  addReferenceFiles(referenceImages?.files || []);
}

function setReferenceFiles(files) {
  return addReferenceFiles(files);
}

function clearReferenceImages() {
  referenceMaterials.forEach((item) => {
    if (item.kind === "file" && item.src) URL.revokeObjectURL(item.src);
  });
  referenceMaterials = [];
  renderReferenceMaterials();
  refreshEstimateOnBlur();
}
```

- [ ] **Step 5: Submit payload with materials**

In `submitGeneration`, before creating `formData`, call:

```javascript
rebuildReferenceFileInput();
```

After `const formData = new FormData(form);`, force reference paths into payload:

```javascript
formData.delete("reference_paths");
referenceMaterials
  .filter((item) => item.kind === "path" && item.path)
  .forEach((item) => formData.append("reference_paths", item.path));
```

Set mode from `referenceMaterials.length`:

```javascript
if (modeInput) modeInput.value = referenceMaterials.length ? "reference" : "text";
formData.set("mode", modeInput?.value || "text");
```

After successful generation and reset, call `clearReferenceImages()` instead of only clearing preview HTML.

- [ ] **Step 6: Existing generated images become draggable**

In `_buildImageGrid`, add draggable attributes to the `img` or wrapper:

```javascript
<img ${index === 0 ? 'id="current-image"' : ""} src="${imagePath}" alt="" loading="lazy" draggable="true" data-reference-path="${imagePath}">
```

For server-rendered images, add the same attributes in `templates/workspace.html`:

```html
<img ... draggable="true" data-reference-path="{{ image_path }}">
```

- [ ] **Step 7: Bind workspace-wide drag/drop**

Replace `bindReferenceDrop` with:

```javascript
function bindReferenceDrop() {
  if (!studioShell) return;
  const stopDrag = (event) => {
    event.preventDefault();
    event.stopPropagation();
  };
  document.addEventListener("dragstart", (event) => {
    const image = event.target.closest("[data-reference-path]");
    if (!image) return;
    event.dataTransfer?.setData("text/huishi-reference-path", image.dataset.referencePath || image.src || "");
    event.dataTransfer?.setData("text/plain", image.dataset.referencePath || image.src || "");
  });
  ["dragenter", "dragover"].forEach((eventName) => {
    studioShell.addEventListener(eventName, (event) => {
      stopDrag(event);
      studioShell.classList.add("is-dragging-reference");
    });
  });
  ["dragleave", "drop"].forEach((eventName) => {
    studioShell.addEventListener(eventName, (event) => {
      stopDrag(event);
      if (eventName === "drop") return;
      studioShell.classList.remove("is-dragging-reference");
    });
  });
  studioShell.addEventListener("drop", (event) => {
    stopDrag(event);
    studioShell.classList.remove("is-dragging-reference");
    const existingPath = event.dataTransfer?.getData("text/huishi-reference-path") || "";
    if (existingPath && addReferencePath(existingPath)) {
      setStatus("");
      return;
    }
    if (!setReferenceFiles(event.dataTransfer?.files)) {
      setStatus("请拖入 PNG、JPG 或 WEBP 图片。", true);
    } else {
      setStatus("");
    }
  });
}
```

- [ ] **Step 8: Blur-only estimate refresh for dimensions**

Add:

```javascript
function refreshEstimateOnBlur() {
  refreshEstimate();
}
```

Change custom dimension listeners from `"input"` to `"blur"` for `refreshEstimate`, while still using input to mark custom ratio:

```javascript
if (customWidthInput) {
  customWidthInput.addEventListener("input", applyCustomDimensions);
  customWidthInput.addEventListener("blur", refreshEstimateOnBlur);
}
if (customHeightInput) {
  customHeightInput.addEventListener("input", applyCustomDimensions);
  customHeightInput.addEventListener("blur", refreshEstimateOnBlur);
}
```

Inside `applyCustomDimensions`, remove direct `refreshEstimate()` calls.

- [ ] **Step 9: Bind add and preview close buttons**

During initialization:

```javascript
referenceAddButton?.addEventListener("click", () => referenceImages?.click());
document.querySelector("[data-close-reference-preview]")?.addEventListener("click", closeReferencePreview);
referencePreviewModal?.addEventListener("click", (event) => {
  if (event.target === referencePreviewModal) closeReferencePreview();
});
```

- [ ] **Step 10: Run syntax/build smoke**

Run:

```powershell
npm run build
```

Expected: TypeScript/Vite build passes. This JS is plain static JS, so also load `/workspace` in browser verification in Task 10.

- [ ] **Step 11: Commit**

If Git is initialized later:

```bash
git add static/js/workspace.js templates/workspace.html
git commit -m "feat: manage workspace reference material stack"
```

## Task 6: Material Stack CSS

**Files:**
- Modify: `static/css/site.css`

- [ ] **Step 1: Add stack styles**

Append or integrate near composer styles:

```css
.reference-input[hidden] {
  display: none;
}

.reference-material-stack {
  position: relative;
  width: 72px;
  min-width: 72px;
  height: 88px;
  display: flex;
  align-items: flex-start;
  isolation: isolate;
}

.reference-add-card,
.reference-material-tile {
  width: 56px;
  height: 72px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.72);
  box-shadow: 0 10px 26px rgba(15, 23, 42, 0.12);
}

.reference-add-card {
  font-size: 30px;
  color: #6b7280;
  transform: rotate(-8deg);
  cursor: pointer;
}

.reference-material-list {
  position: absolute;
  inset: 0 auto auto 0;
  display: flex;
  align-items: flex-start;
}

.reference-material-tile {
  position: absolute;
  left: calc(var(--stack-index) * 7px);
  top: calc(var(--stack-index) * 3px);
  padding: 0;
  overflow: hidden;
  transform: rotate(calc((var(--stack-index) - 1) * -5deg));
  cursor: zoom-in;
  transition: left 160ms ease, transform 160ms ease;
}

.reference-material-tile img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.reference-material-stack.has-materials .reference-add-card {
  position: absolute;
  left: 40px;
  top: 48px;
  z-index: 20;
  width: 34px;
  height: 34px;
  border-radius: 999px;
  font-size: 22px;
  transform: none;
}

.reference-material-stack:hover,
.reference-material-stack.is-expanded {
  width: min(280px, 42vw);
}

.reference-material-stack:hover .reference-material-tile,
.reference-material-stack.is-expanded .reference-material-tile {
  position: relative;
  left: auto;
  top: auto;
  margin-right: 8px;
  transform: none;
}

.reference-remove {
  position: absolute;
  right: 4px;
  top: 4px;
  width: 20px;
  height: 20px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.82);
  color: white;
  font-size: 14px;
  line-height: 20px;
  opacity: 0;
}

.reference-material-stack:hover .reference-remove,
.reference-material-stack.is-expanded .reference-remove {
  opacity: 1;
}

.studio-shell.is-dragging-reference::after {
  content: "松手添加为参考素材";
  position: fixed;
  inset: 18px;
  z-index: 1000;
  display: grid;
  place-items: center;
  border: 2px dashed rgba(14, 165, 233, 0.75);
  border-radius: 20px;
  background: rgba(248, 250, 252, 0.72);
  color: #0f172a;
  font-weight: 700;
  pointer-events: none;
}
```

- [ ] **Step 2: Mobile expansion style**

Add:

```css
@media (max-width: 720px) {
  .reference-material-stack:hover {
    width: 72px;
  }

  .reference-material-stack.is-expanded {
    width: min(260px, 64vw);
  }
}
```

- [ ] **Step 3: Run build**

Run:

```powershell
npm run build
```

Expected: build passes and CSS is bundled.

- [ ] **Step 4: Commit**

If Git is initialized later:

```bash
git add static/css/site.css
git commit -m "style: add reference material stack states"
```

## Task 7: Homepage Login Baseline

**Files:**
- Modify: `src/App.tsx`
- Modify: `src/App.test.tsx`

- [ ] **Step 1: Replace old homepage tests**

Rewrite `src/App.test.tsx` tests to assert the new baseline:

```tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import App from "./App";

function mockSession(payload: object) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => payload,
    }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("landing page", () => {
  it("keeps the current homepage content and primary links", () => {
    mockSession({ authenticated: false });
    render(<App />);

    expect(screen.getByRole("heading", { name: "AI 图像生成" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /充值/ })).toHaveAttribute("href", "/pricing");
    expect(screen.queryByRole("link", { name: "资产" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "管理后台" })).not.toBeInTheDocument();
  });

  it("opens auth modal from start button when signed out", () => {
    mockSession({ authenticated: false });
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: /开始创作/ }));

    expect(screen.getByRole("dialog", { name: "登录绘世" })).toBeInTheDocument();
    expect(screen.getByRole("form", { name: "登录绘世" })).toHaveAttribute("action", "/login?next=/");
  });

  it("keeps registered users on the homepage after auth form submission target", () => {
    mockSession({ authenticated: false });
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: /开始创作/ }));
    fireEvent.click(screen.getByRole("button", { name: "注册账号" }));

    expect(screen.getByRole("form", { name: "注册绘世" })).toHaveAttribute("action", "/register?next=/");
  });

  it("sends authenticated users to workspace only when they click start", async () => {
    mockSession({ authenticated: true, user: { username: "admin", role: "admin", points: 1000 } });
    render(<App />);

    await waitFor(() => expect(screen.getByText("admin")).toBeInTheDocument());
    expect(screen.getByRole("link", { name: /开始创作/ })).toHaveAttribute("href", "/workspace");
  });
});
```

Use the real Chinese text from `src/App.tsx` after encoding is cleaned up; if file text is currently mojibake but renders correctly through Vite, update both implementation and tests to valid UTF-8 Chinese in the same task.

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
npm test -- --run src/App.test.tsx
```

Expected: fails because current `开始创作` is a link for signed-out users and auth form target is `/workspace`.

- [ ] **Step 3: Update `Hero` to branch on session**

Change `Hero` signature:

```tsx
function Hero({ session, onAuthOpen }: { session: SessionState; onAuthOpen: (mode: "login" | "register") => void }) {
```

In `App`, call:

```tsx
<Hero session={session} onAuthOpen={setAuthMode} />
```

Inside `Hero`, replace the primary link with:

```tsx
{session.authenticated ? (
  <a className="primary-button" href="/workspace">
    开始创作
    <ArrowRight size={18} />
  </a>
) : (
  <button className="primary-button" type="button" onClick={() => onAuthOpen("login")}>
    开始创作
    <ArrowRight size={18} />
  </button>
)}
```

Keep the recharge link unchanged.

- [ ] **Step 4: Update auth form targets and button text**

In `AuthModal`, change form action and fallback links to use `next=/`:

```tsx
action={`${isLogin ? "/login" : "/register"}?next=/`}
```

and:

```tsx
href={isLogin ? "/login?next=/" : "/register?next=/"}
```

Change submit text to avoid promising auto workspace entry:

```tsx
<button type="submit">{isLogin ? "登录" : "注册账号"}</button>
```

If keeping current visual text exactly is required, only change action targets; tests should not assert submit text.

- [ ] **Step 5: Run homepage tests**

Run:

```powershell
npm test -- --run src/App.test.tsx
```

Expected: pass.

- [ ] **Step 6: Commit**

If Git is initialized later:

```bash
git add src/App.tsx src/App.test.tsx
git commit -m "fix: keep users on homepage after login"
```

## Task 8: Estimate and Generate Backend Validation

**Files:**
- Modify: `huishi/routes_workspace.py`
- Test: `tests/test_auth_records.py`

- [ ] **Step 1: Add estimate test for longest-edge custom size**

Append:

```python
def test_estimate_uses_custom_width_height_longest_edge(client):
    client.post("/register", data={"username": "estimate-size-user", "password": "secret123"}, follow_redirects=True)

    response = client.get("/api/estimate?width=2048&height=2048&count=2")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["cost"] == 4
```

- [ ] **Step 2: Add generate rejects over-4k test**

Append:

```python
def test_generate_rejects_size_above_4k(client):
    client.post("/register", data={"username": "oversize-user", "password": "secret123"}, follow_redirects=True)

    response = client.post(
        "/generate",
        data={"prompt": "too large", "width": "5000", "height": "3000", "count": "1"},
        headers={"X-Requested-With": "fetch"},
    )

    assert response.status_code == 400
    assert "分辨率" in response.get_json()["error"]
```

- [ ] **Step 3: Run tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_auth_records.py::test_estimate_uses_custom_width_height_longest_edge tests/test_auth_records.py::test_generate_rejects_size_above_4k -q --basetemp=.pytest-tmp-plan-estimate
```

Expected: estimate may pass after Task 1; generate should fail until route uses billing helper to reject over-4k before API call.

- [ ] **Step 4: Simplify `_resolution_for_billing`**

In `huishi/routes_workspace.py`, import:

```python
from huishi.billing import adjust_points, calculate_cost, require_balance, tier_for_size
```

Update `_resolution_for_billing` to:

```python
def _resolution_for_billing(resolution: str) -> str:
    return tier_for_size(resolution)
```

In `/generate`, after forming `resolution`, call:

```python
try:
    billing_resolution = _resolution_for_billing(resolution)
except ValueError as exc:
    return generation_error(str(exc), 400)
```

Do the same in `/api/estimate` and `/assets/<id>/regenerate`.

- [ ] **Step 5: Keep custom sizes supported but bounded**

Do not rely on `supports_size(ratio, resolution)` for `WxH` strings because it currently returns true for all custom sizes. The billing tier check is the 4K bound for this task.

- [ ] **Step 6: Run focused tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_auth_records.py::test_estimate_uses_custom_width_height_longest_edge tests/test_auth_records.py::test_generate_rejects_size_above_4k -q --basetemp=.pytest-tmp-plan-estimate
```

Expected: pass.

- [ ] **Step 7: Commit**

If Git is initialized later:

```bash
git add huishi/routes_workspace.py tests/test_auth_records.py
git commit -m "fix: validate custom output sizes by billing tier"
```

## Task 9: Update Legacy Tests to New Baseline

**Files:**
- Modify: `tests/test_auth_records.py`
- Modify: `tests/test_routes.py`
- Modify: `tests/test_billing.py`
- Modify: `src/App.test.tsx`

- [ ] **Step 1: Update old workspace HTML assertions**

Replace assertions expecting:

```python
'id="resolution-label">2K'
"选择分辨率"
"size-pill"
'name="resolution" id="resolution" value="2K"'
```

with assertions matching the current custom width/height and material stack:

```python
assert 'id="custom-width"' in text
assert 'id="custom-height"' in text
assert 'data-reference-stack' in text
assert 'id="reference-paths"' in text
```

- [ ] **Step 2: Update reference billing expectations**

Any test expecting reference 4K to cost 8 should expect 4. Any test expecting a reference 1K generation to leave `18` points from `20` should expect `19` if count is 1 and 1K text price is 1.

- [ ] **Step 3: Update home bundle route test**

In `tests/test_routes.py`, replace the assertion that the home bundle includes `/assets` with assertions for current homepage:

```python
assert "/workspace" in bundle_text
assert "/pricing" in bundle_text
assert "/admin/" not in bundle_text
```

Do not require `/assets`.

- [ ] **Step 4: Run Python test suite**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest-tmp-plan-all
```

Expected: pass or reveal implementation-specific misses to fix in the same task.

- [ ] **Step 5: Run frontend tests**

Run:

```powershell
npm test -- --run
```

Expected: pass.

- [ ] **Step 6: Commit**

If Git is initialized later:

```bash
git add tests src/App.test.tsx
git commit -m "test: align suite with current product baseline"
```

## Task 10: Browser Verification

**Files:**
- No source files unless verification reveals bugs.

- [ ] **Step 1: Start or reuse Flask server**

If port 8000 is already running, use it. Otherwise run:

```powershell
.\.venv\Scripts\python.exe app.py
```

Expected: app serves `http://127.0.0.1:8000`.

- [ ] **Step 2: Verify homepage login flow**

Open `http://127.0.0.1:8000/`.

Check:

- Logged-out `开始创作` opens auth modal.
- Login/register target returns to `/`.
- After login, homepage shows username.
- Clicking `开始创作` while logged in opens `/workspace`.
- `充值` still opens `/pricing`.
- No `资产` or admin entry appears on homepage.

- [ ] **Step 3: Verify workspace material stack**

Open `/workspace`.

Check:

- Input area has plus material card at the left.
- Clicking plus opens file chooser.
- Dragging a local image onto the workspace adds a stacked thumbnail.
- Multiple thumbnails stack.
- Hover expands on desktop.
- Clicking a thumbnail opens preview.
- Deleting a thumbnail removes it.
- Dragging a generated image back onto the workspace adds it as a reference material.

- [ ] **Step 4: Verify point display**

Check:

- Composer shows `X 点`, without `预计消耗`.
- Changing width/height does not update while typing.
- Blurring width/height updates point count.
- Insufficient points disables generate and shows `积分不足`.

- [ ] **Step 5: Capture issues**

If UI is visually broken, fix CSS/JS in place and rerun:

```powershell
npm run build
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest-tmp-plan-final
npm test -- --run
```

Expected: all pass before completion.

## Self-Review

- Spec coverage: homepage login baseline is covered in Task 7 and Task 10; material stack is covered in Tasks 4-6 and Task 10; reference saving and reuse is covered in Tasks 2-3; longest-edge same-price billing is covered in Tasks 1 and 8; test alignment is covered in Task 9.
- Placeholder scan: no task contains TBD/TODO/implement later placeholders. Each code change has concrete snippets or exact behavior.
- Type consistency: `reference_paths`, `referenceMaterials`, `tier_for_size`, and `hidden` are named consistently across tasks.

