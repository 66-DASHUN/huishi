from __future__ import annotations

from pathlib import Path

import pytest

from app import create_app
from huishi.billing import calculate_cost
from huishi.db import get_db, init_db
from huishi.generation_queue import run_generation_task
from huishi.providers import save_provider
from huishi.records import create_generation_task


@pytest.fixture()
def app(tmp_path: Path):
    application = create_app(testing=True)
    application.config["DATABASE"] = tmp_path / "test.sqlite3"
    application.config["OUTPUT_DIR"] = tmp_path / "uploads"
    with application.app_context():
        init_db()
    return application


def login_user(app, *, username: str = "media-user", points: int = 40):
    with app.app_context():
        cursor = get_db().execute(
            "INSERT INTO users (username, email, password_hash, role, email_verified, points, created_at) VALUES (?, '', 'hash', 'user', 1, ?, 'now')",
            (username, points),
        )
        user_id = int(cursor.lastrowid)
        get_db().commit()
    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = user_id
    return client, user_id


def test_music_cost_uses_model_specific_music_rule(app):
    with app.app_context():
        get_db().execute(
            "INSERT INTO pricing_rules (mode, model, resolution, points_per_image, enabled, media_type) VALUES (?, ?, ?, ?, 1, ?)",
            ("music", "music-3.0", "default", 9, "music"),
        )
        get_db().commit()

        assert calculate_cost("music", "default", 1, model="music-3.0", media_type="music") == 9


def test_workspace_speech_request_creates_speech_task(app, monkeypatch):
    monkeypatch.setattr("huishi.routes_workspace.enqueue_generation_task", lambda *args, **kwargs: None)
    with app.app_context():
        save_provider(
            provider_type="audio",
            name="MiniMax Speech",
            base_url="https://api.minimaxi.com",
            api_key="test-key",
            model="speech-2.8-hd",
            api_format="minimax",
            priority=1,
            enabled=True,
            capabilities=["speech"],
            models=[{"id": "speech-2.8-hd", "label": "MiniMax Speech 2.8 HD", "media_type": "speech"}],
        )
        get_db().execute(
            "INSERT INTO pricing_rules (mode, model, resolution, points_per_image, enabled, media_type) VALUES (?, ?, ?, ?, 1, ?)",
            ("speech", "speech-2.8-hd", "default", 2, "speech"),
        )
        get_db().commit()
    client, user_id = login_user(app)

    response = client.post(
        "/generate",
        data={"prompt": "你好", "media_type": "speech", "model": "speech-2.8-hd", "count": "1"},
        headers={"X-Requested-With": "fetch"},
    )

    assert response.status_code == 200
    with app.app_context():
        task = get_db().execute(
            "SELECT media_type, model FROM generation_tasks WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (user_id,),
        ).fetchone()
    assert dict(task) == {"media_type": "speech", "model": "speech-2.8-hd"}


def test_audio_worker_persists_speech_result_in_upload_storage(app, monkeypatch):
    with app.app_context():
        provider_id = save_provider(
            provider_type="audio",
            name="MiniMax Speech",
            base_url="https://api.minimaxi.com",
            api_key="test-key",
            model="speech-2.8-hd",
            api_format="minimax",
            priority=1,
            enabled=True,
            capabilities=["speech"],
            models=[{"id": "speech-2.8-hd", "label": "MiniMax Speech 2.8 HD", "media_type": "speech"}],
        )
        get_db().execute(
            "INSERT INTO pricing_rules (mode, model, resolution, points_per_image, enabled, media_type) VALUES (?, ?, ?, ?, 1, ?)",
            ("speech", "speech-2.8-hd", "default", 2, "speech"),
        )
        user_cursor = get_db().execute(
            "INSERT INTO users (username, email, password_hash, role, email_verified, points, created_at) VALUES ('worker-user', '', 'hash', 'user', 1, 20, 'now')"
        )
        user_id = int(user_cursor.lastrowid)
        task_id = create_generation_task(
            user_id=user_id,
            prompt="你好",
            mode="speech",
            ratio="auto",
            resolution="default",
            actual_size="",
            quality="auto",
            output_format="mp3",
            count=1,
            cost=2,
            model="speech-2.8-hd",
            media_type="speech",
            provider_id=provider_id,
            metadata={"audio_kind": "speech", "audio_format": "mp3"},
        )
        get_db().commit()

    monkeypatch.setattr(
        "huishi.generation_queue.generate_speech",
        lambda provider, request: {"content": b"audio-bytes", "mime_type": "audio/mpeg", "extension": "mp3", "model": "speech-2.8-hd"},
    )
    app.config["GENERATION_LIMIT_WAIT_TIMEOUT_SECONDS"] = 1
    run_generation_task(app, task_id)

    with app.app_context():
        task = get_db().execute("SELECT status, media_type, record_id FROM generation_tasks WHERE id = ?", (task_id,)).fetchone()
        record = get_db().execute("SELECT media_type, mime_type, image_path, asset_source FROM records WHERE id = ?", (task["record_id"],)).fetchone()
        assert task["status"] == "succeeded"
        assert task["media_type"] == "speech"
        assert record["media_type"] == "speech"
        assert record["mime_type"] == "audio/mpeg"
        assert record["asset_source"] == "audio"
    assert (app.config["OUTPUT_DIR"] / Path(record["image_path"]).name).read_bytes() == b"audio-bytes"


