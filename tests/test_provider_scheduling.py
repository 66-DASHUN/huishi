from pathlib import Path

import httpx
import pytest
from openai import APIConnectionError

from app import create_app
from huishi import providers
from huishi.db import get_db


@pytest.fixture()
def app(tmp_path: Path):
    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "test.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"
    with app.app_context():
        from huishi.db import init_db

        init_db()
    return app


def save_image_provider(name: str, *, base_url: str, api_key: str, resolutions=None, enabled=True, priority=100):
    provider_id = providers.save_provider(
        provider_type="image",
        name=name,
        base_url=base_url,
        api_key=api_key,
        model="gpt-image-2",
        priority=priority,
        enabled=enabled,
        resolutions=resolutions or ["1K", "2K", "4K"],
    )
    get_db().commit()
    return provider_id


def test_failover_tries_all_providers_before_raising(app, monkeypatch):
    """Failover should try every candidate provider before raising the final error."""
    with app.app_context():
        providers._round_robin_offsets.clear()
        save_image_provider("first", base_url="https://first.example.com", api_key="sk-first")
        save_image_provider("second", base_url="https://second.example.com", api_key="sk-second")
        calls = []

        def fake_generate_image(**kwargs):
            calls.append(kwargs["base_url"])
            raise RuntimeError("upstream failed")

        monkeypatch.setattr(providers, "generate_image", fake_generate_image)
        monkeypatch.setattr(providers, "notify_provider_disabled", lambda provider, error: None)
        monkeypatch.setattr(providers, "disable_provider", lambda provider_id, error: None)

        with pytest.raises(RuntimeError):
            providers.generate_image_with_failover(
                prompt="test",
                mode="text",
                ratio="16:9",
                resolution="2K",
                count=1,
                quality="auto",
                output_format="png",
                reference_images=[],
            )

        # Both providers should have been tried before giving up
        assert "https://first.example.com" in calls
        assert "https://second.example.com" in calls
        assert calls.count("https://first.example.com") == 1
        assert calls.count("https://second.example.com") == 1


def test_transient_image_connection_error_retries_same_provider_once(app, monkeypatch):
    with app.app_context():
        providers._round_robin_offsets.clear()
        save_image_provider("first", base_url="https://first.example.com", api_key="sk-first")
        calls = []

        def fake_generate_image(**kwargs):
            calls.append(kwargs["base_url"])
            if len(calls) == 1:
                raise APIConnectionError(request=httpx.Request("POST", kwargs["base_url"]))
            return {"images": [], "size": "2048x1152", "model_source": kwargs["model"], "elapsed_seconds": 0.0}

        monkeypatch.setattr(providers, "generate_image", fake_generate_image)
        monkeypatch.setattr(providers.time, "sleep", lambda _seconds: None)

        result = providers.generate_image_with_failover(
            prompt="test",
            mode="text",
            ratio="16:9",
            resolution="2K",
            count=1,
            quality="auto",
            output_format="png",
            reference_images=[],
        )

        assert result["model_source"] == "gpt-image-2"
        assert calls == ["https://first.example.com", "https://first.example.com"]


def test_transient_image_connection_error_switches_after_one_retry(app, monkeypatch):
    with app.app_context():
        providers._round_robin_offsets.clear()
        save_image_provider("first", base_url="https://first.example.com", api_key="sk-first")
        save_image_provider("second", base_url="https://second.example.com", api_key="sk-second")
        calls = []

        def fake_generate_image(**kwargs):
            calls.append(kwargs["base_url"])
            if kwargs["base_url"] == "https://first.example.com":
                raise APIConnectionError(request=httpx.Request("POST", kwargs["base_url"]))
            return {"images": [], "size": "2048x1152", "model_source": kwargs["model"], "elapsed_seconds": 0.0}

        monkeypatch.setattr(providers, "generate_image", fake_generate_image)
        monkeypatch.setattr(providers.time, "sleep", lambda _seconds: None)

        providers.generate_image_with_failover(
            prompt="test",
            mode="text",
            ratio="16:9",
            resolution="2K",
            count=1,
            quality="auto",
            output_format="png",
            reference_images=[],
        )

        assert calls == [
            "https://first.example.com",
            "https://first.example.com",
            "https://second.example.com",
        ]


