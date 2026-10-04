from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from app import create_app
from huishi.db import get_db, init_db
from huishi.records import create_record, list_records_for_user, normalize_record
from huishi.storage import sweep_local_uploads
from huishi.upload_storage import get_upload_storage


@pytest.fixture()
def app(tmp_path):
    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "test.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"
    app.config["OUTPUT_DIR"].mkdir(parents=True, exist_ok=True)
    with app.app_context():
        init_db()
    yield app


def _write_upload(output_dir: Path, name: str, *, size: int = 8, age_seconds: int = 7200) -> Path:
    path = output_dir / name
    path.write_bytes(b"x" * size)
    old_timestamp = time.time() - age_seconds
    os.utime(path, (old_timestamp, old_timestamp))
    return path


def _create_user(db) -> int:
    db.execute(
        "INSERT INTO users (username, email, password_hash, role, points, email_verified, created_at) VALUES (?, ?, 'hash', 'user', 100, 1, 'now')",
        ("storage-user", "storage@example.com"),
    )
    return int(db.execute("SELECT id FROM users WHERE email = ?", ("storage@example.com",)).fetchone()["id"])


def test_sweep_local_uploads_deletes_old_orphans_and_preserves_referenced_files(app):
    with app.app_context():
        output_dir = app.config["OUTPUT_DIR"]
        _write_upload(output_dir, "main.png")
        _write_upload(output_dir, "extra.png")
        _write_upload(output_dir, "ref.png")
        _write_upload(output_dir, "orphan.png")
        _write_upload(output_dir, "fresh-orphan.png", age_seconds=10)

        user_id = _create_user(get_db())
        create_record(
            user_id=user_id,
            prompt="keep files",
            image_path="/static/uploads/main.png",
            mode="reference",
            ratio="16:9",
            resolution="2K",
            actual_size="2560x1440",
            quality="auto",
            output_format="png",
            count=1,
            model_source="fake",
            elapsed_seconds=0.1,
            points_charged=1,
            reference_paths=["/static/uploads/ref.png"],
            image_paths=["/static/uploads/main.png", "/static/uploads/extra.png"],
        )
        get_db().execute(
            """
            INSERT INTO generation_tasks
            (user_id, prompt, mode, ratio, resolution, actual_size, quality, output_format, count, cost, status, reference_paths, created_at, updated_at)
            VALUES (?, 'pending', 'reference', '16:9', '2K', '2560x1440', 'auto', 'png', 1, 1, 'queued', ?, 'now', 'now')
            """,
            (user_id, '["/static/uploads/ref.png"]'),
        )
        get_db().commit()

        result = sweep_local_uploads(output_dir, get_db(), retention_seconds=3600)

        assert result.deleted_files == ["/static/uploads/orphan.png"]
        assert not (output_dir / "orphan.png").exists()
        assert (output_dir / "fresh-orphan.png").exists()
        assert (output_dir / "main.png").exists()
        assert (output_dir / "extra.png").exists()
        assert (output_dir / "ref.png").exists()
        assert result.referenced_files == 3
        assert result.orphan_files == 2


def test_record_visibility_uses_upload_storage_exists(app, monkeypatch):
    with app.app_context():
        user_id = _create_user(get_db())
        create_record(
            user_id=user_id,
            prompt="remote only",
            image_path="/static/uploads/remote-only.png",
            mode="text",
            ratio="1:1",
            resolution="1K",
            actual_size="1024x1024",
            quality="auto",
            output_format="png",
            count=1,
            model_source="fake",
            elapsed_seconds=0.1,
            points_charged=1,
            image_paths=["/static/uploads/remote-only.png"],
        )
        get_db().commit()
        storage = get_upload_storage()
        monkeypatch.setattr(storage, "exists", lambda key: key == "remote-only.png")

        records = list_records_for_user(user_id)

        assert [record["image_path"] for record in records] == [
            "/static/uploads/remote-only.png"
        ]


def test_sweeper_deletes_through_upload_storage(app):
    deleted: list[str] = []

    class Storage:
        def delete(self, key: str) -> None:
            deleted.append(key)
            (app.config["OUTPUT_DIR"] / key).unlink(missing_ok=True)

    with app.app_context():
        _write_upload(app.config["OUTPUT_DIR"], "orphan.png")

        result = sweep_local_uploads(
            app.config["OUTPUT_DIR"],
            get_db(),
            retention_seconds=0,
            min_age_seconds=0,
            storage=Storage(),
        )

    assert result.deleted_files == ["/static/uploads/orphan.png"]
    assert deleted == ["orphan.png"]