def test_record_generation_seed_preserves_media_type_and_model(app):
    from huishi.records import create_record, record_generation_seed

    with app.app_context():
        user_cursor = get_db().execute(
            "INSERT INTO users (username, email, password_hash, role, email_verified, points, created_at) VALUES (?, '', 'hash', 'user', 1, 40, 'now')",
            ("seed-audio",),
        )
        user_id = int(user_cursor.lastrowid)
        record_id = create_record(
            user_id=user_id,
            prompt="旁白",
            image_path="/static/uploads/voice.mp3",
            mode="speech",
            ratio="auto",
            resolution="default",
            actual_size="",
            quality="auto",
            output_format="mp3",
            count=1,
            model_source="speech-2.8-hd",
            elapsed_seconds=0,
            points_charged=1,
            asset_source="audio",
            media_type="speech",
            mime_type="audio/mpeg",
        )
        record = get_db().execute("SELECT * FROM records WHERE id = ?", (record_id,)).fetchone()

    seed = record_generation_seed(record)
    assert seed["media_type"] == "speech"
    assert seed["model"] == "speech-2.8-hd"


def test_assets_template_renders_video_and_audio_players():
    template = Path("templates/assets.html").read_text(encoding="utf-8")

    assert "<video" in template
    assert "<audio" in template
    assert "record.get('media_type'" in template


def test_video_reference_hint_is_wired_and_derived():
    """参考素材提示必须由 capabilities 派生，且模板里的元素确实被赋值。

    缺陷背景（需求 ④）：
    * `templates/workspace.html` 的 `<small data-video-hint>` 是**死元素**——
      全仓库没有任何 JS 给它赋值，用户永远看不到解析出来的能力上限；
    * `static/js/settings.js` 的测试面板提示把 H3 的规格（图片≤9、视频≤3、
      音频≤3、合计≤12）**写死**，对 seedance_media（30 张）完全失真。

    这条测试锁住"读源码"的层面：元素被引用、硬编码文案已消除、并且两侧
    都有从 caps 派生的函数。数值行为本身由 tests/check_settings_models.cjs
    与 huishi.media_capabilities 的用例覆盖。
    """
    root = Path(__file__).resolve().parent.parent
    template = (root / "templates" / "workspace.html").read_text(encoding="utf-8")
    workspace_js = (root / "static" / "js" / "workspace.js").read_text(encoding="utf-8")
    settings_js = (root / "static" / "js" / "settings.js").read_text(encoding="utf-8")

    # 元素仍在模板里（删掉它会让下面的查询变成空操作而无人察觉）
    assert "data-video-hint" in template
    # 并且真的被 JS 查询与赋值
    assert 'document.querySelector("[data-video-hint]")' in workspace_js
    assert "describeVideoReferenceHint" in workspace_js
    assert "hint.textContent = text" in workspace_js

    # 硬编码的 H3 规格必须消失
    assert "图片≤9、视频≤3、音频≤3，合计≤12" not in settings_js
    assert "describeTestReferenceHint" in settings_js
    assert "describeTestReferenceHint(caps)" in settings_js

    # 不支持的能力对应的按钮应隐藏，而不是永远灰着
    assert "button.hidden = !supported;" in workspace_js
