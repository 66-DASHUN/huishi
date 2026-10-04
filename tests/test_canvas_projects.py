from __future__ import annotations

import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from app import create_app
from huishi.canvas_session import issue_canvas_session_token
from huishi.db import get_db, init_db
from huishi.storage import sweep_local_uploads


@pytest.fixture()
def app(tmp_path: Path):
    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "test.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"
    app.config["OUTPUT_DIR"].mkdir(parents=True, exist_ok=True)
    app.config["CANVAS_APP_URL"] = "http://127.0.0.1:3000"
    with app.app_context():
        init_db()
    return app


def _create_user(username: str) -> tuple[int, str]:
    cursor = get_db().execute(
        """
        INSERT INTO users (username, email, password_hash, role, email_verified, points, created_at)
        VALUES (?, '', 'hash', 'user', 1, 20, 'now')
        """,
        (username,),
    )
    get_db().commit()
    user_id = int(cursor.lastrowid)
    user = get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    token, _ = issue_canvas_session_token(user)
    return user_id, token


def _headers(token: str) -> dict[str, str]:
    return {"Origin": "http://127.0.0.1:3000", "X-Canvas-Session": token}


def _project(project_id: str = "project-1", *, title: str = "第一张画布", base_rev: int = 0):
    return {
        "id": project_id,
        "title": title,
        "schemaVersion": 1,
        "baseRev": base_rev,
        "createdAt": "2026-07-15T00:00:00+00:00",
        "updatedAt": "2026-07-15T00:00:00+00:00",
        "payload": {
            "nodes": [
                {
                    "id": "image-1",
                    "type": "image",
                    "title": "图片",
                    "position": {"x": 0, "y": 0},
                    "width": 512,
                    "height": 512,
                    "metadata": {
                        "content": "/static/uploads/canvas-kept.png",
                        "storageKey": "image:canvas-kept",
                    },
                }
            ],
            "connections": [],
            "chatSessions": [],
            "activeChatId": None,
            "backgroundMode": "lines",
            "showImageInfo": False,
            "viewport": {"x": 0, "y": 0, "k": 1},
        },
    }


def test_init_db_creates_canvas_project_and_asset_tables(app):
    with app.app_context():
        rows = get_db().execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name IN ('canvas_projects', 'canvas_project_assets')
            """
        ).fetchall()

    assert {row["name"] for row in rows} == {"canvas_projects", "canvas_project_assets"}


def test_canvas_project_routes_are_user_scoped_and_revision_guarded(app):
    with app.app_context():
        _owner_id, owner_token = _create_user("project-owner")
        _other_id, other_token = _create_user("project-other")

    with app.test_client() as client:
        created = client.post(
            "/api/canvas/projects",
            json={"project": _project()},
            headers=_headers(owner_token),
        )
        assert created.status_code == 200
        assert created.get_json()["project"]["rev"] == 1

        listed = client.get("/api/canvas/projects", headers=_headers(owner_token))
        assert listed.status_code == 200
        assert [item["id"] for item in listed.get_json()["projects"]] == ["project-1"]
        assert listed.get_json()["projects"][0]["payload"]["nodes"][0]["id"] == "image-1"

        hidden = client.get("/api/canvas/projects/project-1", headers=_headers(other_token))
        assert hidden.status_code == 404

        updated_project = _project(title="已更新", base_rev=1)
        updated = client.patch(
            "/api/canvas/projects/project-1",
            json={"project": updated_project},
            headers=_headers(owner_token),
        )
        assert updated.status_code == 200
        assert updated.get_json()["project"]["rev"] == 2
        assert updated.get_json()["project"]["title"] == "已更新"

        conflict = client.patch(
            "/api/canvas/projects/project-1",
            json={"project": _project(title="过期覆盖", base_rev=1)},
            headers=_headers(owner_token),
        )
        assert conflict.status_code == 409
        assert conflict.get_json()["error"] == "revision_conflict"
        assert conflict.get_json()["project"]["rev"] == 2
        assert conflict.get_json()["project"]["title"] == "已更新"

        deleted = client.delete("/api/canvas/projects/project-1", headers=_headers(owner_token))
        assert deleted.status_code == 200
        assert client.get("/api/canvas/projects/project-1", headers=_headers(owner_token)).status_code == 404

    with app.app_context():
        row = get_db().execute("SELECT deleted_at FROM canvas_projects WHERE id = ?", ("project-1",)).fetchone()
        assert row is not None
        assert row["deleted_at"]


def test_canvas_embed_url_includes_canvas_projects_endpoint(app):
    from huishi.routes_workspace import build_canvas_embed_url

    with app.test_request_context("/", base_url="https://huishi.example"):
        url = build_canvas_embed_url("http://127.0.0.1:3000", "session-token")

    params = parse_qs(urlsplit(url).query)
    assert params["host_projects_url"] == ["https://huishi.example/api/canvas/projects"]


def test_canvas_project_asset_references_are_protected_from_storage_sweep(app):
    with app.app_context():
        _user_id, token = _create_user("asset-owner")
        upload = app.config["OUTPUT_DIR"] / "canvas-kept.png"
        upload.write_bytes(b"canvas")
        old = time.time() - 10 * 86400
        upload.touch()
        import os

        os.utime(upload, (old, old))

    with app.test_client() as client:
        created = client.post(
            "/api/canvas/projects",
            json={"project": _project()},
            headers=_headers(token),
        )
        assert created.status_code == 200

    with app.app_context():
        refs = get_db().execute(
            "SELECT asset_ref FROM canvas_project_assets WHERE project_id = ?",
            ("project-1",),
        ).fetchall()
        result = sweep_local_uploads(
            app.config["OUTPUT_DIR"],
            get_db(),
            retention_seconds=0,
            orphan_retention_seconds=0,
        )

    assert {row["asset_ref"] for row in refs} == {"/static/uploads/canvas-kept.png"}
    assert result.deleted_files == []
    assert upload.exists()