def test_sweep_local_uploads_reports_capacity_pressure_without_deleting_referenced_files(app):
    with app.app_context():
        output_dir = app.config["OUTPUT_DIR"]
        _write_upload(output_dir, "large.png", size=32)
        user_id = _create_user(get_db())
        create_record(
            user_id=user_id,
            prompt="keep large",
            image_path="/static/uploads/large.png",
            mode="text",
            ratio="16:9",
            resolution="2K",
            actual_size="2560x1440",
            quality="auto",
            output_format="png",
            count=1,
            model_source="fake",
            elapsed_seconds=0.1,
            points_charged=1,
            image_paths=["/static/uploads/large.png"],
        )
        get_db().commit()

        result = sweep_local_uploads(output_dir, get_db(), retention_seconds=0, max_bytes=16)

        assert result.deleted_files == []
        assert (output_dir / "large.png").exists()
        assert result.total_bytes == 32
        assert result.max_bytes == 16
        assert result.over_capacity_bytes == 16
        assert result.capacity_warning is True


def test_sweep_local_uploads_can_remove_files_from_hidden_records_after_retention(app):
    with app.app_context():
        output_dir = app.config["OUTPUT_DIR"]
        _write_upload(output_dir, "deleted.png")
        user_id = _create_user(get_db())
        record_id = create_record(
            user_id=user_id,
            prompt="deleted asset",
            image_path="/static/uploads/deleted.png",
            mode="text",
            ratio="16:9",
            resolution="2K",
            actual_size="2560x1440",
            quality="auto",
            output_format="png",
            count=1,
            model_source="fake",
            elapsed_seconds=0.1,
            points_charged=1,
            image_paths=["/static/uploads/deleted.png"],
        )
        get_db().execute("UPDATE records SET hidden = 1 WHERE id = ?", (record_id,))
        get_db().commit()

        result = sweep_local_uploads(output_dir, get_db(), retention_seconds=3600)

        assert result.deleted_files == ["/static/uploads/deleted.png"]
        assert not (output_dir / "deleted.png").exists()


def test_sweep_local_uploads_uses_separate_orphan_and_hidden_retention(app):
    with app.app_context():
        output_dir = app.config["OUTPUT_DIR"]
        _write_upload(output_dir, "old-orphan.png", age_seconds=10 * 86400)
        _write_upload(output_dir, "recent-orphan.png", age_seconds=2 * 86400)
        _write_upload(output_dir, "hidden-retained.png", age_seconds=10 * 86400)
        _write_upload(output_dir, "hidden-deleted.png", age_seconds=20 * 86400)
        user_id = _create_user(get_db())
        retained_record_id = create_record(
            user_id=user_id,
            prompt="hidden retained",
            image_path="/static/uploads/hidden-retained.png",
            mode="text",
            ratio="16:9",
            resolution="2K",
            actual_size="2560x1440",
            quality="auto",
            output_format="png",
            count=1,
            model_source="fake",
            elapsed_seconds=0.1,
            points_charged=1,
            image_paths=["/static/uploads/hidden-retained.png"],
        )
        deleted_record_id = create_record(
            user_id=user_id,
            prompt="hidden deleted",
            image_path="/static/uploads/hidden-deleted.png",
            mode="text",
            ratio="16:9",
            resolution="2K",
            actual_size="2560x1440",
            quality="auto",
            output_format="png",
            count=1,
            model_source="fake",
            elapsed_seconds=0.1,
            points_charged=1,
            image_paths=["/static/uploads/hidden-deleted.png"],
        )
        get_db().execute("UPDATE records SET hidden = 1 WHERE id IN (?, ?)", (retained_record_id, deleted_record_id))
        get_db().commit()

        result = sweep_local_uploads(
            output_dir,
            get_db(),
            retention_seconds=14 * 86400,
            orphan_retention_seconds=7 * 86400,
            hidden_retention_seconds=14 * 86400,
        )

        assert result.deleted_files == ["/static/uploads/hidden-deleted.png", "/static/uploads/old-orphan.png"]
        assert result.hidden_files == 2
        assert result.orphan_files == 2
        assert not (output_dir / "old-orphan.png").exists()
        assert (output_dir / "recent-orphan.png").exists()
        assert (output_dir / "hidden-retained.png").exists()
        assert not (output_dir / "hidden-deleted.png").exists()


