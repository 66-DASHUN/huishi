from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app import create_app

from huishi.db import SCHEMA
from huishi.db_backend import PostgreSQLConnection


TARGET = "grok-imagine-image-2.0"
LEGACY = "grok-imagine-image"
LEGACY_PRO = "grok-imagine-image-pro"


@pytest.fixture()
def app(tmp_path: Path):
    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "test.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"
    with app.app_context():
        from huishi.db import init_db

        init_db()
    return app


def database() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    return db


def add_provider(
    db: sqlite3.Connection,
    *,
    model: str,
    name: str,
    base_url: str,
    api_key: str,
    priority: int = 100,
    resolutions: str = '["1K","2K"]',
) -> int:
    cursor = db.execute(
        """
        INSERT INTO api_providers
        (provider_type, name, base_url, api_key, model, api_format, resolutions, priority, enabled, last_error, disabled_at, last_checked_at, created_at, updated_at)
        VALUES ('image', ?, ?, ?, ?, 'grok', ?, ?, 1, '', '', '', 'created', 'updated')
        """,
        (name, base_url, api_key, model, resolutions, priority),
    )
    return int(cursor.lastrowid)


def add_price(db: sqlite3.Connection, model: str, resolution: str, points: int, enabled: int = 1, *, mode: str = "text") -> int:
    cursor = db.execute(
        "INSERT INTO pricing_rules (mode, model, resolution, points_per_image, enabled) VALUES (?, ?, ?, ?, ?)",
        (mode, model, resolution, points, enabled),
    )
    return int(cursor.lastrowid)


def test_grok_model_migration_is_idempotent_and_preserves_custom_ids():
    from huishi.db import migrate_grok_imagine_model_ids

    db = database()
    legacy_id = add_provider(db, model=LEGACY, name="old channel", base_url="https://one.example", api_key="encrypted-key", priority=12)
    add_provider(db, model="grok-imagine-image-custom", name="custom", base_url="https://custom.example", api_key="custom-key")
    add_price(db, LEGACY, "1K", 3)
    add_price(db, "grok-imagine-image-custom", "1K", 17)

    migrate_grok_imagine_model_ids(db)
    migrate_grok_imagine_model_ids(db)

    migrated = db.execute("SELECT * FROM api_providers WHERE id = ?", (legacy_id,)).fetchone()
    assert migrated["model"] == TARGET
    assert dict(migrated)["name"] == "old channel"
    assert dict(migrated)["base_url"] == "https://one.example"
    assert dict(migrated)["api_key"] == "encrypted-key"
    assert dict(migrated)["priority"] == 12
    assert dict(migrated)["enabled"] == 1
    assert dict(migrated)["resolutions"] == '["1K","2K"]'
    assert dict(migrated)["created_at"] == "created"
    assert dict(migrated)["updated_at"] == "updated"
    assert db.execute("SELECT COUNT(*) AS count FROM api_providers WHERE model = ?", (TARGET,)).fetchone()["count"] == 1
    assert db.execute("SELECT points_per_image FROM pricing_rules WHERE model = ? AND resolution = '1K'", (TARGET,)).fetchone()["points_per_image"] == 3
    assert db.execute("SELECT COUNT(*) AS count FROM api_providers WHERE model = 'grok-imagine-image-custom'").fetchone()["count"] == 1
    assert db.execute("SELECT COUNT(*) AS count FROM pricing_rules WHERE model = 'grok-imagine-image-custom'").fetchone()["count"] == 1


