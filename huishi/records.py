from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from flask import current_app

from huishi.db import get_db, utc_now
from huishi.upload_storage import get_upload_storage


def dialogue_title_from_prompt(prompt: str) -> str:
    compact = " ".join((prompt or "").split())
    if not compact:
        return "未命名对话"
    return f"{compact[:18]}..." if len(compact) > 18 else compact


def _looks_like_mojibake_title(title: str) -> bool:
    value = (title or "").strip()
    if not value:
        return True
    suspicious_markers = ("????", "鈧", "閫", "鍘", "鍐", "褰", "灏", "绉", "纭", "脳", "臥")
    return any(marker in value for marker in suspicious_markers)


def normalize_dialogue(row):
    if row is None:
        return None
    dialogue = dict(row)
    title = str(dialogue.get("title") or "").strip()
    latest_prompt = str(dialogue.get("latest_prompt") or "").strip()
    if _looks_like_mojibake_title(title):
        dialogue["title"] = dialogue_title_from_prompt(latest_prompt)
    else:
        dialogue["title"] = title
    return dialogue


def create_dialogue(*, user_id: int, title: str) -> int:
    now = utc_now()
    cursor = get_db().execute(
        """
        INSERT INTO dialogues (user_id, title, created_at, updated_at)
        VALUES (?, ?, ?, ?)
        """,
        (user_id, title or "未命名对话", now, now),
    )
    return int(cursor.lastrowid)


def get_dialogue_for_user(dialogue_id: int, user_id: int):
    row = get_db().execute(
        """
        SELECT dialogues.*,
               (
                 SELECT records.prompt
                 FROM records
                 WHERE records.dialogue_id = dialogues.id AND records.user_id = dialogues.user_id
                 ORDER BY records.id DESC
                 LIMIT 1
               ) AS latest_prompt
        FROM dialogues
        WHERE dialogues.id = ? AND dialogues.user_id = ?
        """,
        (dialogue_id, user_id),
    ).fetchone()
    return normalize_dialogue(row)


def list_dialogues_for_user(user_id: int):
    rows = get_db().execute(
        """
        SELECT dialogues.*,
               COUNT(records.id) AS record_count,
               MAX(records.created_at) AS last_record_at,
               (
                 SELECT latest.prompt
                 FROM records AS latest
                 WHERE latest.dialogue_id = dialogues.id AND latest.user_id = dialogues.user_id
                 ORDER BY latest.id DESC
                 LIMIT 1
               ) AS latest_prompt
        FROM dialogues
        LEFT JOIN records ON records.dialogue_id = dialogues.id
        WHERE dialogues.user_id = ?
        GROUP BY dialogues.id
        ORDER BY COALESCE(MAX(records.id), dialogues.id) DESC
        """,
        (user_id,),
    ).fetchall()
    return [normalize_dialogue(row) for row in rows]


def delete_dialogue_for_user(dialogue_id: int, user_id: int) -> bool:
    db = get_db()
    dialogue = get_dialogue_for_user(dialogue_id, user_id)
    if dialogue is None:
        return False
    db.execute(
        "UPDATE records SET hidden = 1, dialogue_id = NULL WHERE dialogue_id = ? AND user_id = ?",
        (dialogue_id, user_id),
    )
    db.execute(
        "UPDATE generation_tasks SET dismissed_at = COALESCE(NULLIF(dismissed_at, ''), ?), dialogue_id = NULL WHERE dialogue_id = ? AND user_id = ?",
        (utc_now(), dialogue_id, user_id),
    )
    db.execute("DELETE FROM dialogues WHERE id = ? AND user_id = ?", (dialogue_id, user_id))
    return True


def ensure_legacy_dialogue_for_user(user_id: int) -> None:
    rows = get_db().execute(
        "SELECT * FROM records WHERE user_id = ? AND dialogue_id IS NULL AND (asset_source IS NULL OR asset_source != 'canvas') ORDER BY id",
        (user_id,),
    ).fetchall()
    if not rows:
        return
    first_prompt = rows[0]["prompt"] if rows else ""
    dialogue_id = create_dialogue(user_id=user_id, title=dialogue_title_from_prompt(first_prompt))
    get_db().execute(
        "UPDATE records SET dialogue_id = ? WHERE user_id = ? AND dialogue_id IS NULL AND (asset_source IS NULL OR asset_source != 'canvas')",
        (dialogue_id, user_id),
    )