def test_successful_provider_does_not_call_next(app, monkeypatch):
    """当第一个 provider 成功时，不应调用后续 provider。"""
    with app.app_context():
        providers._round_robin_offsets.clear()
        save_image_provider("first", base_url="https://first.example.com", api_key="sk-first")
        save_image_provider("second", base_url="https://second.example.com", api_key="sk-second")

        calls: list[str] = []

        def fake_generate_success(prompt, *, base_url, api_key, **kwargs):
            calls.append(base_url)
            return {
                "image_path": "/static/uploads/ok.png",
                "image_paths": ["/static/uploads/ok.png"],
                "actual_size": "1024x1024",
                "model_source": "test",
                "elapsed_seconds": 0.1,
            }

        monkeypatch.setattr(providers, "generate_image", fake_generate_success)
        monkeypatch.setattr(providers, "notify_provider_disabled", lambda provider, error: None)
        monkeypatch.setattr(providers, "disable_provider", lambda provider_id, error: None)

        providers.generate_image_with_failover(
            prompt="test",
            mode="text",
            ratio="1:1",
            resolution="1024x1024",
            count=1,
            quality="auto",
            output_format="png",
            reference_images=[],
        )

        # 第一个 provider 成功后不应调用第二个
        assert calls == ["https://first.example.com"]


def test_selected_grok_failure_never_calls_banana_provider(app, monkeypatch):
    with app.app_context():
        providers._round_robin_offsets.clear()
        providers.save_provider(
            provider_type="image", name="grok", base_url="https://grok.example.com", api_key="test-grok-key",
            model="grok-imagine-image-2.0", api_format="grok", priority=10, enabled=True, resolutions=["1K", "2K"],
        )
        providers.save_provider(
            provider_type="image", name="banana", base_url="https://banana.example.com", api_key="test-banana-key",
            model="gemini-3.1-flash-image", api_format="banana", priority=10, enabled=True, resolutions=["1K", "2K", "4K"],
        )
        get_db().commit()
        calls = []

        def fail_grok(**kwargs):
            calls.append(kwargs["model"])
            raise RuntimeError("grok failed")

        monkeypatch.setattr(providers, "generate_image", fail_grok)

        with pytest.raises(RuntimeError, match="grok failed"):
            providers.generate_image_with_failover(
                prompt="test", mode="text", ratio="1:1", resolution="2K", count=1,
                quality="auto", output_format="png", reference_images=[], model="grok-imagine-image-2.0",
            )

        assert calls == ["grok-imagine-image-2.0"]


def test_selected_model_fails_over_to_second_provider_of_same_model(app, monkeypatch):
    with app.app_context():
        providers._round_robin_offsets.clear()
        providers.save_provider(
            provider_type="image", name="grok-primary", base_url="https://grok-primary.example.com", api_key="test-grok-primary-key",
            model="grok-imagine-image-2.0", api_format="grok", priority=10, enabled=True, resolutions=["1K", "2K"],
        )
        providers.save_provider(
            provider_type="image", name="grok-secondary", base_url="https://grok-secondary.example.com", api_key="test-grok-secondary-key",
            model="grok-imagine-image-2.0", api_format="grok", priority=10, enabled=True, resolutions=["1K", "2K"],
        )
        get_db().commit()
        calls = []

        def fail_primary_then_succeed(**kwargs):
            calls.append(kwargs["base_url"])
            if kwargs["base_url"].endswith("primary.example.com"):
                raise RuntimeError("primary failed")
            return {"image_path": "/static/uploads/ok.png", "image_paths": ["/static/uploads/ok.png"], "actual_size": "2048x2048", "model_source": kwargs["model"], "elapsed_seconds": 0.0}

        monkeypatch.setattr(providers, "generate_image", fail_primary_then_succeed)

        result = providers.generate_image_with_failover(
            prompt="test", mode="text", ratio="1:1", resolution="2K", count=1,
            quality="auto", output_format="png", reference_images=[], model="grok-imagine-image-2.0",
        )

        assert result["model_source"] == "grok-imagine-image-2.0"
        assert calls == ["https://grok-primary.example.com", "https://grok-secondary.example.com"]


def test_image_model_catalog_includes_all_models_from_each_provider(app):
    with app.app_context():
        providers.save_provider(
            provider_type="image", name="multi-model", base_url="https://multi.example.com", api_key="test-key",
            model="gpt-image-2", api_format="openai", priority=10, enabled=True,
            resolutions=["1K", "2K"],
            models=[
                {"id": "gpt-image-2", "label": "GPT Image 2"},
                {"id": "gpt-image-2.5-flare", "label": "GPT Image 2.5 Flare"},
            ],
        )
        get_db().commit()

        assert providers.selectable_image_models() == [
            {"id": "gpt-image-2", "label": "GPT Image 2", "resolutions": ["1K", "2K"]},
            {"id": "gpt-image-2.5-flare", "label": "GPT Image 2.5 Flare", "resolutions": ["1K", "2K"]},
        ]


