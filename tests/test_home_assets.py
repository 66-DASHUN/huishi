from __future__ import annotations

from pathlib import Path
import hashlib

import pytest

from app import create_app
from huishi.db import init_db


@pytest.fixture()
def client(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("HUISHI_DATABASE", str(tmp_path / "test.sqlite3"))
    monkeypatch.setenv("HUISHI_OUTPUT_DIR", str(tmp_path / "uploads"))
    app = create_app(testing=True)
    with app.app_context():
        init_db()
    return app.test_client()


def test_home_does_not_load_global_site_css(client):
    body = client.get("/").get_data(as_text=True)

    assert "css/home-tailwind.css" in body
    assert "css/site.css" not in body


def test_home_uses_one_nonblocking_font_stylesheet():
    base = Path("templates/base.html").read_text(encoding="utf-8")
    home = Path("templates/home.html").read_text(encoding="utf-8")

    assert "{% block font_styles %}" in base
    assert "{% block font_styles %}" in home
    assert home.count("fonts.googleapis.com/css2") == 1
    assert 'media="print"' in home
    assert "onload=\"this.media='all'\"" in home


def test_home_uses_two_scoped_chinese_font_families():
    home = Path("templates/home.html").read_text(encoding="utf-8")
    styles = Path("static/css/home-tailwind.input.css").read_text(encoding="utf-8")

    assert "Noto+Sans+SC" in home
    assert "Noto+Serif+SC" in home
    assert "Instrument+Serif" not in home
    assert 'font-family: "Noto Sans SC"' in styles
    assert 'font-family: "Noto Serif SC"' in styles
    for legacy_font in ("Instrument Serif", "Songti SC", "Barlow"):
        assert legacy_font not in styles


def test_home_uses_local_sea_media_contract():
    source = Path("static/js/home.js").read_text(encoding="utf-8")

    assert 'const HERO_VIDEO = "/static/media/shouyeshipin-sea.mp4"' in source
    assert 'const HERO_POSTER = "/static/media/shouyeshipin-poster.jpg"' in source
    assert 'const CAPABILITIES_VIDEO = "/static/media/huishi-workflow-cloud.mp4"' in source
    assert 'const CAPABILITIES_POSTER = "/static/media/huishi-workflow-cloud-poster.jpg"' in source
    assert '"/static/media/huishi-workflow-poster.jpg"' not in source
    assert source.count("src={HERO_VIDEO}") == 1
    assert source.count("poster={HERO_POSTER}") == 1
    assert source.count("src={CAPABILITIES_VIDEO}") == 1
    assert source.count("poster={CAPABILITIES_POSTER}") == 1
    assert "cloudfront.net" not in source


def test_home_uses_the_requested_video_binaries():
    expected = {
        "static/media/huishi-workflow-cloud.mp4": "a4b75d294659722fcecaaacd4f7d0cebe89b79a0ff1e74b43346f3d0581f3b9e",
        "static/media/huishi-workflow-cloud-poster.jpg": "0231e3214dc4ba90fd478341bc31ed7da63e8141f2aff632a286ad9101061d8d",
        "static/media/shouyeshipin-sea.mp4": "d45d3d896f740cd3455679a67597b872238f5fb36c75bc904ca24e46f50c38b4",
    }

    for path, digest in expected.items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest


def test_home_uses_cinematic_layout_without_fullscreen_luminous_overlays():
    source = Path("static/js/home.js").read_text(encoding="utf-8")
    styles = Path("static/css/home-tailwind.input.css").read_text(encoding="utf-8")

    assert 'id="hero"' in source
    assert 'id="capabilities"' in source
    assert "hero-luminous-overlay" not in source
    assert "workflow-luminous-overlay" not in source
    assert "capability-rail" in source
    assert "liquid-glass" in source
    assert "prefers-reduced-motion: reduce" in styles
    assert "--huishi-cobalt" in styles


def test_workflow_uses_its_own_background_video():
    source = Path("static/js/home.js").read_text(encoding="utf-8")
    styles = Path("static/css/home-tailwind.input.css").read_text(encoding="utf-8")

    assert 'const CAPABILITIES_VIDEO = "/static/media/huishi-workflow-cloud.mp4";' in source
    assert 'const CAPABILITIES_POSTER = "/static/media/huishi-workflow-cloud-poster.jpg";' in source
    assert '<FadingVideo src={CAPABILITIES_VIDEO} poster={CAPABILITIES_POSTER} loadWhenVisible className="home-video workflow-video" />' in source
    assert ".workflow-section {\n  min-height: 100svh;\n  background: var(--huishi-deep);" in styles


def test_home_uses_workflow_video_cache_busting_asset_version():
    home = Path("templates/home.html").read_text(encoding="utf-8")

    assert home.count("20260830-workflow-video-3") == 2


def test_home_brand_keeps_the_mark_without_the_adjacent_wordmark():
    source = Path("static/js/home.js").read_text(encoding="utf-8")

    assert '<span className="home-brand-mark">绘</span>' in source
    assert 'className="home-brand-name"' not in source


def test_home_auth_forms_expose_loading_and_error_states():
    source = Path("static/js/home.js").read_text(encoding="utf-8")

    assert source.count('aria-busy={isSubmitting ? "true" : "false"}') == 3
    assert source.count('data-auth-state={notice?.type === "error" ? "error" : isSubmitting ? "loading" : "idle"}') == 3


def test_auth_modal_traps_and_restores_keyboard_focus():
    source = Path("static/js/home.js").read_text(encoding="utf-8")

    assert "const dialogRef = useRef(null)" in source
    assert "const restoreFocusRef = useRef(document.activeElement)" in source
    assert 'event.key === "Tab"' in source
    assert "restoreFocusRef.current?.focus" in source
    assert "ref={dialogRef}" in source


def test_video_fades_over_an_independent_poster_surface():
    source = Path("static/js/home.js").read_text(encoding="utf-8")
    component = source[source.index("function FadingVideo") : source.index("function BlurText")]

    assert "fading-video-element" in source
    assert "backgroundImage: poster ?" in source
    assert "video-poster-frame" in source
    assert "requestAnimationFrame" in component
    assert "cancelAnimationFrame" in component
    assert 'video.addEventListener("timeupdate"' in component
    assert 'video.addEventListener("ended"' in component
    assert "FADE_OUT_LEAD" in component
    assert " loop" not in component


def test_hero_fills_the_first_viewport_without_a_workflow_preview_strip():
    styles = Path("static/css/home-tailwind.input.css").read_text(encoding="utf-8")

    assert "--hero-viewport: 100svh" in styles
    assert styles.count("min-height: var(--hero-viewport)") >= 2
    assert "94svh" not in styles
    assert "96svh" not in styles


def test_home_preserves_video_framing_without_a_fullscreen_shade():
    source = Path("static/js/home.js").read_text(encoding="utf-8")
    styles = Path("static/css/home-tailwind.input.css").read_text(encoding="utf-8")

    assert 'className="home-video home-hero-video"' in source
    assert 'className="home-hero-shade"' not in source
    assert "object-position: center 42%" in styles
    assert ".home-hero-shade" not in styles


def test_home_video_uses_no_css_transition_or_filter():
    styles = Path("static/css/home-tailwind.input.css").read_text(encoding="utf-8")
    video_start = styles.index(".fading-video-element {")
    video_rule = styles[video_start : styles.index("}", video_start)]

    assert "transition" not in video_rule
    assert "filter:" not in video_rule


def test_home_exposes_real_prompt_handoff_and_approved_copy():
    source = Path("static/js/home.js").read_text(encoding="utf-8")

    assert 'const HOME_PROMPT_DRAFT_KEY = "huishi.home.promptDraft"' in source
    assert "sessionStorage.setItem(HOME_PROMPT_DRAFT_KEY" in source
    assert "绘梦造世" in source
    assert "让灵感在无限画布中持续显形" in source
    assert "描述你想创造的世界" in source
    assert "从灵感的轮廓" in source
    assert "到世界的细节" in source
    assert "多图参考" in source


def test_workflow_video_covers_the_full_mobile_section():
    styles = Path("static/css/home-tailwind.input.css").read_text(encoding="utf-8")

    assert "--workflow-mobile-stage" not in styles
    assert "height: var(--workflow-mobile-stage)" not in styles
    assert styles.count(".workflow-video {\n    bottom: 0;\n    height: 100%;") >= 2
