"""JiasuAPI async image/video transport helpers.

The adapter deliberately keeps creation and polling explicit. A timeout after a
successful create is not retried because the upstream task may already exist.
"""
from __future__ import annotations

import time
from typing import Any
import requests

from huishi.image_api import ConfigurationError, images_from_payload
from huishi.network import request_proxy_kwargs
from huishi.secrets import redact_sensitive_text


TERMINAL_STATES = {"completed", "failed"}


def _url(provider: dict[str, Any], path: str) -> str:
    base = str(provider.get("base_url") or "").rstrip("/")
    suffix = "/" + str(path or "").lstrip("/")
    if base.lower().endswith("/v1") and suffix.lower().startswith("/v1/"):
        suffix = suffix[3:]
    return base + suffix


def _headers(provider: dict[str, Any]) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {str(provider.get('api_key') or '').strip()}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _json(response: requests.Response, provider: dict[str, Any]) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise ConfigurationError("JiasuAPI 返回了非 JSON 响应") from exc
    if not isinstance(payload, dict):
        raise ConfigurationError("JiasuAPI 返回格式不受支持")
    if response.status_code < 200 or response.status_code >= 300:
        error = payload.get("error")
        message = error.get("message") if isinstance(error, dict) else error
        message = message or payload.get("message") or f"HTTP {response.status_code}"
        raise ConfigurationError(redact_sensitive_text(str(message), provider.get("api_key"), provider.get("base_url")))
    return payload


def _request(provider: dict[str, Any], method: str, path: str, *, payload: dict[str, Any] | None = None, timeout: float = 30) -> dict[str, Any]:
    try:
        response = requests.request(
            method,
            _url(provider, path),
            headers=_headers(provider),
            json=payload,
            timeout=timeout,
            **request_proxy_kwargs(provider.get("proxy_url")),
        )
    except requests.RequestException as exc:
        raise ConfigurationError(redact_sensitive_text(str(exc), provider.get("api_key"), provider.get("base_url"))) from exc
    return _json(response, provider)


def _status(payload: dict[str, Any]) -> str:
    value = str(payload.get("status") or "unknown").strip().lower()
    if value in {"queued", "in_progress", "completed", "failed", "unknown"}:
        return value
    return "unknown"


def _task_id(payload: dict[str, Any]) -> str:
    return str(payload.get("task_id") or payload.get("id") or "").strip()


def _poll_interval(provider: dict[str, Any]) -> float:
    settings = provider.get("settings") if isinstance(provider.get("settings"), dict) else {}
    try:
        return max(0.0, min(30.0, float(settings.get("poll_interval", 3))))
    except (TypeError, ValueError):
        return 3.0


def _result_urls(payload: dict[str, Any]) -> list[str]:
    return [str(item).strip() for item in (payload.get("result_urls") or []) if str(item).strip()]


def _upload_reference(provider: dict[str, Any], item: Any, timeout: float) -> str:
    filename = str(getattr(item, "filename", "reference.png") or "reference.png")
    content_type = str(getattr(item, "mimetype", "") or "image/png")
    try:
        data = item.read()
        item.seek(0)
        response = requests.post(
            _url(provider, "/v1/media/upload"),
            headers={"Authorization": _headers(provider)["Authorization"], "Accept": "application/json"},
            files={"file": (filename, data, content_type)},
            data={"kind": "image"},
            timeout=min(float(timeout), 120),
            **request_proxy_kwargs(provider.get("proxy_url")),
        )
    except requests.RequestException as exc:
        raise ConfigurationError(redact_sensitive_text(str(exc), provider.get("api_key"), provider.get("base_url"))) from exc
    try:
        body = response.json()
    except ValueError as exc:
        raise ConfigurationError("JiasuAPI 素材上传返回了非 JSON 响应") from exc
    if response.status_code < 200 or response.status_code >= 300 or body.get("success") is False:
        raise ConfigurationError(redact_sensitive_text(str(body.get("message") or f"HTTP {response.status_code}"), provider.get("api_key"), provider.get("base_url")))
    data_block = body.get("data") if isinstance(body.get("data"), dict) else body
    items = data_block.get("items") if isinstance(data_block, dict) else None
    candidate = items[0] if isinstance(items, list) and items else data_block
    url = str(candidate.get("url") or "").strip() if isinstance(candidate, dict) else ""
    if not url.startswith("https://"):
        raise ConfigurationError("JiasuAPI 素材上传没有返回 HTTPS 地址")
    return url


def generate_images(*, provider: dict[str, Any], prompt: str, model: str, ratio: str, resolution: str,
                    count: int, quality: str, reference_images: list[Any], timeout: float) -> list[str]:
    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "n": int(count),
        "quality": quality,
        "ratio": ratio,
        "resolution": resolution,
    }
    if reference_images:
        images = []
        for item in reference_images:
            filename = str(getattr(item, "filename", "reference.png") or "reference.png")
            # The generic image route has no stable public URL for a FileStorage
            # object. Refusing an undocumented data URI is safer than sending a
            # request that silently drops the reference image.
            public_url = str(getattr(item, "public_url", "") or "").strip()
            if not public_url:
                public_url = _upload_reference(provider, item, timeout)
            images.append({"url": public_url, "name": filename})
        payload["images"] = images

    created = _request(provider, "POST", "/v1/images/create", payload=payload, timeout=min(float(timeout), 120))
    task_id = _task_id(created)
    if not task_id:
        raise ConfigurationError("JiasuAPI 图片创建响应缺少任务 ID")

    deadline = time.monotonic() + max(1.0, float(timeout))
    interval = _poll_interval(provider)
    while True:
        state = _request(provider, "GET", f"/v1/images/tasks/{task_id}", timeout=min(float(timeout), 60))
        status = _status(state)
        if status == "completed":
            urls = _result_urls(state)
            if not urls:
                raise ConfigurationError("JiasuAPI 图片任务已完成但没有结果地址")
            return images_from_payload(
                {"data": [{"url": url} for url in urls]},
                proxy_url=str(provider.get("proxy_url") or ""),
            )[: int(count)]
        if status == "failed":
            error = state.get("error")
            message = error.get("message") if isinstance(error, dict) else error
            raise ConfigurationError(redact_sensitive_text(str(message or "JiasuAPI 图片任务失败"), provider.get("api_key"), provider.get("base_url")))
        if time.monotonic() >= deadline:
            raise ConfigurationError("JiasuAPI 图片任务轮询超时，已停止自动重试")
        if interval:
            time.sleep(interval)


def video_result_url(payload: dict[str, Any]) -> str:
    urls = _result_urls(payload)
    return urls[0] if urls else ""