def test_api_provider_schema_migration_defaults_to_openai_then_normalizes_official_grok():
    from huishi.db import migrate_api_providers_table, migrate_grok_imagine_model_ids

    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute(
        """
        CREATE TABLE api_providers (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          provider_type TEXT NOT NULL,
          name TEXT NOT NULL,
          base_url TEXT NOT NULL DEFAULT '',
          api_key TEXT NOT NULL DEFAULT '',
          model TEXT NOT NULL DEFAULT '',
          resolutions TEXT NOT NULL DEFAULT '[\"1K\",\"2K\",\"4K\"]',
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
    db.execute(
        """
        CREATE TABLE pricing_rules (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          mode TEXT NOT NULL,
          model TEXT NOT NULL DEFAULT '*',
          resolution TEXT NOT NULL,
          points_per_image INTEGER NOT NULL,
          enabled INTEGER NOT NULL DEFAULT 1,
          UNIQUE(mode, model, resolution)
        )
        """
    )
    db.execute(
        """
        INSERT INTO api_providers
        (provider_type, name, model, created_at, updated_at)
        VALUES ('image', 'legacy', 'some-openai-model', 'created', 'updated')
        """
    )
    db.execute(
        """
        INSERT INTO api_providers
        (provider_type, name, model, created_at, updated_at)
        VALUES ('image', 'official grok', ?, 'created', 'updated')
        """,
        (TARGET,),
    )

    migrate_api_providers_table(db)
    assert [row["api_format"] for row in db.execute("SELECT api_format FROM api_providers ORDER BY id")] == [
        "openai",
        "openai",
    ]
    migrate_grok_imagine_model_ids(db)
    migrate_grok_imagine_model_ids(db)

    columns = {row["name"] for row in db.execute("PRAGMA table_info(api_providers)").fetchall()}
    assert "api_format" in columns
    providers = db.execute("SELECT model, api_format, resolutions FROM api_providers ORDER BY id").fetchall()
    assert [tuple(row) for row in providers] == [
        ("some-openai-model", "openai", '["1K","2K","4K"]'),
        (TARGET, "grok", '["1K","2K"]'),
    ]


def test_legacy_grok_models_migrate_protocol_and_resolutions_idempotently():
    from huishi.db import migrate_grok_imagine_model_ids

    db = database()
    legacy_id = add_provider(
        db,
        model=LEGACY,
        name="legacy",
        base_url="https://legacy.example",
        api_key="legacy-key",
        resolutions='["1K","2K","4K"]',
    )
    pro_id = add_provider(
        db,
        model=LEGACY_PRO,
        name="pro",
        base_url="https://pro.example",
        api_key="pro-key",
        resolutions='["1K","2K","4K"]',
    )
    db.execute("UPDATE api_providers SET api_format = 'openai' WHERE id IN (?, ?)", (legacy_id, pro_id))

    migrate_grok_imagine_model_ids(db)
    migrate_grok_imagine_model_ids(db)

    providers = db.execute(
        "SELECT id, model, api_format, resolutions FROM api_providers ORDER BY id"
    ).fetchall()
    assert [tuple(row) for row in providers] == [
        (legacy_id, TARGET, "grok", '["1K","2K"]'),
        (pro_id, TARGET, "grok", '["1K","2K"]'),
    ]


def test_grok_provider_migration_keeps_distinct_channels_but_removes_true_duplicate():
    from huishi.db import migrate_grok_imagine_model_ids

    db = database()
    target_id = add_provider(db, model=TARGET, name="target", base_url="https://target.example", api_key="target-key", priority=10)
    distinct_legacy_id = add_provider(db, model=LEGACY, name="old distinct", base_url="https://legacy.example", api_key="legacy-key", priority=20)
    add_provider(db, model=LEGACY_PRO, name="target", base_url="https://target.example", api_key="target-key", priority=10)

    migrate_grok_imagine_model_ids(db)

    providers = db.execute("SELECT id, model, name, base_url, api_key, priority FROM api_providers ORDER BY id").fetchall()
    assert [(row["id"], row["model"], row["base_url"]) for row in providers] == [
        (target_id, TARGET, "https://target.example"),
        (distinct_legacy_id, TARGET, "https://legacy.example"),
    ]


def test_grok_provider_migration_normalizes_resolutions_before_deduplication():
    from huishi.db import migrate_grok_imagine_model_ids

    db = database()
    target_id = add_provider(
        db, model=TARGET, name="same", base_url="https://same.example", api_key="same-key", resolutions='["1K","2K"]'
    )
    add_provider(
        db, model=LEGACY, name="same", base_url="https://same.example", api_key="same-key", resolutions='["1K","2K","4K"]'
    )
    fallback_id = add_provider(
        db, model=LEGACY_PRO, name="fallback", base_url="https://fallback.example", api_key="fallback-key", resolutions='["4K"]'
    )

    migrate_grok_imagine_model_ids(db)

    providers = db.execute("SELECT id, model, resolutions FROM api_providers ORDER BY id").fetchall()
    assert [tuple(row) for row in providers] == [
        (target_id, TARGET, '["1K","2K"]'),
        (fallback_id, TARGET, '["1K","2K"]'),
    ]


def test_grok_pricing_migration_prefers_existing_target_then_pro_rule():
    from huishi.db import migrate_grok_imagine_model_ids

    db = database()
    add_price(db, TARGET, "1K", 99, enabled=0)
    add_price(db, LEGACY_PRO, "1K", 7, enabled=1)
    add_price(db, LEGACY, "1K", 3, enabled=1)
    add_price(db, LEGACY_PRO, "2K", 8, enabled=1)
    add_price(db, LEGACY, "2K", 4, enabled=0)

    migrate_grok_imagine_model_ids(db)

    rules = db.execute("SELECT model, resolution, points_per_image, enabled FROM pricing_rules ORDER BY resolution").fetchall()
    assert [tuple(row) for row in rules] == [
        (TARGET, "1K", 99, 0),
        (TARGET, "2K", 8, 1),
    ]
    assert db.execute("SELECT COUNT(*) AS count FROM pricing_rules WHERE model IN (?, ?)", (LEGACY, LEGACY_PRO)).fetchone()["count"] == 0


def test_seed_defaults_only_adds_supported_resolutions_for_official_models(app):
    from huishi.db import get_db

    with app.app_context():
        db = get_db()
        grok = db.execute("SELECT resolution FROM pricing_rules WHERE model = ? ORDER BY resolution", (TARGET,)).fetchall()
        banana_pro = db.execute("SELECT resolution FROM pricing_rules WHERE model = 'gemini-3-pro-image' ORDER BY resolution").fetchall()

    assert [row["resolution"] for row in grok] == ["1K", "2K"]
    assert [row["resolution"] for row in banana_pro] == ["1K", "2K", "4K"]


def test_sqlite_init_is_repeatable_after_explicit_schema_transaction(app):
    from huishi.db import get_db, init_db

    with app.app_context():
        init_db()
        init_db()
        pricing_count = get_db().execute("SELECT COUNT(*) AS count FROM pricing_rules").fetchone()["count"]

    assert pricing_count > 0


def test_grok_model_migration_uses_postgres_compatible_sql_without_committing():
    from huishi.db import migrate_grok_imagine_model_ids

    class Cursor:
        rowcount = 0

        def fetchone(self):
            return None

        def fetchall(self):
            return []

    class RawPostgres:
        def __init__(self):
            self.executed: list[tuple[str, tuple[object, ...]]] = []
            self.commits = 0

        def execute(self, sql, params=()):
            self.executed.append((sql, tuple(params or ())))
            return Cursor()

        def commit(self):
            self.commits += 1

        def rollback(self):
            pass

        def close(self):
            pass

    raw = RawPostgres()
    migrate_grok_imagine_model_ids(PostgreSQLConnection(raw))

    assert raw.commits == 0
    assert raw.executed
    assert all("PRAGMA" not in sql and "INSERT OR IGNORE" not in sql for sql, _params in raw.executed)
    assert all("%s" in sql for sql, _params in raw.executed)


def test_grok_model_migration_postgres_contract_migrates_realistic_rows_idempotently():
    from huishi.db import migrate_grok_imagine_model_ids

    class Cursor:
        rowcount = 1

        def __init__(self, rows=()):
            self.rows = list(rows)

        def fetchone(self):
            return self.rows[0] if self.rows else None

        def fetchall(self):
            return list(self.rows)

    class RawPostgres:
        def __init__(self):
            self.executed: list[tuple[str, tuple[object, ...]]] = []
            self.commits = 0
            self.providers = [
                {"id": 1, "provider_type": "image", "name": "target", "base_url": "https://same.example", "api_key": "key", "api_format": "openai", "resolutions": '["1K","2K"]', "priority": 10, "enabled": 1},
                {"id": 2, "provider_type": "image", "name": "target", "base_url": "https://same.example", "api_key": "key", "api_format": "grok", "resolutions": '["1K","2K","4K"]', "priority": 10, "enabled": 1, "model": LEGACY},
                {"id": 3, "provider_type": "image", "name": "fallback", "base_url": "https://other.example", "api_key": "other", "api_format": "grok", "resolutions": '["4K"]', "priority": 20, "enabled": 1, "model": LEGACY_PRO},
            ]
            self.providers[0]["model"] = TARGET
            self.prices = [
                {"id": 10, "mode": "text", "model": TARGET, "resolution": "1K", "points_per_image": 99, "enabled": 0},
                {"id": 11, "mode": "text", "model": LEGACY_PRO, "resolution": "1K", "points_per_image": 7, "enabled": 1},
                {"id": 12, "mode": "text", "model": LEGACY_PRO, "resolution": "2K", "points_per_image": 8, "enabled": 1},
                {"id": 13, "mode": "text", "model": LEGACY, "resolution": "2K", "points_per_image": 4, "enabled": 1},
            ]

        def execute(self, sql, params=()):
            params = tuple(params or ())
            self.executed.append((sql, params))
            compact = " ".join(sql.split())
            if compact.startswith("SELECT id, api_format, resolutions FROM api_providers"):
                return Cursor(sorted((row for row in self.providers if row["model"] == params[0]), key=lambda row: row["id"]))
            if compact.startswith("SELECT * FROM api_providers"):
                return Cursor(sorted((row for row in self.providers if row["model"] == params[0]), key=lambda row: row["id"]))
            if compact.startswith("UPDATE api_providers SET resolutions"):
                for row in self.providers:
                    if row["id"] == params[1]:
                        row["resolutions"] = params[0]
                return Cursor()
            if compact.startswith("UPDATE api_providers SET api_format"):
                for row in self.providers:
                    if row["id"] == params[2]:
                        row["api_format"], row["resolutions"] = params[0], params[1]
                return Cursor()
            if compact.startswith("UPDATE api_providers SET model"):
                for row in self.providers:
                    if row["id"] == params[2]:
                        row["model"], row["resolutions"] = params[0], params[1]
                return Cursor()
            if compact.startswith("DELETE FROM api_providers"):
                self.providers = [row for row in self.providers if row["id"] != params[0]]
                return Cursor()
            if compact.startswith("SELECT id, mode, resolution FROM pricing_rules"):
                return Cursor(sorted((row for row in self.prices if row["model"] == params[0]), key=lambda row: row["id"]))
            if compact.startswith("SELECT id FROM pricing_rules"):
                return Cursor([row for row in self.prices if row["mode"] == params[0] and row["model"] == params[1] and row["resolution"] == params[2]])
            if compact.startswith("UPDATE pricing_rules SET model"):
                for row in self.prices:
                    if row["id"] == params[1]:
                        row["model"] = params[0]
                return Cursor()
            if compact.startswith("DELETE FROM pricing_rules"):
                self.prices = [row for row in self.prices if row["id"] != params[0]]
                return Cursor()
            raise AssertionError(f"Unexpected PostgreSQL migration statement: {sql}")

        def commit(self):
            self.commits += 1

        def rollback(self):
            pass

        def close(self):
            pass

    raw = RawPostgres()
    db = PostgreSQLConnection(raw)
    migrate_grok_imagine_model_ids(db)
    migrate_grok_imagine_model_ids(db)

    assert [(row["id"], row["model"], row["api_format"], row["resolutions"]) for row in raw.providers] == [
        (1, TARGET, "grok", '["1K","2K"]'),
        (3, TARGET, "grok", '["1K","2K"]'),
    ]
    assert [(row["id"], row["model"], row["resolution"], row["points_per_image"], row["enabled"]) for row in raw.prices] == [
        (10, TARGET, "1K", 99, 0),
        (12, TARGET, "2K", 8, 1),
    ]
    assert raw.commits == 0
    assert any("UPDATE api_providers SET api_format = %s, resolutions = %s" in sql for sql, _params in raw.executed)
    assert any("DELETE FROM api_providers" in sql for sql, _params in raw.executed)
    assert any("UPDATE api_providers SET model = %s, resolutions = %s" in sql for sql, _params in raw.executed)
    assert any("DELETE FROM pricing_rules" in sql for sql, _params in raw.executed)
    assert all("PRAGMA" not in sql for sql, _params in raw.executed)


def test_grok_provider_dedup_compares_decrypted_api_keys(app):
    from huishi.db import migrate_grok_imagine_model_ids
    from huishi.secrets import encrypt_secret

    app.config["ENCRYPTION_KEY"] = "uD2L71QbvXhnhtT4pWJ-WdSCA_WlVpcOrTpeUt2Y9T0="
    with app.app_context():
        db = database()
        add_provider(db, model=TARGET, name="channel", base_url="https://same.example", api_key=encrypt_secret("same secret"))
        add_provider(db, model=LEGACY, name="channel", base_url="https://same.example", api_key=encrypt_secret("same secret"))
        different_id = add_provider(db, model=LEGACY_PRO, name="channel", base_url="https://same.example", api_key=encrypt_secret("different secret"))

        migrate_grok_imagine_model_ids(db)

        providers = db.execute("SELECT id, model FROM api_providers ORDER BY id").fetchall()

    assert [tuple(row) for row in providers] == [(1, TARGET), (different_id, TARGET)]


def test_init_db_rolls_back_sqlite_migration_errors(monkeypatch):
    import huishi.db as db_module

    class TrackingSQLite:
        def __init__(self):
            self.connection = sqlite3.connect(":memory:")
            self.rollbacks = 0

        def executescript(self, script):
            return self.connection.executescript(script)

        def execute(self, sql, params=()):
            return self.connection.execute(sql, params)

        def commit(self):
            self.connection.commit()

        def rollback(self):
            self.rollbacks += 1
            self.connection.rollback()

    db = TrackingSQLite()
    monkeypatch.setattr(db_module, "get_db", lambda: db)
    monkeypatch.setattr(db_module, "migrate_users_table", lambda _db: (_ for _ in ()).throw(ValueError("sqlite migration failure")))

    with pytest.raises(ValueError, match="sqlite migration failure"):
        db_module.init_db()

    assert db.rollbacks == 1
    assert db.connection.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = 'pricing_rules'"
    ).fetchone()[0] == 0


def test_init_db_rolls_back_schema_and_existing_sqlite_changes_together(monkeypatch):
    import huishi.db as db_module

    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE existing_state (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
    db.execute("INSERT INTO existing_state (id, value) VALUES (1, 'before')")
    db.commit()
    monkeypatch.setattr(db_module, "get_db", lambda: db)

    def fail_after_partial_migration(connection):
        connection.execute("ALTER TABLE existing_state ADD COLUMN transient TEXT NOT NULL DEFAULT ''")
        connection.execute("UPDATE existing_state SET value = 'during' WHERE id = 1")
        raise ValueError("partial sqlite migration failure")

    monkeypatch.setattr(db_module, "migrate_users_table", fail_after_partial_migration)

    with pytest.raises(ValueError, match="partial sqlite migration failure"):
        db_module.init_db()

    columns = {row[1] for row in db.execute("PRAGMA table_info(existing_state)").fetchall()}
    assert columns == {"id", "value"}
    assert db.execute("SELECT value FROM existing_state WHERE id = 1").fetchone()[0] == "before"
    assert db.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = 'pricing_rules'"
    ).fetchone()[0] == 0


def test_init_db_rolls_back_postgres_and_unlock_failure_does_not_hide_original(monkeypatch):
    import huishi.db as db_module

    class Cursor:
        def fetchone(self):
            return None

        def fetchall(self):
            return []

    class RawPostgres:
        def __init__(self):
            self.executed: list[str] = []
            self.rollbacks = 0

        def execute(self, sql, params=()):
            self.executed.append(sql)
            if "pg_advisory_unlock" in sql:
                raise RuntimeError("unlock failure")
            return Cursor()

        def commit(self):
            raise AssertionError("must not commit a failed migration")

        def rollback(self):
            self.rollbacks += 1

        def close(self):
            pass

    raw = RawPostgres()
    db = PostgreSQLConnection(raw)
    monkeypatch.setattr(db_module, "get_db", lambda: db)
    monkeypatch.setattr(db_module, "postgres_schema_from_sqlite", lambda _schema: "")
    monkeypatch.setattr(db_module, "migrate_postgres_schema_columns", lambda _db: (_ for _ in ()).throw(ValueError("postgres migration failure")))

    with pytest.raises(ValueError, match="postgres migration failure"):
        db_module.init_db()

    assert raw.rollbacks == 1
    assert any("pg_advisory_lock" in sql for sql in raw.executed)
    assert any("pg_advisory_unlock" in sql for sql in raw.executed)


def test_postgres_init_runs_secret_migration_and_encrypts_provider_key(monkeypatch):
    import huishi.db as db_module
    from huishi.secrets import is_encrypted_secret

    class Cursor:
        def __init__(self, rows=()):
            self.rows = list(rows)

        def fetchone(self):
            return self.rows[0] if self.rows else None

        def fetchall(self):
            return list(self.rows)

    class RawPostgres:
        def __init__(self):
            self.updated_key = ""
            self.commits = 0

        def execute(self, sql, params=()):
            compact = " ".join(sql.split())
            if "FROM app_settings" in compact or "FROM user_settings" in compact:
                return Cursor()
            if "SELECT id, api_key FROM api_providers" in compact:
                return Cursor([{"id": 7, "api_key": "plain-provider-key"}])
            if compact.startswith("UPDATE api_providers SET api_key"):
                self.updated_key = params[0]
            return Cursor()

        def commit(self):
            self.commits += 1

        def rollback(self):
            raise AssertionError("successful migration must not roll back")

        def close(self):
            pass

    raw = RawPostgres()
    db = PostgreSQLConnection(raw)
    monkeypatch.setattr(db_module, "get_db", lambda: db)
    monkeypatch.setattr(db_module, "postgres_schema_from_sqlite", lambda _schema: "")
    monkeypatch.setattr(db_module, "migrate_postgres_schema_columns", lambda _db: None)
    monkeypatch.setattr(db_module, "migrate_grok_imagine_model_ids", lambda _db: None)
    monkeypatch.setattr(db_module, "migrate_packages_table", lambda _db: None)
    monkeypatch.setattr(db_module, "seed_defaults", lambda _db: None)

    app = create_app(testing=True)
    app.config["ENCRYPTION_KEY"] = "uD2L71QbvXhnhtT4pWJ-WdSCA_WlVpcOrTpeUt2Y9T0="
    with app.app_context():
        db_module.init_db()

    assert is_encrypted_secret(raw.updated_key)
    assert raw.commits == 1
