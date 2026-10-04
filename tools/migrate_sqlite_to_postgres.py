from __future__ import annotations

import argparse
import sqlite3

import psycopg
from psycopg.rows import dict_row

from huishi.db import SCHEMA
from huishi.db_backend import PostgreSQLConnection, postgres_schema_from_sqlite
from huishi.db_migration import migrate_sqlite_to_postgres


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate Huishi SQLite data into an empty PostgreSQL database.")
    parser.add_argument("--sqlite", required=True, help="Path to the source SQLite database.")
    parser.add_argument("--postgres-url", required=True, help="PostgreSQL DATABASE_URL.")
    parser.add_argument("--init-schema", action="store_true", help="Create PostgreSQL tables before importing rows.")
    args = parser.parse_args()

    sqlite_db = sqlite3.connect(args.sqlite)
    sqlite_db.row_factory = sqlite3.Row
    raw_pg = psycopg.connect(args.postgres_url, row_factory=dict_row)
    pg_db = PostgreSQLConnection(raw_pg)
    try:
        if args.init_schema:
            pg_db.executescript(postgres_schema_from_sqlite(SCHEMA))
            pg_db.commit()
        summary = migrate_sqlite_to_postgres(sqlite_db, pg_db)
    except Exception:
        pg_db.rollback()
        raise
    finally:
        sqlite_db.close()
        pg_db.close()

    total = sum(summary.table_counts.values())
    print(f"migrated_rows={total}")
    for table, count in summary.table_counts.items():
        print(f"{table}={count}")


if __name__ == "__main__":
    main()
