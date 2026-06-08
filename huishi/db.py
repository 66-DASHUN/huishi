from __future__ import annotations

import secrets
import sqlite3
import os
from datetime import datetime, timezone

from flask import current_app, g
from werkzeug.security import generate_password_hash


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT NOT NULL DEFAULT '',
  username TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'user',
  email_verified INTEGER NOT NULL DEFAULT 0,
  email_verification_token TEXT NOT NULL DEFAULT '',
  email_verified_at TEXT NOT NULL DEFAULT '',
  points INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pricing_rules (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  mode TEXT NOT NULL,
  resolution TEXT NOT NULL,
  points_per_image INTEGER NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  UNIQUE(mode, resolution)
);

CREATE TABLE IF NOT EXISTS packages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  price_cents INTEGER NOT NULL,
  points INTEGER NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  enabled INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS records (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  prompt TEXT NOT NULL,
  dialogue_id INTEGER,
  image_path TEXT NOT NULL,
  image_paths TEXT NOT NULL DEFAULT '[]',
  mode TEXT NOT NULL,
  ratio TEXT NOT NULL DEFAULT '16:9',
  resolution TEXT NOT NULL,
  actual_size TEXT NOT NULL,
  quality TEXT NOT NULL,
  output_format TEXT NOT NULL,
  count INTEGER NOT NULL,
  model_source TEXT NOT NULL DEFAULT '',
  elapsed_seconds REAL NOT NULL DEFAULT 0,
  points_charged INTEGER NOT NULL DEFAULT 0,
  reference_paths TEXT NOT NULL DEFAULT '[]',
  favorite INTEGER NOT NULL DEFAULT 0,
  hidden INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  FOREIGN KEY(dialogue_id) REFERENCES dialogues(id),
  FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS dialogues (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  title TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS point_ledger (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  delta INTEGER NOT NULL,
  reason TEXT NOT NULL,
  record_id INTEGER,
  admin_note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  FOREIGN KEY(user_id) REFERENCES users(id),
  FOREIGN KEY(record_id) REFERENCES records(id)
);

CREATE TABLE IF NOT EXISTS user_settings (
  user_id INTEGER PRIMARY KEY,
  base_url TEXT NOT NULL DEFAULT '',
  api_key TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL,
  FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS app_settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL
);
"""


DEFAULT_PRICING = [
    ("text", "1K", 1),
    ("text", "2K", 2),
    ("text", "4K", 4),
]


DEFAULT_PACKAGES = [
    ("入门包", 990, 100, "适合体验绘世的基础创作。"),
    ("创作包", 3990, 500, "适合持续生成和调试作品。"),
    ("专业包", 8990, 1200, "适合高频创作和 4K 输出。"),
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        db = sqlite3.connect(current_app.config["DATABASE"])
        db.row_factory = sqlite3.Row
        g.db = db
    return g.db


def close_db(_: object = None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    db = get_db()
    db.executescript(SCHEMA)
    migrate_users_table(db)
    migrate_records_table(db)
    migrate_dialogues_table(db)
    seed_defaults(db)
    db.commit()


def migrate_users_table(db: sqlite3.Connection) -> None:
    columns = {row["name"] for row in db.execute("PRAGMA table_info(users)").fetchall()}
    migrations = {
        "email": "ALTER TABLE users ADD COLUMN email TEXT NOT NULL DEFAULT ''",
        "email_verified": "ALTER TABLE users ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 0",
        "email_verification_token": "ALTER TABLE users ADD COLUMN email_verification_token TEXT NOT NULL DEFAULT ''",
        "email_verified_at": "ALTER TABLE users ADD COLUMN email_verified_at TEXT NOT NULL DEFAULT ''",
    }
    for column, statement in migrations.items():
        if column not in columns:
            db.execute(statement)
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_unique ON users(email) WHERE email != ''")
    db.execute("UPDATE users SET email_verified = 1 WHERE role = 'admin' OR email = ''")


def migrate_records_table(db: sqlite3.Connection) -> None:
    columns = {row["name"] for row in db.execute("PRAGMA table_info(records)").fetchall()}
    migrations = {
        "dialogue_id": "ALTER TABLE records ADD COLUMN dialogue_id INTEGER",
        "ratio": "ALTER TABLE records ADD COLUMN ratio TEXT NOT NULL DEFAULT '16:9'",
        "reference_paths": "ALTER TABLE records ADD COLUMN reference_paths TEXT NOT NULL DEFAULT '[]'",
        "image_paths": "ALTER TABLE records ADD COLUMN image_paths TEXT NOT NULL DEFAULT '[]'",
        "hidden": "ALTER TABLE records ADD COLUMN hidden INTEGER NOT NULL DEFAULT 0",
    }
    for column, statement in migrations.items():
        if column not in columns:
            db.execute(statement)


def migrate_dialogues_table(db: sqlite3.Connection) -> None:
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS dialogues (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL,
          title TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )


def seed_defaults(db: sqlite3.Connection) -> None:
    for mode, resolution, points in DEFAULT_PRICING:
        db.execute(
            """
            INSERT OR IGNORE INTO pricing_rules (mode, resolution, points_per_image, enabled)
            VALUES (?, ?, ?, 1)
            """,
            (mode, resolution, points),
        )
    for name, price_cents, points, description in DEFAULT_PACKAGES:
        db.execute(
            """
            INSERT OR IGNORE INTO packages (name, price_cents, points, description, enabled)
            VALUES (?, ?, ?, ?, 1)
            """,
            (name, price_cents, points, description),
        )
    admin_password = current_app.config.get("ADMIN_PASSWORD") or os.environ.get("HUISHI_ADMIN_PASSWORD", "")
    if not admin_password:
        admin_password = secrets.token_urlsafe(12)
        print(
            f"\n{'='*60}\n"
            f"  绘世管理员密码（自动生成，请妥善保存）:\n"
            f"  {admin_password}\n"
            f"{'='*60}\n",
            flush=True,
        )
    db.execute(
        """
        INSERT OR IGNORE INTO users (email, username, password_hash, role, email_verified, points, created_at)
        VALUES ('', ?, ?, 'admin', 1, 1000, ?)
        """,
        ("admin", generate_password_hash(admin_password), utc_now()),
    )
