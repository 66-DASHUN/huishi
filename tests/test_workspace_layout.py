from pathlib import Path


def _desktop_workspace_composer_css() -> str:
    css = Path("static/css/site.css").read_text(encoding="utf-8")
    start = css.index(".composer-controls {")
    mobile = css.index("@media (max-width: 760px)", start)
    return css[start:mobile]


def test_workspace_composer_keeps_media_controls_on_one_compact_desktop_row():
    css = _desktop_workspace_composer_css()

    assert ".workspace-page .composer .generation-mode-picker" in css
    assert ".workspace-page .composer .generation-mode-menu" in css
    assert "bottom: calc(100% + 8px)" in css
    assert "flex-wrap: nowrap" in css
    assert ".workspace-page .composer .music-generation-options" in css
    assert "display: inline-flex" in css
    assert "white-space: nowrap" in css


def test_workspace_composer_hidden_media_controls_do_not_take_layout_space():
    css = Path("static/css/site.css").read_text(encoding="utf-8")

    assert ".workspace-page .composer .image-only-control[hidden]" in css
    assert ".workspace-page .composer .audio-generation-options[hidden]" in css
    assert ".workspace-page .composer .music-generation-options[hidden]" in css
    assert "display: none !important" in css


def test_workspace_composer_mobile_layout_can_still_wrap_controls():
    css = Path("static/css/site.css").read_text(encoding="utf-8")
    mobile_start = css.index("@media (max-width: 760px)")
    mobile_css = css[mobile_start:]

    assert ".composer-controls { display: grid;" in mobile_css
    assert ".workspace-page .composer .music-generation-options" in mobile_css
    assert "flex-wrap: wrap" in mobile_css


def test_workspace_creation_type_uses_compact_vertical_picker():
    template = Path("templates/workspace.html").read_text(encoding="utf-8")
    source = Path("static/js/workspace.js").read_text(encoding="utf-8")
    css = Path("static/css/site.css").read_text(encoding="utf-8")

    assert 'data-generation-mode-picker' in template
    assert 'data-generation-mode-trigger' in template
    assert 'data-generation-mode-menu' in template
    assert 'role="listbox"' in template
    # 生成模式菜单固定 4 项（图片/视频/音乐/语音）。页面上另有"参考类型"
    # 菜单，因此全模板的 role="option" 总数会更多——这里只约束生成模式的
    # 那个 listbox，避免把无关菜单的增删也算进来。
    mode_menu = template.split('data-generation-mode-menu', 1)[1].split("</div>", 1)[0]
    assert mode_menu.count('role="option"') == 4
    assert 'class="generation-mode-tabs"' not in template
    assert 'const generationModePicker' in source
    assert 'function syncGenerationModePicker()' in source
    assert 'aria-expanded' in source
    assert '.workspace-page .composer .generation-mode-menu' in css
    assert '.generation-mode-menu[hidden]' in css
    assert 'grid-template-columns: 1fr;' in css