def _record_local_images_exist(record) -> bool:
    storage = get_upload_storage()
    for image_path in record.get("image_paths") or []:
        image_path = str(image_path or "")
        if not image_path.startswith("/static/uploads/"):
            continue
        filename = Path(image_path.removeprefix("/static/uploads/")).name
        if not filename:
            return False
        if not storage.exists(filename):
            return False
    return True


def list_records_for_user(user_id: int, *, exclude_canvas: bool = False):
    query = "SELECT * FROM records WHERE user_id = ? AND hidden = 0"
    if exclude_canvas:
        query += " AND (asset_source IS NULL OR asset_source != 'canvas')"
    query += " ORDER BY id DESC, group_index ASC"
    rows = get_db().execute(query, (user_id,)).fetchall()
    return [record for record in (normalize_record(row) for row in rows) if _record_local_images_exist(record)]


def list_records_for_dialogue(user_id: int, dialogue_id: int):
    rows = get_db().execute(
        """
        SELECT *
        FROM records
        WHERE user_id = ? AND dialogue_id = ? AND hidden = 0
        ORDER BY id DESC
        """,
        (user_id, dialogue_id),
    ).fetchall()
    return [normalize_record(row) for row in rows]


def get_record_for_user(record_id: int, user_id: int, *, is_admin: bool = False):
    if is_admin:
        row = get_db().execute("SELECT * FROM records WHERE id = ?", (record_id,)).fetchone()
        return normalize_record(row)
    row = get_db().execute(
        "SELECT * FROM records WHERE id = ? AND user_id = ? AND hidden = 0",
        (record_id, user_id),
    ).fetchone()
    return normalize_record(row)


def list_record_group_for_user(record_id: int, user_id: int, *, is_admin: bool = False):
    record = get_record_for_user(record_id, user_id, is_admin=is_admin)
    if not record:
        return []
    group_id = record.get("generation_group_id") or f"legacy-{record['id']}"
    if is_admin:
        rows = get_db().execute(
            """
            SELECT * FROM records
            WHERE generation_group_id = ? AND hidden = 0
            ORDER BY group_index ASC, id ASC
            """,
            (group_id,),
        ).fetchall()
    else:
        rows = get_db().execute(
            """
            SELECT * FROM records
            WHERE user_id = ? AND generation_group_id = ? AND hidden = 0
            ORDER BY group_index ASC, id ASC
            """,
            (user_id, group_id),
        ).fetchall()
    records = [normalize_record(row) for row in rows]
    return records or [record]


def create_record(
    *,
    user_id: int,
    prompt: str,
    image_path: str,
    mode: str,
    ratio: str,
    resolution: str,
    actual_size: str,
    quality: str,
    output_format: str,
    count: int,
    model_source: str,
    elapsed_seconds: float,
    points_charged: int,
    asset_source: str = "image",
    reference_paths: list[str] | None = None,
    image_paths: list[str] | None = None,
    dialogue_id: int | None = None,
    generation_group_id: str | None = None,
    group_index: int = 0,
    media_type: str = "image",
    mime_type: str = "",
    duration_ms: int = 0,
) -> int:
    normalized_image_paths = image_paths or [image_path]
    cursor = get_db().execute(
        """
        INSERT INTO records
        (user_id, prompt, dialogue_id, image_path, image_paths, generation_group_id, group_index, mode, ratio, resolution, actual_size, quality, output_format, count, model_source, elapsed_seconds, points_charged, asset_source, media_type, mime_type, duration_ms, reference_paths, favorite, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
        """,
        (
            user_id,
            prompt,
            dialogue_id,
            image_path,
            json.dumps(normalized_image_paths, ensure_ascii=False),
            generation_group_id or "",
            int(group_index),
            mode,
            ratio,
            resolution,
            actual_size,
            quality,
            output_format,
            count,
            model_source,
            elapsed_seconds,
            points_charged,
            asset_source or "image",
            str(media_type or asset_source or "image"),
            str(mime_type or ""),
            int(duration_ms or 0),
            json.dumps(reference_paths or [], ensure_ascii=False),
            utc_now(),
        ),
    )
    if not generation_group_id:
        get_db().execute(
            "UPDATE records SET generation_group_id = ? WHERE id = ?",
            (f"record-{int(cursor.lastrowid)}", int(cursor.lastrowid)),
        )
    if dialogue_id is not None:
        get_db().execute("UPDATE dialogues SET updated_at = ? WHERE id = ?", (utc_now(), dialogue_id))
    return int(cursor.lastrowid)


