from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_PYTHON_PATHS = [ROOT / "app.py", ROOT / "wsgi.py", ROOT / "huishi"]


def _production_python_files() -> list[Path]:
    files: list[Path] = []
    for path in PRODUCTION_PYTHON_PATHS:
        if path.is_file():
            files.append(path)
        else:
            files.extend(sorted(path.rglob("*.py")))
    return [path for path in files if "__pycache__" not in path.parts]


def test_sqlite_connection_entrypoint_stays_in_db_module():
    offenders = [
        path.relative_to(ROOT).as_posix()
        for path in _production_python_files()
        if path != ROOT / "huishi" / "db.py" and "sqlite3.connect" in path.read_text(encoding="utf-8")
    ]

    assert offenders == []


def test_sqlite_pragmas_stay_in_db_module():
    offenders = [
        path.relative_to(ROOT).as_posix()
        for path in _production_python_files()
        if path != ROOT / "huishi" / "db.py" and "PRAGMA " in path.read_text(encoding="utf-8")
    ]

    assert offenders == []


def test_sql_inventory_document_tracks_postgresql_risks():
    inventory = ROOT / "docs" / "db" / "sql-inventory.md"

    assert inventory.exists()

    body = inventory.read_text(encoding="utf-8")
    for required in [
        "SQLite-Specific Constructs",
        "PostgreSQL Compatibility Risks",
        "High-Risk Write Paths",
        "AUTOINCREMENT",
        "INSERT OR IGNORE",
        "PRAGMA",
        "BEGIN IMMEDIATE",
        "lastrowid",
    ]:
        assert required in body


def test_workspace_bulk_asset_sql_uses_placeholder_helper():
    source = (ROOT / "huishi" / "routes_workspace.py").read_text(encoding="utf-8")
    bulk_start = source.index("def bulk_favorite_assets()")
    bulk_end = source.index("def delete_local_upload(")
    bulk_source = source[bulk_start:bulk_end]

    assert '",".join("?" for _ in ids)' not in bulk_source
    assert "sql_placeholders(ids)" in bulk_source


def test_settings_key_sql_uses_placeholder_helper():
    providers_source = (ROOT / "huishi" / "providers.py").read_text(encoding="utf-8")
    db_source = (ROOT / "huishi" / "db.py").read_text(encoding="utf-8")

    assert '",".join("?" for _ in keys)' not in providers_source
    assert "sql_placeholders(keys)" in providers_source
    assert '",".join("?" for _ in SECRET_APP_SETTING_KEYS)' not in db_source
    assert "sql_placeholders(SECRET_APP_SETTING_KEYS)" in db_source


def test_admin_bulk_sql_uses_placeholder_helper():
    source = (ROOT / "huishi" / "routes_admin.py").read_text(encoding="utf-8")
    invite_start = source.index("def bulk_update_invites()")
    invite_end = source.index("def export_users()")
    user_start = source.index("def bulk_update_users()")
    user_end = source.index("def reset_user_password(")
    bulk_source = source[invite_start:invite_end] + source[user_start:user_end]

    assert '",".join("?" for _ in invite_ids)' not in bulk_source
    assert '",".join("?" for _ in existing_ids)' not in bulk_source
    assert '",".join("?" for _ in user_ids)' not in bulk_source
    assert "sql_placeholders(invite_ids)" in bulk_source
    assert "sql_placeholders(existing_ids)" in bulk_source
    assert "sql_placeholders(user_ids)" in bulk_source


def test_auth_verification_writes_use_transaction_helper():
    source = (ROOT / "huishi" / "auth.py").read_text(encoding="utf-8")
    start = source.index("def reset_password_with_email_code()")
    end = source.index("def logout()")
    auth_write_source = source[start:end]

    assert ".commit()" not in auth_write_source
    assert "with transaction()" in auth_write_source
