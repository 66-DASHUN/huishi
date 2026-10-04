from io import BytesIO
from pathlib import Path

import pytest
from werkzeug.datastructures import FileStorage

from app import create_app
from huishi.db import get_db
from huishi.routes_workspace import is_allowed_reference_image


@pytest.fixture()
def app(tmp_path: Path):
    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "test.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"
    with app.app_context():
        from huishi.db import init_db

        init_db()
    return app


def create_user(points: int = 20, username: str = "u") -> int:
    cursor = get_db().execute(
        """
        INSERT INTO users (username, email, password_hash, role, email_verified, points, created_at)
        VALUES (?, '', 'hash', 'user', 1, ?, 'now')
        """,
        (username, points),
    )
    get_db().commit()
    return int(cursor.lastrowid)


def login(client, user_id: int) -> None:
    with client.session_transaction() as session:
        session["user_id"] = user_id


def test_reference_upload_accepts_jpg_mimetype_alias():
    file_storage = FileStorage(
        stream=BytesIO(b"jpg"),
        filename="reference.jpg",
        content_type="image/jpg",
    )

    assert is_allowed_reference_image(file_storage)


def test_generate_rejects_when_user_reaches_active_task_limit(app, monkeypatch):
    called = False

    def fake_generate_image_with_failover(**kwargs):
        nonlocal called
        called = True
        return {
            "image_path": "/static/uploads/generated.png",
            "image_paths": ["/static/uploads/generated.png"],
            "actual_size": "2560x1440",
            "model_source": "fake",
            "elapsed_seconds": 0.1,
        }

    app.config["MAX_ACTIVE_GENERATION_TASKS_PER_USER"] = 1

    with app.app_context():
        user_id = create_user(points=20)
        get_db().execute(
            """
            INSERT INTO generation_tasks
            (user_id, prompt, mode, ratio, resolution, actual_size, quality, output_format, count, cost, status, reference_paths, created_at, updated_at)
            VALUES (?, 'already running', 'text', '16:9', '2K', '2560x1440', 'auto', 'png', 1, 2, 'queued', '[]', 'now', 'now')
            """,
            (user_id,),
        )
        get_db().commit()

    monkeypatch.setattr(
        "huishi.generation_queue.generate_image_with_failover",
        fake_generate_image_with_failover,
    )

    with app.test_client() as client:
        login(client, user_id)
        response = client.post(
            "/generate",
            data={
                "prompt": "new generation",
                "ratio": "16:9",
                "resolution": "2K",
                "quality": "auto",
                "output_format": "png",
                "count": "1",
            },
            headers={"X-Requested-With": "fetch", "Accept": "application/json"},
        )

    assert response.status_code == 429
    payload = response.get_json()
    assert payload["ok"] is False
    assert "已有 1 个生成任务" in payload["error"]
    assert called is False


def test_reference_generation_uses_saved_reference_path(app, monkeypatch):
    captured = {}

    def fake_generate_image_with_failover(**kwargs):
        captured.update(kwargs)
        return {
            "image_path": "/static/uploads/generated.png",
            "image_paths": ["/static/uploads/generated.png"],
            "actual_size": "2560x1440",
            "model_source": "fake",
            "elapsed_seconds": 0.1,
        }

    with app.app_context():
        user_id = create_user()
        upload_dir = app.config["OUTPUT_DIR"]
        upload_dir.mkdir(parents=True, exist_ok=True)
        (upload_dir / "ref.png").write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
            b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
            b"\x90wS\xde"
        )
        get_db().execute(
            """
            INSERT INTO dialogues (user_id, title, created_at, updated_at)
            VALUES (?, 'existing', 'now', 'now')
            """,
            (user_id,),
        )
        dialogue_id = int(get_db().execute("SELECT id FROM dialogues").fetchone()["id"])
        get_db().commit()

    monkeypatch.setattr(
        "huishi.generation_queue.generate_image_with_failover",
        fake_generate_image_with_failover,
    )

    with app.test_client() as client:
        login(client, user_id)
        response = client.post(
            "/generate",
            data={
                "prompt": "use reference",
                "ratio": "16:9",
                "resolution": "2K",
                "quality": "auto",
                "output_format": "png",
                "count": "1",
                "dialogue_id": str(dialogue_id),
                "reference_paths": "/static/uploads/ref.png",
            },
            headers={"X-Requested-With": "fetch", "Accept": "application/json"},
        )

    assert response.status_code == 200
    assert response.get_json()["ok"] is True
    assert captured["mode"] == "reference"
    assert len(captured["reference_images"]) == 1
    assert captured["reference_images"][0].filename == "ref.png"

    with app.app_context():
        task = get_db().execute("SELECT mode, reference_paths FROM generation_tasks").fetchone()
        record = get_db().execute("SELECT mode, reference_paths FROM records").fetchone()
        assert task["mode"] == "reference"
        assert "/static/uploads/ref.png" in task["reference_paths"]
        assert record["mode"] == "reference"
        assert "/static/uploads/ref.png" in record["reference_paths"]


def test_generate_persists_selected_image_model_from_provider_catalog(app, monkeypatch):
    from huishi.providers import save_provider

    def fake_generate_image_with_failover(**kwargs):
        assert kwargs["model"] == "gpt-image-2.5-flare"
        return {
            "image_path": "/static/uploads/generated.png",
            "image_paths": ["/static/uploads/generated.png"],
            "actual_size": "2560x1440",
            "model_source": kwargs["model"],
            "elapsed_seconds": 0.1,
        }

    with app.app_context():
        user_id = create_user(username="selected-model")
        save_provider(
            provider_type="image",
            name="multi-model",
            base_url="https://image.example",
            api_key="platform-key",
            model="gpt-image-2",
            api_format="openai",
            priority=10,
            enabled=True,
            resolutions=["1K", "2K"],
            models=[
                {"id": "gpt-image-2", "label": "GPT Image 2"},
                {"id": "gpt-image-2.5-flare", "label": "GPT Image 2.5 Flare"},
            ],
        )
        get_db().commit()

    monkeypatch.setattr("huishi.generation_queue.generate_image_with_failover", fake_generate_image_with_failover)

    with app.test_client() as client:
        login(client, user_id)
        response = client.post(
            "/generate",
            data={
                "prompt": "selected model",
                "model": "gpt-image-2.5-flare",
                "ratio": "16:9",
                "resolution": "2K",
                "quality": "auto",
                "output_format": "png",
                "count": "1",
            },
            headers={"X-Requested-With": "fetch", "Accept": "application/json"},
        )

    assert response.status_code == 200
    with app.app_context():
        task = get_db().execute("SELECT model FROM generation_tasks ORDER BY id DESC LIMIT 1").fetchone()
    assert task["model"] == "gpt-image-2.5-flare"