def create_generation_task(
    *,
    user_id: int,
    prompt: str,
    mode: str,
    ratio: str,
    resolution: str,
    actual_size: str,
    quality: str,
    output_format: str,
    count: int,
    cost: int,
    model: str = "",
    reference_paths: list[str] | None = None,
    dialogue_id: int | None = None,
    status: str = "queued",
    bypass_billing: bool = False,
    media_type: str = "image",
    provider_id: int | None = None,
    duration_seconds: int = 0,
    metadata: dict | None = None,
) -> int:
    now = utc_now()
    cursor = get_db().execute(
        """
        INSERT INTO generation_tasks
        (user_id, dialogue_id, prompt, mode, model, ratio, resolution, actual_size, quality, output_format, count, cost, status, record_id, reference_paths, error_message, created_at, updated_at, finished_at, dismissed_at, bypass_billing, media_type, provider_id, provider_task_id, duration_seconds, metadata_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, '', ?, ?, '', '', ?, ?, ?, '', ?, ?)
        """,
        (
            user_id,
            dialogue_id,
            prompt,
            mode,
            model,
            ratio,
            resolution,
            actual_size,
            quality,
            output_format,
            count,
            cost,
            status,
            json.dumps(reference_paths or [], ensure_ascii=False),
            now,
            now,
            int(bypass_billing),
            str(media_type or "image"),
            provider_id,
            int(duration_seconds or 0),
            json.dumps(metadata or {}, ensure_ascii=False),
        ),
    )
    return int(cursor.lastrowid)


def get_generation_task(task_id: int):
    row = get_db().execute("SELECT * FROM generation_tasks WHERE id = ?", (task_id,)).fetchone()
    return normalize_generation_task(row)


def get_generation_task_for_user(task_id: int, user_id: int):
    row = get_db().execute(
        "SELECT * FROM generation_tasks WHERE id = ? AND user_id = ?",
        (task_id, user_id),
    ).fetchone()
    return normalize_generation_task(row)


def list_visible_generation_tasks_for_user(
    user_id: int,
    dialogue_id: int | None = None,
    *,
    stale_seconds: float | None = None,
    limit: int = 20,
    include_unbound: bool = False,
):
    if stale_seconds is not None:
        expire_stale_generation_tasks_for_user(user_id, stale_seconds)
    params: list[object] = [user_id]
    base_dialogue_filter = ""
    failed_dialogue_filter = ""
    if dialogue_id is not None:
        base_dialogue_filter = "AND (base.dialogue_id = ? OR base.dialogue_id IS NULL)" if include_unbound else "AND base.dialogue_id = ?"
        failed_dialogue_filter = "AND dialogue_id = ?"
        params.append(dialogue_id)
    rows = get_db().execute(
        f"""
        SELECT base.*
        FROM generation_tasks AS base
        WHERE base.user_id = ?
          AND (
            base.status IN ('queued', 'running')
            OR (base.status = 'failed' AND base.dismissed_at = '')
          )
          {base_dialogue_filter}
        ORDER BY
          base.created_at ASC,
          base.id ASC
        LIMIT ?
        """,
        [*params, max(1, int(limit))],
    ).fetchall()
    return [normalize_generation_task(row) for row in rows]


