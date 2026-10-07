"""JiasuAPI asynchronous video transport, including MiniMax H3 material mapping."""
from __future__ import annotations

from typing import Any

from huishi.media_capabilities import validate_video_request, video_capabilities
from huishi.secrets import redact_sensitive_text
from huishi.video_api import VideoApiError, VideoTask, VideoTaskState, _normalize_status
from .common import RetryableVideoError, request_json, require_idempotency


def _reference_payload(content: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped = {"images": [], "videos": [], "audios": []}
    for item in content:
        if not isinstance(item, dict) or item.get("type") == "text":
            continue
        kind = str(item.get("type") or "")
        nested = item.get(kind)
        if not isinstance(nested, dict) or not str(nested.get("url") or "").strip():
            continue
        value: dict[str, Any] = {"url": str(nested["url"]).strip()}
        role = str(item.get("role") or "")
        if kind == "image_url":
            if role == "first_frame":
                value["type"] = "first_frame"
            elif role == "last_frame":
                value["type"] = "end_frame"
            grouped["images"].append(value)
        elif kind == "video_url":
            for key in ("duration_seconds", "mime"):
                if nested.get(key) not in (None, ""):
                    value[key] = nested[key]
            grouped["videos"].append(value)
        elif kind == "audio_url":
            if nested.get("mime") not in (None, ""):
                value["mime"] = nested["mime"]
            grouped["audios"].append(value)
    return grouped


def create(provider: dict[str, Any], request: dict[str, Any]) -> VideoTask:
    key = require_idempotency(request)
    model = str(request.get("model") or provider.get("model") or "").strip()
    caps = video_capabilities("jiasuapi", model, request.get("capabilities"))
    if not caps:
        raise VideoApiError("JiasuAPI 不支持该视频模型")
    try:
        normalized = validate_video_request(model, caps, request)
    except ValueError as exc:
        raise VideoApiError(str(exc)) from exc
    payload: dict[str, Any] = {
        "model": model,
        "prompt": normalized["prompt"],
        "duration": normalized["duration_seconds"],
        "ratio": normalized["ratio"],
        "resolution": normalized["resolution"],
    }
    for key_name, values in _reference_payload(normalized.get("content") or []).items():
        if values:
            payload[key_name] = values
    result = request_json(provider, "POST", "/v1/video/generations", payload=payload, idempotency_key=key)
    task_id = str(result.get("id") or result.get("task_id") or "").strip()
    if not task_id:
        raise RetryableVideoError("JiasuAPI 视频创建响应缺少任务 ID")
    return VideoTask(task_id, status=str(result.get("status") or "pending"))


def poll(provider: dict[str, Any], task_id: str) -> VideoTaskState:
    payload = request_json(provider, "GET", f"/v1/videos/tasks/{task_id}")
    status = str(payload.get("status") or "unknown").strip().lower()
    if status == "failed":
        error = payload.get("error")
        message = error.get("message") if isinstance(error, dict) else error
        return VideoTaskState("failed", error=redact_sensitive_text(str(message or "JiasuAPI 视频任务失败"), provider.get("api_key")))
    normalized = _normalize_status(status)
    if normalized == "completed":
        urls = [str(url).strip() for url in (payload.get("result_urls") or []) if str(url).strip()]
        if not urls:
            raise RetryableVideoError("JiasuAPI 视频已完成但结果地址尚未生成")
        return VideoTaskState("completed", url=urls[0])
    return VideoTaskState("pending")
