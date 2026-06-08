from pathlib import Path

from app import should_enable_debug


def test_readme_contains_readable_launch_and_deploy_guidance():
    text = Path("README.md").read_text(encoding="utf-8")

    assert "绘世" in text
    assert "本地启动" in text
    assert "上线部署" in text
    assert "HUISHI_SECRET_KEY" in text
    assert "API_KEY" in text
    assert "缁" not in text
    assert "鐢" not in text


def test_debug_is_disabled_by_default_for_direct_run(monkeypatch):
    monkeypatch.delenv("FLASK_DEBUG", raising=False)

    assert should_enable_debug() is False


def test_debug_can_be_enabled_explicitly(monkeypatch):
    monkeypatch.setenv("FLASK_DEBUG", "1")

    assert should_enable_debug() is True
