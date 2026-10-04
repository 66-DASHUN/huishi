from pathlib import Path


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_base_exposes_theme_before_styles_render():
    base = read("templates/base.html")

    assert "data-theme" in base
    assert "color-scheme" in base


def test_base_loads_only_the_shared_modern_sans_font():
    base = read("templates/base.html")

    assert "Noto+Sans+SC" in base
    for legacy_font in ("Instrument+Serif", "Barlow", "Inter"):
        assert legacy_font not in base


def test_theme_script_supports_light_and_dark_toggle():
    source = read("static/js/theme.js")
    options = read("templates/partials/theme_options.html")

    assert 'const THEME_VALUES = new Set(["light", "dark"]);' in source
    assert 'data-theme-toggle' in options
    assert 'class="theme-menu"' not in options
    assert 'data-theme-option=' not in options


def test_theme_selector_is_a_single_light_dark_toggle():
    options = read("templates/partials/theme_options.html")
    source = read("static/js/theme.js")

    assert 'data-theme-toggle' in options
    assert 'class="theme-menu"' not in options
    assert 'data-theme-option=' not in options
    assert '<span>主题</span>' not in options
    assert 'data-theme-current' not in options
    assert 'const THEME_VALUES = new Set(["light", "dark"]);' in source
    assert 'savePreference(resolveTheme(storedPreference()) === "dark" ? "light" : "dark");' in source


def test_site_css_defines_semantic_theme_tokens():
    css = read("static/css/site.css")

    for token in ("--color-bg", "--color-surface", "--color-text", "--color-primary"):
        assert token in css
    assert ".rail-theme-toggle .theme-toggle-button" in css
    assert ".rail-theme-toggle .theme-toggle-button:focus-visible" in css


def test_semantic_console_theme_overrides_the_legacy_forced_dark_pass():
    css = read("static/css/site.css")
    selector = ':root[data-theme="light"] body.console-page'
    marker = "Final product-theme overrides: keep this block last."

    assert selector in css
    assert css.rfind(marker) > css.rfind("Claude UI design pass")
    final_theme_block = css[css.rfind(marker) :]
    assert "background: var(--color-bg) !important" in final_theme_block
    assert "color: var(--color-text) !important" in final_theme_block
    assert "color-scheme: light" in final_theme_block


def test_theme_selector_only_lives_in_workspace_settings():
    template_root = Path("templates")
    usages = []
    for path in template_root.rglob("*.html"):
        if 'include "partials/theme_options.html"' in path.read_text(encoding="utf-8"):
            usages.append(path.as_posix())

    assert usages == ["templates/partials/studio_nav.html"]


def test_theme_toggle_sits_above_settings_menu_and_panel_is_compact():
    nav = read("templates/partials/studio_nav.html")
    css = read("static/css/site.css")

    assert '<div class="rail-theme-toggle">' in nav
    assert nav.index('<div class="rail-theme-toggle">') < nav.index('<details class="rail-settings">')
    assert 'settings-menu-preference' not in nav
    assert ".rail-theme-toggle .theme-toggle-button" in css
    assert "width: 144px;" in css
    assert "min-width: 144px;" in css


def test_canvas_bridge_sends_the_host_resolved_theme_as_authoritative():
    canvas = read("templates/canvas.html")

    assert 'preference: document.documentElement.dataset.themePreference || "system"' in canvas
    assert 'resolvedTheme: document.documentElement.dataset.theme || "light"' in canvas
    assert "hostPreference" not in canvas


def test_canvas_does_not_expose_or_restore_an_independent_theme_selector():
    canvas_root = Path("infinite-canvas/web/src")
    user_actions = read(str(canvas_root / "components/layout/user-status-actions.tsx"))
    appearance = read(str(canvas_root / "app/(user)/canvas/components/canvas-appearance-panel.tsx"))
    theme_store = read(str(canvas_root / "stores/use-theme-store.ts"))
    layout = read(str(canvas_root / "app/layout.tsx"))

    assert "Segmented" not in user_actions
    assert "setPreference" not in user_actions
    assert "????" not in appearance
    assert "setTheme" not in appearance
    assert "AnimatedThemeToggler" not in appearance
    assert "persist(" not in theme_store
    assert "infinite-canvas:theme_store" not in theme_store