def test_workspace_lists_all_enabled_image_models_with_display_labels(app):
    from huishi.providers import save_provider

    with app.app_context():
        user_id = create_user(username="model-list")
        save_provider(
            provider_type="image",
            name="multi-model",
            base_url="https://image.example",
            api_key="platform-key",
            model="gpt-image-2",
            api_format="openai",
            priority=10,
            enabled=True,
            resolutions=["1K", "2K"],
            models=[
                {"id": "gpt-image-2", "label": "GPT Image 2"},
                {"id": "gpt-image-2.5-flare", "label": "GPT Image 2.5 Flare"},
            ],
        )
        get_db().commit()

    with app.test_client() as client:
        login(client, user_id)
        response = client.get("/workspace")

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'value="gpt-image-2"' in body
    assert 'value="gpt-image-2.5-flare"' in body
    assert "GPT Image 2.5 Flare" in body


def test_generate_without_dialogue_does_not_create_dialogue(app, monkeypatch):
    def fake_generate_image_with_failover(**kwargs):
        return {
            "image_path": "/static/uploads/generated.png",
            "image_paths": ["/static/uploads/generated.png"],
            "actual_size": "2560x1440",
            "model_source": "fake",
            "elapsed_seconds": 0.1,
        }

    with app.app_context():
        user_id = create_user()

    monkeypatch.setattr(
        "huishi.generation_queue.generate_image_with_failover",
        fake_generate_image_with_failover,
    )

    with app.test_client() as client:
        login(client, user_id)
        response = client.post(
            "/generate",
            data={
                "prompt": "standalone generation",
                "ratio": "16:9",
                "resolution": "2K",
                "quality": "auto",
                "output_format": "png",
                "count": "1",
                "dialogue_id": "",
            },
            headers={"X-Requested-With": "fetch", "Accept": "application/json"},
        )

    assert response.status_code == 200
    assert response.get_json()["ok"] is True

    with app.app_context():
        dialogue_count = get_db().execute("SELECT COUNT(*) AS count FROM dialogues").fetchone()["count"]
        task = get_db().execute("SELECT dialogue_id FROM generation_tasks").fetchone()
        record = get_db().execute("SELECT dialogue_id FROM records").fetchone()

        assert dialogue_count == 0
        assert task["dialogue_id"] is None
        assert record["dialogue_id"] is None


def test_generate_with_create_dialogue_flag_creates_dialogue(app, monkeypatch):
    def fake_generate_image_with_failover(**kwargs):
        return {
            "image_path": "/static/uploads/generated.png",
            "image_paths": ["/static/uploads/generated.png"],
            "actual_size": "2560x1440",
            "model_source": "fake",
            "elapsed_seconds": 0.1,
        }

    with app.app_context():
        user_id = create_user()

    monkeypatch.setattr(
        "huishi.generation_queue.generate_image_with_failover",
        fake_generate_image_with_failover,
    )

    with app.test_client() as client:
        login(client, user_id)
        response = client.post(
            "/generate",
            data={
                "prompt": "new dialogue",
                "ratio": "16:9",
                "resolution": "2K",
                "quality": "auto",
                "output_format": "png",
                "count": "1",
                "dialogue_id": "",
                "create_dialogue": "1",
            },
            headers={"X-Requested-With": "fetch", "Accept": "application/json"},
        )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True

    with app.app_context():
        dialogue = get_db().execute("SELECT id FROM dialogues").fetchone()
        task = get_db().execute("SELECT dialogue_id FROM generation_tasks").fetchone()
        record = get_db().execute("SELECT dialogue_id FROM records").fetchone()

        assert dialogue["id"]
        assert payload["dialogue"]["id"] == dialogue["id"]
        assert payload["dialogue"]["title"] == "new dialogue"
        assert task["dialogue_id"] == dialogue["id"]
        assert record["dialogue_id"] == dialogue["id"]


def test_generate_rolls_back_dialogue_when_task_creation_fails(app, monkeypatch):
    with app.app_context():
        user_id = create_user()

    def fail_create_generation_task(**kwargs):
        raise ValueError("task creation failed")

    monkeypatch.setattr("huishi.routes_workspace.create_generation_task", fail_create_generation_task)

    with app.test_client() as client:
        login(client, user_id)
        response = client.post(
            "/generate",
            data={
                "prompt": "rollback generation",
                "ratio": "16:9",
                "resolution": "2K",
                "quality": "auto",
                "output_format": "png",
                "count": "1",
                "dialogue_id": "",
                "create_dialogue": "1",
            },
            headers={"X-Requested-With": "fetch", "Accept": "application/json"},
        )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["ok"] is False
    assert "task creation failed" in payload["error"]

    with app.app_context():
        dialogue_count = get_db().execute("SELECT COUNT(*) AS count FROM dialogues WHERE user_id = ?", (user_id,)).fetchone()["count"]
        task_count = get_db().execute("SELECT COUNT(*) AS count FROM generation_tasks WHERE user_id = ?", (user_id,)).fetchone()["count"]

    assert dialogue_count == 0
    assert task_count == 0


def test_generate_locks_user_before_reserving_generation_task(app, monkeypatch):
    locked_user_ids = []

    def fake_enqueue_generation_task(_app, _task_id, _cleanup_paths):
        return None

    def track_lock(user_id):
        locked_user_ids.append(user_id)

    with app.app_context():
        user_id = create_user(points=20)

    monkeypatch.setattr("huishi.routes_workspace.enqueue_generation_task", fake_enqueue_generation_task)
    monkeypatch.setattr("huishi.routes_workspace.lock_user_for_update", track_lock)

    with app.test_client() as client:
        login(client, user_id)
        response = client.post(
            "/generate",
            data={
                "prompt": "lock before reservation",
                "ratio": "16:9",
                "resolution": "2K",
                "quality": "auto",
                "output_format": "png",
                "count": "1",
            },
            headers={"X-Requested-With": "fetch", "Accept": "application/json"},
        )

    assert response.status_code == 200
    assert locked_user_ids == [user_id]


def test_generate_locks_user_before_transactional_reservation_checks(app, monkeypatch):
    calls = []

    def fake_enqueue_generation_task(_app, _task_id, _cleanup_paths):
        return None

    def track_lock(_user_id):
        calls.append("lock")

    def track_points(_user_id, _cost):
        calls.append("points")

    def track_slot(_user_id):
        calls.append("slot")

    with app.app_context():
        user_id = create_user(points=20)

    monkeypatch.setattr("huishi.routes_workspace.enqueue_generation_task", fake_enqueue_generation_task)
    monkeypatch.setattr("huishi.routes_workspace.lock_user_for_update", track_lock)
    monkeypatch.setattr("huishi.routes_workspace.require_available_generation_points", track_points)
    monkeypatch.setattr("huishi.routes_workspace.require_active_generation_task_slot", track_slot)

    with app.test_client() as client:
        login(client, user_id)
        response = client.post(
            "/generate",
            data={
                "prompt": "lock order",
                "ratio": "16:9",
                "resolution": "2K",
                "quality": "auto",
                "output_format": "png",
                "count": "1",
            },
            headers={"X-Requested-With": "fetch", "Accept": "application/json"},
        )

    assert response.status_code == 200
    assert calls == ["points", "slot", "lock", "points", "slot"]