def test_selected_image_model_from_provider_catalog_is_sent_to_upstream(app, monkeypatch):
    with app.app_context():
        providers.save_provider(
            provider_type="image", name="multi-model", base_url="https://multi.example.com", api_key="test-key",
            model="gpt-image-2", api_format="openai", priority=10, enabled=True,
            resolutions=["1K", "2K"],
            models=[
                {"id": "gpt-image-2", "label": "GPT Image 2"},
                {"id": "gpt-image-2.5-flare", "label": "GPT Image 2.5 Flare"},
            ],
        )
        get_db().commit()
        captured = {}

        def fake_generate_image(**kwargs):
            captured.update(kwargs)
            return {"image_path": "/static/uploads/ok.png", "image_paths": ["/static/uploads/ok.png"], "model_source": kwargs["model"]}

        monkeypatch.setattr(providers, "generate_image", fake_generate_image)

        providers.generate_image_with_failover(
            prompt="test", mode="text", ratio="1:1", resolution="2K", count=1,
            quality="auto", output_format="png", reference_images=[], model="gpt-image-2.5-flare",
        )

        assert captured["model"] == "gpt-image-2.5-flare"


def test_wildcard_image_model_uses_provider_default_model(app, monkeypatch):
    with app.app_context():
        providers.save_provider(
            provider_type="image", name="wildcard", base_url="https://wildcard.example.com", api_key="test-key",
            model="gpt-image-2", api_format="openai", priority=10, enabled=True, resolutions=["1K", "2K"],
        )
        get_db().commit()
        captured = {}
        monkeypatch.setattr(
            providers,
            "generate_image",
            lambda **kwargs: captured.update(kwargs) or {"image_path": "/static/uploads/ok.png", "image_paths": ["/static/uploads/ok.png"], "model_source": kwargs["model"]},
        )

        providers.generate_image_with_failover(
            prompt="test", mode="text", ratio="1:1", resolution="2K", count=1,
            quality="auto", output_format="png", reference_images=[], model="*",
        )

        assert captured["model"] == "gpt-image-2"


def test_generation_tasks_round_robin_across_matching_resolution(app, monkeypatch):
    with app.app_context():
        providers._round_robin_offsets.clear()
        save_image_provider("first", base_url="https://first.example.com", api_key="sk-first", resolutions=["2K"])
        save_image_provider("second", base_url="https://second.example.com", api_key="sk-second", resolutions=["2K"])
        save_image_provider("third", base_url="https://third.example.com", api_key="sk-third", resolutions=["1K"])
        calls = []

        def fake_generate_image(**kwargs):
            calls.append(kwargs["base_url"])
            return {"images": [], "size": "2048x1152", "model_source": kwargs["model"], "elapsed_seconds": 0.0}

        monkeypatch.setattr(providers, "generate_image", fake_generate_image)

        for _ in range(3):
            providers.generate_image_with_failover(
                prompt="test",
                mode="text",
                ratio="16:9",
                resolution="2K",
                count=1,
                quality="auto",
                output_format="png",
                reference_images=[],
            )

        assert calls == [
            "https://first.example.com",
            "https://second.example.com",
            "https://first.example.com",
        ]


def test_failed_connectivity_check_disables_provider(app, monkeypatch):
    with app.app_context():
        provider_id = save_image_provider("broken", base_url="https://broken.example.com", api_key="sk-broken")
        provider = providers.get_provider(provider_id)

        monkeypatch.setattr(providers, "probe_provider_connectivity", lambda provider: (_ for _ in ()).throw(RuntimeError("boom")))
        monkeypatch.setattr(providers, "notify_provider_disabled", lambda provider, error: None)

        ok, message = providers.check_provider_connectivity(provider)
        providers.mark_provider_check_result(provider_id, ok=ok, message=message)
        get_db().commit()

        row = get_db().execute("SELECT enabled, last_error FROM api_providers WHERE id = ?", (provider_id,)).fetchone()
        assert ok is False
        assert "boom" in message
        assert row["enabled"] == 0
        assert "boom" in row["last_error"]


