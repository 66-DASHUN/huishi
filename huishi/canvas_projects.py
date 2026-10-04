from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from huishi.db import utc_now


PROJECT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
UPLOAD_PREFIX = "/static/uploads/"


@dataclass(slots=True)
class CanvasProjectConflict(Exception):
    project: dict[str, object]


def normalize_canvas_project(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("invalid_project")
    project_id = str(value.get("id") or "").strip()
    if not PROJECT_ID_PATTERN.fullmatch(project_id):
        raise ValueError("invalid_project_id")
    payload = value.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("invalid_project_payload")
    try:
        schema_version = max(1, int(value.get("schemaVersion") or 1))
        base_rev = max(0, int(value.get("baseRev") or 0))
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid_project_revision") from exc
    now = utc_now()
    return {
        "id": project_id,
        "title": str(value.get("title") or "").strip() or "未命名画布",
        "schema_version": schema_version,
        "base_rev": base_rev,
        "payload": payload,
        "created_at": str(value.get("createdAt") or "").strip() or now,
        "updated_at": str(value.get("updatedAt") or "").strip() or now,
    }


def canvas_project_hash(project: dict[str, object]) -> str:
    encoded = json.dumps(
        {
            "title": project["title"],
            "schemaVersion": project["schema_version"],
            "payload": project["payload"],
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def extract_canvas_asset_refs(payload: object) -> set[str]:
    refs: set[str] = set()

    def visit(value: object) -> None:
        if isinstance(value, dict):
            for item in value.values():
                visit(item)
            return
        if isinstance(value, list):
            for item in value:
                visit(item)
            return
        if not isinstance(value, str):
            return
        parsed = urlsplit(value)
        path = parsed.path if parsed.scheme and parsed.netloc else value.split("?", 1)[0]
        if not path.startswith(UPLOAD_PREFIX):
            return
        filename = Path(path.removeprefix(UPLOAD_PREFIX)).name
        if filename:
            refs.add(f"{UPLOAD_PREFIX}{filename}")

    visit(payload)
    return refs


def serialize_canvas_project(row) -> dict[str, object]:
    return {
        "id": str(row["id"]),
        "title": str(row["title"]),
        "schemaVersion": int(row["schema_version"]),
        "rev": int(row["rev"]),
        "payload": json.loads(str(row["payload"] or "{}")),
        "createdAt": str(row["created_at"]),
        "updatedAt": str(row["updated_at"]),
    }


def canvas_project_for_user(db, project_id: str, user_id: int, *, include_deleted: bool = False):
    deleted_clause = "" if include_deleted else " AND deleted_at = ''"
    return db.execute(
        f"""
        SELECT id, user_id, title, schema_version, rev, payload, content_hash, created_at, updated_at, deleted_at
        FROM canvas_projects
        WHERE id = ? AND user_id = ?{deleted_clause}
        """,
        (project_id, user_id),
    ).fetchone()


def list_canvas_projects(db, user_id: int) -> list[dict[str, object]]:
    rows = db.execute(
        """
        SELECT id, user_id, title, schema_version, rev, payload, content_hash, created_at, updated_at, deleted_at
        FROM canvas_projects
        WHERE user_id = ? AND deleted_at = ''
        ORDER BY updated_at DESC, id DESC
        """,
        (user_id,),
    ).fetchall()
    return [serialize_canvas_project(row) for row in rows]


def _replace_project_assets(db, project_id: str, payload: object) -> None:
    db.execute("DELETE FROM canvas_project_assets WHERE project_id = ?", (project_id,))
    for asset_ref in sorted(extract_canvas_asset_refs(payload)):
        db.execute(
            "INSERT OR IGNORE INTO canvas_project_assets (project_id, asset_ref) VALUES (?, ?)",
            (project_id, asset_ref),
        )


def create_canvas_project(db, user_id: int, value: object) -> dict[str, object]:
    project = normalize_canvas_project(value)
    existing = db.execute(
        """
        SELECT id, user_id, title, schema_version, rev, payload, content_hash, created_at, updated_at, deleted_at
        FROM canvas_projects WHERE id = ?
        """,
        (project["id"],),
    ).fetchone()
    content_hash = canvas_project_hash(project)
    if existing is not None:
        if int(existing["user_id"]) == user_id and not existing["deleted_at"] and str(existing["content_hash"]) == content_hash:
            return serialize_canvas_project(existing)
        if int(existing["user_id"]) == user_id:
            raise CanvasProjectConflict(serialize_canvas_project(existing))
        raise ValueError("project_id_conflict")
    payload_json = json.dumps(project["payload"], ensure_ascii=False, separators=(",", ":"))
    db.execute(
        """
        INSERT INTO canvas_projects
        (id, user_id, title, schema_version, rev, payload, content_hash, created_at, updated_at, deleted_at)
        VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, '')
        """,
        (
            project["id"],
            user_id,
            project["title"],
            project["schema_version"],
            payload_json,
            content_hash,
            project["created_at"],
            project["updated_at"],
        ),
    )
    _replace_project_assets(db, str(project["id"]), project["payload"])
    return serialize_canvas_project(canvas_project_for_user(db, str(project["id"]), user_id))


def update_canvas_project(db, user_id: int, project_id: str, value: object) -> dict[str, object]:
    project = normalize_canvas_project(value)
    if project["id"] != project_id:
        raise ValueError("project_id_mismatch")
    current = canvas_project_for_user(db, project_id, user_id)
    if current is None:
        raise LookupError("not_found")
    if int(project["base_rev"]) != int(current["rev"]):
        raise CanvasProjectConflict(serialize_canvas_project(current))
    next_rev = int(current["rev"]) + 1
    payload_json = json.dumps(project["payload"], ensure_ascii=False, separators=(",", ":"))
    db.execute(
        """
        UPDATE canvas_projects
        SET title = ?, schema_version = ?, rev = ?, payload = ?, content_hash = ?, updated_at = ?
        WHERE id = ? AND user_id = ? AND deleted_at = ''
        """,
        (
            project["title"],
            project["schema_version"],
            next_rev,
            payload_json,
            canvas_project_hash(project),
            project["updated_at"],
            project_id,
            user_id,
        ),
    )
    _replace_project_assets(db, project_id, project["payload"])
    return serialize_canvas_project(canvas_project_for_user(db, project_id, user_id))


def soft_delete_canvas_project(db, user_id: int, project_id: str) -> bool:
    current = canvas_project_for_user(db, project_id, user_id)
    if current is None:
        return False
    db.execute(
        "UPDATE canvas_projects SET deleted_at = ?, updated_at = ?, rev = rev + 1 WHERE id = ? AND user_id = ?",
        (utc_now(), utc_now(), project_id, user_id),
    )
    return True