def test_generate_marks_task_failed_when_enqueue_fails_after_commit(app, monkeypatch):
    def fail_enqueue_generation_task(_app, _task_id, _cleanup_paths):
        raise RuntimeError("queue unavailable")

    with app.app_context():
        user_id = create_user(points=20)

    monkeypatch.setattr("huishi.routes_workspace.enqueue_generation_task", fail_enqueue_generation_task)

    with app.test_client() as client:
        login(client, user_id)
        response = client.post(
            "/generate",
            data={
                "prompt": "enqueue fails",
                "ratio": "16:9",
                "resolution": "2K",
                "quality": "auto",
                "output_format": "png",
                "count": "1",
            },
            headers={"X-Requested-With": "fetch", "Accept": "application/json"},
        )

    assert response.status_code == 502
    payload = response.get_json()
    assert payload["ok"] is False
    assert "queue unavailable" in payload["error"]

    with app.app_context():
        task = get_db().execute(
            "SELECT status, error_message FROM generation_tasks WHERE user_id = ?",
            (user_id,),
        ).fetchone()

    assert task["status"] == "failed"
    assert "queue unavailable" in task["error_message"]


def test_generation_worker_rolls_back_record_and_billing_when_success_mark_fails(app, monkeypatch):
    def fake_generate_image_with_failover(**_kwargs):
        return {
            "image_path": "/static/uploads/generated.png",
            "image_paths": ["/static/uploads/generated.png"],
            "actual_size": "2560x1440",
            "model_source": "fake",
            "elapsed_seconds": 0.1,
        }

    def fail_mark_generation_task_succeeded(_task_id, _record_id):
        raise RuntimeError("cannot mark succeeded")

    with app.app_context():
        user_id = create_user(points=20)
        upload_dir = app.config["OUTPUT_DIR"]
        upload_dir.mkdir(parents=True, exist_ok=True)
        (upload_dir / "generated.png").write_bytes(b"png")
        task_id = get_db().execute(
            """
            INSERT INTO generation_tasks
            (user_id, prompt, mode, ratio, resolution, actual_size, quality, output_format, count, cost, status, reference_paths, created_at, updated_at)
            VALUES (?, 'queued task', 'text', '16:9', '2K', '2560x1440', 'auto', 'png', 1, 2, 'queued', '[]', 'now', 'now')
            """,
            (user_id,),
        ).lastrowid
        get_db().commit()

    monkeypatch.setattr("huishi.generation_queue.generate_image_with_failover", fake_generate_image_with_failover)
    monkeypatch.setattr("huishi.generation_queue.mark_generation_task_succeeded", fail_mark_generation_task_succeeded)

    from huishi.generation_queue import run_generation_task

    run_generation_task(app, task_id, [])

    with app.app_context():
        task = get_db().execute("SELECT status, record_id, error_message FROM generation_tasks WHERE id = ?", (task_id,)).fetchone()
        records = get_db().execute("SELECT id FROM records WHERE user_id = ?", (user_id,)).fetchall()
        ledger = get_db().execute("SELECT id FROM point_ledger WHERE user_id = ?", (user_id,)).fetchall()
        user = get_db().execute("SELECT points FROM users WHERE id = ?", (user_id,)).fetchone()

        assert task["status"] == "failed"
        assert task["record_id"] is None
        assert "cannot mark succeeded" in task["error_message"]
        assert records == []
        assert ledger == []
        assert user["points"] == 20
        assert not (app.config["OUTPUT_DIR"] / "generated.png").exists()


def test_generate_with_new_workspace_dialogue_creates_dialogue(app, monkeypatch):
    def fake_generate_image_with_failover(**kwargs):
        return {
            "image_path": "/static/uploads/generated.png",
            "image_paths": ["/static/uploads/generated.png"],
            "actual_size": "2560x1440",
            "model_source": "fake",
            "elapsed_seconds": 0.1,
        }

    with app.app_context():
        user_id = create_user()

    monkeypatch.setattr(
        "huishi.generation_queue.generate_image_with_failover",
        fake_generate_image_with_failover,
    )

    with app.test_client() as client:
        login(client, user_id)
        response = client.post(
            "/generate",
            data={
                "prompt": "new workspace dialogue",
                "ratio": "16:9",
                "resolution": "2K",
                "quality": "auto",
                "output_format": "png",
                "count": "1",
                "dialogue_id": "",
                "create_dialogue": "1",
            },
            headers={"X-Requested-With": "fetch", "Accept": "application/json"},
        )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["dialogue"]["title"] == "new workspace dial..."
    assert payload["task"]["dialogue_id"] == payload["dialogue"]["id"]

    with app.app_context():
        dialogue_row = get_db().execute("SELECT id, title FROM dialogues ORDER BY id DESC LIMIT 1").fetchone()
        task_row = get_db().execute("SELECT dialogue_id, resolution, actual_size, reference_paths FROM generation_tasks ORDER BY id DESC LIMIT 1").fetchone()
        record_row = get_db().execute("SELECT dialogue_id, resolution, actual_size, reference_paths FROM records ORDER BY id DESC LIMIT 1").fetchone()

        assert dialogue_row["id"] == payload["dialogue"]["id"]
        assert task_row["dialogue_id"] == dialogue_row["id"]
        assert record_row["dialogue_id"] == dialogue_row["id"]
        assert task_row["resolution"] == "2K"
        assert task_row["actual_size"] == "2560x1440"
        assert record_row["resolution"] == "2K"
        assert record_row["actual_size"] == "2560x1440"


def test_serialized_record_keeps_reference_paths_for_workspace_render(app):
    with app.app_context():
        user_id = create_user()
        db = get_db()
        dialogue_id = db.execute(
            """
            INSERT INTO dialogues (user_id, title, created_at, updated_at)
            VALUES (?, 'ref', 'now', 'now')
            """,
            (user_id,),
        ).lastrowid
        db.execute(
            """
            INSERT INTO records
            (user_id, prompt, dialogue_id, image_path, image_paths, generation_group_id, group_index, mode, ratio, resolution, actual_size, quality, output_format, count, model_source, elapsed_seconds, points_charged, reference_paths, favorite, hidden, created_at)
            VALUES (?, 'prompt', ?, '/static/uploads/main.png', '["/static/uploads/main.png"]', 'g1', 0, 'reference', '16:9', '2K', '2560x1440', 'auto', 'png', 1, 'fake', 0.1, 2, '["/static/uploads/ref.png"]', 0, 0, 'now')
            """,
            (user_id, dialogue_id),
        )
        db.commit()

        record = db.execute("SELECT * FROM records ORDER BY id DESC LIMIT 1").fetchone()
        assert record["reference_paths"] == '["/static/uploads/ref.png"]'


