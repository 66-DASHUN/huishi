from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from huishi.db_backend import SCHEMA_TABLE_ORDER


@dataclass
class MigrationSummary:
    table_counts: dict[str, int] = field(default_factory=dict)


def migrate_sqlite_to_postgres(sqlite_db: sqlite3.Connection, postgres_db) -> MigrationSummary:
    sqlite_db.row_factory = sqlite3.Row
    summary = MigrationSummary()
    for table in migration_table_order(sqlite_db):
        rows = sqlite_db.execute(f"SELECT * FROM {table} ORDER BY id" if has_column(sqlite_db, table, "id") else f"SELECT * FROM {table}").fetchall()
        if not rows:
            summary.table_counts[table] = 0
            continue
        columns = list(rows[0].keys())
        placeholders = ",".join("?" for _ in columns)
        column_list = ",".join(columns)
        sql = f"INSERT INTO {table} ({column_list}) VALUES ({placeholders})"
        max_id = None
        for row in rows:
            postgres_db.execute(sql, tuple(row[column] for column in columns))
            if "id" in columns:
                max_id = max(int(row["id"]), int(max_id or 0))
        if max_id is not None:
            postgres_db.execute("SELECT setval(pg_get_serial_sequence(?, ?), ?, true)", (table, "id", max_id))
        summary.table_counts[table] = len(rows)
    postgres_db.commit()
    return summary


def migration_table_order(sqlite_db: sqlite3.Connection) -> list[str]:
    rows = sqlite_db.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'").fetchall()
    tables = [str(row["name"]) for row in rows]
    return sorted(tables, key=lambda table: SCHEMA_TABLE_ORDER.get(table, 9_000))


def has_column(sqlite_db: sqlite3.Connection, table: str, column: str) -> bool:
    cursor = sqlite_db.execute(f"SELECT * FROM {table} LIMIT 0")
    return any(description[0] == column for description in (cursor.description or ()))
