from __future__ import annotations

from pathlib import Path

from app import create_app
from huishi.db import init_db


def test_homepage_has_meta_description(tmp_path: Path):
    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "test.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"
    with app.app_context():
        init_db()

    with app.test_client() as client:
        response = client.get("/")

    assert response.status_code == 200
    assert b'<meta name="description"' in response.data
    assert "AI".encode() in response.data


def test_home_script_does_not_suppress_console_errors():
    source = Path("static/js/home.js").read_text(encoding="utf-8")

    assert "console.error =" not in source


def test_homepage_uses_precompiled_script_instead_of_browser_babel(tmp_path: Path):
    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "test.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"
    with app.app_context():
        init_db()

    with app.test_client() as client:
        response = client.get("/")

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "@babel/standalone" not in html
    assert 'type="text/babel"' not in html
    assert "cdn.tailwindcss.com" not in html
    assert "css/home-tailwind.css" in html
    assert "js/home.compiled.js" in html


def test_home_videos_use_poster_and_deferred_loading():
    source = Path("static/js/home.js").read_text(encoding="utf-8")

    assert "shouyeshipin-sea.mp4" in source
    assert 'HERO_VIDEO = "/static/media/shouyeshipin.mp4"' not in source
    assert "shouyeshipin-poster.jpg" in source
    assert 'preload="auto"' not in source
    assert "loadDelayMs" in source
    assert "loadWhenVisible" in source
    assert 'rootMargin: "0px"' in source
    assert "threshold: 0.15" in source
    assert 'rootMargin: "160px 0px"' not in source

def test_homepage_hero_title_renders_as_h1():
    source = Path("static/js/home.js").read_text(encoding="utf-8")

    assert 'function BlurText({ text, className, as: Tag = "p" })' in source
    assert "<Tag ref={ref}" in source
    assert '<BlurText text="绘梦造世" as="h1"' in source