def test_sweep_local_uploads_batch_size_does_not_limit_retention_cleanup_by_default(app):
    with app.app_context():
        output_dir = app.config["OUTPUT_DIR"]
        _write_upload(output_dir, "old-a.png", age_seconds=20 * 86400)
        _write_upload(output_dir, "old-b.png", age_seconds=19 * 86400)
        _write_upload(output_dir, "old-c.png", age_seconds=18 * 86400)

        result = sweep_local_uploads(
            output_dir,
            get_db(),
            retention_seconds=7 * 86400,
            orphan_retention_seconds=7 * 86400,
            batch_size=2,
        )

        assert result.deleted_files == [
            "/static/uploads/old-a.png",
            "/static/uploads/old-b.png",
            "/static/uploads/old-c.png",
        ]
        assert result.retained_orphan_files == []
        assert not (output_dir / "old-a.png").exists()
        assert not (output_dir / "old-b.png").exists()
        assert not (output_dir / "old-c.png").exists()


def test_sweep_local_uploads_reports_remaining_files_after_delete_limit(app):
    with app.app_context():
        output_dir = app.config["OUTPUT_DIR"]
        _write_upload(output_dir, "old-a.png", age_seconds=20 * 86400)
        _write_upload(output_dir, "old-b.png", age_seconds=19 * 86400)
        _write_upload(output_dir, "old-c.png", age_seconds=18 * 86400)

        result = sweep_local_uploads(
            output_dir,
            get_db(),
            retention_seconds=7 * 86400,
            orphan_retention_seconds=7 * 86400,
            max_delete_files=2,
        )

        assert result.deleted_files == ["/static/uploads/old-a.png", "/static/uploads/old-b.png"]
        assert result.max_delete_files == 2
        assert result.delete_limit_reached is True
        assert result.remaining_deletable_files == 1
        assert result.retained_due_to_delete_limit == ["/static/uploads/old-c.png"]
        assert not (output_dir / "old-a.png").exists()
        assert not (output_dir / "old-b.png").exists()
        assert (output_dir / "old-c.png").exists()


def test_sweep_local_uploads_retains_recent_files_even_when_retention_is_zero(app):
    with app.app_context():
        output_dir = app.config["OUTPUT_DIR"]
        now = time.time()
        recent = _write_upload(output_dir, "recent-output.png", age_seconds=10)
        old = _write_upload(output_dir, "old-output.png", age_seconds=600)

        result = sweep_local_uploads(
            output_dir,
            get_db(),
            retention_seconds=0,
            orphan_retention_seconds=0,
            now=now,
        )

        assert result.deleted_files == ["/static/uploads/old-output.png"]
        assert result.retained_orphan_files == ["/static/uploads/recent-output.png"]
        assert recent.exists()
        assert not old.exists()


def test_sweep_local_uploads_ignores_dotfiles_and_keep_files(app):
    with app.app_context():
        output_dir = app.config["OUTPUT_DIR"]
        _write_upload(output_dir, ".gitkeep", age_seconds=30 * 86400)
        _write_upload(output_dir, ".keep", age_seconds=30 * 86400)
        _write_upload(output_dir, "old-orphan.png", age_seconds=30 * 86400)

        result = sweep_local_uploads(
            output_dir,
            get_db(),
            retention_seconds=7 * 86400,
            orphan_retention_seconds=7 * 86400,
        )

        assert result.deleted_files == ["/static/uploads/old-orphan.png"]
        assert (output_dir / ".gitkeep").exists()
        assert (output_dir / ".keep").exists()
        assert not (output_dir / "old-orphan.png").exists()


