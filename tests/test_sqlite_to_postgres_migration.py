from __future__ import annotations

import sqlite3

from huishi.db import SCHEMA
from huishi.db_backend import PostgreSQLConnection
from huishi.db_migration import migrate_sqlite_to_postgres


class FakeCursor:
    rowcount = 1

    def __init__(self, row=None):
        self.row = row

    def fetchone(self):
        return self.row

    def fetchall(self):
        return [self.row] if self.row is not None else []


class FakeRawPostgres:
    def __init__(self):
        self.executed = []
        self.commits = 0

    def execute(self, sql, params=()):
        self.executed.append((sql, tuple(params or ())))
        return FakeCursor({"id": params[0]} if "RETURNING id" in sql and params else None)

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def close(self):
        pass


def test_migrate_sqlite_to_postgres_preserves_ids_and_resets_sequences():
    sqlite_db = sqlite3.connect(":memory:")
    sqlite_db.row_factory = sqlite3.Row
    sqlite_db.executescript(SCHEMA)
    sqlite_db.execute(
        """
        INSERT INTO users (id, email, username, password_hash, role, email_verified, points, created_at)
        VALUES (7, '', 'migrated', 'hash', 'user', 1, 10, 'now')
        """
    )
    sqlite_db.commit()
    fake_raw = FakeRawPostgres()

    summary = migrate_sqlite_to_postgres(sqlite_db, PostgreSQLConnection(fake_raw))

    user_insert = next(sql for sql, params in fake_raw.executed if sql.startswith("INSERT INTO users") and params[0] == 7)
    assert "id,email,username,password_hash" in user_insert
    assert "RETURNING id" in user_insert
    assert ("SELECT setval(pg_get_serial_sequence(%s, %s), %s, true)", ("users", "id", 7)) in fake_raw.executed
    assert summary.table_counts["users"] == 1
    assert fake_raw.commits == 1


def test_migrate_sqlite_to_postgres_inserts_dependency_tables_in_order():
    sqlite_db = sqlite3.connect(":memory:")
    sqlite_db.row_factory = sqlite3.Row
    sqlite_db.executescript(SCHEMA)
    sqlite_db.execute(
        """
        INSERT INTO users (id, email, username, password_hash, role, email_verified, points, created_at)
        VALUES (1, '', 'owner', 'hash', 'user', 1, 10, 'now')
        """
    )
    sqlite_db.execute("INSERT INTO dialogues (id, user_id, title, created_at, updated_at) VALUES (2, 1, 'd', 'now', 'now')")
    sqlite_db.execute(
        """
        INSERT INTO records
        (id, user_id, prompt, dialogue_id, image_path, image_paths, generation_group_id, group_index, mode, ratio, resolution, actual_size, quality, output_format, count, model_source, elapsed_seconds, points_charged, reference_paths, asset_source, favorite, hidden, created_at)
        VALUES (3, 1, 'p', 2, '/static/uploads/a.png', '[]', 'g', 0, 'text', '16:9', '2K', '2560x1440', 'auto', 'png', 1, 'fake', 0.1, 1, '[]', 'image', 0, 0, 'now')
        """
    )
    sqlite_db.commit()
    fake_raw = FakeRawPostgres()

    migrate_sqlite_to_postgres(sqlite_db, PostgreSQLConnection(fake_raw))

    executed_sql = [sql for sql, _params in fake_raw.executed if sql.startswith("INSERT INTO")]
    users_index = next(index for index, sql in enumerate(executed_sql) if sql.startswith("INSERT INTO users"))
    dialogues_index = next(index for index, sql in enumerate(executed_sql) if sql.startswith("INSERT INTO dialogues"))
    records_index = next(index for index, sql in enumerate(executed_sql) if sql.startswith("INSERT INTO records"))
    assert users_index < dialogues_index < records_index