def list_active_generation_tasks_for_user(
    user_id: int,
    dialogue_id: int | None = None,
    *,
    stale_seconds: float | None = None,
):
    if stale_seconds is not None:
        expire_stale_generation_tasks_for_user(user_id, stale_seconds)
    params: list[object] = [user_id]
    dialogue_filter = ""
    if dialogue_id is not None:
        dialogue_filter = "AND dialogue_id = ?"
        params.append(dialogue_id)
    rows = get_db().execute(
        f"""
        SELECT *
        FROM generation_tasks
        WHERE user_id = ? AND status IN ('queued', 'running') {dialogue_filter}
        ORDER BY id ASC
        """,
        params,
    ).fetchall()
    return [normalize_generation_task(row) for row in rows]


def active_generation_task_count_for_user(user_id: int, *, stale_seconds: float | None = None) -> int:
    if stale_seconds is not None:
        expire_stale_generation_tasks_for_user(user_id, stale_seconds)
    row = get_db().execute(
        """
        SELECT COUNT(*) AS value
        FROM generation_tasks
        WHERE user_id = ? AND status IN ('queued', 'running')
        """,
        (user_id,),
    ).fetchone()
    return int(row["value"] if row is not None else 0)


def expire_stale_generation_tasks_for_user(user_id: int, stale_seconds: float) -> int:
    if stale_seconds <= 0:
        return 0
    cutoff = (datetime.fromisoformat(utc_now()) - timedelta(seconds=stale_seconds)).isoformat()
    now = utc_now()
    cursor = get_db().execute(
        """
        UPDATE generation_tasks
        SET status = 'failed',
            error_message = ?,
            updated_at = ?,
            finished_at = ?
        WHERE user_id = ?
          AND status IN ('queued', 'running')
          AND created_at < ?
          AND media_type <> 'video'
        """,
        ("生成任务超时，请重新提交。", now, now, user_id, cutoff),
    )
    return int(cursor.rowcount or 0)


def latest_active_generation_task_for_user(
    user_id: int,
    dialogue_id: int | None = None,
    *,
    stale_seconds: float | None = None,
):
    if stale_seconds is not None:
        expire_stale_generation_tasks_for_user(user_id, stale_seconds)
    params: list[object] = [user_id]
    dialogue_filter = ""
    if dialogue_id is not None:
        dialogue_filter = "AND dialogue_id = ?"
        params.append(dialogue_id)
    row = get_db().execute(
        f"""
        SELECT *
        FROM generation_tasks
        WHERE user_id = ? AND status IN ('queued', 'running') {dialogue_filter}
        ORDER BY id DESC
        LIMIT 1
        """,
        params,
    ).fetchone()
    return normalize_generation_task(row)


def mark_generation_task_succeeded(task_id: int, record_id: int) -> None:
    now = utc_now()
    get_db().execute(
        """
        UPDATE generation_tasks
        SET status = 'succeeded',
            record_id = ?,
            error_message = '',
            updated_at = ?,
            finished_at = ?
        WHERE id = ?
        """,
        (record_id, now, now, task_id),
    )


def mark_generation_task_running(task_id: int) -> None:
    get_db().execute(
        """
        UPDATE generation_tasks
        SET status = 'running',
            updated_at = ?
        WHERE id = ? AND status = 'queued'
        """,
        (utc_now(), task_id),
    )


