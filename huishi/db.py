from __future__ import annotations

import secrets
import sqlite3
import os
import json
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Iterator, Sequence

from flask import current_app, g
from werkzeug.security import generate_password_hash

from huishi.db_backend import (
    PostgreSQLConnection,
    database_settings_from_mapping,
    postgres_schema_from_sqlite,
)


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT NOT NULL DEFAULT '',
  username TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'user',
  email_verified INTEGER NOT NULL DEFAULT 0,
  email_verification_code TEXT NOT NULL DEFAULT '',
  email_verification_token TEXT NOT NULL DEFAULT '',
  email_verified_at TEXT NOT NULL DEFAULT '',
  enabled INTEGER NOT NULL DEFAULT 1,
  points INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS admin_audit_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  actor_user_id INTEGER,
  action TEXT NOT NULL,
  target_type TEXT NOT NULL DEFAULT '',
  target_id TEXT NOT NULL DEFAULT '',
  summary TEXT NOT NULL DEFAULT '',
  before_json TEXT NOT NULL DEFAULT '{}',
  after_json TEXT NOT NULL DEFAULT '{}',
  result TEXT NOT NULL DEFAULT 'success',
  request_id TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  FOREIGN KEY(actor_user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_admin_audit_created ON admin_audit_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_admin_audit_actor ON admin_audit_logs(actor_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_admin_audit_action ON admin_audit_logs(action, created_at DESC);

CREATE TABLE IF NOT EXISTS pricing_rules (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  mode TEXT NOT NULL,
  model TEXT NOT NULL DEFAULT '*',
  resolution TEXT NOT NULL,
  points_per_image INTEGER NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  media_type TEXT NOT NULL DEFAULT 'image',
  duration_tier TEXT NOT NULL DEFAULT '',
  UNIQUE(mode, model, resolution)
);

CREATE TABLE IF NOT EXISTS packages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  price_cents INTEGER NOT NULL,
  points INTEGER NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  enabled INTEGER NOT NULL DEFAULT 1,
  UNIQUE(name, price_cents, points, description)
);

CREATE TABLE IF NOT EXISTS records (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  prompt TEXT NOT NULL,
  dialogue_id INTEGER,
  image_path TEXT NOT NULL,
  image_paths TEXT NOT NULL DEFAULT '[]',
  generation_group_id TEXT NOT NULL DEFAULT '',
  group_index INTEGER NOT NULL DEFAULT 0,
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
  asset_source TEXT NOT NULL DEFAULT 'image',
  media_type TEXT NOT NULL DEFAULT 'image',
  mime_type TEXT NOT NULL DEFAULT '',
  duration_ms INTEGER NOT NULL DEFAULT 0,
  favorite INTEGER NOT NULL DEFAULT 0,
  hidden INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  FOREIGN KEY(dialogue_id) REFERENCES dialogues(id),
  FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS generation_tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  dialogue_id INTEGER,
  prompt TEXT NOT NULL,
  mode TEXT NOT NULL,
  model TEXT NOT NULL DEFAULT '',
  ratio TEXT NOT NULL,
  resolution TEXT NOT NULL,
  actual_size TEXT NOT NULL,
  quality TEXT NOT NULL,
  output_format TEXT NOT NULL,
  count INTEGER NOT NULL,
  cost INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL,
  record_id INTEGER,
  reference_paths TEXT NOT NULL DEFAULT '[]',
  error_message TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  finished_at TEXT NOT NULL DEFAULT '',
  dismissed_at TEXT NOT NULL DEFAULT '',
  bypass_billing INTEGER NOT NULL DEFAULT 0,
  media_type TEXT NOT NULL DEFAULT 'image',
  provider_id INTEGER,
  provider_task_id TEXT NOT NULL DEFAULT '',
  duration_seconds INTEGER NOT NULL DEFAULT 0,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  FOREIGN KEY(dialogue_id) REFERENCES dialogues(id),
  FOREIGN KEY(record_id) REFERENCES records(id),
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

CREATE TABLE IF NOT EXISTS api_providers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  provider_type TEXT NOT NULL,
  name TEXT NOT NULL,
  base_url TEXT NOT NULL DEFAULT '',
  api_key TEXT NOT NULL DEFAULT '',
  model TEXT NOT NULL DEFAULT '',
  api_format TEXT NOT NULL DEFAULT 'openai',
  resolutions TEXT NOT NULL DEFAULT '["1K","2K","4K"]',
  capabilities TEXT NOT NULL DEFAULT '[]',
  models_json TEXT NOT NULL DEFAULT '[]',
  settings_json TEXT NOT NULL DEFAULT '{}',
  priority INTEGER NOT NULL DEFAULT 100,
  enabled INTEGER NOT NULL DEFAULT 1,
  last_error TEXT NOT NULL DEFAULT '',
  disabled_at TEXT NOT NULL DEFAULT '',
  last_checked_at TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS provider_call_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  provider_id INTEGER,
  provider_name TEXT NOT NULL DEFAULT '',
  api_format TEXT NOT NULL DEFAULT '',
  media_type TEXT NOT NULL DEFAULT '',
  model TEXT NOT NULL DEFAULT '',
  task_id INTEGER,
  record_id INTEGER,
  outcome TEXT NOT NULL,
  error_class TEXT NOT NULL DEFAULT '',
  error_message TEXT NOT NULL DEFAULT '',
  latency_ms INTEGER NOT NULL DEFAULT 0,
  attempt_index INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_provider_call_logs_provider_time
ON provider_call_logs(provider_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_provider_call_logs_created
ON provider_call_logs(created_at DESC);

CREATE TABLE IF NOT EXISTS invite_codes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT NOT NULL UNIQUE,
  owner_user_id INTEGER NOT NULL,
  reward_points INTEGER NOT NULL DEFAULT 0,
  max_uses INTEGER,
  used_count INTEGER NOT NULL DEFAULT 0,
  enabled INTEGER NOT NULL DEFAULT 1,
  created_by_admin_id INTEGER,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(owner_user_id) REFERENCES users(id),
  FOREIGN KEY(created_by_admin_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS invite_redemptions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  invite_code_id INTEGER NOT NULL,
  inviter_user_id INTEGER NOT NULL,
  invitee_user_id INTEGER NOT NULL UNIQUE,
  reward_points INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY(inviter_user_id) REFERENCES users(id),
  FOREIGN KEY(invitee_user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS canvas_conversations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  title TEXT NOT NULL DEFAULT '新对话',
  archived INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS canvas_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  conversation_id INTEGER NOT NULL,
  role TEXT NOT NULL,
  content TEXT NOT NULL DEFAULT '',
  tool_calls TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL,
  FOREIGN KEY(conversation_id) REFERENCES canvas_conversations(id)
);

CREATE TABLE IF NOT EXISTS canvas_projects (
  id TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL,
  title TEXT NOT NULL DEFAULT '未命名画布',
  schema_version INTEGER NOT NULL DEFAULT 1,
  rev INTEGER NOT NULL DEFAULT 1,
  payload TEXT NOT NULL DEFAULT '{}',
  content_hash TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  deleted_at TEXT NOT NULL DEFAULT '',
  FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_canvas_projects_user_updated
ON canvas_projects(user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS canvas_project_assets (
  project_id TEXT NOT NULL,
  asset_ref TEXT NOT NULL,
  PRIMARY KEY(project_id, asset_ref),
  FOREIGN KEY(project_id) REFERENCES canvas_projects(id)
);

CREATE INDEX IF NOT EXISTS idx_canvas_project_assets_ref
ON canvas_project_assets(asset_ref);

-- 余额预留：reserved_generation_points 按 (user_id, status) 求和，
-- 每次提交生成、每次工作台列表刷新都会走到。
CREATE INDEX IF NOT EXISTS idx_generation_tasks_user_status
ON generation_tasks(user_id, status);

-- 我的作品/画布素材库：按 user_id 过滤 + 时间倒序。
CREATE INDEX IF NOT EXISTS idx_records_user_created
ON records(user_id, id DESC);

CREATE INDEX IF NOT EXISTS idx_records_user_hidden
ON records(user_id, hidden);

-- 积分流水页：按 user_id 过滤 + 时间倒序。
CREATE INDEX IF NOT EXISTS idx_point_ledger_user_created
ON point_ledger(user_id, id DESC);
"""


DEFAULT_PRICING = [
    # Pricing is model-scoped. A wildcard row is intentionally not seeded.
]

# User billing is expressed in points where 1 point equals RMB 0.01. Keep
# this catalog explicit so a newly enabled model cannot silently inherit an
# unrelated legacy price.
IMAGE_PRICING_CATALOG = (
    ("gpt-image-2", "1K", 2), ("gpt-image-2", "2K", 3), ("gpt-image-2", "4K", 3),
    ("gpt-image-2-adobe", "1K", 6), ("gpt-image-2-adobe", "2K", 6), ("gpt-image-2-adobe", "4K", 6),
    ("gpt-image-2.5-flare", "1K", 2), ("gpt-image-2.5-flare", "2K", 3), ("gpt-image-2.5-flare", "4K", 3),
    ("gpt-image-2.5-sunburst", "1K", 2), ("gpt-image-2.5-sunburst", "2K", 3), ("gpt-image-2.5-sunburst", "4K", 3),
    ("grok-imagine", "1K", 2), ("grok-imagine", "2K", 2),
    ("grok-imagine-image-2.0", "1K", 2), ("grok-imagine-image-2.0", "2K", 2),
    ("grok-imagine-image-quality", "1K", 1), ("grok-imagine-image-quality", "2K", 1),
    ("gemini-3.1-flash-image", "1K", 6), ("gemini-3.1-flash-image", "2K", 6), ("gemini-3.1-flash-image", "4K", 6),
    ("nano-banana2", "1K", 6), ("nano-banana2", "2K", 6), ("nano-banana2", "4K", 6),
    ("gemini-3-pro-image", "1K", 9), ("gemini-3-pro-image", "2K", 9), ("gemini-3-pro-image", "4K", 9),
    ("nano-banana-pro", "1K", 9), ("nano-banana-pro", "2K", 9), ("nano-banana-pro", "4K", 9),
)

VIDEO_PRICING_CATALOG = (
    ("grok-imagine-video", "480p", "per_second", 0, 7),
    ("grok-imagine-video", "720p", "per_second", 0, 10),
    ("grok-imagine-video", "1080p", "per_second", 0, 15),
    ("grok-imagine-video-1.5", "480p", "per_second", 0, 12),
    ("grok-imagine-video-1.5", "720p", "per_second", 0, 21),
    ("grok-imagine-video-1.5", "1080p", "per_second", 0, 37),
    # A request price is independent of the selected duration. The capability
    # layer still limits the actual duration values accepted by each model.
    ("seedance2.0mini", "720p", "per_request", 0, 300),
    ("seedance2.0fast", "720p", "per_request", 0, 300),
    ("seedance2.0", "720p", "per_request", 0, 300),
    ("seedance2.5", "720p", "per_request", 0, 400),
)


GROK_IMAGINE_MODEL_ID = "grok-imagine-image-2.0"
# Keep this order stable: if both obsolete ids supplied a price for the same
# target rule, the former Pro rule wins.  An existing 2.0 rule always wins.
LEGACY_GROK_IMAGINE_MODEL_IDS = (
    "grok-imagine-image-pro",
    "grok-imagine-image",
)
GROK_IMAGINE_RESOLUTIONS = ("1K", "2K")


DEFAULT_PACKAGES = [
    ("入门包", 990, 990, "适合体验绘世的基础创作。"),
    ("创作包", 3990, 3990, "适合持续生成和调试作品。"),
    ("专业包", 8990, 8990, "适合高频创作和 4K 输出。"),
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sqlite_timeout_seconds() -> float:
    raw = os.environ.get("HUISHI_SQLITE_TIMEOUT_SECONDS", "30")
    try:
        return max(1.0, float(raw))
    except ValueError:
        return 30.0


def _sqlite_busy_timeout_ms(timeout_seconds: float) -> int:
    raw = os.environ.get("HUISHI_SQLITE_BUSY_TIMEOUT_MS", "")
    if raw:
        try:
            return max(1000, int(raw))
        except ValueError:
            pass
    return int(timeout_seconds * 1000)


def configure_sqlite_connection(db: sqlite3.Connection, database_path: Path | str) -> None:
    timeout_seconds = _sqlite_timeout_seconds()
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.execute(f"PRAGMA busy_timeout = {_sqlite_busy_timeout_ms(timeout_seconds)}")
    if str(database_path) != ":memory:":
        db.execute("PRAGMA journal_mode = WAL")
        db.execute("PRAGMA synchronous = NORMAL")


def sql_placeholders(values: Sequence[object]) -> tuple[str, tuple[object, ...]]:
    params = tuple(values)
    if not params:
        raise ValueError("sql_placeholders requires at least one value")
    return ",".join("?" for _ in params), params


def is_integrity_error(exc: BaseException) -> bool:
    if isinstance(exc, sqlite3.IntegrityError):
        return True
    try:
        import psycopg
    except ImportError:
        return False
    return isinstance(exc, psycopg.IntegrityError)


@contextmanager
def transaction() -> Iterator[object]:
    db = get_db()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    else:
        db.commit()


@contextmanager
def immediate_transaction() -> Iterator[object]:
    db = get_db()
    if not isinstance(db, PostgreSQLConnection):
        db.execute("BEGIN IMMEDIATE")
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    else:
        db.commit()


def lock_user_for_update(user_id: int) -> None:
    db = get_db()
    if not isinstance(db, PostgreSQLConnection):
        return
    row = db.execute("SELECT id FROM users WHERE id = ? FOR UPDATE", (user_id,)).fetchone()
    if row is None:
        raise ValueError("用户不存在")


def lock_enabled_admins_for_update() -> list[object]:
    db = get_db()
    sql = "SELECT id FROM users WHERE role IN ('admin', 'super_admin') AND enabled = ? ORDER BY id"
    if isinstance(db, PostgreSQLConnection):
        sql += " FOR UPDATE"
    return list(db.execute(sql, (1,)).fetchall())


def get_db():
    if "db" not in g:
        settings = database_settings_from_mapping(current_app.config)
        if settings.backend == "postgresql":
            db = connect_postgresql(settings.dsn)
        else:
            database_path = current_app.config["DATABASE"]
            timeout_seconds = _sqlite_timeout_seconds()
            db = sqlite3.connect(database_path, timeout=timeout_seconds)
            configure_sqlite_connection(db, database_path)
        g.db = db
    return g.db


def connect_postgresql(dsn: str) -> PostgreSQLConnection:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise RuntimeError("Install psycopg[binary] to use PostgreSQL DATABASE_URL") from exc
    return PostgreSQLConnection(psycopg.connect(dsn, row_factory=dict_row))


def close_db(_: object = None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    from huishi.media_tasks import SCHEMA as MEDIA_SCHEMA
    db = get_db()
    if isinstance(db, PostgreSQLConnection):
        lock_key = 481273901
        db.raw_connection.execute("SELECT pg_advisory_lock(%s)", (lock_key,))
        migration_failed = False
        try:
            db.executescript(postgres_schema_from_sqlite(SCHEMA + MEDIA_SCHEMA))
            migrate_postgres_schema_columns(db)
            migrate_provider_model_types(db)
            migrate_pricing_contract(db)
            migrate_video_pricing_contract(db)
            migrate_packages_table(db)
            migrate_secret_values(db)
            seed_defaults(db)
            db.commit()
        except BaseException:
            migration_failed = True
            try:
                db.rollback()
            except Exception:
                # Preserve the migration error even if the driver has already
                # put the connection into an aborted state.
                pass
            raise
        finally:
            try:
                db.raw_connection.execute("SELECT pg_advisory_unlock(%s)", (lock_key,))
            except Exception:
                if not migration_failed:
                    raise
        return
    try:
        # sqlite3.executescript implicitly commits any transaction already in
        # progress. Start the script's own transaction so its DDL remains in
        # the same unit of work as every migration and seed operation below.
        db.executescript("BEGIN IMMEDIATE;\n" + SCHEMA + MEDIA_SCHEMA)
        migrate_users_table(db)
        migrate_pricing_rules_table(db)
        migrate_records_table(db)
        migrate_generation_tasks_table(db)
        migrate_dialogues_table(db)
        migrate_api_providers_table(db)
        migrate_provider_model_types(db)
        migrate_pricing_contract(db)
        migrate_video_pricing_contract(db)
        migrate_packages_table(db)
        migrate_invites_table(db)
        migrate_secret_values(db)
        migrate_canvas_tables(db)
        fix_canvas_records_dialogue(db)
        seed_defaults(db)
        db.commit()
    except BaseException:
        try:
            db.rollback()
        except Exception:
            pass
        raise


def migrate_users_table(db: sqlite3.Connection) -> None:
    columns = {row["name"] for row in db.execute("PRAGMA table_info(users)").fetchall()}
    migrations = {
        "email": "ALTER TABLE users ADD COLUMN email TEXT NOT NULL DEFAULT ''",
        "email_verified": "ALTER TABLE users ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 0",
        "email_verification_code": "ALTER TABLE users ADD COLUMN email_verification_code TEXT NOT NULL DEFAULT ''",
        "email_verification_token": "ALTER TABLE users ADD COLUMN email_verification_token TEXT NOT NULL DEFAULT ''",
        "email_verified_at": "ALTER TABLE users ADD COLUMN email_verified_at TEXT NOT NULL DEFAULT ''",
        "enabled": "ALTER TABLE users ADD COLUMN enabled INTEGER NOT NULL DEFAULT 1",
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
        "generation_group_id": "ALTER TABLE records ADD COLUMN generation_group_id TEXT NOT NULL DEFAULT ''",
        "group_index": "ALTER TABLE records ADD COLUMN group_index INTEGER NOT NULL DEFAULT 0",
        "asset_source": "ALTER TABLE records ADD COLUMN asset_source TEXT NOT NULL DEFAULT 'image'",
        "media_type": "ALTER TABLE records ADD COLUMN media_type TEXT NOT NULL DEFAULT 'image'",
        "mime_type": "ALTER TABLE records ADD COLUMN mime_type TEXT NOT NULL DEFAULT ''",
        "duration_ms": "ALTER TABLE records ADD COLUMN duration_ms INTEGER NOT NULL DEFAULT 0",
        "hidden": "ALTER TABLE records ADD COLUMN hidden INTEGER NOT NULL DEFAULT 0",
    }
    for column, statement in migrations.items():
        if column not in columns:
            db.execute(statement)
    db.execute("UPDATE records SET generation_group_id = 'legacy-' || id WHERE generation_group_id = ''")
    db.execute("UPDATE records SET asset_source = 'image' WHERE asset_source = '' OR asset_source IS NULL")


def migrate_pricing_rules_table(db: sqlite3.Connection) -> None:
    """Add model-scoped pricing while preserving every legacy rule and id."""
    columns = {row["name"] for row in db.execute("PRAGMA table_info(pricing_rules)").fetchall()}
    if "model" in columns:
        if "media_type" not in columns:
            db.execute("ALTER TABLE pricing_rules ADD COLUMN media_type TEXT NOT NULL DEFAULT 'image'")
        if "duration_tier" not in columns:
            db.execute("ALTER TABLE pricing_rules ADD COLUMN duration_tier TEXT NOT NULL DEFAULT ''")
        db.execute("UPDATE pricing_rules SET media_type = 'image' WHERE media_type = '' OR media_type IS NULL")
        db.execute("UPDATE pricing_rules SET model = '*' WHERE model IS NULL OR model = ''")
        return

    db.execute("ALTER TABLE pricing_rules RENAME TO pricing_rules_legacy")
    db.execute(
        """
        CREATE TABLE pricing_rules (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          mode TEXT NOT NULL,
          model TEXT NOT NULL DEFAULT '*',
          resolution TEXT NOT NULL,
          points_per_image INTEGER NOT NULL,
          enabled INTEGER NOT NULL DEFAULT 1,
          media_type TEXT NOT NULL DEFAULT 'image',
          duration_tier TEXT NOT NULL DEFAULT '',
          UNIQUE(mode, model, resolution)
        )
        """
    )
    db.execute(
        """
        INSERT INTO pricing_rules (id, mode, model, resolution, points_per_image, enabled, media_type, duration_tier)
        SELECT id, mode, '*', resolution, points_per_image, enabled, 'image', ''
        FROM pricing_rules_legacy
        """
    )
    db.execute("DROP TABLE pricing_rules_legacy")


def migrate_pricing_contract(db: object) -> None:
    """Replace retired wildcard/default rules with explicit model prices once."""
    marker = db.execute("SELECT value FROM app_settings WHERE key = ?", ("pricing_contract_20260922",)).fetchone()
    if marker is not None:
        return
    db.execute("DELETE FROM pricing_rules")
    db.execute("DELETE FROM video_pricing_rules")
    for model, resolution, points in IMAGE_PRICING_CATALOG:
        db.execute(
            "INSERT INTO pricing_rules (mode, model, resolution, points_per_image, enabled, media_type, duration_tier) VALUES (?, ?, ?, ?, 1, 'image', '')",
            ("text", model, resolution, points),
        )
    for model, resolution, unit, duration, points in VIDEO_PRICING_CATALOG:
        db.execute(
            "INSERT INTO video_pricing_rules (model, resolution, billing_unit, duration_seconds, points, enabled) VALUES (?, ?, ?, ?, ?, 1)",
            (model, resolution, unit, duration, points),
        )
    db.execute(
        "INSERT INTO app_settings (key, value, updated_at) VALUES (?, ?, ?) ON CONFLICT(key) DO NOTHING",
        ("pricing_contract_20260922", "explicit-model-prices", utc_now()),
    )


def migrate_video_pricing_contract(db: object) -> None:
    """Collapse legacy Seedance duration rows into one request-price rule.

    Older deployments created one identical ``per_request`` row for every
    duration option.  The duration remains a capability constraint, while the
    price is now represented by ``duration_seconds = 0`` (unlimited).
    """
    marker_key = "pricing_contract_20260922_video_request_v2"
    if db.execute("SELECT value FROM app_settings WHERE key = ?", (marker_key,)).fetchone() is not None:
        return

    seedance_models = {model for model, _resolution, _unit, _duration, _points in VIDEO_PRICING_CATALOG if model.startswith("seedance")}
    if seedance_models:
        placeholders = ",".join("?" for _ in seedance_models)
        rows = db.execute(
            f"SELECT id, model, resolution, points, enabled, billing_unit, duration_seconds "
            f"FROM video_pricing_rules WHERE billing_unit = 'per_request' AND model IN ({placeholders}) "
            "ORDER BY model, resolution, duration_seconds, id",
            tuple(sorted(seedance_models)),
        ).fetchall()
        groups = {}
        for row in rows:
            groups.setdefault((row["model"], row["resolution"]), []).append(row)
        for (model, resolution), group in groups.items():
            # Preserve the price from the largest legacy duration tier. This
            # is deterministic if an administrator used different prices.
            selected = max(group, key=lambda row: (int(row["duration_seconds"] or 0), int(row["id"])))
            db.execute(
                "DELETE FROM video_pricing_rules WHERE model = ? AND resolution = ? AND billing_unit = 'per_request'",
                (model, resolution),
            )
            db.execute(
                "INSERT INTO video_pricing_rules(model, resolution, billing_unit, duration_seconds, points, enabled) "
                "VALUES (?, ?, 'per_request', 0, ?, ?)",
                (model, resolution, int(selected["points"]), int(selected["enabled"])),
            )

    db.execute(
        "INSERT INTO app_settings (key, value, updated_at) VALUES (?, ?, ?) ON CONFLICT(key) DO NOTHING",
        (marker_key, "seedance-request-prices-v2", utc_now()),
    )


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


def migrate_generation_tasks_table(db: sqlite3.Connection) -> None:
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS generation_tasks (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL,
          dialogue_id INTEGER,
          prompt TEXT NOT NULL,
          mode TEXT NOT NULL,
          model TEXT NOT NULL DEFAULT '',
          ratio TEXT NOT NULL,
          resolution TEXT NOT NULL,
          actual_size TEXT NOT NULL,
          quality TEXT NOT NULL,
          output_format TEXT NOT NULL,
          count INTEGER NOT NULL,
          cost INTEGER NOT NULL DEFAULT 0,
          status TEXT NOT NULL,
          record_id INTEGER,
          reference_paths TEXT NOT NULL DEFAULT '[]',
          error_message TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          finished_at TEXT NOT NULL DEFAULT '',
          dismissed_at TEXT NOT NULL DEFAULT '',
          bypass_billing INTEGER NOT NULL DEFAULT 0,
          media_type TEXT NOT NULL DEFAULT 'image',
          provider_id INTEGER,
          provider_task_id TEXT NOT NULL DEFAULT '',
          duration_seconds INTEGER NOT NULL DEFAULT 0,
          metadata_json TEXT NOT NULL DEFAULT '{}',
          FOREIGN KEY(dialogue_id) REFERENCES dialogues(id),
          FOREIGN KEY(record_id) REFERENCES records(id),
          FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )
    columns = {row["name"] for row in db.execute("PRAGMA table_info(generation_tasks)").fetchall()}
    migrations = {
        "model": "ALTER TABLE generation_tasks ADD COLUMN model TEXT NOT NULL DEFAULT ''",
        "dismissed_at": "ALTER TABLE generation_tasks ADD COLUMN dismissed_at TEXT NOT NULL DEFAULT ''",
        "bypass_billing": "ALTER TABLE generation_tasks ADD COLUMN bypass_billing INTEGER NOT NULL DEFAULT 0",
        "media_type": "ALTER TABLE generation_tasks ADD COLUMN media_type TEXT NOT NULL DEFAULT 'image'",
        "provider_id": "ALTER TABLE generation_tasks ADD COLUMN provider_id INTEGER",
        "provider_task_id": "ALTER TABLE generation_tasks ADD COLUMN provider_task_id TEXT NOT NULL DEFAULT ''",
        "duration_seconds": "ALTER TABLE generation_tasks ADD COLUMN duration_seconds INTEGER NOT NULL DEFAULT 0",
        "metadata_json": "ALTER TABLE generation_tasks ADD COLUMN metadata_json TEXT NOT NULL DEFAULT '{}'",
    }
    for column, statement in migrations.items():
        if column not in columns:
            db.execute(statement)
    if "dismissed_at" not in columns:
        db.execute(
            """
            UPDATE generation_tasks
            SET dismissed_at = COALESCE(NULLIF(finished_at, ''), updated_at, created_at)
            WHERE status = 'failed'
            """
        )


def migrate_api_providers_table(db: sqlite3.Connection) -> None:
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS api_providers (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          provider_type TEXT NOT NULL,
          name TEXT NOT NULL,
          base_url TEXT NOT NULL DEFAULT '',
          api_key TEXT NOT NULL DEFAULT '',
          model TEXT NOT NULL DEFAULT '',
          api_format TEXT NOT NULL DEFAULT 'openai',
          resolutions TEXT NOT NULL DEFAULT '["1K","2K","4K"]',
          capabilities TEXT NOT NULL DEFAULT '[]',
          models_json TEXT NOT NULL DEFAULT '[]',
          settings_json TEXT NOT NULL DEFAULT '{}',
          priority INTEGER NOT NULL DEFAULT 100,
          enabled INTEGER NOT NULL DEFAULT 1,
          last_error TEXT NOT NULL DEFAULT '',
          disabled_at TEXT NOT NULL DEFAULT '',
          last_checked_at TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        )
        """
    )
    columns = {row["name"] for row in db.execute("PRAGMA table_info(api_providers)").fetchall()}
    if "resolutions" not in columns:
        db.execute("ALTER TABLE api_providers ADD COLUMN resolutions TEXT NOT NULL DEFAULT '[\"1K\",\"2K\",\"4K\"]'")
    if "api_format" not in columns:
        db.execute("ALTER TABLE api_providers ADD COLUMN api_format TEXT NOT NULL DEFAULT 'openai'")
    if "capabilities" not in columns:
        db.execute("ALTER TABLE api_providers ADD COLUMN capabilities TEXT NOT NULL DEFAULT '[]'")
    if "models_json" not in columns:
        db.execute("ALTER TABLE api_providers ADD COLUMN models_json TEXT NOT NULL DEFAULT '[]'")
    if "settings_json" not in columns:
        db.execute("ALTER TABLE api_providers ADD COLUMN settings_json TEXT NOT NULL DEFAULT '{}'")
    db.execute(
        """
        UPDATE api_providers
        SET resolutions = '["1K","2K","4K"]'
        WHERE provider_type = 'image' AND (resolutions = '' OR resolutions IS NULL)
        """
    )
    db.execute(
        """
        UPDATE api_providers
        SET capabilities = CASE provider_type
            WHEN 'video' THEN '["video"]'
            WHEN 'prompt' THEN '["prompt"]'
            ELSE '["image"]'
          END
        WHERE capabilities = '' OR capabilities IS NULL OR capabilities = '[]'
        """
    )


def migrate_provider_model_types(db: object) -> None:
    """Repair known model capabilities persisted by older admin saves.

    The runtime catalog already treats official ids as authoritative, but the
    stored JSON is also rendered by the admin console and used by publication
    checks.  Normalize only ids with a documented type; custom models retain
    the administrator's explicit classification.
    """
    from huishi.provider_catalog import model_type

    rows = db.execute("SELECT id, provider_type, models_json FROM api_providers").fetchall()  # type: ignore[attr-defined]
    for row in rows:
        raw = row["models_json"]
        try:
            entries = json.loads(raw or "[]")
        except (TypeError, ValueError):
            continue
        if not isinstance(entries, list):
            continue
        changed = False
        normalized: list[object] = []
        for entry in entries:
            if not isinstance(entry, dict):
                normalized.append(entry)
                continue
            updated = dict(entry)
            canonical = model_type(updated, row["provider_type"])
            if canonical and updated.get("media_type") != canonical:
                updated["media_type"] = canonical
                changed = True
            normalized.append(updated)
        if changed:
            db.execute(
                "UPDATE api_providers SET models_json = ?, updated_at = ? WHERE id = ?",
                (json.dumps(normalized, ensure_ascii=False, separators=(",", ":")), utc_now(), row["id"]),
            )


def _normalized_grok_resolutions(value: object) -> str:
    """Return a valid, canonical resolution list for an official Grok channel."""
    from huishi.providers import normalize_provider_resolutions

    selected = [
        resolution
        for resolution in normalize_provider_resolutions(value, "image")
        if resolution in GROK_IMAGINE_RESOLUTIONS
    ]
    # A legacy empty/4K-only configuration must not become an enabled channel
    # with no schedulable resolutions. This mirrors the provider normalizer.
    return json.dumps(selected or list(GROK_IMAGINE_RESOLUTIONS), separators=(",", ":"))


def _same_provider_configuration(
    left: object,
    right: object,
    *,
    left_resolutions: str | None = None,
    left_api_format: str | None = None,
) -> bool:
    """Compare provider fields whose equality makes an id-only rename redundant."""
    fields = (
        "provider_type",
        "name",
        "base_url",
        "api_key",
        "api_format",
        "resolutions",
        "priority",
        "enabled",
    )
    for field in fields:
        if field == "resolutions":
            left_value = left_resolutions if left_resolutions is not None else left[field]  # type: ignore[index]
            right_value = _normalized_grok_resolutions(right[field])  # type: ignore[index]
        elif field == "api_format" and left_api_format is not None:
            left_value = left_api_format
            right_value = right[field]  # type: ignore[index]
        elif field == "api_key":
            left_value = _provider_api_key_for_comparison(left[field])  # type: ignore[index]
            right_value = _provider_api_key_for_comparison(right[field])  # type: ignore[index]
        else:
            left_value = left[field]  # type: ignore[index]
            right_value = right[field]  # type: ignore[index]
        if left_value != right_value:
            return False
    return True


def _provider_api_key_for_comparison(value: object) -> str:
    """Compare encrypted keys by plaintext without exposing them outside this scope."""
    from huishi.secrets import decrypt_secret, is_encrypted_secret

    raw_value = str(value or "")
    decrypted = decrypt_secret(raw_value)
    # Invalid or undecryptable legacy ciphertext must not collapse unrelated
    # providers merely because both decrypt attempts return an empty string.
    if is_encrypted_secret(raw_value) and not decrypted:
        return raw_value
    return decrypted


def migrate_grok_imagine_model_ids(db: object) -> None:
    """Rename only obsolete official Grok ids without collapsing live channels.

    This deliberately does not commit: ``init_db`` owns the surrounding
    migration transaction for both SQLite and PostgreSQL.
    """
    # Normalize established 2.0 channels before comparing legacy records. A
    # pre-upgrade 4K checkbox is not a distinct Grok channel configuration.
    target_rows = db.execute(  # type: ignore[attr-defined]
        "SELECT id, api_format, resolutions FROM api_providers WHERE model = ? ORDER BY id",
        (GROK_IMAGINE_MODEL_ID,),
    ).fetchall()
    for target_provider in target_rows:
        normalized_resolutions = _normalized_grok_resolutions(target_provider["resolutions"])
        if target_provider["api_format"] != "grok" or target_provider["resolutions"] != normalized_resolutions:
            db.execute(  # type: ignore[attr-defined]
                "UPDATE api_providers SET api_format = ?, resolutions = ? WHERE id = ?",
                ("grok", normalized_resolutions, target_provider["id"]),
            )

    for legacy_model in LEGACY_GROK_IMAGINE_MODEL_IDS:
        provider_rows = db.execute(  # type: ignore[attr-defined]
            "SELECT * FROM api_providers WHERE model = ? ORDER BY id",
            (legacy_model,),
        ).fetchall()
        for legacy_provider in provider_rows:
            normalized_resolutions = _normalized_grok_resolutions(legacy_provider["resolutions"])
            # Legacy Grok model ids were created before protocol selection was
            # persisted; make the protocol explicit before renaming/deduping.
            legacy_api_format = str(legacy_provider["api_format"] or "").strip().lower()
            if legacy_api_format != "grok":
                db.execute(  # type: ignore[attr-defined]
                    "UPDATE api_providers SET api_format = ? WHERE id = ?",
                    ("grok", legacy_provider["id"]),
                )
            target_rows = db.execute(  # type: ignore[attr-defined]
                "SELECT * FROM api_providers WHERE model = ? ORDER BY id",
                (GROK_IMAGINE_MODEL_ID,),
            ).fetchall()
            if any(
                _same_provider_configuration(
                    legacy_provider,
                    target,
                    left_resolutions=normalized_resolutions,
                    left_api_format="grok",
                )
                for target in target_rows
            ):
                db.execute("DELETE FROM api_providers WHERE id = ?", (legacy_provider["id"],))  # type: ignore[attr-defined]
            else:
                db.execute(  # type: ignore[attr-defined]
                    "UPDATE api_providers SET model = ?, resolutions = ? WHERE id = ?",
                    (GROK_IMAGINE_MODEL_ID, normalized_resolutions, legacy_provider["id"]),
                )

        pricing_rows = db.execute(  # type: ignore[attr-defined]
            "SELECT id, mode, resolution FROM pricing_rules WHERE model = ? ORDER BY id",
            (legacy_model,),
        ).fetchall()
        for legacy_rule in pricing_rows:
            target_rule = db.execute(  # type: ignore[attr-defined]
                """
                SELECT id FROM pricing_rules
                WHERE mode = ? AND model = ? AND resolution = ?
                """,
                (legacy_rule["mode"], GROK_IMAGINE_MODEL_ID, legacy_rule["resolution"]),
            ).fetchone()
            if target_rule is not None:
                # The target is either a manually edited 2.0 rule, or the
                # higher-priority Pro legacy rule moved earlier in this loop.
                db.execute("DELETE FROM pricing_rules WHERE id = ?", (legacy_rule["id"],))  # type: ignore[attr-defined]
            else:
                db.execute(  # type: ignore[attr-defined]
                    "UPDATE pricing_rules SET model = ? WHERE id = ?",
                    (GROK_IMAGINE_MODEL_ID, legacy_rule["id"]),
                )


def migrate_postgres_schema_columns(db: PostgreSQLConnection) -> None:
    db.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS enabled INTEGER NOT NULL DEFAULT 1")
    db.execute("ALTER TABLE records ADD COLUMN IF NOT EXISTS media_type TEXT NOT NULL DEFAULT 'image'")
    db.execute("ALTER TABLE records ADD COLUMN IF NOT EXISTS mime_type TEXT NOT NULL DEFAULT ''")
    db.execute("ALTER TABLE records ADD COLUMN IF NOT EXISTS duration_ms INTEGER NOT NULL DEFAULT 0")
    db.execute("ALTER TABLE api_providers ADD COLUMN IF NOT EXISTS api_format TEXT NOT NULL DEFAULT 'openai'")
    db.execute("ALTER TABLE api_providers ADD COLUMN IF NOT EXISTS resolutions TEXT NOT NULL DEFAULT '[\"1K\",\"2K\",\"4K\"]'")
    db.execute("ALTER TABLE api_providers ADD COLUMN IF NOT EXISTS capabilities TEXT NOT NULL DEFAULT '[]'")
    db.execute("ALTER TABLE api_providers ADD COLUMN IF NOT EXISTS models_json TEXT NOT NULL DEFAULT '[]'")
    db.execute("ALTER TABLE api_providers ADD COLUMN IF NOT EXISTS settings_json TEXT NOT NULL DEFAULT '{}'")
    db.execute("ALTER TABLE pricing_rules ADD COLUMN IF NOT EXISTS model TEXT NOT NULL DEFAULT '*'")
    db.execute("ALTER TABLE pricing_rules ADD COLUMN IF NOT EXISTS media_type TEXT NOT NULL DEFAULT 'image'")
    db.execute("ALTER TABLE pricing_rules ADD COLUMN IF NOT EXISTS duration_tier TEXT NOT NULL DEFAULT ''")
    db.execute("ALTER TABLE generation_tasks ADD COLUMN IF NOT EXISTS model TEXT NOT NULL DEFAULT ''")
    db.execute("ALTER TABLE generation_tasks ADD COLUMN IF NOT EXISTS media_type TEXT NOT NULL DEFAULT 'image'")
    db.execute("ALTER TABLE generation_tasks ADD COLUMN IF NOT EXISTS provider_id INTEGER")
    db.execute("ALTER TABLE generation_tasks ADD COLUMN IF NOT EXISTS provider_task_id TEXT NOT NULL DEFAULT ''")
    db.execute("ALTER TABLE generation_tasks ADD COLUMN IF NOT EXISTS duration_seconds INTEGER NOT NULL DEFAULT 0")
    db.execute("ALTER TABLE generation_tasks ADD COLUMN IF NOT EXISTS metadata_json TEXT NOT NULL DEFAULT '{}'")
    db.execute("UPDATE pricing_rules SET media_type = 'image' WHERE media_type IS NULL OR media_type = ''")
    db.execute("UPDATE pricing_rules SET model = '*' WHERE model IS NULL OR model = ''")
    db.execute("ALTER TABLE pricing_rules DROP CONSTRAINT IF EXISTS pricing_rules_mode_resolution_key")
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_pricing_rules_mode_model_resolution ON pricing_rules(mode, model, resolution)")


def migrate_packages_table(db: sqlite3.Connection) -> None:
    db.execute(
        """
        DELETE FROM packages
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM packages
            GROUP BY name, price_cents, points, description
        )
        """
    )
    for name, price_cents, points, description in DEFAULT_PACKAGES:
        db.execute(
            """
            DELETE FROM packages
            WHERE name = ?
              AND price_cents = ?
              AND points = ?
              AND description = ?
              AND EXISTS (
                SELECT 1
                FROM packages AS edited
                WHERE edited.name = packages.name
                  AND edited.id != packages.id
              )
            """,
            (name, price_cents, points, description),
        )
    db.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_packages_unique_bundle
        ON packages(name, price_cents, points, description)
        """
    )
    marker = db.execute("SELECT value FROM app_settings WHERE key = ?", ("points_equal_price_cents_20260922",)).fetchone()
    if marker is None:
        db.execute("UPDATE packages SET points = price_cents WHERE points <> price_cents")
        db.execute(
            "INSERT INTO app_settings (key, value, updated_at) VALUES (?, ?, ?) ON CONFLICT(key) DO NOTHING",
            ("points_equal_price_cents_20260922", "1-point-equals-1-cent", utc_now()),
        )


def migrate_invites_table(db: sqlite3.Connection) -> None:
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS invite_codes (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          code TEXT NOT NULL UNIQUE,
          owner_user_id INTEGER NOT NULL,
          reward_points INTEGER NOT NULL DEFAULT 0,
          max_uses INTEGER,
          used_count INTEGER NOT NULL DEFAULT 0,
          enabled INTEGER NOT NULL DEFAULT 1,
          created_by_admin_id INTEGER,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          FOREIGN KEY(owner_user_id) REFERENCES users(id),
          FOREIGN KEY(created_by_admin_id) REFERENCES users(id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS invite_redemptions (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          invite_code_id INTEGER NOT NULL,
          inviter_user_id INTEGER NOT NULL,
          invitee_user_id INTEGER NOT NULL UNIQUE,
          reward_points INTEGER NOT NULL,
          created_at TEXT NOT NULL,
          FOREIGN KEY(inviter_user_id) REFERENCES users(id),
          FOREIGN KEY(invitee_user_id) REFERENCES users(id)
        )
        """
    )


def migrate_secret_values(db: sqlite3.Connection) -> None:
    from huishi.secrets import SECRET_APP_SETTING_KEYS, encrypt_secret, is_encrypted_secret

    if not current_app.config.get("ENCRYPTION_KEY"):
        return
    now = utc_now()
    placeholders, params = sql_placeholders(SECRET_APP_SETTING_KEYS)
    rows = db.execute(
        f"SELECT key, value FROM app_settings WHERE key IN ({placeholders})",
        params,
    ).fetchall()
    for row in rows:
        value = str(row["value"] or "")
        if not value or is_encrypted_secret(value):
            continue
        db.execute(
            "UPDATE app_settings SET value = ?, updated_at = ? WHERE key = ?",
            (encrypt_secret(value), now, row["key"]),
        )

    provider_rows = db.execute("SELECT id, api_key FROM api_providers WHERE api_key != ''").fetchall()
    for row in provider_rows:
        value = str(row["api_key"] or "")
        if not value or is_encrypted_secret(value):
            continue
        db.execute(
            "UPDATE api_providers SET api_key = ?, updated_at = ? WHERE id = ?",
            (encrypt_secret(value), now, row["id"]),
        )

    user_setting_rows = db.execute(
        "SELECT user_id, api_key FROM user_settings WHERE api_key != ''"
    ).fetchall()
    for row in user_setting_rows:
        value = str(row["api_key"] or "")
        if not value or is_encrypted_secret(value):
            continue
        db.execute(
            "UPDATE user_settings SET api_key = ?, updated_at = ? WHERE user_id = ?",
            (encrypt_secret(value), now, row["user_id"]),
        )


def seed_defaults(db: sqlite3.Connection) -> None:
    for model, resolution, points in IMAGE_PRICING_CATALOG:
        db.execute(
            """
            INSERT INTO pricing_rules (mode, model, resolution, points_per_image, enabled, media_type, duration_tier)
            VALUES ('text', ?, ?, ?, 1, 'image', '')
            ON CONFLICT (mode, model, resolution) DO NOTHING
            """,
            (model, resolution, points),
        )
    for model, resolution, unit, duration, points in VIDEO_PRICING_CATALOG:
        db.execute(
            """
            INSERT INTO video_pricing_rules (model, resolution, billing_unit, duration_seconds, points, enabled)
            VALUES (?, ?, ?, ?, ?, 1)
            ON CONFLICT (model, resolution, billing_unit, duration_seconds) DO NOTHING
            """,
            (model, resolution, unit, duration, points),
        )
    package_count = db.execute("SELECT COUNT(*) AS count FROM packages").fetchone()["count"]
    if package_count == 0:
        for name, price_cents, points, description in DEFAULT_PACKAGES:
            db.execute(
                """
                INSERT INTO packages (name, price_cents, points, description, enabled)
                VALUES (?, ?, ?, ?, 1)
                """,
                (name, price_cents, points, description),
            )
    db.execute(
        """
        INSERT OR IGNORE INTO app_settings (key, value, updated_at)
        VALUES ('invite_default_reward_points', '0', ?)
        """,
        (utc_now(),),
    )
    db.execute(
        """
        INSERT OR IGNORE INTO app_settings (key, value, updated_at)
        VALUES ('user_key_enabled', '1', ?)
        """,
        (utc_now(),),
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


def fix_canvas_records_dialogue(db: sqlite3.Connection) -> None:
    """把错误分配了 dialogue_id 的 canvas 记录还原为 NULL，
    同时清理因此变空的对话行。"""
    db.execute(
        "UPDATE records SET dialogue_id = NULL WHERE asset_source = 'canvas' AND dialogue_id IS NOT NULL"
    )
    db.execute(
        """
        DELETE FROM dialogues
        WHERE id NOT IN (
            SELECT DISTINCT dialogue_id FROM records WHERE dialogue_id IS NOT NULL
        )
        """
    )


def migrate_canvas_tables(db: sqlite3.Connection) -> None:
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS canvas_conversations (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL,
          title TEXT NOT NULL DEFAULT '新对话',
          archived INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS canvas_messages (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          conversation_id INTEGER NOT NULL,
          role TEXT NOT NULL,
          content TEXT NOT NULL DEFAULT '',
          tool_calls TEXT NOT NULL DEFAULT '[]',
          created_at TEXT NOT NULL,
          FOREIGN KEY(conversation_id) REFERENCES canvas_conversations(id)
        )
        """
    )
