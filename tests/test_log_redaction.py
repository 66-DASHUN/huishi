from __future__ import annotations

from pathlib import Path

import pytest

import huishi.prompt_api as prompt_api
import huishi.providers as provider_store
import huishi.routes_workspace as routes_workspace
from app import create_app


@pytest.fixture()
def app(tmp_path: Path):
    application = create_app(testing=True)
    application.config["DATABASE"] = tmp_path / "test.sqlite3"
    application.config["OUTPUT_DIR"] = tmp_path / "uploads"
    return application


def test_prompt_optimization_log_redacts_base_url(app, monkeypatch, caplog):
    base_url = "https://user:password@example.com/v1?token=url-secret"

    class FailingClient:
        class _Chat:
            class _Completions:
                def create(self, **kwargs):
                    raise RuntimeError("request failed")

            completions = _Completions()

        chat = _Chat()

    monkeypatch.setattr(prompt_api, "OpenAI", lambda **kwargs: FailingClient())
    with app.app_context(), caplog.at_level("INFO"):
        with pytest.raises(RuntimeError):
            prompt_api.optimize_prompt(
                prompt="猫",
                style="通用增强",
                api_key="api-secret",
                base_url=base_url,
                model="gpt-4.1",
            )

    assert "user:" not in caplog.text
    assert "password" not in caplog.text
    assert "token=url-secret" not in caplog.text
    assert "https://example.com/v1" in caplog.text


def test_canvas_text_chat_log_redacts_upstream_exception(app, monkeypatch, caplog):
    base_url = "https://user:password@example.com/v1?token=url-secret"
    api_key = "sk-upstream-secret-123456"
    upstream_error = (
        "upstream response leaked api_key=sk-upstream-secret-123456 "
        "Authorization: Bearer bearer-secret https://user:password@example.com/v1?token=url-secret"
    )

    class FailingCompletions:
        def create(self, **kwargs):
            from openai import OpenAIError

            raise OpenAIError(upstream_error)

    class FakeClient:
        class _Chat:
            completions = FailingCompletions()

        chat = _Chat()

    monkeypatch.setattr("openai.OpenAI", lambda **kwargs: FakeClient())
    monkeypatch.setattr(routes_workspace, "canvas_api_user", lambda: ("https://canvas.example", {"id": 1}))
    monkeypatch.setattr(
        provider_store,
        "prompt_provider_candidates",
        lambda: [{"api_key": api_key, "base_url": base_url, "model": "text-model"}],
    )

    with app.test_request_context(
        "/api/canvas/text-chat",
        method="POST",
        json={"messages": [], "stream": False},
    ), caplog.at_level("WARNING"):
        response = routes_workspace.canvas_text_chat()

    assert response.status_code == 502
    assert "Canvas text chat provider failed" in caplog.text
    assert "upstream response leaked" in caplog.text
    assert "password" not in caplog.text
    assert "user:" not in caplog.text
    assert "token=url-secret" not in caplog.text
    assert "bearer-secret" not in caplog.text
    assert api_key not in caplog.text


def test_unused_image_config_status_is_removed():
    source = Path(routes_workspace.__file__).read_text(encoding="utf-8")
    assert "def _image_config_status" not in source
