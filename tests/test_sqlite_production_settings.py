from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from app import create_app
from huishi.config import Config
from huishi.db import get_db, init_db


def _set_production_test_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HUISHI_ENV", "production")
    monkeypatch.setenv("HUISHI_REQUIRE_POSTGRES", "0")
    monkeypatch.setenv("HUISHI_REQUIRE_REDIS_LIMITS", "0")
    monkeypatch.setenv("HUISHI_DATABASE", str(tmp_path / "prod.sqlite3"))
    monkeypatch.setenv("HUISHI_OUTPUT_DIR", str(tmp_path / "uploads"))


def test_production_rejects_default_session_secret(monkeypatch, tmp_path: Path):
    _set_production_test_env(monkeypatch, tmp_path)
    monkeypatch.setenv("HUISHI_SECRET_KEY", "dev-change-me")
    monkeypatch.setenv("HUISHI_ADMIN_PASSWORD", "strong-admin-password")
    monkeypatch.setenv("HUISHI_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))

    with pytest.raises(RuntimeError, match="HUISHI_SECRET_KEY"):
        create_app(testing=False)


def test_production_requires_encryption_key(monkeypatch, tmp_path: Path):
    _set_production_test_env(monkeypatch, tmp_path)
    monkeypatch.setenv("HUISHI_SECRET_KEY", "strong-session-secret")
    monkeypatch.setenv("HUISHI_ADMIN_PASSWORD", "strong-admin-password")
    monkeypatch.setattr(Config, "ENCRYPTION_KEY", "")
    monkeypatch.delenv("HUISHI_ENCRYPTION_KEY", raising=False)

    with pytest.raises(RuntimeError, match="HUISHI_ENCRYPTION_KEY"):
        create_app(testing=False)


def test_production_rejects_default_admin_password(monkeypatch, tmp_path: Path):
    _set_production_test_env(monkeypatch, tmp_path)
    monkeypatch.setenv("HUISHI_SECRET_KEY", "strong-session-secret")
    monkeypatch.setenv("HUISHI_ADMIN_PASSWORD", "1qaz@WSX")
    monkeypatch.setenv("HUISHI_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))

    with pytest.raises(RuntimeError, match="HUISHI_ADMIN_PASSWORD"):
        create_app(testing=False)


def test_production_rejects_invalid_encryption_key(monkeypatch, tmp_path: Path):
    _set_production_test_env(monkeypatch, tmp_path)
    monkeypatch.setenv("HUISHI_SECRET_KEY", "strong-session-secret")
    monkeypatch.setenv("HUISHI_ADMIN_PASSWORD", "strong-admin-password")
    monkeypatch.setenv("HUISHI_ENCRYPTION_KEY", "not-a-fernet-key")

    with pytest.raises(RuntimeError, match="valid Fernet key"):
        create_app(testing=False)

def test_dotenv_loader_skips_unreadable_files(tmp_path: Path):
    from huishi.config import _load_dotenv_file

    env_path = tmp_path / ".env"
    env_path.write_text("IGNORED_VALUE=1\n", encoding="utf-8")
    env_path.chmod(0)
    try:
        _load_dotenv_file(env_path)
    finally:
        env_path.chmod(0o600)


def test_testing_mode_ignores_production_database_url_by_default(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("HUISHI_TEST_DATABASE_URL", raising=False)
    monkeypatch.delenv("HUISHI_TEST_REQUIRE_POSTGRES", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://huishi:secret@127.0.0.1:5432/huishi")
    monkeypatch.setenv("HUISHI_REQUIRE_POSTGRES", "1")
    monkeypatch.setenv("HUISHI_DATABASE", str(tmp_path / "test.sqlite3"))
    monkeypatch.setenv("HUISHI_OUTPUT_DIR", str(tmp_path / "uploads"))

    app = create_app(testing=True)

    assert app.config["DATABASE_URL"] == ""
    assert app.config["REQUIRE_POSTGRES"] is False
    assert app.config["DATABASE"] == tmp_path / "test.sqlite3"



def test_sqlite_connection_uses_production_pragmas(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("HUISHI_TEST_DATABASE_URL", raising=False)
    monkeypatch.delenv("HUISHI_TEST_REQUIRE_POSTGRES", raising=False)
    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "prod.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"

    with app.app_context():
        init_db()
        db = get_db()

        journal_mode = db.execute("PRAGMA journal_mode").fetchone()[0]
        busy_timeout = db.execute("PRAGMA busy_timeout").fetchone()[0]
        foreign_keys = db.execute("PRAGMA foreign_keys").fetchone()[0]
        synchronous = db.execute("PRAGMA synchronous").fetchone()[0]

    assert journal_mode == "wal"
    assert busy_timeout >= 30000
    assert foreign_keys == 1
    assert synchronous == 1


def test_production_requires_redis_for_shared_limits(monkeypatch, tmp_path: Path):
    from cryptography.fernet import Fernet

    monkeypatch.setenv("HUISHI_ENV", "production")
    monkeypatch.setenv("HUISHI_REQUIRE_POSTGRES", "0")
    monkeypatch.setenv("HUISHI_SECRET_KEY", "not-the-default-secret")
    monkeypatch.setenv("HUISHI_ADMIN_PASSWORD", "not-the-default-password")
    monkeypatch.setenv("HUISHI_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    monkeypatch.setenv("HUISHI_DATABASE", str(tmp_path / "prod.sqlite3"))
    monkeypatch.setenv("HUISHI_OUTPUT_DIR", str(tmp_path / "uploads"))
    monkeypatch.delenv("HUISHI_REDIS_URL", raising=False)
    monkeypatch.setenv("HUISHI_REQUIRE_REDIS_LIMITS", "1")

    with pytest.raises(RuntimeError, match="HUISHI_REDIS_URL"):
        create_app(testing=False)


def test_require_postgres_guard_rejects_sqlite_fallback(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("HUISHI_REQUIRE_POSTGRES", "1")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("HUISHI_DATABASE", str(tmp_path / "prod.sqlite3"))
    monkeypatch.setenv("HUISHI_OUTPUT_DIR", str(tmp_path / "uploads"))

    with pytest.raises(RuntimeError, match="DATABASE_URL must be set to postgresql://"):
        create_app(testing=False)


def test_default_generation_stale_window_covers_limit_wait_and_provider_timeout(tmp_path: Path):
    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "prod.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"

    assert app.config["GENERATION_TASK_STALE_SECONDS"] >= (
        app.config["GENERATION_LIMIT_WAIT_TIMEOUT_SECONDS"] + app.config["IMAGE_API_TIMEOUT"]
    )