def test_runtime_image_failure_does_not_disable_provider(app, monkeypatch):
    with app.app_context():
        provider_id = save_image_provider("temporary failure", base_url="https://temporary.example.com", api_key="sk-real")

        def fail_generation(**kwargs):
            raise RuntimeError("temporary upstream error")

        monkeypatch.setattr(providers, "generate_image", fail_generation)

        with pytest.raises(RuntimeError, match="temporary upstream error"):
            providers.generate_image_with_failover(
                prompt="test",
                mode="text",
                ratio="16:9",
                resolution="2K",
                count=1,
                quality="auto",
                output_format="png",
                reference_images=[],
            )

        row = get_db().execute("SELECT enabled, api_key FROM api_providers WHERE id = ?", (provider_id,)).fetchone()
        assert row["enabled"] == 1
        assert row["api_key"]


def test_provider_connectivity_route_handles_unexpected_errors(app, monkeypatch):
    with app.app_context():
        provider_id = save_image_provider("broken", base_url="https://broken.example.com", api_key="sk-broken")

    monkeypatch.setattr(providers, "check_provider_connectivity", lambda provider: (False, "boom"))

    def explode(*args, **kwargs):
        raise RuntimeError("database write exploded")

    monkeypatch.setattr(providers, "mark_provider_check_result", explode)

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = 1
            session["csrf_token"] = "token"

        response = client.post(
            f"/settings/providers/{provider_id}/test",
            data={"csrf_token": "token"},
            follow_redirects=False,
        )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/settings")


def test_provider_connectivity_route_keeps_missing_provider_404(app):
    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = 1
            session["csrf_token"] = "token"

        response = client.post(
            "/settings/providers/99999/test",
            data={"csrf_token": "token"},
            follow_redirects=False,
        )

    assert response.status_code == 404


def test_provider_connectivity_route_returns_image_result_json(app, monkeypatch):
    with app.app_context():
        provider_id = save_image_provider("image-test", base_url="https://image.example.com", api_key="image-key")
        admin = get_db().execute("SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1").fetchone()

    def fake_check(provider, mode="probe"):
        provider["_test_image"] = "/static/uploads/provider-test.png"
        return True, "connection ok"

    monkeypatch.setattr(providers, "check_provider_connectivity", fake_check)
    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = admin["id"]
        response = client.post(
            f"/settings/providers/{provider_id}/test",
            data={"csrf_token": "test", "test_mode": "generate", "test_model": "gpt-image-2"},
            headers={"Accept": "application/json"},
        )

    assert response.status_code == 200
    assert response.get_json()["image"] == "/static/uploads/provider-test.png"
    assert response.get_json()["message"] == "生图测试成功"


def test_provider_connectivity_route_returns_dialogue_result_json(app, monkeypatch):
    with app.app_context():
        provider_id = providers.save_provider(
            provider_type="prompt", name="prompt-test", base_url="https://prompt.example.com", api_key="prompt-key",
            model="chat-model", priority=100, enabled=True,
        )
        get_db().commit()
        admin = get_db().execute("SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1").fetchone()

    def fake_check(provider, mode="probe"):
        provider["_test_text"] = "OK"
        return True, "connection ok"

    monkeypatch.setattr(providers, "check_provider_connectivity", fake_check)
    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = admin["id"]
        response = client.post(
            f"/settings/providers/{provider_id}/test",
            data={"csrf_token": "test", "test_mode": "generate", "test_model": "chat-model"},
            headers={"Accept": "application/json"},
        )

    assert response.status_code == 200
    assert response.get_json()["text"] == "OK"
    assert response.get_json()["message"] == "对话测试成功"


def test_provider_connectivity_route_returns_video_result_json(app, monkeypatch):
    with app.app_context():
        provider_id = providers.save_provider(
            provider_type="video", name="video-test", base_url="https://video.example.com", api_key="video-key",
            model="video-model", api_format="grok", priority=100, enabled=True,
        )
        get_db().commit()
        admin = get_db().execute("SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1").fetchone()

    def fake_check(provider, mode="probe"):
        provider["_test_video_task"] = "task-1"
        provider["_test_video_url"] = "/static/uploads/provider-test.mp4"
        provider["_test_video_status"] = "completed"
        return True, "connection ok"

    monkeypatch.setattr(providers, "check_provider_connectivity", fake_check)
    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = admin["id"]
        response = client.post(
            f"/settings/providers/{provider_id}/test",
            data={"csrf_token": "test", "test_mode": "generate", "test_model": "video-model"},
            headers={"Accept": "application/json"},
        )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["video"] == "/static/uploads/provider-test.mp4"
    assert payload["video_task_id"] == "task-1"
    assert payload["video_status"] == "completed"


