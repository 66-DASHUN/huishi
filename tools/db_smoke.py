from __future__ import annotations

import argparse
from collections.abc import MutableMapping
import os
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from werkzeug.security import generate_password_hash

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app
from huishi.db import get_db, init_db, transaction, utc_now
from huishi.providers import delete_provider, get_canvas_settings, save_canvas_setting, save_provider
from huishi.records import (
    active_generation_task_count_for_user,
    create_generation_task,
    create_record,
    mark_generation_task_running,
    mark_generation_task_succeeded,
)
from huishi.routes_admin import delete_user_cascade
from huishi.storage import sweep_local_uploads


def masked_dsn(dsn: str) -> str:
    try:
        parts = urlsplit(dsn)
    except ValueError:
        return "[invalid-dsn]"
    netloc = parts.netloc
    if "@" in netloc:
        userinfo, hostinfo = netloc.rsplit("@", 1)
        user = userinfo.split(":", 1)[0]
        netloc = f"{user}:***@{hostinfo}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def assert_postgres_database_url(dsn: str, *, allow_sqlite: bool) -> None:
    scheme = dsn.split(":", 1)[0].lower() if ":" in dsn else ""
    if scheme in {"postgres", "postgresql"}:
        return
    if allow_sqlite and (scheme == "sqlite" or not dsn):
        return
    raise SystemExit("DATABASE_URL must use postgresql:// for this smoke test. Pass --allow-sqlite only for local script debugging.")


def configure_smoke_environment(dsn: str, environment: MutableMapping[str, str] | None = None) -> None:
    target = os.environ if environment is None else environment
    target["HUISHI_TEST_DATABASE_URL"] = dsn
    scheme = dsn.split(":", 1)[0].lower() if ":" in dsn else ""
    target["HUISHI_TEST_REQUIRE_POSTGRES"] = "1" if scheme in {"postgres", "postgresql"} else "0"


def pass_step(name: str) -> None:
    print(f"PASS {name}")


def fail_step(name: str, exc: BaseException) -> None:
    print(f"FAIL {name}: {exc}", file=sys.stderr)


