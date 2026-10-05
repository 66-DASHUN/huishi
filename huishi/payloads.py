"""Response payload shapes and request-value parsing.

The functions here turn database rows into the JSON the frontend expects, and
coerce the string values that arrive in HTML forms. They are deliberately free
of Flask context: no ``request``, ``g``, ``current_app``, or database access.
That keeps the wire format testable without spinning up an app.

Anything that needs the request context (``wants_json``, ``generation_error``)
or a database lookup (``serialize_generation_task``) stays in the route module.

The original names are kept alongside public aliases so existing call sites and
tests continue to work.
"""
from __future__ import annotations

from urllib.parse import urlsplit


def parse_optional_int(raw_value: str | None) -> int | None:
    """Parse an optional integer form field.

    Empty and whitespace-only values mean "not provided" and return None;
    anything else must parse, because a malformed value here means a stale form
    rather than an intent to omit the field.
    """
    value = (raw_value or "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError("对话参数无效，请刷新页面后重试") from exc


def is_http_url(raw_url: str) -> bool:
    parsed = urlsplit(str(raw_url or ""))
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def format_file_size_limit(size_bytes: int) -> str:
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.0f}MB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.0f}KB"
    return f"{size_bytes}B"


def serialize_record(record) -> dict[str, object]:
    return {
        "id": record["id"],
        "dialogue_id": record["dialogue_id"] if "dialogue_id" in record.keys() else None,
        "generation_group_id": record["generation_group_id"],
        "group_index": record["group_index"],
        "prompt": record["prompt"],
        "image_path": record["image_path"],
        "images": record["image_paths"],
        "mode": record["mode"],
        "ratio": record["ratio"],
        "resolution": record["resolution"],
        "actual_size": record["actual_size"],
        "quality": record["quality"],
        "output_format": record["output_format"],
        "count": record["count"],
        "model_source": record["model_source"],
        "elapsed_seconds": record["elapsed_seconds"],
        "points_charged": record["points_charged"],
        "reference_paths": record["reference_paths"],
        "asset_source": record.get("asset_source", "image"),
        "media_type": record.get("media_type") or record.get("asset_source", "image"),
        "mime_type": record.get("mime_type", ""),
        "duration_ms": int(record.get("duration_ms") or 0),
        "favorite": record["favorite"],
        "created_at": record["created_at"],
    }


def serialize_dialogue(dialogue) -> dict[str, object]:
    return {
        "id": dialogue["id"],
        "title": dialogue["title"],
        "created_at": dialogue["created_at"],
        "updated_at": dialogue["updated_at"],
    }


# Public aliases for new code.
parse_optional_integer = parse_optional_int
record_payload = serialize_record
dialogue_payload = serialize_dialogue