def test_workspace_renders_reference_strip_before_prompt(app):
    with app.app_context():
        user_id = create_user()
        db = get_db()
        dialogue_id = db.execute(
            """
            INSERT INTO dialogues (user_id, title, created_at, updated_at)
            VALUES (?, 'ref order', 'now', 'now')
            """,
            (user_id,),
        ).lastrowid
        db.execute(
            """
            INSERT INTO records
            (user_id, prompt, dialogue_id, image_path, image_paths, generation_group_id, group_index, mode, ratio, resolution, actual_size, quality, output_format, count, model_source, elapsed_seconds, points_charged, reference_paths, favorite, hidden, created_at)
            VALUES (?, 'prompt with reference', ?, '/static/uploads/main.png', '["/static/uploads/main.png"]', 'g1', 0, 'reference', '16:9', '2K', '2560x1440', 'auto', 'png', 1, 'fake', 0.1, 2, '["/static/uploads/ref.png"]', 0, 0, 'now')
            """,
            (user_id, dialogue_id),
        )
        db.commit()

    with app.test_client() as client:
        login(client, user_id)
        response = client.get(f"/workspace?dialogue={dialogue_id}")

    html = response.get_data(as_text=True)
    start = html.index('<article class="creation-item is-featured"')
    end = html.index("</article>", start)
    article = html[start:end]

    assert article.index('data-record-references') < article.index('class="creation-prompt"')


def test_workspace_script_renders_reference_strip_before_prompt_and_mounts_tasks_in_current_canvas():
    source = Path("static/js/workspace.js").read_text(encoding="utf-8")

    render_current_start = source.index("function renderCurrentRecord(record, replaceElement = null)")
    task_preview_start = source.index("function taskReferencePreviewFromFormData(formData)")
    render_current_snippet = source[render_current_start:task_preview_start]
    assert render_current_snippet.index('data-record-references') < render_current_snippet.index('class="creation-prompt"')

    render_task_start = source.index("function renderTaskCard(formData)")
    render_task_end = source.index("function renderTaskCardFromTask(task)")
    render_task_snippet = source[render_task_start:render_task_end]
    assert 'const targetRegion =' not in render_task_snippet
    assert 'currentCanvas?.prepend(clone);' not in render_task_snippet
    assert 'currentCanvas?.appendChild(clone);' in render_task_snippet


def test_workspace_script_renders_each_media_type_with_its_native_player():
    source = Path("static/js/workspace.js").read_text(encoding="utf-8")

    render_start = source.index("function _buildImageGrid(records, prompt, returnUrl = \"/workspace\")")
    render_end = source.index("function findExistingCreationRecord(record)", render_start)
    render_snippet = source[render_start:render_end]

    assert "recordMediaType" in render_snippet
    assert "<audio" in render_snippet
    assert "<video" in render_snippet
    assert "data-media-type" in render_snippet


def test_restored_generation_tasks_insert_by_submitted_time():
    source = Path("static/js/workspace.js").read_text(encoding="utf-8")

    assert "function creationSortValue(element)" in source
    assert "function appendCreationElementBySubmittedTime(element)" in source
    assert "card.dataset.createdAt = task?.created_at ||" in source
    assert "appendCreationElementBySubmittedTime(card);" in source
    assert "currentCanvas?.appendChild(clone);" in source


def test_render_current_record_reuses_existing_record_or_group_card():
    source = Path("static/js/workspace.js").read_text(encoding="utf-8")

    assert "function findExistingCreationRecord(record)" in source
    find_start = source.index("function findExistingCreationRecord(record)")
    find_end = source.index("function renderCurrentRecord(record, replaceElement = null)", find_start)
    find_snippet = source[find_start:find_end]
    assert "data-record-id" in find_snippet
    assert "data-generation-group-id" in find_snippet

    render_start = source.index("function renderCurrentRecord(record, replaceElement = null)")
    render_end = source.index("function taskReferencePreviewFromFormData(formData)", render_start)
    render_snippet = source[render_start:render_end]
    assert "replaceElement ||= findExistingCreationRecord(record);" in render_snippet


def test_visible_generation_tasks_are_ordered_by_submitted_time():
    source = Path("huishi/records.py").read_text(encoding="utf-8")
    start = source.index("def list_visible_generation_tasks_for_user(")
    end = source.index("def list_active_generation_tasks_for_user", start)
    snippet = source[start:end]

    assert "base.created_at ASC" in snippet
    assert "base.id ASC" in snippet
    assert "base.updated_at" not in snippet


def test_workspace_hides_upstream_generation_error_details_from_users():
    from huishi.routes_workspace import _sanitize_generation_error_message

    raw = (
        "Error code: 403 - {'error': {'message': '预扣费额度失败, 用户剩余额度: $0.044500, "
        "需要预扣费额度: $0.050000 (request id: 202606172123599186431288268d9d6ZHWuAOOz)', "
        "'type': 'new_api_error', 'code': 'insufficient_user_quota'}}"
    )

    assert _sanitize_generation_error_message(raw) == "生成失败，请联系管理员"


def test_workspace_sort_preserves_generation_task_positions():
    source = Path("static/js/workspace.js").read_text(encoding="utf-8")
    sort_start = source.index("function bindWorkspaceFilterbar()")
    sort_end = source.index("function focusLatestCreation()", sort_start)
    sort_snippet = source[sort_start:sort_end]

    assert 'const children = Array.from(stream.children);' in sort_snippet
    assert 'children.forEach((child) => {' in sort_snippet
    assert 'child.classList.contains("creation-item") ? ordered[nextRecordIndex++] : child' in sort_snippet
    assert "creationSortValue(a)" in sort_snippet
    assert "creationSortValue(b)" in sort_snippet
    assert "Number(a.dataset.createdIndex || 0)" not in sort_snippet
    assert 'ordered.forEach((item) => stream.appendChild(item));' not in sort_snippet


