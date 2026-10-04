from __future__ import annotations

import base64
import binascii
import json
import re
from typing import Any

import requests

from huishi.network import request_proxy_kwargs
from huishi.secrets import redact_sensitive_text


class AudioApiError(RuntimeError):
    """Raised when a speech or music provider cannot return audio bytes."""


def generate_speech(provider: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    model = _required_model(request)
    text = str(request.get("text") or request.get("prompt") or "").strip()
    if not text:
        raise AudioApiError("语音合成文本不能为空")
    output_format = _audio_format(request.get("output_format") or request.get("format"))
    payload = {
        "model": model,
        "text": text,
        "stream": False,
        "voice_setting": {
            "voice_id": str(request.get("voice_id") or request.get("voice") or "male-qn-qingse"),
            "speed": _bounded_number(request.get("speed"), 1, 0.25, 4),
            "vol": _bounded_number(request.get("volume"), 1, 0, 10),
            "pitch": _bounded_number(request.get("pitch"), 0, -12, 12),
            "emotion": str(request.get("emotion") or "").strip() or "happy",
        },
        "audio_setting": {
            "sample_rate": int(request.get("sample_rate") or 32000),
            "bitrate": int(request.get("bitrate") or 128000),
            "format": output_format,
            "channel": int(request.get("channel") or 1),
        },
        "language_boost": str(request.get("language_boost") or "auto"),
        "subtitle_enable": bool(request.get("subtitle_enable", False)),
        "output_format": "hex",
    }
    instructions = str(request.get("instructions") or "").strip()
    if instructions:
        payload["voice_setting"]["instructions"] = instructions
    response = post_audio_request(provider, _configured_audio_path(provider, "speech_path", "/v1/t2a_v2"), payload)
    return decode_audio_response(response, model=model, default_extension=output_format)


def generate_music(provider: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    model = _required_model(request)
    prompt = str(request.get("prompt") or request.get("text") or "").strip()
    if not prompt:
        raise AudioApiError("音乐描述不能为空")
    output_format = _audio_format(request.get("output_format") or request.get("format"))
    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "lyrics": str(request.get("lyrics") or ""),
        "lyrics_optimizer": bool(request.get("lyrics_optimizer", False)),
        "is_instrumental": bool(request.get("is_instrumental", False)),
        "audio_setting": {"format": output_format},
        "output_format": "hex",
        "aigc_watermark": bool(request.get("aigc_watermark", False)),
    }
    if model == "music-cover":
        for key in ("audio_url", "audio_base64", "cover_feature_id"):
            value = request.get(key)
            if value not in (None, ""):
                payload[key] = value
    response = post_audio_request(provider, _configured_audio_path(provider, "music_path", "/v1/music_generation"), payload)
    return decode_audio_response(response, model=model, default_extension=output_format)


def post_audio_request(provider: dict[str, Any], path: str, payload: dict[str, Any]):
    base_url = str(provider.get("base_url") or "").rstrip("/")
    if not base_url:
        raise AudioApiError("音频 Base URL 不能为空")
    url = f"{base_url}{path if path.startswith('/') else f'/{path}'}"
    headers = {
        "Authorization": f"Bearer {str(provider.get('api_key') or '').strip()}",
        "Content-Type": "application/json",
        "Accept": "application/json, audio/*",
    }
    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=float(provider.get("timeout") or 180),
            **request_proxy_kwargs(provider.get("proxy_url")),
        )
    except requests.RequestException as exc:
        message = redact_sensitive_text(str(exc), provider.get("api_key"), provider.get("base_url"))
        raise AudioApiError(message or "音频服务连接失败") from exc
    if response.status_code < 200 or response.status_code >= 300:
        raise AudioApiError(_response_error(response, provider))
    return response


def _configured_audio_path(provider: dict[str, Any], key: str, default: str) -> str:
    settings = provider.get("settings") if isinstance(provider.get("settings"), dict) else {}
    value = provider.get(key) or settings.get(key) or default
    path = str(value or "").strip()
    if not path.startswith("/") or "\n" in path or "\r" in path:
        raise AudioApiError("音频接口路径必须是相对路径")
    return f"/{path.lstrip('/')}"


def decode_audio_response(response: Any, *, model: str, default_extension: str) -> dict[str, Any]:
    content_type = str(getattr(response, "headers", {}).get("content-type") or "").lower()
    if content_type.startswith("audio/") or (getattr(response, "content", b"") and "json" not in content_type):
        content = bytes(response.content)
        extension = _extension_for_mime(content_type, default_extension)
        return {"content": content, "mime_type": _mime_type(extension), "extension": extension, "model": model}
    try:
        payload = response.json()
    except (TypeError, ValueError) as exc:
        raise AudioApiError("音频服务返回了无法解析的结果") from exc
    if not isinstance(payload, dict):
        raise AudioApiError("音频服务返回格式不正确")
    base_resp = payload.get("base_resp") if isinstance(payload.get("base_resp"), dict) else {}
    if int(base_resp.get("status_code") or 0) != 0:
        raise AudioApiError(str(base_resp.get("status_msg") or payload.get("msg") or "音频生成失败"))
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    raw_audio = data.get("audio") or data.get("audio_base64") or payload.get("audio")
    if not isinstance(raw_audio, str) or not raw_audio:
        raise AudioApiError(str(data.get("message") or payload.get("msg") or "音频服务未返回音频"))
    content = _decode_audio_text(raw_audio)
    extension = _audio_format(data.get("format") or payload.get("format") or default_extension)
    return {"content": content, "mime_type": _mime_type(extension), "extension": extension, "model": model}


def _decode_audio_text(value: str) -> bytes:
    compact = value.strip()
    if re.fullmatch(r"[0-9a-fA-F]+", compact) and len(compact) % 2 == 0:
        try:
            return bytes.fromhex(compact)
        except ValueError:
            pass
    try:
        decoded = base64.b64decode(compact, validate=True)
    except (binascii.Error, ValueError):
        return compact.encode("utf-8")
    return decoded


def _required_model(request: dict[str, Any]) -> str:
    model = str(request.get("model") or "").strip()
    if not model:
        raise AudioApiError("音频模型不能为空")
    return model


def _audio_format(value: object) -> str:
    normalized = str(value or "mp3").strip().lower()
    return normalized if normalized in {"mp3", "wav", "opus", "aac", "flac", "pcm"} else "mp3"


def _bounded_number(value: object, default: float, minimum: float, maximum: float) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = default
    return max(minimum, min(maximum, numeric))


def _mime_type(extension: str) -> str:
    return {
        "wav": "audio/wav",
        "opus": "audio/opus",
        "aac": "audio/aac",
        "flac": "audio/flac",
        "pcm": "audio/pcm",
    }.get(extension, "audio/mpeg")


def _extension_for_mime(content_type: str, fallback: str) -> str:
    for extension, mime_type in (("wav", "audio/wav"), ("opus", "audio/opus"), ("aac", "audio/aac"), ("flac", "audio/flac"), ("pcm", "audio/pcm"), ("mp3", "audio/mpeg")):
        if mime_type in content_type:
            return extension
    return _audio_format(fallback)


def _response_error(response: Any, provider: dict[str, Any]) -> str:
    message = ""
    try:
        payload = response.json()
        if isinstance(payload, dict):
            error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
            message = str(error.get("message") or payload.get("msg") or payload.get("message") or "")
    except (TypeError, ValueError, json.JSONDecodeError):
        message = ""
    safe = redact_sensitive_text(message, provider.get("api_key"), provider.get("base_url"))
    return safe or f"音频服务返回 HTTP {response.status_code}"
