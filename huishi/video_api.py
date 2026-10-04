from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlsplit

import requests

from huishi.network import request_proxy_kwargs
from huishi.secrets import redact_sensitive_text


@dataclass(frozen=True)
class VideoTask:
    provider_task_id: str
    status: str = "pending"


@dataclass(frozen=True)
class VideoTaskState:
    status: str
    url: str = ""
    file_id: str = ""
    error: str = ""


class VideoApiError(RuntimeError):
    pass


def _setting(provider: dict[str, Any], key: str, default: str) -> str:
    settings = provider.get("settings")
    if not isinstance(settings, dict):
        settings = {}
    value = str(settings.get(key) or "").strip()
    return value or default


def _url(base_url: str, path: str) -> str:
    base = str(base_url or "").strip().rstrip("/")
    suffix = "/" + str(path or "").lstrip("/")
    # Provider defaults sometimes include the protocol prefix in the path.
    if base.lower().endswith("/v1") and suffix.lower().startswith("/v1/"):
        suffix = suffix[3:]
    if base.lower().endswith("/api/v3") and suffix.lower().startswith("/api/v3/"):
        suffix = suffix[7:]
    return base + suffix


def _headers(provider: dict[str, Any], content_type: str = "application/json") -> dict[str, str]:
    headers = {"Authorization": f"Bearer {str(provider.get('api_key') or '').strip()}", "Accept": "application/json"}
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def _json(response: requests.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise VideoApiError("视频接口返回的不是 JSON") from exc
    if not isinstance(payload, dict):
        raise VideoApiError("视频接口返回格式不支持")
    return payload


def _request_error(response: requests.Response) -> VideoApiError:
    body = ""
    try:
        body = str(response.json().get("message") or response.json().get("msg") or "")
    except Exception:
        body = response.text[:200]
    return VideoApiError(redact_sensitive_text(body or f"HTTP {response.status_code}"))


def _task_id(payload: dict[str, Any]) -> str:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    for source in (payload, data):
        for key in ("id", "task_id", "request_id"):
            value = str(source.get(key) or "").strip()
            if value:
                return value
    return ""


def create_video_task(provider: dict[str, Any], request: dict[str, Any]) -> VideoTask:
    api_format = str(provider.get("api_format") or "openai").strip().lower()
    if api_format in {"dmc_h3", "seedance_media", "jiasuapi"}:
        from huishi.video_adapters import dmc_h3, jiasuapi, seedance_media
        adapter = {"dmc_h3": dmc_h3, "seedance_media": seedance_media, "jiasuapi": jiasuapi}[api_format]
        return adapter.create(provider, request)
    model = str(request.get("model") or provider.get("model") or "").strip()
    prompt = str(request.get("prompt") or "").strip()
    if not model:
        raise VideoApiError("视频模型不能为空")
    if not prompt and not request.get("content"):
        raise VideoApiError("视频提示词不能为空")

    if api_format == "seedance":
        path = _setting(provider, "create_path", "/contents/generations/tasks")
        payload: dict[str, Any] = {
            "model": model,
            "content": request.get("content") or [{"type": "text", "text": prompt}],
            "ratio": request.get("ratio") or "adaptive",
            "resolution": request.get("resolution") or "720p",
            "duration": int(request.get("duration_seconds") or 5),
            "generate_audio": bool(request.get("generate_audio", True)),
            "watermark": bool(request.get("watermark", False)),
        }
    elif api_format == "minimax":
        path = _setting(provider, "create_path", "/v1/video_generation")
        payload = {
            "model": model,
            "prompt": prompt,
            "duration": int(request.get("duration_seconds") or 6),
        }
        if request.get("resolution"):
            payload["resolution"] = request["resolution"]
        if request.get("ratio"):
            payload["aspect_ratio"] = request["ratio"]
    elif api_format == "grok":
        path = _setting(provider, "create_path", "/v1/videos/generations")
        payload = {
            "model": model,
            "prompt": prompt,
            "duration": int(request.get("duration_seconds") or 6),
        }
        if request.get("ratio"):
            payload["aspect_ratio"] = request["ratio"]
        # Grok Imagine accepts one reference image.  The workbench marks the
        # selected @主体 item explicitly; forward that signed URL instead of
        # silently dropping the uploaded subject from the upstream request.
        subject = next((item for item in (request.get("content") or [])
                        if isinstance(item, dict) and item.get("type") == "image_url"
                        and item.get("is_subject") is True), None)
        if subject:
            nested = subject.get("image_url")
            subject_url = str(nested.get("url") or "").strip() if isinstance(nested, dict) else ""
            if subject_url:
                payload["image_url"] = subject_url
    else:
        path = _setting(provider, "create_path", "/videos")
        payload = {
            "model": model,
            "prompt": prompt,
            "seconds": int(request.get("duration_seconds") or 6),
        }
        if request.get("size"):
            payload["size"] = request["size"]

    try:
        response = requests.post(_url(str(provider.get("base_url") or ""), path), headers=_headers(provider), json=payload, timeout=float(request.get("timeout", 60)), **request_proxy_kwargs(provider.get("proxy_url")))
    except requests.RequestException as exc:
        raise VideoApiError(redact_sensitive_text(str(exc), provider.get("api_key"), provider.get("base_url"))) from exc
    if response.status_code < 200 or response.status_code >= 300:
        raise _request_error(response)
    payload_response = _json(response)
    task_id = _task_id(payload_response)
    if not task_id:
        raise VideoApiError("视频接口没有返回任务 ID")
    return VideoTask(provider_task_id=task_id, status=str(payload_response.get("status") or "pending"))


def _normalize_status(value: object) -> str:
    text = str(value or "").strip().lower()
    if text in {"success", "succeeded", "completed", "complete", "done"}:
        return "completed"
    if text in {"failed", "failure", "error", "cancelled", "canceled", "expired"}:
        return "failed"
    return "pending"


def _find_url(payload: dict[str, Any], base_url: str = "") -> str:
    for source in (payload, payload.get("data"), payload.get("content"), payload.get("result"), payload.get("video")):
        if not isinstance(source, dict):
            continue
        for key in ("video_url", "url", "download_url", "file_url"):
            value = str(source.get(key) or "").strip()
            if value.startswith(("http://", "https://")):
                return value
            if base_url and value.startswith("/") and not value.startswith("//"):
                return urljoin(base_url.rstrip("/") + "/", value)
    return ""


def poll_video_task(provider: dict[str, Any], provider_task_id: str) -> VideoTaskState:
    api_format = str(provider.get("api_format") or "openai").strip().lower()
    if api_format in {"dmc_h3", "seedance_media", "jiasuapi"}:
        from huishi.video_adapters import dmc_h3, jiasuapi, seedance_media
        adapter = {"dmc_h3": dmc_h3, "seedance_media": seedance_media, "jiasuapi": jiasuapi}[api_format]
        return adapter.poll(provider, provider_task_id)
    if api_format == "minimax":
        path = _setting(provider, "poll_path", "/v1/query/video_generation")
        try:
            response = requests.get(_url(str(provider.get("base_url") or ""), path), headers=_headers(provider, ""), params={"task_id": provider_task_id}, timeout=30, **request_proxy_kwargs(provider.get("proxy_url")))
        except requests.RequestException as exc:
            raise VideoApiError(redact_sensitive_text(str(exc), provider.get("api_key"), provider.get("base_url"))) from exc
    else:
        default_path = "/contents/generations/tasks/{task_id}" if api_format == "seedance" else ("/v1/videos/{task_id}" if api_format == "grok" else "/videos/{task_id}")
        path = _setting(provider, "poll_path", default_path).replace("{task_id}", provider_task_id)
        try:
            response = requests.get(_url(str(provider.get("base_url") or ""), path), headers=_headers(provider, ""), timeout=30, **request_proxy_kwargs(provider.get("proxy_url")))
        except requests.RequestException as exc:
            raise VideoApiError(redact_sensitive_text(str(exc), provider.get("api_key"), provider.get("base_url"))) from exc
    if response.status_code < 200 or response.status_code >= 300:
        raise _request_error(response)
    payload = _json(response)
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    status = _normalize_status(data.get("status") if isinstance(data, dict) else payload.get("status"))
    if status == "failed":
        error = data.get("error") if isinstance(data, dict) else payload.get("error")
        message = error.get("message") if isinstance(error, dict) else error
        return VideoTaskState(status="failed", error=redact_sensitive_text(str(message or "视频生成失败"), provider.get("api_key"), provider.get("base_url")))
    file_id = ""
    if isinstance(data, dict):
        file_id = str(data.get("file_id") or "").strip()
    return VideoTaskState(status=status, url=_find_url(payload, str(provider.get("base_url") or "")), file_id=file_id)


def download_video_result(provider: dict[str, Any], state: VideoTaskState, *, timeout: float = 120, destination=None):
    url = state.url
    if provider.get("api_format") == "seedance_media":
        from huishi.video_adapters import seedance_media
        return seedance_media.download(provider, state, timeout=timeout, destination=destination)
    if not url and state.file_id:
        path = _setting(provider, "file_path", "/v1/files/retrieve")
        try:
            response = requests.get(_url(str(provider.get("base_url") or ""), path), headers=_headers(provider, ""), params={"file_id": state.file_id}, timeout=timeout, **request_proxy_kwargs(provider.get("proxy_url")))
        except requests.RequestException as exc:
            raise VideoApiError(redact_sensitive_text(str(exc), provider.get("api_key"), provider.get("base_url"))) from exc
        if response.status_code < 200 or response.status_code >= 300:
            raise _request_error(response)
        payload = _json(response)
        url = _find_url(payload)
    if not url:
        raise VideoApiError("视频任务已完成但没有可下载地址")
    if provider.get('api_format') in {'dmc_h3','seedance_media','jiasuapi'}:
        from huishi.media_download import download_media
        return download_media(provider,url,authenticated=provider.get('api_format')=='seedance_media',timeout=timeout,destination=destination)
    try:
        # Public result CDNs must never receive the channel's bearer credential.
        same_origin = urlsplit(url)[:2] == urlsplit(str(provider.get("base_url") or ""))[:2]
        authenticated = same_origin and provider.get("api_format") != "dmc_h3"
        headers = _headers(provider, "") if authenticated else {"Accept": "video/*"}
        response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=False, **request_proxy_kwargs(provider.get("proxy_url")))
    except requests.RequestException as exc:
        raise VideoApiError(redact_sensitive_text(str(exc), provider.get("api_key"), provider.get("base_url"))) from exc
    if response.status_code < 200 or response.status_code >= 300:
        if response.status_code == 409 and provider.get("api_format") == "seedance_media":
            from huishi.video_adapters.common import RetryableVideoError
            raise RetryableVideoError('视频结果准备中')
        raise _request_error(response)
    content = response.content
    if not content:
        raise VideoApiError("视频下载结果为空")
    return content