def test_storage_sweep_cli_defaults_to_dry_run_and_delete_requires_flag(app):
    with app.app_context():
        output_dir = app.config["OUTPUT_DIR"]
        _write_upload(output_dir, "old-orphan.png")

    runner = app.test_cli_runner()
    preview = runner.invoke(args=["storage-sweep", "--retention-days", "0"])

    assert preview.exit_code == 0
    assert "dry_run=True" in preview.output
    assert "/static/uploads/old-orphan.png" in preview.output
    assert (app.config["OUTPUT_DIR"] / "old-orphan.png").exists()

    delete = runner.invoke(args=["storage-sweep", "--retention-days", "0", "--delete"])

    assert delete.exit_code == 0
    assert "dry_run=False" in delete.output
    assert not (app.config["OUTPUT_DIR"] / "old-orphan.png").exists()


def test_storage_sweep_cli_supports_separate_retention_windows(app):
    with app.app_context():
        output_dir = app.config["OUTPUT_DIR"]
        _write_upload(output_dir, "old-orphan.png", age_seconds=10 * 86400)
        _write_upload(output_dir, "hidden-retained.png", age_seconds=10 * 86400)
        user_id = _create_user(get_db())
        record_id = create_record(
            user_id=user_id,
            prompt="hidden retained",
            image_path="/static/uploads/hidden-retained.png",
            mode="text",
            ratio="16:9",
            resolution="2K",
            actual_size="2560x1440",
            quality="auto",
            output_format="png",
            count=1,
            model_source="fake",
            elapsed_seconds=0.1,
            points_charged=1,
            image_paths=["/static/uploads/hidden-retained.png"],
        )
        get_db().execute("UPDATE records SET hidden = 1 WHERE id = ?", (record_id,))
        get_db().commit()

    runner = app.test_cli_runner()
    result = runner.invoke(
        args=[
            "storage-sweep",
            "--orphan-retention-days",
            "7",
            "--hidden-retention-days",
            "14",
            "--delete",
        ]
    )

    assert result.exit_code == 0
    assert "orphan_retention_days=7" in result.output
    assert "hidden_retention_days=14" in result.output
    assert "/static/uploads/old-orphan.png" in result.output
    assert not (app.config["OUTPUT_DIR"] / "old-orphan.png").exists()
    assert (app.config["OUTPUT_DIR"] / "hidden-retained.png").exists()


def test_storage_sweep_cli_reports_max_delete_files_limit(app):
    with app.app_context():
        app.config["STORAGE_SWEEP_MAX_DELETE_FILES"] = 1
        output_dir = app.config["OUTPUT_DIR"]
        _write_upload(output_dir, "old-a.png", age_seconds=10 * 86400)
        _write_upload(output_dir, "old-b.png", age_seconds=10 * 86400)

    runner = app.test_cli_runner()
    result = runner.invoke(args=["storage-sweep", "--orphan-retention-days", "7", "--delete"])

    assert result.exit_code == 0
    assert "max_delete_files=1" in result.output
    assert "delete_limit_reached=True" in result.output
    assert "remaining_deletable_files=1" in result.output


def test_storage_sweep_cli_defaults_to_large_delete_safety_limit(app):
    with app.app_context():
        output_dir = app.config["OUTPUT_DIR"]
        _write_upload(output_dir, "old-a.png", age_seconds=10 * 86400)
        _write_upload(output_dir, "old-b.png", age_seconds=10 * 86400)

    runner = app.test_cli_runner()
    result = runner.invoke(args=["storage-sweep", "--orphan-retention-days", "7", "--delete"])

    assert result.exit_code == 0
    assert "max_delete_files=20000" in result.output
    assert "delete_limit_reached=False" in result.output
    assert not (app.config["OUTPUT_DIR"] / "old-a.png").exists()
    assert not (app.config["OUTPUT_DIR"] / "old-b.png").exists()


def test_storage_sweep_cli_reports_min_age_safety_window(app):
    with app.app_context():
        app.config["STORAGE_SWEEP_MIN_AGE_SECONDS"] = 123
        output_dir = app.config["OUTPUT_DIR"]
        _write_upload(output_dir, "recent-output.png", age_seconds=10)

    runner = app.test_cli_runner()
    result = runner.invoke(args=["storage-sweep", "--orphan-retention-days", "0", "--delete"])

    assert result.exit_code == 0
    assert "min_age_seconds=123" in result.output
    assert "deleted_files=0" in result.output
    assert (app.config["OUTPUT_DIR"] / "recent-output.png").exists()