def run_smoke() -> dict[str, int | str]:
    suffix = uuid.uuid4().hex[:10]
    username = f"pg_smoke_{suffix}"
    email = f"{username}@example.test"
    provider_id: int | None = None
    user_id: int | None = None
    previous_canvas_url: str | None = None

    app = create_app(testing=True)
    output_dir = Path(app.config["OUTPUT_DIR"])
    output_dir.mkdir(parents=True, exist_ok=True)
    ref_file = output_dir / f"{username}-ref.png"
    out_file = output_dir / f"{username}-out.png"
    ref_path = f"/static/uploads/{ref_file.name}"
    out_path = f"/static/uploads/{out_file.name}"

    with app.app_context():
        try:
            init_db()
            pass_step("schema_init")
            db = get_db()

            row = db.execute("SELECT COUNT(*) AS value FROM users").fetchone()
            assert row is not None
            pass_step("basic_select")

            rollback_username = f"{username}_rollback"
            try:
                db.execute(
                    """
                    INSERT INTO users (username, email, password_hash, role, email_verified, points, created_at)
                    VALUES (?, ?, ?, 'user', 1, 0, ?)
                    """,
                    (
                        rollback_username,
                        f"{rollback_username}@example.test",
                        generate_password_hash("rollback-password"),
                        utc_now(),
                    ),
                )
                raise RuntimeError("force rollback")
            except RuntimeError:
                db.rollback()
            rollback_row = db.execute("SELECT COUNT(*) AS value FROM users WHERE username = ?", (rollback_username,)).fetchone()
            assert rollback_row is not None and int(rollback_row["value"]) == 0
            pass_step("transaction_rollback")

            conflict_key = f"pg_smoke_conflict_{suffix}"
            db.execute(
                """
                INSERT OR IGNORE INTO app_settings (key, value, updated_at)
                VALUES (?, 'first', ?)
                """,
                (conflict_key, utc_now()),
            )
            db.execute(
                """
                INSERT OR IGNORE INTO app_settings (key, value, updated_at)
                VALUES (?, 'second', ?)
                """,
                (conflict_key, utc_now()),
            )
            conflict_row = db.execute("SELECT value FROM app_settings WHERE key = ?", (conflict_key,)).fetchone()
            assert conflict_row is not None and conflict_row["value"] == "first"
            db.execute("DELETE FROM app_settings WHERE key = ?", (conflict_key,))
            db.commit()
            pass_step("insert_or_ignore_conflict")

            user_id = int(
                db.execute(
                    """
                    INSERT INTO users (username, email, password_hash, role, email_verified, points, created_at)
                    VALUES (?, ?, ?, 'user', 1, 100, ?)
                    """,
                    (username, email, generate_password_hash("smoke-password"), utc_now()),
                ).lastrowid
            )
            db.commit()
            assert user_id > 0
            pass_step("user_insert")

            provider_id = save_provider(
                provider_type="image",
                name=f"PG Smoke Provider {suffix}",
                base_url="https://example.invalid",
                api_key=f"smoke-key-{suffix}",
                model="gpt-image-2",
                priority=10,
                enabled=True,
                resolutions=["1K", "2K"],
            )
            canvas_settings = get_canvas_settings()
            previous_canvas_url = str(canvas_settings.get("canvas_app_url") or "")
            save_canvas_setting("canvas_app_url", "http://127.0.0.1:3000")
            db.commit()
            provider = db.execute("SELECT * FROM api_providers WHERE id = ?", (provider_id,)).fetchone()
            assert provider is not None and provider["name"].startswith("PG Smoke Provider")
            assert get_canvas_settings()["canvas_app_url"] == "http://127.0.0.1:3000"
            pass_step("provider_and_canvas_settings")

            ref_file.write_bytes(b"pg smoke reference")
            out_file.write_bytes(b"pg smoke output")
            task_id = create_generation_task(
                user_id=user_id,
                prompt="pg smoke task",
                mode="text",
                ratio="1:1",
                resolution="1K",
                actual_size="1024x1024",
                quality="auto",
                output_format="png",
                count=1,
                cost=2,
                reference_paths=[ref_path],
            )
            db.commit()
            assert active_generation_task_count_for_user(user_id) == 1
            pass_step("generation_task_insert")

            mark_generation_task_running(task_id)
            record_id = create_record(
                user_id=user_id,
                prompt="pg smoke task",
                image_path=out_path,
                mode="text",
                ratio="1:1",
                resolution="1K",
                actual_size="1024x1024",
                quality="auto",
                output_format="png",
                count=1,
                model_source="pg-smoke",
                elapsed_seconds=0.1,
                points_charged=2,
                reference_paths=[ref_path],
            )
            mark_generation_task_succeeded(task_id, record_id)
            db.commit()
            task = db.execute("SELECT status, record_id FROM generation_tasks WHERE id = ?", (task_id,)).fetchone()
            assert task is not None and task["status"] == "succeeded" and int(task["record_id"]) == int(record_id)
            pass_step("generation_task_to_record")

            sweep = sweep_local_uploads(output_dir, db, retention_seconds=0, dry_run=True)
            assert sweep.referenced_files >= 2
            pass_step("storage_reference_protection")

            with transaction() as tx:
                delete_user_cascade(tx, user_id)
            user_id = None
            pass_step("delete_user_cascade")

            return {
                "status": "passed",
                "provider_id": int(provider_id),
                "record_id": int(record_id),
                "task_id": int(task_id),
                "referenced_files": int(sweep.referenced_files),
            }
        finally:
            db = get_db()
            if user_id is not None:
                try:
                    with transaction() as tx:
                        delete_user_cascade(tx, user_id)
                except Exception:
                    db.rollback()
            if provider_id is not None:
                try:
                    delete_provider(provider_id)
                    db.commit()
                except Exception:
                    db.rollback()
            if previous_canvas_url is not None:
                try:
                    save_canvas_setting("canvas_app_url", previous_canvas_url)
                    db.commit()
                except Exception:
                    db.rollback()
            ref_file.unlink(missing_ok=True)
            out_file.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Huishi database smoke checks against DATABASE_URL.")
    parser.add_argument("--allow-sqlite", action="store_true", help="Allow SQLite for script debugging. PostgreSQL is required by default.")
    args = parser.parse_args()

    dsn = os.environ.get("DATABASE_URL", "").strip()
    assert_postgres_database_url(dsn, allow_sqlite=args.allow_sqlite)
    configure_smoke_environment(dsn)
    print(f"DATABASE_URL={masked_dsn(dsn) if dsn else '[sqlite default]'}")

    try:
        result = run_smoke()
    except BaseException as exc:
        fail_step("db_smoke", exc)
        return 1
    print(f"db_smoke={result['status']}")
    print(
        "summary "
        f"provider_id={result['provider_id']} "
        f"task_id={result['task_id']} "
        f"record_id={result['record_id']} "
        f"referenced_files={result['referenced_files']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
