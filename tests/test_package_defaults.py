from __future__ import annotations

from pathlib import Path

import pytest

from app import create_app
from huishi.db import get_db, init_db


@pytest.fixture()
def app(tmp_path: Path):
    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "test.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"
    with app.app_context():
        init_db()
    return app


def test_init_db_does_not_recreate_edited_default_packages(app):
    with app.app_context():
        db = get_db()
        db.execute("UPDATE packages SET points = 450 WHERE name = ?", ("创作包",))
        db.execute("UPDATE packages SET points = 1100 WHERE name = ?", ("专业包",))
        db.commit()

        init_db()

        rows = db.execute(
            """
            SELECT name, points, COUNT(*) AS count
            FROM packages
            GROUP BY name, points
            ORDER BY name, points
            """
        ).fetchall()

    assert [dict(row) for row in rows] == [
        {"name": "专业包", "points": 1100, "count": 1},
        {"name": "入门包", "points": 100, "count": 1},
        {"name": "创作包", "points": 450, "count": 1},
    ]


def test_init_db_removes_recreated_default_package_when_edited_version_exists(app):
    with app.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO packages (name, price_cents, points, description, enabled) VALUES (?, ?, ?, ?, 1)",
            ("创作包", 3990, 450, "适合持续生成和调试作品。"),
        )
        db.execute(
            "INSERT INTO packages (name, price_cents, points, description, enabled) VALUES (?, ?, ?, ?, 1)",
            ("专业包", 8990, 1100, "适合高频创作和 4K 输出。"),
        )
        db.commit()

        init_db()

        rows = db.execute(
            """
            SELECT name, points, COUNT(*) AS count
            FROM packages
            GROUP BY name, points
            ORDER BY name, points
            """
        ).fetchall()

    assert [dict(row) for row in rows] == [
        {"name": "专业包", "points": 1100, "count": 1},
        {"name": "入门包", "points": 100, "count": 1},
        {"name": "创作包", "points": 450, "count": 1},
    ]
