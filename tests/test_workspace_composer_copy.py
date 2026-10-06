from pathlib import Path


def test_workspace_composer_copy_and_empty_prompt_state():
    template = Path("templates/workspace.html").read_text(encoding="utf-8")
    source = Path("static/js/workspace.js").read_text(encoding="utf-8")

    assert 'data-reference-add' in template
    assert '参考内容' in template
    assert '添加素材' in template
    assert 'data-max-reference-images=' in template
    assert 'accept="image/png,image/jpeg,image/jpg,image/webp,.jpg,.jpeg,.png,.webp"' in template
    assert 'placeholder="上传最多{{ config.get(\'MAX_REFERENCE_IMAGES\', 16) }}个参考素材，输入文字或参考内容，定义精彩互动。"' in template
    assert '<span class="reference-add-mark" aria-hidden="true">+</span>' in template
    assert 'setAttribute("placeholder", "请输入提示词")' in source
    assert 'function updateComposerPromptState()' in source
    assert 'composerPrompt.classList.add("is-error")' in source
    assert 'composerPrompt.value.trim()' in source
    assert 'showPromptError()' in source
    assert "PNG、JPG、JPEG、WEBP" in source


def test_reference_material_add_card_keeps_empty_and_uploaded_states_separate():
    css = Path("static/css/site.css").read_text(encoding="utf-8")

    assert ".reference-material-stack.is-empty" in css
    assert ".reference-material-stack.is-empty .reference-add-card" in css
    assert "grid-template-columns: 1fr;" in css
    assert "justify-items: center;" in css
    assert "text-align: center;" in css
    assert "grid-template-rows: 20px minmax(0, 1fr);" in css
    assert "width: 76px;" in css
    assert "height: 78px;" in css
    assert "width: 64px;" in css
    assert "height: 70px;" in css
    assert ".reference-material-tile {" in css
    assert "width: 36px;" in css
    assert "min-width: 36px;" in css
    assert ".reference-material-stack.has-materials .reference-add-copy" in css
    assert "display: none;" in css
    assert ".reference-material-stack.has-materials .reference-add-card" in css
    assert "width: 22px;" in css
    assert ".reference-remove {" in css
    assert "inline-size: 18px;" in css
    assert "block-size: 18px;" in css
    assert "min-width: 18px;" in css
    assert "min-height: 18px;" in css
    assert "max-width: 18px;" in css
    assert "max-height: 18px;" in css
    assert "aspect-ratio: 1;" in css
    assert "border-radius: 50%;" in css
    assert "top: -7px;" in css
    assert "right: -7px;" in css
    assert "background: rgba(255, 255, 255, .98);" in css
    assert "color: #1f2a1d;" in css
    assert ".reference-remove:hover" in css
    assert "scale(1.24)" in css
    assert "overflow: visible;" in css


def test_reference_material_tiles_keep_unique_stack_positions_past_five_items():
    source = Path("static/js/workspace.js").read_text(encoding="utf-8")
    css = Path("static/css/site.css").read_text(encoding="utf-8")

    # 渲染用的是"可见素材"列表的本地别名 materials（referenceMaterials 全量，
    # 视频模式会过滤），因此断言渲染循环按顺序写入 --stack-index。
    assert "materials.forEach((item, index) =>" in source
    assert 'tile.style.setProperty("--stack-index", String(index));' in source
    assert 'referenceStack?.style.setProperty("--reference-count", String(materials.length || 1));' in source
    assert 'referenceStack?.style.setProperty("--reference-expanded-width"' in source
    assert ".reference-material-tile:nth-child(n+5)" not in css
    assert "min(var(--reference-expanded-width, 118px), 72vw)" in css


def test_reference_material_over_limit_reports_error_instead_of_silent_truncation():
    source = Path("static/js/workspace.js").read_text(encoding="utf-8")

    overflow_guard = source.index("if (incoming.length > available)")
    slice_call = source.index("incoming.slice(0, available).forEach")
    assert overflow_guard < slice_call
    # 文案统一为"参考素材…项"（视频/图片共用同一上限语义）。
    assert "setStatus(`参考素材最多支持 ${maxReferenceImages} 项`, true);" in source
    assert "return false;" in source[overflow_guard:slice_call]