def test_provider_model_sync_returns_models_and_persists_catalog(app, monkeypatch):
    with app.app_context():
        provider_id = save_image_provider("model-sync", base_url="https://image.example.com", api_key="image-key")
        admin = get_db().execute("SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1").fetchone()

    models = [{"id": "gpt-image-2.5", "label": "GPT Image 2.5"}]
    monkeypatch.setattr(providers, "fetch_provider_models", lambda provider: models)
    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = admin["id"]
        response = client.post(
            f"/settings/providers/{provider_id}/models/sync",
            data={"csrf_token": "test"},
            headers={"Accept": "application/json", "X-Requested-With": "fetch"},
        )

    assert response.status_code == 200
    assert response.get_json()["source"] == "remote"
    with app.app_context():
        row = get_db().execute("SELECT models_json FROM api_providers WHERE id = ?", (provider_id,)).fetchone()
    assert '"gpt-image-2.5"' in row["models_json"]


def test_connectivity_probe_calls_image_generation(monkeypatch):
    captured = {}

    def fake_generate_image(**kwargs):
        captured.update(kwargs)
        return {"image_path": "data:image/png;base64,abc"}

    monkeypatch.setattr(providers, "generate_image", fake_generate_image)

    providers.probe_provider_connectivity(
        {"base_url": "https://api.example.com/", "api_key": "sk-test", "model": "gpt-image-2"}
    )

    assert captured["prompt"]
    assert captured["mode"] == "text"
    assert captured["ratio"] == "1:1"
    assert captured["resolution"] == "1K"
    assert captured["count"] == 1
    assert captured["quality"] == "low"
    assert captured["output_format"] == "png"
    assert captured["api_key"] == "sk-test"
    assert captured["base_url"] == "https://api.example.com/"
    assert captured["model"] == "gpt-image-2"


def test_fetch_provider_models_parses_gemini_models_payload(monkeypatch):
    class Response:
        status_code = 200

        def json(self):
            return {"models": [{"name": "models/gemini-3.1-flash-image", "displayName": "Nano Banana 2"}]}

    monkeypatch.setattr(providers.requests, "get", lambda *args, **kwargs: Response())
    result = providers.fetch_provider_models({"api_format": "gemini", "base_url": "https://generativelanguage.googleapis.com", "api_key": "key"})
    assert result == [{"id": "gemini-3.1-flash-image", "label": "Nano Banana 2"}]


def test_fetch_provider_models_falls_back_to_v1_for_openai_gateway(monkeypatch):
    class HtmlResponse:
        status_code = 200

        def json(self):
            raise ValueError("HTML response")

    class JsonResponse:
        status_code = 200

        def json(self):
            return {"data": [{"id": "gpt-image-2", "owned_by": "gateway"}]}

    calls = []

    def fake_get(url, *args, **kwargs):
        calls.append(url)
        return HtmlResponse() if url == "https://ai.junze.me/models" else JsonResponse()

    monkeypatch.setattr(providers.requests, "get", fake_get)
    result = providers.fetch_provider_models({"api_format": "openai", "base_url": "https://ai.junze.me", "api_key": "key"})
    assert calls == ["https://ai.junze.me/models", "https://ai.junze.me/v1/models"]
    assert result == [{"id": "gpt-image-2", "label": "gpt-image-2"}]


def test_connectivity_probe_returns_dialogue_text(monkeypatch):
    class Response:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": "OK"}}]}

    monkeypatch.setattr(providers.requests, "post", lambda *args, **kwargs: Response())
    provider = {"provider_type": "prompt", "base_url": "https://api.example.com", "api_key": "key", "model": "chat-model"}
    providers.probe_provider_connectivity(provider, mode="generate")
    assert provider["_test_text"] == "OK"


def test_connectivity_probe_falls_back_to_v1_dialogue_endpoint(monkeypatch):
    class HtmlResponse:
        status_code = 200

        def json(self):
            raise ValueError("HTML response")

    class JsonResponse:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": "OK"}}]}

    calls = []

    def fake_post(url, *args, **kwargs):
        calls.append(url)
        return HtmlResponse() if not url.endswith("/v1/chat/completions") else JsonResponse()

    monkeypatch.setattr(providers.requests, "post", fake_post)
    provider = {"provider_type": "prompt", "base_url": "https://api.example.com", "api_key": "key", "model": "chat-model"}
    providers.probe_provider_connectivity(provider, mode="generate")
    assert calls == ["https://api.example.com/chat/completions", "https://api.example.com/v1/chat/completions"]
    assert provider["_test_text"] == "OK"


