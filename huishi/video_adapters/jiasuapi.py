"""JiasuAPI asynchronous video transport, including MiniMax H3 material mapping."""
from __future__ import annotations

from typing import Any

import requests

from huishi.media_capabilities import validate_video_request, video_capabilities
from huishi.network import request_proxy_kwargs
from huishi.secrets import redact_sensitive_text
from huishi.video_api import VideoApiError, VideoTask, VideoTaskState, _normalize_status
from .common import RetryableVideoError, require_idempotency


def _url(provider: dict[str, Any], path: str) -> str:
    base = str(provider.get("base_url") or "").rstrip("/")
    suffix = "/" + str(path or "").lstrip("/")
    if base.lower().endswith("/v1") and suffix.lower().startswith("/v1/"):
        suffix = suffix[3:]
    return base + suffix


def _headers(provider: dict[str, Any], idempotency_key: str = "") -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {str(provider.get('api_key') or '').strip()}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    return headers


def _request(provider: dict[str, Any], method: str, path: str, *, payload: dict[str, Any] | None = None,
             idempotency_key: str = "") -> dict[str, Any]:
    try:
        response = requests.request(
            method,
            _url(provider, path),
            headers=_headers(provider, idempotency_key),
            json=payload,
            timeout=(15, 60),
            **request_proxy_kwargs(provider.get("proxy_url")),
        )
    except requests.RequestException as exc:
        raise RetryableVideoError(redact_sensitive_text(str(exc), provider.get("api_key"))) from exc
    try:
        body = response.json()
    except ValueError as exc:
        raise RetryableVideoError("JiasuAPI 视频接口返回了非 JSON 响应") from exc
    if not isinstance(body, dict):
        raise RetryableVideoError("JiasuAPI 视频接口返回格式不受支持")
    if response.status_code < 200 or response.status_code >= 300:
        error = body.get("error")
        message = error.get("message") if isinstance(error, dict) else error
        message = message or body.get("message") or f"HTTP {response.status_code}"
        exc_type = RetryableVideoError if response.status_code in (408, 409, 425, 429) or response.status_code >= 500 else VideoApiError
        raise exc_type(redact_sensitive_text(str(message), provider.get("api_key")))
    return body


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
    result = _request(provider, "POST", "/v1/video/generations", payload=payload, idempotency_key=key)
    task_id = str(result.get("id") or result.get("task_id") or "").strip()
    if not task_id:
        raise RetryableVideoError("JiasuAPI 视频创建响应缺少任务 ID")
    return VideoTask(task_id, status=str(result.get("status") or "pending"))


def poll(provider: dict[str, Any], task_id: str) -> VideoTaskState:
    payload = _request(provider, "GET", f"/v1/videos/tasks/{task_id}")
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
