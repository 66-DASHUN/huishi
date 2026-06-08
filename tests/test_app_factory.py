import importlib
import os
import sys
from pathlib import Path


def test_importing_app_module_does_not_initialize_database(tmp_path, monkeypatch):
    db_path = tmp_path / "import-side-effect.sqlite3"
    monkeypatch.setenv("HUISHI_DATABASE", str(db_path))
    monkeypatch.setenv("HUISHI_OUTPUT_DIR", str(tmp_path / "output"))
    sys.modules.pop("app", None)

    importlib.import_module("app")

    assert not db_path.exists()


def test_seeded_admin_password_can_be_configured(tmp_path, monkeypatch):
    from werkzeug.security import check_password_hash

    from app import create_app
    from huishi.db import get_db

    monkeypatch.setenv("HUISHI_DATABASE", str(tmp_path / "admin-password.sqlite3"))
    monkeypatch.setenv("HUISHI_OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("HUISHI_SECRET_KEY", "test-secret")
    monkeypatch.setenv("HUISHI_ADMIN_PASSWORD", "configured-secret")

    flask_app = create_app(testing=True)

    with flask_app.app_context():
        admin = get_db().execute("SELECT * FROM users WHERE username = 'admin'").fetchone()

    assert admin is not None
    assert check_password_hash(admin["password_hash"], "configured-secret")