def test_workspace_record_header_keeps_references_and_prompt_on_same_row():
    template = Path("templates/workspace.html").read_text(encoding="utf-8")
    source = Path("static/js/workspace.js").read_text(encoding="utf-8")
    css = Path("static/css/site.css").read_text(encoding="utf-8")

    assert 'data-created-at="{{ record[\'created_at\'] }}"' in template
    header_rule_start = css.index(".creation-record-head {")
    header_rule_end = css.index("}", header_rule_start)
    header_rule = css[header_rule_start:header_rule_end]
    assert "width: min(100%, var(--creation-result-width, 620px));" in header_rule
    assert "align-items: flex-start;" in header_rule
    assert "gap: 6px;" in header_rule

    template_header_start = template.index('<div class="creation-record-head">')
    template_header_end = template.index('<div class="creation-image-grid"', template_header_start)
    template_header = template[template_header_start:template_header_end]
    assert 'data-record-references' in template_header
    assert 'reference-material-stack' in template_header
    assert 'reference-material-list' in template_header
    assert 'reference-material-tile' in template_header
    assert 'style="--stack-index: {{ loop.index0 }};"' in template_header
    assert 'class="creation-prompt"' in template_header

    render_current_start = source.index("function renderCurrentRecord(record, replaceElement = null)")
    task_preview_start = source.index("function taskReferencePreviewFromFormData(formData)")
    render_current_snippet = source[render_current_start:task_preview_start]
    assert 'reference-material-stack' in render_current_snippet
    assert 'reference-material-list' in render_current_snippet
    assert 'renderReferenceStackItems(referenceList)' in render_current_snippet


def test_workspace_record_toolbar_aligns_to_image_width():
    template = Path("templates/workspace.html").read_text(encoding="utf-8")
    source = Path("static/js/workspace.js").read_text(encoding="utf-8")
    css = Path("static/css/site.css").read_text(encoding="utf-8")

    frame_start = css.index(".creation-result-frame {")
    frame_end = css.index("}", frame_start)
    frame_rule = css[frame_start:frame_end]

    assert "--creation-result-width: 620px;" in frame_rule
    assert "width: min(100%, var(--creation-result-width));" in frame_rule
    assert ".creation-result-frame .creation-image-grid" in css
    assert ".creation-result-frame .creation-toolbar" in css
    assert "justify-content: space-between;" in css[
        css.index(".creation-result-frame .creation-toolbar {"):
        css.index("}", css.index(".creation-result-frame .creation-toolbar {"))
    ]
    assert ".creation-result-frame .creation-action-group button" in css
    assert "border-radius: 999px;" in css[
        css.index(".creation-result-frame .creation-action-group button"):
        css.index("}", css.index(".creation-result-frame .creation-action-group button"))
    ]
    assert ".creation-result-frame .creation-meta span" in css
    assert "border-radius: 999px;" in css[
        css.index(".creation-result-frame .creation-meta span"):
        css.index("}", css.index(".creation-result-frame .creation-meta span"))
    ]
    assert ".creation-result-frame .creation-image-grid[data-image-count=\"1\"] .creation-image-link" in css
    assert ".creation-result-frame .creation-image-grid[data-image-count=\"1\"] .creation-image-link img" in css
    single_image_rule = css[
        css.index(".creation-result-frame .creation-image-grid[data-image-count=\"1\"] .creation-image-link img"):
        css.index("}", css.index(".creation-result-frame .creation-image-grid[data-image-count=\"1\"] .creation-image-link img"))
    ]
    assert "height: auto;" in single_image_rule
    assert "max-height: none;" in single_image_rule

    template_frame_start = template.index('<div class="creation-result-frame">')
    template_frame_end = template.index('</article>', template_frame_start)
    template_frame = template[template_frame_start:template_frame_end]
    assert template_frame.index('class="creation-image-grid"') < template_frame.index('class="creation-toolbar"')

    render_start = source.index("function renderCurrentRecord(record, replaceElement = null)")
    render_end = source.index("function taskReferencePreviewFromFormData(formData)")
    render_snippet = source[render_start:render_end]
    assert '<div class="creation-result-frame">' in render_snippet
    assert render_snippet.index('class="creation-image-grid"') < render_snippet.index('class="creation-toolbar"')


def test_workspace_generation_reference_thumb_is_clickable():
    source = Path("static/js/workspace.js").read_text(encoding="utf-8")
    summary_start = source.index("function rebuildTaskCardSummary(card)")
    format_task_start = source.index("function formatTaskParameterText")
    summary_snippet = source[summary_start:format_task_start]

    assert 'reference-material-stack' in summary_snippet
    assert 'reference-material-list' in summary_snippet
    assert 'data-task-reference-list' in summary_snippet
    assert 'renderReferenceStackItems(paths)' in source
    assert 'taskReferencePreviewsFromFormData(formData)' in source


def test_workspace_generation_reference_thumb_is_refreshed_from_server_task_paths():
    source = Path("static/js/workspace.js").read_text(encoding="utf-8")

    assert "function setTaskReferencePreview(card, previewPaths)" in source
    bind_start = source.index("function bindServerTaskToCard(card, task)")
    bind_end = source.index("async function restoreServerGenerationTask()", bind_start)
    bind_snippet = source[bind_start:bind_end]
    assert "setTaskReferencePreview(card, referencePaths);" in bind_snippet
    assert "card.classList.toggle(\"has-reference\", Boolean(paths.length));" in source


def test_workspace_render_current_record_keeps_reference_strip_visible():
    source = Path("static/js/workspace.js").read_text(encoding="utf-8")
    render_start = source.index("function renderCurrentRecord(record, replaceElement = null)")
    task_preview_start = source.index("function taskReferencePreviewFromFormData(formData)")
    render_snippet = source[render_start:task_preview_start]

    assert "renderReferenceStackItems(referenceList)" in render_snippet
    assert "referenceStrip.hidden = false;" in render_snippet
    assert "article.classList.toggle(\"has-reference\", Boolean(referenceList.length));" in render_snippet


def test_regenerate_asset_uses_provider_failover_for_platform_key(app, monkeypatch):
    captured = {}

    def fake_generate_image_with_failover(**kwargs):
        captured.update(kwargs)
        return {
            "image_path": "/static/uploads/regenerated.png",
            "image_paths": ["/static/uploads/regenerated.png"],
            "actual_size": "1024x1024",
            "model_source": "fake-provider",
            "elapsed_seconds": 0.1,
        }

    def fail_legacy_generate(**_kwargs):
        raise AssertionError("legacy generate_image should not be used for platform regenerate")

    with app.app_context():
        user_id = create_user(points=20)
        record_id = get_db().execute(
            """
            INSERT INTO records
            (user_id, prompt, image_path, image_paths, mode, ratio, resolution, actual_size, quality, output_format, count, created_at)
            VALUES (?, 'old prompt', '/static/uploads/old.png', '["/static/uploads/old.png"]', 'text', '1:1', '2K', '2048x2048', 'auto', 'png', 1, 'now')
            """,
            (user_id,),
        ).lastrowid
        get_db().commit()

    monkeypatch.setattr("huishi.routes_workspace.generate_image_with_failover", fake_generate_image_with_failover)
    monkeypatch.setattr("huishi.routes_workspace.generate_image", fail_legacy_generate)

    with app.test_client() as client:
        login(client, user_id)
        response = client.post(
            f"/assets/{record_id}/regenerate",
            headers={"X-Requested-With": "fetch", "Accept": "application/json"},
        )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert captured["prompt"] == "old prompt"
    assert "api_key" not in captured
    assert "base_url" not in captured


