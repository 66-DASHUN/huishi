from pathlib import Path


def test_asset_detail_buttons_have_hover_and_focus_highlight():
    css = Path("static/css/site.css").read_text(encoding="utf-8")

    assert ".detail-panel button:hover," in css
    assert ".detail-panel button:focus-visible," in css
    assert "transform: translateY(-1px);" in css
    assert "box-shadow: 0 0 0 3px rgba(0, 169, 199, .24), 0 10px 26px rgba(47, 68, 42, .12);" in css
    assert ".detail-panel .danger-button:hover," in css
    assert ".detail-panel .favorite-button.is-favorite:hover," in css
