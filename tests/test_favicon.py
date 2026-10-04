from pathlib import Path


def test_base_template_includes_favicon():
    template = Path("templates/base.html").read_text(encoding="utf-8")

    assert 'rel="icon"' in template
    assert "favicon.svg" in template


def test_favicon_asset_exists():
    assert Path("static/favicon.svg").exists()


def test_favicon_uses_light_transparent_background():
    favicon = Path("static/favicon.svg").read_text(encoding="utf-8")

    assert 'fill="#050606"' not in favicon
    assert "<rect" not in favicon
    assert ">绘</text>" in favicon