def test_workspace_record_actions_include_edit_image_after_refill():
    template = Path("templates/workspace.html").read_text(encoding="utf-8")
    source = Path("static/js/workspace.js").read_text(encoding="utf-8")

    template_actions_start = template.index('<button type="button" data-refill-record')
    template_actions_end = template.index('<form method="post" action="/assets/bulk/delete"', template_actions_start)
    template_actions = template[template_actions_start:template_actions_end]
    assert template_actions.index("data-refill-record") < template_actions.index("data-edit-record-images") < template_actions.index("data-regenerate-record")
    assert 'data-edit-image-paths=' in template_actions

    render_start = source.index("function renderCurrentRecord(record, replaceElement = null)")
    render_end = source.index("function taskReferencePreviewFromFormData(formData)")
    render_snippet = source[render_start:render_end]
    assert render_snippet.index("data-refill-record") < render_snippet.index("data-edit-record-images") < render_snippet.index("data-regenerate-record")
    assert "editImagePaths" in render_snippet


def test_edit_image_action_refills_generated_images_as_references():
    source = Path("static/js/workspace.js").read_text(encoding="utf-8")

    assert "function imagePathsForRecordEditing(records)" in source
    assert "function applyRecordImagesToComposer(button)" in source
    edit_start = source.index("function applyRecordImagesToComposer(button)")
    edit_end = source.index("function bindRecordActionButtons()", edit_start)
    edit_snippet = source[edit_start:edit_end]
    assert 'prompt: ""' in edit_snippet
    assert "prompt: button.dataset.prompt" not in edit_snippet
    assert "referencePaths: parseReferencePathList(button.dataset.editImagePaths || \"\")" in edit_snippet
    assert "applyComposerSeed({" in edit_snippet
    assert "submitImmediately" not in edit_snippet
    bind_start = source.index("function bindRecordActionButtons()")
    bind_end = source.index("function bindAssetRegenerateButtons()", bind_start)
    bind_snippet = source[bind_start:bind_end]
    assert "[data-edit-record-images]" in bind_snippet
    assert "applyRecordImagesToComposer(button)" in bind_snippet


def test_retry_failed_task_keeps_failure_card_if_retry_request_fails():
    source = Path("static/js/workspace.js").read_text(encoding="utf-8")

    form_data_start = source.index("function formDataFromTaskCard(card)")
    form_data_end = source.index("async function retryFailedTask(card)", form_data_start)
    form_data_snippet = source[form_data_start:form_data_end]
    assert 'formData.set("created_at", card?.dataset.createdAt || String(Date.now()));' in form_data_snippet

    retry_start = source.index("async function retryFailedTask(card)")
    retry_end = source.index("function restorePendingGeneration()", retry_start)
    retry_snippet = source[retry_start:retry_end]
    assert "if (card) card.hidden = true;" in retry_snippet
    assert "card?.remove();" not in retry_snippet
    assert "taskCard?.remove();" in retry_snippet
    assert "if (card) card.hidden = false;" in retry_snippet


def test_generation_task_prompt_is_clamped_beside_fixed_params():
    template = Path("templates/workspace.html").read_text(encoding="utf-8")
    source = Path("static/js/workspace.js").read_text(encoding="utf-8")
    css = Path("static/css/site.css").read_text(encoding="utf-8")

    template_progress = template[
        template.index('<div class="generation-progress-pill">'):
        template.index('</div>', template.index('<div class="generation-progress-pill">'))
    ]
    assert template_progress.index("data-task-progress") < template_progress.index("task-spinner")
    summary_start = source.index("function rebuildTaskCardSummary(card)")
    summary_end = source.index("function formatTaskParameterText", summary_start)
    summary_snippet = source[summary_start:summary_end]
    assert summary_snippet.index("data-task-progress") < summary_snippet.index("task-spinner")
    assert ".generation-task-copy {" in css
    assert "grid-template-columns: minmax(0, 1fr) auto;" in css
    assert ".generation-task-prompt.creation-prompt {" in css
    assert "-webkit-line-clamp: 2;" in css
    assert "text-indent: 1.5em;" in css
    assert ".generation-task-prompt.creation-prompt:hover," in css
    assert "grid-column: 1 / -1;" in css
    assert "background: var(--studio-floating) !important;" in css
    assert ".generation-task-params.creation-meta {" in css
    assert "grid-column: 2;" in css
    progress_rule_start = css.index(".generation-progress-pill {")
    progress_rule_end = css.index("}", progress_rule_start)
    progress_rule = css[progress_rule_start:progress_rule_end]
    assert "grid-column: 1;" in progress_rule


def test_workspace_generated_images_scale_on_hover():
    css = Path("static/css/site.css").read_text(encoding="utf-8")

    image_hover_start = css.index(".workspace-page .creation-image-link:hover img {")
    image_hover_end = css.index("}", image_hover_start)
    image_hover_rule = css[image_hover_start:image_hover_end]
    assert "scale(" not in image_hover_rule

    assert ".workspace-page .creation-reference-strip.reference-material-stack," in css
    assert ".workspace-page .generation-reference-stack.reference-material-stack {" in css
    assert "position: relative;" in css
    assert "width: 64px;" in css
    assert "height: 64px;" in css
    assert ".workspace-page .creation-reference-strip.reference-material-stack:hover,\n.workspace-page .generation-reference-stack.reference-material-stack:hover {" in css
    assert ".workspace-page .creation-reference-strip.reference-material-stack .reference-material-list," in css
    assert ".workspace-page .generation-reference-stack.reference-material-stack .reference-material-list {" in css


def test_workspace_reference_stack_tiles_zoom_when_expanded():
    css = Path("static/css/site.css").read_text(encoding="utf-8")

    assert ".workspace-page .creation-reference-strip.reference-material-stack:hover .reference-material-tile:hover," in css
    assert ".workspace-page .generation-reference-stack.reference-material-stack:hover .reference-material-tile:hover {" in css
    assert "scale(1.32)" in css