def mark_generation_task_dialogue(task_id: int, dialogue_id: int) -> None:
    get_db().execute(
        """
        UPDATE generation_tasks
        SET dialogue_id = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (dialogue_id, utc_now(), task_id),
    )


def mark_generation_task_failed(task_id: int, message: str) -> None:
    now = utc_now()
    get_db().execute(
        """
        UPDATE generation_tasks
        SET status = 'failed',
            error_message = ?,
            updated_at = ?,
            finished_at = ?
        WHERE id = ?
        """,
        (message, now, now, task_id),
    )


def dismiss_failed_generation_task_for_user(task_id: int, user_id: int) -> bool:
    now = utc_now()
    cursor = get_db().execute(
        """
        UPDATE generation_tasks
        SET dismissed_at = ?,
            updated_at = ?
        WHERE id = ?
          AND user_id = ?
          AND status = 'failed'
          AND dismissed_at = ''
        """,
        (now, now, task_id, user_id),
    )
    return bool(cursor.rowcount)


def normalize_record(row):
    if row is None:
        return None
    record = dict(row)
    record["image_paths"] = parse_image_paths(record)
    record["reference_paths"] = parse_reference_paths(record)
    record["asset_source"] = str(record.get("asset_source") or "image")
    record["media_type"] = str(record.get("media_type") or record["asset_source"] or "image")
    record["mime_type"] = str(record.get("mime_type") or "")
    record["duration_ms"] = int(record.get("duration_ms") or 0)
    if not record.get("generation_group_id"):
        record["generation_group_id"] = f"legacy-{record['id']}"
    record["group_index"] = int(record.get("group_index") or 0)
    return record


def normalize_generation_task(row):
    if row is None:
        return None
    task = dict(row)
    task["reference_paths"] = parse_reference_paths(task)
    raw_metadata = task.get("metadata_json")
    if isinstance(raw_metadata, str):
        try:
            raw_metadata = json.loads(raw_metadata)
        except json.JSONDecodeError:
            raw_metadata = {}
    task["metadata"] = dict(raw_metadata) if isinstance(raw_metadata, dict) else {}
    task["media_type"] = str(task.get("media_type") or "image")
    return task


def parse_image_paths(record) -> list[str]:
    try:
        value = json.loads(record.get("image_paths") or "[]")
    except (AttributeError, TypeError, json.JSONDecodeError):
        value = []
    paths = [str(item) for item in value if isinstance(item, str)] if isinstance(value, list) else []
    fallback = str(record["image_path"]) if record["image_path"] else ""
    if fallback and fallback not in paths:
        paths.insert(0, fallback)
    return paths


def parse_reference_paths(record) -> list[str]:
    try:
        raw_value = record["reference_paths"]
        value = raw_value if isinstance(raw_value, list) else json.loads(raw_value or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str)]


def infer_ratio_from_size(actual_size: str) -> str:
    try:
        width_raw, height_raw = actual_size.lower().split("x", 1)
        width = int(width_raw)
        height = int(height_raw)
    except (AttributeError, ValueError):
        return "16:9"
    known = {
        (1680, 720): "21:9",
        (3360, 1440): "21:9",
        (1024, 1024): "1:1",
        (2048, 2048): "1:1",
        (1536, 864): "16:9",
        (2560, 1440): "16:9",
        (3840, 2160): "16:9",
        (864, 1536): "9:16",
        (1440, 2560): "9:16",
        (2160, 3840): "9:16",
        (1536, 1024): "3:2",
        (2160, 1440): "3:2",
        (1024, 1536): "2:3",
        (1440, 2160): "2:3",
    }
    return known.get((width, height), "16:9")


def record_generation_seed(record) -> dict[str, object]:
    keys = set(record.keys()) if hasattr(record, "keys") else set()
    model_source = record.get("model_source") if hasattr(record, "get") else (record["model_source"] if "model_source" in keys else "")
    media_type = record.get("media_type") if hasattr(record, "get") else (record["media_type"] if "media_type" in keys else "")
    if not media_type:
        media_type = record.get("asset_source") if hasattr(record, "get") else (record["asset_source"] if "asset_source" in keys else "image")
    return {
        "id": record["id"],
        "prompt": record["prompt"],
        "mode": record["mode"],
        "ratio": record["ratio"] or infer_ratio_from_size(record["actual_size"]),
        "resolution": record["resolution"],
        "actual_size": record["actual_size"],
        "quality": record["quality"],
        "output_format": record["output_format"],
        "count": record["count"],
        "model": str(model_source or ""),
        "media_type": str(media_type or "image"),
        "reference_paths": parse_reference_paths(record),
    }
