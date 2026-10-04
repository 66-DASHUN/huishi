from __future__ import annotations

from pathlib import Path

import pytest

from app import create_app
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


def create_queued_byok_task(app, *, include_grok: bool = True) -> tuple[int, int]:
    from huishi.providers import save_provider
    from huishi.records import create_generation_task
    from huishi.user_key import save_user_api_key

    with app.app_context():
        user_id = int(
            get_db()
            .execute(
                """
                INSERT INTO users (username, email, password_hash, role, email_verified, points, created_at)
                VALUES ('queued-byok', '', 'hash', 'user', 1, 20, 'now')
                """
            )
            .lastrowid
        )
        save_user_api_key(user_id, "user-key")
        if include_grok:
            save_provider(
                provider_type="image",
                name="grok",
                base_url="https://grok.example",
                api_key="platform-grok-key",
                model="grok-imagine-image-2.0",
                api_format="grok",
                resolutions=["1K", "2K"],
                priority=10,
                enabled=True,
            )
        task_id = create_generation_task(
            user_id=user_id,
            prompt="queued prompt",
            mode="text",
            ratio="1:1",
            resolution="2K",
            actual_size="2048x2048",
            quality="auto",
            output_format="png",
            count=1,
            cost=0,
            model="grok-imagine-image-2.0",
            bypass_billing=True,
        )
        save_provider(
            provider_type="image",
            name="banana promoted after enqueue",
            base_url="https://banana.example",
            api_key="platform-banana-key",
            model="gemini-3.1-flash-image",
            api_format="banana",
            resolutions=["1K"],
            priority=1,
            enabled=True,
        )
        get_db().commit()
    return user_id, task_id


def test_queued_byok_task_keeps_frozen_model_and_resolution_when_provider_order_changes(app, monkeypatch):
    from huishi.generation_queue import run_generation_task

    captured = {}

    def fake_generate_image(**kwargs):
        captured.update(kwargs)
        return {
            "image_path": "/static/uploads/generated.png",
            "image_paths": ["/static/uploads/generated.png"],
            "actual_size": "2048x2048",
            "model_source": kwargs["model"],
            "elapsed_seconds": 0.1,
        }

    _user_id, task_id = create_queued_byok_task(app)
    monkeypatch.setattr("huishi.generation_queue.generate_image", fake_generate_image)

    run_generation_task(app, task_id, [])

    assert captured["model"] == "grok-imagine-image-2.0"
    assert captured["resolution"] == "2K"
    assert captured["api_format"] == "grok"
    assert captured["base_url"] == "https://grok.example"


def test_queued_byok_task_fails_instead_of_crossing_models_when_frozen_provider_is_missing(app, monkeypatch):
    from huishi.generation_queue import run_generation_task

    _user_id, task_id = create_queued_byok_task(app, include_grok=False)
    monkeypatch.setattr(
        "huishi.generation_queue.generate_image",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("must not call a different model")),
    )

    run_generation_task(app, task_id, [])

    with app.app_context():
        task = get_db().execute(
            "SELECT status, error_message FROM generation_tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
    assert task["status"] == "failed"
    assert "管理员尚未设置生图提供商" in task["error_message"]