def test_generation_reference_stack_stays_in_summary_row():
    css = Path("static/css/site.css").read_text(encoding="utf-8")

    region_rule_start = css.index(".generation-task-region {")
    region_rule_end = css.index("}", region_rule_start)
    region_rule = css[region_rule_start:region_rule_end]
    assert "width: min(100%, var(--creation-result-width, 620px));" in region_rule
    assert ".generation-task-region { width: min(100%, var(--creation-result-width, 620px)); }" in css
    assert ".generation-task-region { width: min(100%, var(--creation-result-width, 620px)); }" in css[
        css.index("@media (max-width: 760px)"):
    ]
    card_rule_start = css.index(".generation-task-card {")
    card_rule_end = css.index("}", card_rule_start)
    card_rule = css[card_rule_start:card_rule_end]
    assert "width: 100%;" in card_rule
    stream_card_rule_start = css.index(".creation-stream > .generation-task-card {")
    stream_card_rule_end = css.index("}", stream_card_rule_start)
    stream_card_rule = css[stream_card_rule_start:stream_card_rule_end]
    assert "width: min(100%, var(--creation-result-width, 620px));" in stream_card_rule
    assert "justify-self: center;" in stream_card_rule
    summary_base_start = css.index(".generation-task-summary {")
    summary_base_end = css.index("}", summary_base_start)
    summary_base_rule = css[summary_base_start:summary_base_end]
    assert "width: 100%;" in summary_base_rule
    assert ".workspace-page .generation-reference-stack.reference-material-stack {" in css
    assert "grid-column: 1;" in css
    assert "grid-row: 1;" in css
    summary_rule_start = css.index(".workspace-page .generation-task-card.has-reference .generation-task-summary {")
    summary_rule_end = css.index("}", summary_rule_start)
    summary_rule = css[summary_rule_start:summary_rule_end]
    assert "grid-template-columns: 44px minmax(0, 1fr);" in summary_rule
    assert "column-gap: 0;" in summary_rule
    assert ".generation-task-card.has-reference .generation-task-summary { grid-template-columns: 44px minmax(0, 1fr); column-gap: 0; }" in css
    assert ".workspace-page .generation-task-card.has-reference .generation-task-copy {" in css
    assert "grid-column: 2;" in css
    assert "grid-row: 1;" in css
    assert "margin-left: 0;" in css[
        css.index(".workspace-page .generation-task-card.has-reference .generation-task-copy {"):
        css.index("}", css.index(".workspace-page .generation-task-card.has-reference .generation-task-copy {"))
    ]


def test_generation_task_reference_stack_is_offset_toward_prompt_corner():
    css = Path("static/css/site.css").read_text(encoding="utf-8")

    rule_start = css.index(".workspace-page .generation-task-card.has-reference .generation-reference-stack.reference-material-stack {")
    rule_end = css.index("}", rule_start)
    rule = css[rule_start:rule_end]

    assert "margin-left: 4px;" in rule
    assert "margin-top: -8px;" in rule


def test_generation_task_without_reference_starts_at_first_column():
    css = Path("static/css/site.css").read_text(encoding="utf-8")

    assert ".workspace-page .generation-task-copy {" not in css
    assert ".workspace-page .generation-task-card.has-reference .generation-task-copy {" in css
    assert ".workspace-page .creation-reference-strip.reference-material-stack[hidden]," in css
    assert ".workspace-page .generation-reference-stack.reference-material-stack[hidden] {" in css
    assert "display: none;" in css


def test_workspace_reference_preview_does_not_open_new_page():
    source = Path("static/js/workspace.js").read_text(encoding="utf-8")
    template = Path("templates/workspace.html").read_text(encoding="utf-8")

    assert 'window.open(item.src, "_blank", "noopener");' not in source
    assert 'openReferencePreview(item);' in source
    assert 'target="_blank" rel="noopener" aria-label="查看参考图"' not in template
    assert 'data-reference-preview-path="{{ reference_path }}"' in template


def test_workspace_reference_previews_use_shared_preview_modal_hooks():
    source = Path("static/js/workspace.js").read_text(encoding="utf-8")

    assert 'data-reference-preview-path="${escapeAttribute(path)}"' in source
    assert 'data-task-reference-list' in source
    assert 'currentCanvas?.addEventListener("click", (event) => {' in source
    assert 'openReferencePreview({ src: path, name: "参考图" });' in source


def test_workspace_generation_count_max_comes_from_config():
    template = Path("templates/workspace.html").read_text(encoding="utf-8")
    source = Path("static/js/workspace.js").read_text(encoding="utf-8")

    assert 'data-max-generation-count=' in template
    assert 'max="{{ config.get(\'MAX_GENERATION_COUNT\', 10) }}"' in template
    assert 'const maxGenerationCount = Number.parseInt(form?.dataset.maxGenerationCount || countInput?.max || "10", 10) || 10;' in source
    assert "const max = Number(countInput.max || 10);" in source
    assert 'countInput.max = String(maxGenerationCount);' in source


def test_workspace_generation_count_max_renders_config_value(app):
    app.config["MAX_GENERATION_COUNT"] = 4
    with app.app_context():
        user_id = create_user()

    with app.test_client() as client:
        login(client, user_id)
        response = client.get("/workspace?new=1")

    html = response.get_data(as_text=True)
    assert "data-max-generation-count='4'" in html
    assert 'name="count" type="number" min="1" max="4"' in html


def test_failed_task_replaces_generation_summary_with_failure_panel():
    source = Path("static/js/workspace.js").read_text(encoding="utf-8")
    mark_failed_start = source.index("function markTaskFailed(card, message)")
    mark_failed_end = source.index("async function submitGeneration(event)")
    mark_failed_snippet = source[mark_failed_start:mark_failed_end]

    assert 'const summary = card.querySelector(".generation-task-summary");' in mark_failed_snippet
    assert "summary.replaceWith(failurePanel);" in mark_failed_snippet
    assert "card.prepend(failurePanel);" in mark_failed_snippet
    assert 'card.querySelector(".generation-task-summary")?.remove();' not in mark_failed_snippet
    assert mark_failed_snippet.index("<dt>提示词</dt>") < mark_failed_snippet.index("<dt>参数</dt>")
    assert mark_failed_snippet.index("<dt>参数</dt>") < mark_failed_snippet.index("<dt>积分</dt>")


