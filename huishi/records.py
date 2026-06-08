from __future__ import annotations

import json

from huishi.db import get_db, utc_now


def dialogue_title_from_prompt(prompt: str) -> str:
    compact = " ".join((prompt or "").split())
    if not compact:
        return "未命名对话"
    return f"{compact[:18]}..." if len(compact) > 18 else compact


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
    return get_db().execute(
        "SELECT * FROM dialogues WHERE id = ? AND user_id = ?",
        (dialogue_id, user_id),
    ).fetchone()


def list_dialogues_for_user(user_id: int):
    return get_db().execute(
        """
        SELECT dialogues.*,
               COUNT(records.id) AS record_count,
               MAX(records.created_at) AS last_record_at
        FROM dialogues
        LEFT JOIN records ON records.dialogue_id = dialogues.id
        WHERE dialogues.user_id = ?
        GROUP BY dialogues.id
        ORDER BY COALESCE(MAX(records.id), dialogues.id) DESC
        """,
        (user_id,),
    ).fetchall()


def ensure_legacy_dialogue_for_user(user_id: int) -> None:
    rows = get_db().execute(
        "SELECT * FROM records WHERE user_id = ? AND dialogue_id IS NULL ORDER BY id",
        (user_id,),
    ).fetchall()
    if not rows:
        return
    first_prompt = rows[0]["prompt"] if rows else ""
    dialogue_id = create_dialogue(user_id=user_id, title=dialogue_title_from_prompt(first_prompt))
    get_db().execute(
        "UPDATE records SET dialogue_id = ? WHERE user_id = ? AND dialogue_id IS NULL",
        (dialogue_id, user_id),
    )


def list_records_for_user(user_id: int):
    rows = get_db().execute(
        "SELECT * FROM records WHERE user_id = ? AND hidden = 0 ORDER BY id DESC",
        (user_id,),
    ).fetchall()
    return [normalize_record(row) for row in rows]


def list_records_for_dialogue(user_id: int, dialogue_id: int):
    rows = get_db().execute(
        "SELECT * FROM records WHERE user_id = ? AND dialogue_id = ? AND hidden = 0 ORDER BY id DESC",
        (user_id, dialogue_id),
    ).fetchall()
    return [normalize_record(row) for row in rows]


def get_record_for_user(record_id: int, user_id: int, *, is_admin: bool = False):
    if is_admin:
        row = get_db().execute("SELECT * FROM records WHERE id = ?", (record_id,)).fetchone()
        return normalize_record(row)
    row = get_db().execute(
        "SELECT * FROM records WHERE id = ? AND user_id = ?",
        (record_id, user_id),
    ).fetchone()
    return normalize_record(row)


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
    reference_paths: list[str] | None = None,
    image_paths: list[str] | None = None,
    dialogue_id: int | None = None,
) -> int:
    normalized_image_paths = image_paths or [image_path]
    cursor = get_db().execute(
        """
        INSERT INTO records
        (user_id, prompt, dialogue_id, image_path, image_paths, mode, ratio, resolution, actual_size, quality, output_format, count, model_source, elapsed_seconds, points_charged, reference_paths, favorite, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
        """,
        (
            user_id,
            prompt,
            dialogue_id,
            image_path,
            json.dumps(normalized_image_paths, ensure_ascii=False),
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
            json.dumps(reference_paths or [], ensure_ascii=False),
            utc_now(),
        ),
    )
    if dialogue_id is not None:
        get_db().execute("UPDATE dialogues SET updated_at = ? WHERE id = ?", (utc_now(), dialogue_id))
    return int(cursor.lastrowid)


def normalize_record(row):
    if row is None:
        return None
    record = dict(row)
    record["image_paths"] = parse_image_paths(record)
    record["reference_paths"] = parse_reference_paths(record)
    return record


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
        "reference_paths": parse_reference_paths(record),
    }
