from __future__ import annotations

from pathlib import Path

import pytest

from app import create_app
from huishi.db import get_db, init_db
from huishi.db_backend import PostgreSQLConnection


@pytest.fixture()
def app(tmp_path: Path):
    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "test.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"
    with app.app_context():
        init_db()
    return app


def test_sql_placeholders_returns_stable_parameter_tuple():
    from huishi.db import sql_placeholders

    placeholders, params = sql_placeholders([3, 5, 8])

    assert placeholders == "?,?,?"
    assert params == (3, 5, 8)


def test_sql_placeholders_rejects_empty_values():
    from huishi.db import sql_placeholders

    with pytest.raises(ValueError, match="at least one value"):
        sql_placeholders([])


def test_is_integrity_error_accepts_sqlite_and_psycopg_errors():
    import sqlite3
    import psycopg
    from huishi.db import is_integrity_error

    assert is_integrity_error(sqlite3.IntegrityError())
    assert is_integrity_error(psycopg.IntegrityError())
    assert not is_integrity_error(RuntimeError())


def test_transaction_commits_successful_work(app):
    from huishi.db import transaction

    with app.app_context():
        with transaction() as db:
            db.execute(
                """
                INSERT INTO users (username, email, password_hash, role, email_verified, points, created_at)
                VALUES ('tx-commit', '', 'hash', 'user', 1, 0, 'now')
                """
            )

        row = get_db().execute("SELECT username FROM users WHERE username = 'tx-commit'").fetchone()

    assert row["username"] == "tx-commit"


def test_transaction_rolls_back_failed_work(app):
    from huishi.db import transaction

    with app.app_context():
        with pytest.raises(RuntimeError, match="force rollback"):
            with transaction() as db:
                db.execute(
                    """
                    INSERT INTO users (username, email, password_hash, role, email_verified, points, created_at)
                    VALUES ('tx-rollback', '', 'hash', 'user', 1, 0, 'now')
                    """
                )
                raise RuntimeError("force rollback")

        row = get_db().execute("SELECT username FROM users WHERE username = 'tx-rollback'").fetchone()

    assert row is None


def test_immediate_transaction_starts_with_begin_immediate(app):
    from huishi.db import immediate_transaction

    with app.app_context():
        with immediate_transaction() as db:
            row = db.execute("SELECT 1 AS value").fetchone()

    assert row["value"] == 1


def test_lock_user_for_update_uses_postgres_row_lock(app):
    from flask import g
    from huishi.db import lock_user_for_update

    fake_raw = FakePostgresRaw()

    with app.app_context():
        g.db = PostgreSQLConnection(fake_raw)

        lock_user_for_update(7)

    assert ("SELECT id FROM users WHERE id = %s FOR UPDATE", (7,)) in fake_raw.executed


def test_lock_enabled_admins_for_update_uses_postgres_row_locks(app):
    from flask import g
    from huishi.db import lock_enabled_admins_for_update

    fake_raw = FakePostgresRaw()

    with app.app_context():
        g.db = PostgreSQLConnection(fake_raw)

        lock_enabled_admins_for_update()

    assert any(
        "SELECT id FROM users" in sql
        and "role IN ('admin', 'super_admin')" in sql
        and "enabled = %s" in sql
        and "FOR UPDATE" in sql
        and params == (1,)
        for sql, params in fake_raw.executed
    )


class FakePostgresCursor:
    rowcount = 1

    def __init__(self, row=None):
        self.row = row

    def fetchone(self):
        return self.row

    def fetchall(self):
        return [self.row] if self.row is not None else []


class FakePostgresRaw:
    def __init__(self):
        self.executed = []
        self.commits = 0

    def execute(self, sql, params=()):
        self.executed.append((sql, tuple(params or ())))
        if "SELECT COUNT(*) AS count FROM packages" in sql:
            return FakePostgresCursor({"count": 0})
        if "SELECT id FROM users" in sql and "FOR UPDATE" in sql:
            return FakePostgresCursor({"id": params[0]})
        return FakePostgresCursor({"id": 1} if "RETURNING id" in sql else None)

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def close(self):
        pass


def test_init_db_uses_postgres_schema_when_database_url_is_postgresql(tmp_path, monkeypatch):
    import huishi.db as db_module

    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "unused.sqlite3"
    app.config["DATABASE_URL"] = "postgresql://huishi:secret@127.0.0.1:5432/huishi"
    fake_raw = FakePostgresRaw()
    monkeypatch.setattr(db_module, "connect_postgresql", lambda _dsn: PostgreSQLConnection(fake_raw))

    with app.app_context():
        init_db()

    sql_text = "\n".join(sql for sql, _params in fake_raw.executed)
    assert "GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY" in sql_text
    assert "AUTOINCREMENT" not in sql_text
    assert "PRAGMA" not in sql_text
    assert "ON CONFLICT DO NOTHING" in sql_text
    assert fake_raw.commits == 1