def test_delete_dialogue_hides_own_records_and_removes_dialogue(app):
    with app.app_context():
        user_id = create_user()
        other_user_id = create_user(username="other")
        db = get_db()
        own_dialogue = db.execute(
            """
            INSERT INTO dialogues (user_id, title, created_at, updated_at)
            VALUES (?, 'own', 'now', 'now')
            """,
            (user_id,),
        ).lastrowid
        other_dialogue = db.execute(
            """
            INSERT INTO dialogues (user_id, title, created_at, updated_at)
            VALUES (?, 'other', 'now', 'now')
            """,
            (other_user_id,),
        ).lastrowid
        db.execute(
            """
            INSERT INTO records
            (user_id, prompt, dialogue_id, image_path, image_paths, generation_group_id, group_index, mode, ratio, resolution, actual_size, quality, output_format, count, model_source, elapsed_seconds, points_charged, reference_paths, favorite, hidden, created_at)
            VALUES (?, 'own prompt', ?, '/static/uploads/own.png', '[]', 'g1', 0, 'text', '16:9', '2K', '2560x1440', 'auto', 'png', 1, 'fake', 0.1, 2, '[]', 0, 0, 'now')
            """,
            (user_id, own_dialogue),
        )
        db.execute(
            """
            INSERT INTO records
            (user_id, prompt, dialogue_id, image_path, image_paths, generation_group_id, group_index, mode, ratio, resolution, actual_size, quality, output_format, count, model_source, elapsed_seconds, points_charged, reference_paths, favorite, hidden, created_at)
            VALUES (?, 'other prompt', ?, '/static/uploads/other.png', '[]', 'g2', 0, 'text', '16:9', '2K', '2560x1440', 'auto', 'png', 1, 'fake', 0.1, 2, '[]', 0, 0, 'now')
            """,
            (other_user_id, other_dialogue),
        )
        get_db().commit()

    with app.test_client() as client:
        login(client, user_id)
        response = client.post(
            f"/api/dialogues/{own_dialogue}/delete",
            headers={"X-Requested-With": "fetch", "Accept": "application/json"},
        )

    assert response.status_code == 200
    assert response.get_json()["ok"] is True

    with app.app_context():
        own_dialogue_row = get_db().execute("SELECT * FROM dialogues WHERE id = ?", (own_dialogue,)).fetchone()
        own_record = get_db().execute("SELECT hidden, dialogue_id FROM records WHERE prompt = ?", ("own prompt",)).fetchone()
        other_dialogue_row = get_db().execute("SELECT * FROM dialogues WHERE id = ?", (other_dialogue,)).fetchone()
        other_record = get_db().execute("SELECT hidden FROM records WHERE dialogue_id = ?", (other_dialogue,)).fetchone()

        assert own_dialogue_row is None
        assert own_record["hidden"] == 1
        assert own_record["dialogue_id"] is None
        assert other_dialogue_row is not None
        assert other_record["hidden"] == 0


def test_workspace_nav_shows_canvas_before_assets():
    template = Path("templates/partials/studio_nav.html").read_text(encoding="utf-8")

    assert "画布" in template
    assert "资产" in template
    assert template.index("画布") < template.index("资产")


def test_workspace_nav_shows_prompt_library_below_assets():
    template = Path("templates/partials/studio_nav.html").read_text(encoding="utf-8")

    assert 'href="/assets"' in template
    assert 'href="/prompts"' in template
    assert "提示词库" in template
    assert template.index('href="/assets"') < template.index('href="/prompts"')


def test_prompts_page_embeds_canvas_prompt_library(app):
    app.config["CANVAS_APP_URL"] = "http://127.0.0.1:3000"
    with app.app_context():
        user_id = create_user()

    with app.test_client() as client:
        login(client, user_id)
        response = client.get("/prompts")

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'title="提示词库"' in html
    assert "http://127.0.0.1:3000/prompts" in html
    assert 'active_nav = "prompts"' in Path("templates/prompts.html").read_text(encoding="utf-8")


def test_assets_template_has_send_to_canvas_button():
    template = Path("templates/assets.html").read_text(encoding="utf-8")

    assert "asset-time-filter" in template
    assert "data-filter-time" in template


def test_workspace_defaults_to_light_while_canvas_remains_light_until_theme_bridge():
    workspace_theme = Path("static/js/theme.js").read_text(encoding="utf-8")
    canvas_theme = Path("infinite-canvas/web/src/stores/use-theme-store.ts").read_text(encoding="utf-8")

    assert 'return "light";' in workspace_theme
    assert 'const THEME_VALUES = new Set(["light", "dark"]);' in workspace_theme
    assert 'theme: "light"' in canvas_theme
    assert 'fixedConsoleTheme()' not in workspace_theme


def test_canvas_template_has_bridge_handshake():
    template = Path("templates/canvas.html").read_text(encoding="utf-8")

    assert "huishi-canvas-import" in template
    assert "huishi-canvas-ready" in template
    assert "huishi-canvas-ping" in template


def test_canvas_loading_overlay_handles_cached_iframe_load():
    template = Path("templates/canvas.html").read_text(encoding="utf-8")

    assert "this.dataset.loaded = 'true'" in template
    assert 'frame.dataset.loaded === "true"' in template


def test_canvas_page_renders_embedded_shell(app):
    app.config["CANVAS_APP_URL"] = "http://127.0.0.1:3000"
    with app.app_context():
        user_id = create_user()

    with app.test_client() as client:
        login(client, user_id)
        response = client.get("/canvas")

    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'class="canvas-frame-wrap canvas-embed-frame"' in html
    assert "partials/canvas_nav.html" not in Path("templates/canvas.html").read_text(encoding="utf-8")
    assert "http://127.0.0.1:3000/canvas" in html
    assert "data-canvas-export-assets" not in html
    assert "????" not in html
    assert "???" not in html
    assert "????" not in html

def test_canvas_page_embeds_host_session_bootstrap(app):
    from huishi.providers import save_canvas_setting

    app.config["CANVAS_APP_URL"] = "http://127.0.0.1:3000"
    with app.app_context():
        save_canvas_setting("canvas_app_url", "http://127.0.0.1:3000")
        user_id = create_user()
        get_db().commit()

    with app.test_client() as client:
        login(client, user_id)
        response = client.get("/canvas")

    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "host_mode=huishi" in html
    assert "host_session_token=" in html
    assert "host_session_verify_url=" in html


def test_canvas_page_defaults_to_recent_embed_mode(app):
    from huishi.providers import save_canvas_setting

    app.config["CANVAS_APP_URL"] = "http://127.0.0.1:3000"
    with app.app_context():
        save_canvas_setting("canvas_app_url", "http://127.0.0.1:3000")
        user_id = create_user()
        get_db().commit()

    with app.test_client() as client:
        login(client, user_id)
        response = client.get("/canvas")

    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "mode=recent" in html


def test_canvas_shell_uses_full_stage_layout():
    css = Path("static/css/site.css").read_text(encoding="utf-8")

    assert ".canvas-embed-page .studio-shell {" in css
    assert ".canvas-embed-page .canvas-embed-frame {" in css
    assert ".canvas-embed-page .canvas-embed-frame .canvas-frame {" not in css or ".canvas-embed-page .canvas-embed-frame iframe" in css
    assert ".canvas-workspace-topbar" not in css
    assert ".canvas-page .canvas-shell" not in css