def test_reference_material_stack_reserves_prompt_space_when_collapsed():
    source = Path("static/js/workspace.js").read_text(encoding="utf-8")
    css = Path("static/css/site.css").read_text(encoding="utf-8")

    assert 'form?.style.setProperty("--reference-collapsed-space"' in source
    assert ".composer.has-reference .composer-prompt {" in css
    assert "padding-left: min(var(--reference-collapsed-space, 76px), 150px);" in css


def test_removing_path_reference_syncs_hidden_reference_paths():
    source = Path("static/js/workspace.js").read_text(encoding="utf-8")

    remove_start = source.index("function removeReferenceMaterial(id)")
    remove_end = source.index("function openReferencePreview(item)", remove_start)
    remove_snippet = source[remove_start:remove_end]

    assert "syncReferenceFieldSource();" in remove_snippet
    assert "function syncReferenceFieldSource()" in source
    assert "referencePathsInput.value = getReferencePathMaterials().map" in source


def test_failed_task_panel_centers_error_content():
    css = Path("static/css/site.css").read_text(encoding="utf-8")

    failed_card_start = css.index(".generation-task-card.is-failed {")
    failed_card_end = css.index(".generation-task-card.is-failed .generation-task-prompt", failed_card_start)
    failed_card_css = css[failed_card_start:failed_card_end]
    assert "justify-self: center;" in failed_card_css
    assert ".task-failure-panel {" in css
    failure_panel_start = css.index(".task-failure-panel {")
    failure_panel_end = css.index(".task-failure-panel[hidden]", failure_panel_start)
    failure_panel_css = css[failure_panel_start:failure_panel_end]
    assert "width: min(100%, 680px);" in failure_panel_css
    assert "margin: 0 auto;" in failure_panel_css
    assert "justify-items: center;" in css
    assert "text-align: center;" in css
    assert ".task-failure-detail {" in css
    assert "grid-template-columns: auto minmax(0, auto);" in css
    assert "justify-content: center;" in css
    assert ".task-actions {" in css
    assert "justify-content: center;" in css

def test_mobile_workspace_keeps_latest_result_visible_below_top_nav():
    source = Path("static/js/workspace.js").read_text(encoding="utf-8")
    css = Path("static/css/site.css").read_text(encoding="utf-8")

    assert "function isCompactWorkspaceViewport()" in source
    assert 'document.querySelector(".studio-rail")' in source
    assert 'document.querySelector(".output-composer")' in source
    assert "Math.max(84, railHeight + 10)" in source
    assert "const availableHeight = Math.max(0, composerTop - offset - 12);" in source
    assert "const centeredTop = availableHeight > elementRect.height" in source
    assert "window.scrollTo({ top: targetTop, behavior });" in source
    assert ".workspace-page .creation-item.is-featured" in css
    assert "scroll-margin-top: 88px;" in css


def test_mobile_collapsed_composer_uses_short_placeholder():
    source = Path("static/js/workspace.js").read_text(encoding="utf-8")
    css = Path("static/css/site.css").read_text(encoding="utf-8")

    assert "function syncComposerPlaceholderForState()" in source
    assert 'const compactPlaceholder = "输入提示词，继续生成";' in source
    assert 'form.classList.contains("is-collapsed") && isCompactWorkspaceViewport()' in source
    assert 'window.addEventListener("resize", syncComposerPlaceholderForState' in source
    assert ".workspace-page .output-composer.is-collapsed .composer-prompt" in css
    assert "text-overflow: ellipsis;" in css
    assert "white-space: nowrap;" in css

def test_workspace_submit_generation_locks_before_fetching():
    source = Path("static/js/workspace.js").read_text(encoding="utf-8")

    start = source.index("async function submitGeneration")
    fetch_call = source.index("const response = await fetch(form.action", start)
    submit_prelude = source[start:fetch_call]

    assert 'form.classList.add("is-submitting")' in submit_prelude
    assert 'submitButton.disabled = true' in submit_prelude


def test_workspace_consumes_home_prompt_draft_once():
    source = Path("static/js/workspace.js").read_text(encoding="utf-8")

    assert 'const HOME_PROMPT_DRAFT_KEY = "huishi.home.promptDraft"' in source
    assert "sessionStorage.getItem(HOME_PROMPT_DRAFT_KEY)" in source
    assert "sessionStorage.removeItem(HOME_PROMPT_DRAFT_KEY)" in source
    assert 'composerPrompt.dispatchEvent(new Event("input", { bubbles: true }))' in source