def test_connectivity_probe_accepts_non_object_dialogue_payload(monkeypatch):
    class Response:
        status_code = 200

        def json(self):
            return ["accepted"]

    monkeypatch.setattr(providers.requests, "post", lambda *args, **kwargs: Response())
    provider = {"provider_type": "prompt", "base_url": "https://api.example.com", "api_key": "key", "model": "chat-model"}
    providers.probe_provider_connectivity(provider, mode="generate")
    assert provider["_test_text"] == "收到成功响应"


def test_connectivity_probe_video_saves_completed_result(app, monkeypatch):
    from huishi import upload_storage, video_api

    class Storage:
        def save_bytes(self, filename, content, content_type):
            assert filename.endswith(".mp4")
            assert content == b"video"
            assert content_type == "video/mp4"
            return "/static/uploads/provider-test.mp4"

    monkeypatch.setattr(video_api, "create_video_task", lambda provider, request: video_api.VideoTask("task-1"))
    monkeypatch.setattr(video_api, "poll_video_task", lambda provider, task_id: video_api.VideoTaskState("completed", url="https://cdn.example/video.mp4"))
    monkeypatch.setattr(video_api, "download_video_result", lambda provider, state, timeout=120: b"video")
    monkeypatch.setattr(upload_storage, "get_upload_storage", lambda: Storage())
    with app.app_context():
        provider = {"provider_type": "video", "api_format": "grok", "base_url": "https://api.example.com", "api_key": "key", "model": "video-model"}
        providers.probe_provider_connectivity(provider, mode="generate")
    assert provider["_test_video_task"] == "task-1"
    assert provider["_test_video_url"] == "/static/uploads/provider-test.mp4"


def test_provider_form_rejects_admin_password_as_api_key(app):
    from huishi.routes_workspace import parse_provider_form

    with app.app_context():
        with app.test_request_context(
            "/settings/providers",
            method="POST",
            data={
                "provider_type": "image",
                "name": "bad",
                "base_url": "https://api.example.com",
                "api_key": app.config["ADMIN_PASSWORD"],
                "model": "gpt-image-2",
                "priority": "100",
                "enabled": "1",
                "resolutions": ["1K"],
            },
        ):
            with pytest.raises(ValueError, match="管理员登录密码"):
                parse_provider_form()
def test_provider_form_keeps_encrypted_key_when_current_env_cannot_decrypt(app):
    from huishi.routes_workspace import parse_provider_form
    from huishi.secrets import ENCRYPTED_PREFIX

    with app.app_context():
        provider_id = save_image_provider("encrypted", base_url="https://api.example.com", api_key="sk-real")
        encrypted_key = f"{ENCRYPTED_PREFIX}unreadable"
        get_db().execute("UPDATE api_providers SET api_key = ? WHERE id = ?", (encrypted_key, provider_id))
        get_db().commit()

        existing = providers.get_provider(provider_id)
        assert existing["api_key"] == ""

        with app.test_request_context(
            f"/settings/providers/{provider_id}",
            method="POST",
            data={
                "provider_type": "image",
                "name": "renamed",
                "base_url": "https://api.example.com",
                "api_key": "",
                "model": "gpt-image-2",
                "priority": "100",
                "enabled": "1",
                "resolutions": ["1K"],
            },
        ):
            parsed = parse_provider_form(existing, provider_id=provider_id)

        assert parsed["api_key"] == encrypted_key

def test_legacy_provider_import_is_idempotent_with_encrypted_api_key(app):
    from cryptography.fernet import Fernet

    with app.app_context():
        app.config["ENCRYPTION_KEY"] = Fernet.generate_key().decode("ascii")
        providers.save_app_setting("image_base_url", "https://api.example.com")
        providers.save_app_setting("image_api_key", "sk-real-secret")
        get_db().commit()

        assert providers.import_legacy_providers_from_settings() == 1
        get_db().commit()
        assert providers.import_legacy_providers_from_settings() == 0
        get_db().commit()

        rows = get_db().execute("SELECT base_url, api_key FROM api_providers").fetchall()

    assert len(rows) == 1
    assert rows[0]["base_url"] == "https://api.example.com"
