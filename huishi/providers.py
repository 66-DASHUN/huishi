from __future__ import annotations

import json
import logging
import re
import secrets
import threading
import time
from email.message import EmailMessage
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import requests

from openai import APIConnectionError, OpenAIError

from huishi.auth import prepare_email_message, send_email_message
from huishi.billing import tier_for_size
from huishi.db import get_db, sql_placeholders, utc_now
from huishi.image_api import ConfigurationError
from huishi.network import normalize_proxy_url, request_proxy_kwargs
from huishi.secrets import (
    decrypt_secret,
    encrypt_secret,
    load_secret_app_setting_value,
    store_secret_app_setting_value,
    redact_url as _redact_url,
    redact_sensitive_text as _redact_sensitive_text,
)


logger = logging.getLogger(__name__)
VALID_PROVIDER_TYPES = {"image", "video", "audio", "prompt", "mixed"}
VALID_IMAGE_API_FORMATS = {"openai", "gemini", "banana", "grok", "jiasuapi"}
VALID_VIDEO_API_FORMATS = {"openai", "grok", "seedance", "minimax", "dmc_h3", "seedance_media", "jiasuapi"}
VALID_AUDIO_API_FORMATS = {"openai", "minimax"}
IMAGE_RESOLUTION_TIERS = ("1K", "2K", "4K")
DEFAULT_IMAGE_PROVIDER_RESOLUTIONS = list(IMAGE_RESOLUTION_TIERS)
# Official image model presets. Inputs remain free-form so compatible gateways
# and newly released model ids can still be configured without a code update.
IMAGE_MODEL_CATALOG: dict[str, tuple[dict[str, str], ...]] = {
    "openai": (
        {"id": "gpt-image-2", "label": "GPT Image 2"},
        # Adobe's native channel exposes the same upstream request id but is
        # billed and published as a separate platform model.
        {"id": "gpt-image-2-adobe", "label": "GPT Image 2（Adobe 原生）"},
        {"id": "gpt-image-1", "label": "GPT Image 1"},
    ),
    "gemini": (
        {"id": "gemini-3.1-flash-image", "label": "Nano Banana 2"},
        {"id": "gemini-3-pro-image", "label": "Nano Banana Pro"},
    ),
    "banana": (
        {"id": "gemini-3.1-flash-image", "label": "Nano Banana 2"},
        {"id": "gemini-3-pro-image", "label": "Nano Banana Pro"},
    ),
    "grok": (
        {"id": "grok-imagine-image-2.0", "label": "grok-imagine 2.0"},
    ),
}

# Protocol metadata lives alongside the catalog so UI defaults and backend
# endpoint selection cannot drift apart.
IMAGE_PROVIDER_METADATA: dict[str, dict[str, object]] = {
    "openai": {"default_base_url": "https://api.openai.com/v1", "resolutions": IMAGE_RESOLUTION_TIERS},
    "gemini": {"default_base_url": "https://generativelanguage.googleapis.com", "resolutions": IMAGE_RESOLUTION_TIERS, "interactions_path": "/v1beta/interactions"},
    "banana": {"default_base_url": "https://generativelanguage.googleapis.com", "resolutions": IMAGE_RESOLUTION_TIERS, "interactions_path": "/v1beta/interactions"},
    "grok": {"default_base_url": "https://api.x.ai/v1", "resolutions": ("1K", "2K"), "generations_path": "/v1/images/generations", "generation_path": "/v1/images/generations", "edits_path": "/v1/images/edits", "edit_path": "/v1/images/edits"},
    "jiasuapi": {"default_base_url": "https://ai.jiasuapi.com", "resolutions": IMAGE_RESOLUTION_TIERS, "create_path": "/v1/images/create", "poll_path": "/v1/images/tasks/{task_id}"},
}
# Keep the singular names convenient for callers while retaining explicit
# protocol terminology in the canonical metadata above.
IMAGE_PROVIDER_METADATA["gemini"]["interaction_path"] = "/v1beta/interactions"
IMAGE_PROVIDER_METADATA["banana"]["interaction_path"] = "/v1beta/interactions"

VIDEO_MODEL_CATALOG: dict[str, tuple[dict[str, str], ...]] = {
    "dmc_h3": ({"id": "MiniMax-H3", "label": "MiniMax H3"},),
    "seedance_media": tuple({"id": value, "label": value} for value in ("seedance2.5", "seedance2.0", "seedance2.0fast", "seedance2.0mini")),
    "openai": (
        {"id": "sora-2", "label": "Sora 2"},
        {"id": "grok-imagine-video", "label": "grok-imagine"},
    ),
    "grok": (
        {"id": "grok-imagine-video", "label": "grok-imagine"},
        {"id": "grok-imagine-video-1.5", "label": "grok-imagine 1.5"},
    ),
    "seedance": (
        {"id": "doubao-seedance-1-0-pro-250528", "label": "Seedance 1.0 Pro"},
        {"id": "doubao-seedance-1-0-lite-t2v-250428", "label": "Seedance 1.0 Lite"},
    ),
    "minimax": (
        {"id": "MiniMax-H3", "label": "MiniMax H3"},
        {"id": "MiniMax-Hailuo-3.0", "label": "MiniMax 3"},
    ),
}

VIDEO_PROVIDER_METADATA: dict[str, dict[str, object]] = {
    "dmc_h3": {"default_base_url": "https://dmc.cc", "create_path": "/v2/video_generation", "resolutions": ("768P",)},
    "seedance_media": {"default_base_url": "https://api.laogou.org", "create_path": "/v1/media/videos", "resolutions": ("720p",)},
    "openai": {"default_base_url": "https://api.openai.com/v1", "create_path": "/videos", "resolutions": ("480p", "720p", "1080p")},
    "grok": {"default_base_url": "https://api.x.ai/v1", "create_path": "/v1/videos/generations", "poll_path": "/v1/videos/{task_id}", "resolutions": ("480p", "720p", "1080p")},
    "seedance": {"default_base_url": "https://ark.cn-beijing.volces.com/api/v3", "create_path": "/contents/generations/tasks", "poll_path": "/contents/generations/tasks/{task_id}", "resolutions": ("480p", "720p", "1080p")},
    "minimax": {"default_base_url": "https://api.minimaxi.com", "create_path": "/v1/video_generation", "poll_path": "/v1/query/video_generation", "file_path": "/v1/files/retrieve", "resolutions": ("720p", "1080p")},
    "jiasuapi": {"default_base_url": "https://ai.jiasuapi.com", "create_path": "/v1/video/generations", "poll_path": "/v1/videos/tasks/{task_id}", "resolutions": ("480p", "720p", "1080p", "2k")},
}

AUDIO_MODEL_CATALOG: dict[str, dict[str, tuple[dict[str, str], ...]]] = {
    "minimax": {
        "speech": (
            {"id": "speech-2.8-hd", "label": "MiniMax Speech 2.8 HD"},
            {"id": "speech-2.8-turbo", "label": "MiniMax Speech 2.8 Turbo"},
            {"id": "speech-2.6-hd", "label": "MiniMax Speech 2.6 HD"},
            {"id": "speech-2.6-turbo", "label": "MiniMax Speech 2.6 Turbo"},
            {"id": "speech-02-hd", "label": "MiniMax Speech 02 HD"},
            {"id": "speech-02-turbo", "label": "MiniMax Speech 02 Turbo"},
            {"id": "speech-01-hd", "label": "MiniMax Speech 01 HD"},
            {"id": "speech-01-turbo", "label": "MiniMax Speech 01 Turbo"},
        ),
        "music": (
            {"id": "music-3.0", "label": "MiniMax Music 3.0"},
            {"id": "music-2.6", "label": "MiniMax Music 2.6"},
            {"id": "music-cover", "label": "MiniMax Music Cover"},
        ),
    },
}

AUDIO_PROVIDER_METADATA: dict[str, dict[str, object]] = {
    "openai": {"default_base_url": "https://api.openai.com/v1"},
    "minimax": {"default_base_url": "https://api.minimaxi.com", "speech_path": "/v1/t2a_v2", "music_path": "/v1/music_generation"},
}


def image_model_metadata(model: object = None, api_format: object = None) -> dict[str, object]:
    """Return metadata for a known model, or an empty mapping for custom ids."""
    model_id = str(model or "").strip()
    protocols = [str(api_format).strip().lower()] if api_format else IMAGE_MODEL_CATALOG
    for protocol in protocols:
        options = IMAGE_MODEL_CATALOG.get(protocol, ())
        if any(option["id"] == model_id for option in options):
            result = dict(IMAGE_PROVIDER_METADATA[protocol])
            result["api_format"] = protocol
            result["model"] = model_id
            return result
    return {}


def provider_default_base_url(api_format: object = "openai") -> str:
    protocol = str(api_format or "openai").strip().lower()
    metadata = IMAGE_PROVIDER_METADATA.get(protocol) or VIDEO_PROVIDER_METADATA.get(protocol) or AUDIO_PROVIDER_METADATA.get(protocol) or IMAGE_PROVIDER_METADATA["openai"]
    return str(metadata["default_base_url"])


def image_provider_metadata(api_format: object = "openai") -> dict[str, object]:
    protocol = str(api_format or "openai").strip().lower()
    return dict(IMAGE_PROVIDER_METADATA.get(protocol, IMAGE_PROVIDER_METADATA["openai"]))


def video_provider_metadata(api_format: object = "openai") -> dict[str, object]:
    protocol = str(api_format or "openai").strip().lower()
    return dict(VIDEO_PROVIDER_METADATA.get(protocol, VIDEO_PROVIDER_METADATA["openai"]))


def provider_supported_resolutions(api_format: object = "openai") -> tuple[str, ...]:
    protocol = str(api_format or "openai").strip().lower()
    return tuple(IMAGE_PROVIDER_METADATA.get(protocol, IMAGE_PROVIDER_METADATA["openai"])["resolutions"])


default_image_base_url = provider_default_base_url
supported_image_resolutions = provider_supported_resolutions


def provider_endpoint_path(api_format: object, mode: str = "text", model: object = None) -> str:
    protocol = str(api_format or "openai").strip().lower()
    metadata = IMAGE_PROVIDER_METADATA.get(protocol, IMAGE_PROVIDER_METADATA["openai"])
    if protocol in {"gemini", "banana"}:
        return str(metadata.get("interactions_path", metadata.get("interaction_path", "/v1beta/interactions")))
    return str(metadata.get("edits_path" if mode == "reference" else "generations_path", "/v1/images/generations"))


def validate_image_model_protocol(model: object, api_format: object) -> None:
    model_id = str(model or "").strip()
    protocol = str(api_format or "").strip().lower()
    known_protocols = {p for p, options in IMAGE_MODEL_CATALOG.items() if any(o["id"] == model_id for o in options)}
    if known_protocols and protocol not in known_protocols:
        # Gemini and Banana intentionally share the official model ids.
        if not ({protocol, *known_protocols} <= {"gemini", "banana"}):
            raise ValueError("模型与调用协议不匹配")


def image_model_label(model: object = None) -> str:
    """Return the user-facing name while preserving custom model ids."""
    normalized = str(model or "").strip()
    if not normalized:
        return ""
    for options in IMAGE_MODEL_CATALOG.values():
        for option in options:
            if option["id"] == normalized:
                return option["label"]
    return normalized


def image_model_options(api_format: object = "openai") -> list[dict[str, str]]:
    """Return model suggestions for an image protocol without restricting custom ids."""
    normalized = str(api_format or "openai").strip().lower()
    return [dict(option) for option in IMAGE_MODEL_CATALOG.get(normalized, IMAGE_MODEL_CATALOG["openai"])]


def video_model_options(api_format: object = "openai") -> list[dict[str, str]]:
    """Return model suggestions for a video protocol without restricting custom ids."""
    normalized = str(api_format or "openai").strip().lower()
    return [dict(option) for option in VIDEO_MODEL_CATALOG.get(normalized, VIDEO_MODEL_CATALOG["openai"])]


def video_model_label(model: object = None) -> str:
    normalized = str(model or "").strip()
    if not normalized:
        return ""
    for options in VIDEO_MODEL_CATALOG.values():
        for option in options:
            if option["id"] == normalized:
                return option["label"]
    return normalized


def audio_model_options(api_format: object = "minimax", *, capability: str = "speech") -> list[dict[str, str]]:
    """Return official audio model suggestions for speech or music."""
    normalized_format = str(api_format or "minimax").strip().lower()
    normalized_capability = str(capability or "speech").strip().lower()
    if normalized_capability not in {"speech", "music"}:
        return []
    options = AUDIO_MODEL_CATALOG.get(normalized_format, {}).get(normalized_capability, ())
    return [dict(option) for option in options]


def audio_model_label(model: object = None) -> str:
    normalized = str(model or "").strip()
    if not normalized:
        return ""
    for catalog in AUDIO_MODEL_CATALOG.values():
        for options in catalog.values():
            for option in options:
                if option["id"] == normalized:
                    return option["label"]
    return normalized


def model_label(model: object = None) -> str:
    """Resolve the user-facing label across image, video, and audio catalogs."""
    normalized = str(model or "").strip()
    if not normalized:
        return ""
    for resolver in (image_model_label, video_model_label, audio_model_label):
        label = resolver(normalized)
        if label != normalized:
            return label
    return normalized


def default_image_model(api_format: object = "openai") -> str:
    options = image_model_options(api_format)
    return options[0]["id"]
_round_robin_lock = threading.Lock()
_round_robin_offsets: dict[tuple[str, str, int], int] = {}
SECRET_TOKEN_PATTERN = re.compile(
    r"(?i)\b(?:sk|sess|key|token|secret|bearer)[-_A-Za-z0-9]{8,}\b"
)
URL_PATTERN = re.compile(r"https?://[^\s<>'\")]+")


def generate_image(**kwargs):
    from huishi import routes_workspace

    return routes_workspace.generate_image(**kwargs)


def optimize_prompt(**kwargs):
    from huishi import routes_workspace

    return routes_workspace.optimize_prompt(**kwargs)


def validate_provider_type(provider_type: str) -> str:
    normalized = (provider_type or "").strip().lower()
    if normalized not in VALID_PROVIDER_TYPES:
        raise ValueError("Provider type must be image, video, audio, prompt or mixed")
    return normalized


def normalize_provider_api_format(value: object = None, provider_type: str = "image") -> str:
    normalized_type = validate_provider_type(provider_type)
    if normalized_type == "prompt":
        normalized_prompt = str(value or "openai").strip().lower()
        return normalized_prompt if normalized_prompt in {"openai", "jiasuapi"} else "openai"
    normalized = str(value or "openai").strip().lower()
    if normalized_type == "mixed":
        allowed = VALID_IMAGE_API_FORMATS | VALID_VIDEO_API_FORMATS | VALID_AUDIO_API_FORMATS
    elif normalized_type == "video":
        allowed = VALID_VIDEO_API_FORMATS
    elif normalized_type == "audio":
        allowed = VALID_AUDIO_API_FORMATS
    else:
        allowed = VALID_IMAGE_API_FORMATS
    if normalized not in allowed:
        if normalized_type == "video":
            raise ValueError("视频调用协议必须是 OpenAI 兼容、Grok、Seedance 或 MiniMax")
        if normalized_type == "audio":
            raise ValueError("音频调用协议必须是 OpenAI 兼容或 MiniMax")
        raise ValueError("生图调用协议必须是 OpenAI 兼容、Gemini 官方、Nano Banana 或 Grok 官方")
    return normalized


def normalize_provider_capabilities(value: object = None, provider_type: str = "image") -> list[str]:
    normalized_type = validate_provider_type(provider_type)
    values: list[object]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            parsed = re.split(r"[,;\s]+", value)
        values = parsed if isinstance(parsed, list) else [parsed]
    elif isinstance(value, (list, tuple, set)):
        values = list(value)
    else:
        values = []
    allowed = {"image", "video", "audio", "speech", "music", "prompt"}
    result = [str(item).strip().lower() for item in values if str(item).strip().lower() in allowed]
    if normalized_type != 'mixed' and normalized_type not in result:
        result.insert(0, normalized_type)
    return list(dict.fromkeys(result))


def normalize_provider_models(value: object = None, *, provider_type: str = "image", model: object = None) -> list[dict[str, Any]]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = []
    result: list[dict[str, Any]] = []
    if isinstance(value, (list, tuple)):
        for item in value:
            if isinstance(item, str):
                item = {"id": item, "label": item}
            if not isinstance(item, dict):
                continue
            model_id = str(item.get("id") or "").strip()
            if not model_id or any(existing["id"] == model_id for existing in result):
                continue
            normalized = {"id": model_id, "label": str(item.get("label") or model_id).strip()}
            if "enabled" in item:
                normalized["enabled"] = bool(item.get("enabled"))
            media_type = str(item.get("media_type") or item.get("capability") or "").strip().lower()
            if media_type in {"image", "video", "audio", "speech", "music", "prompt", "text"}:
                normalized["media_type"] = "prompt" if media_type == "text" else media_type
            elif provider_type in {"image", "video", "prompt"}:
                # Single-capability channels still persist an explicit model
                # type. Mixed channels deliberately remain unclassified until
                # the administrator selects a type in the model editor.
                normalized["media_type"] = provider_type
            elif provider_type == "audio":
                normalized["media_type"] = "music" if model_id.lower().startswith("music-") else "speech"
            for key in ("resolutions", "durations", "duration_seconds", "price", "price_unit", "api_format", "capabilities", "capability_source", "verification", "upstream_id", "managed", "cost_amount", "cost_unit", "cost_currency"):
                if key in item and item[key] not in (None, ""):
                    if key in ('capabilities','verification') and not isinstance(item[key],dict):
                        continue
                    normalized[key] = item[key]
            result.append(normalized)
    model_id = str(model or "").strip()
    if model_id and not any(item["id"] == model_id for item in result):
        if provider_type == "video":
            label = video_model_label(model_id)
            media_type = "video"
        elif provider_type == "audio":
            label = audio_model_label(model_id)
            media_type = "music" if model_id.lower().startswith("music-") else "speech"
        elif provider_type == "prompt":
            label = model_id
            media_type = "prompt"
        elif provider_type == "image":
            label = image_model_label(model_id)
            media_type = "image"
        else:
            label = image_model_label(model_id)
            media_type = ""
        item = {"id": model_id, "label": label or model_id}
        if media_type:
            item["media_type"] = media_type
        result.insert(0, item)
    return result


def normalize_provider(row):
    if row is None:
        return None
    provider = dict(row)
    provider["api_key"] = decrypt_secret(str(provider.get("api_key") or ""))
    provider["api_format"] = normalize_provider_api_format(
        provider.get("api_format"),
        str(provider.get("provider_type") or ""),
    )
    provider["resolutions"] = normalize_provider_resolutions(
        provider.get("resolutions"),
        str(provider.get("provider_type") or ""),
    )
    provider["capabilities"] = normalize_provider_capabilities(
        provider.get("capabilities"),
        str(provider.get("provider_type") or ""),
    )
    provider["models"] = normalize_provider_models(
        provider.get("models_json"),
        provider_type=str(provider.get("provider_type") or "image"),
        model=provider.get("model"),
    )
    raw_settings = provider.get("settings_json")
    if isinstance(raw_settings, str):
        try:
            raw_settings = json.loads(raw_settings)
        except json.JSONDecodeError:
            raw_settings = {}
    settings = dict(raw_settings) if isinstance(raw_settings, dict) else {}
    raw_proxy_url = decrypt_secret(str(settings.get("proxy_url") or ""))
    try:
        proxy_url = normalize_proxy_url(raw_proxy_url)
    except ValueError:
        logger.warning("provider has invalid proxy URL name=%s", provider.get("name"))
        proxy_url = ""
    if proxy_url:
        settings["proxy_url"] = proxy_url
    else:
        settings.pop("proxy_url", None)
    provider["settings"] = settings
    provider["proxy_url"] = proxy_url
    if provider['provider_type'] in ('video','mixed'):
        from huishi.media_capabilities import video_capabilities
        from huishi.provider_catalog import model_type
        for entry in provider['models']:
            if model_type(entry,provider['provider_type'])!='video':
                continue
            protocol=entry.get('api_format') or provider['api_format']
            caps=video_capabilities(protocol,entry.get('upstream_id') or entry['id'],entry.get('capabilities'))
            if caps:
                entry['capabilities']=caps
    return provider


def merge_provider_models(existing, fetched):
    current = {item['id']: dict(item) for item in existing}
    upstream_ids={str(item.get('upstream_id') or item['id']) for item in existing}
    for remote in fetched:
        model_id = remote['id']
        if model_id in current or model_id in upstream_ids:
            target=next(e for e in current.values() if e['id']==model_id or e.get('upstream_id')==model_id)
            for key in ('capabilities','capability_source'):
                if key not in target and key in remote: target[key]=remote[key]
            continue
        else:
            current[model_id] = {**remote, 'enabled': False}
    return list(current.values())


def normalize_provider_resolutions(value: object = None, provider_type: str = "image") -> list[str]:
    if validate_provider_type(provider_type) not in ("image", "mixed"):
        return []
    raw_values: list[object]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raw_values = []
        else:
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = re.split(r"[,;\s]+", text)
            raw_values = parsed if isinstance(parsed, list) else [parsed]
    elif isinstance(value, (list, tuple, set)):
        raw_values = list(value)
    else:
        raw_values = []

    selected: list[str] = []
    for item in raw_values:
        normalized = str(item or "").strip().upper()
        if normalized in IMAGE_RESOLUTION_TIERS and normalized not in selected:
            selected.append(normalized)
    return selected or list(DEFAULT_IMAGE_PROVIDER_RESOLUTIONS)


def serialize_provider_resolutions(value: object = None, provider_type: str = "image") -> str:
    return json.dumps(normalize_provider_resolutions(value, provider_type), ensure_ascii=False, separators=(",", ":"))


def redact_url(value: str) -> str:
    return _redact_url(value)


def redact_sensitive_text(value: object, *secrets: object) -> str:
    return _redact_sensitive_text(value, *secrets)


def get_app_settings(*keys: str) -> dict[str, str]:
    if not keys:
        rows = get_db().execute("SELECT key, value FROM app_settings").fetchall()
        return {row["key"]: load_secret_app_setting_value(row["key"], row["value"]) for row in rows}
    placeholders, params = sql_placeholders(keys)
    rows = get_db().execute(f"SELECT key, value FROM app_settings WHERE key IN ({placeholders})", params).fetchall()
    return {row["key"]: load_secret_app_setting_value(row["key"], row["value"]) for row in rows}


def save_app_setting(key: str, value: str) -> None:
    stored_value = store_secret_app_setting_value(key, value)
    get_db().execute(
        """
        INSERT INTO app_settings (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
          value = excluded.value,
          updated_at = excluded.updated_at
        """,
        (key, stored_value, utc_now()),
    )


CANVAS_SETTING_KEYS = {
    "canvas_app_url",
    "canvas_agent_url",
    "canvas_agent_token",
    "canvas_local_start_cmd",
    "canvas_default_template",
}


def get_canvas_settings() -> dict[str, str]:
    return get_app_settings(*CANVAS_SETTING_KEYS)


def save_canvas_setting(key: str, value: str) -> None:
    if key not in CANVAS_SETTING_KEYS:
        raise ValueError("unsupported canvas setting")
    save_app_setting(key, value)


def list_providers(provider_type: str | None = None) -> list[dict[str, Any]]:
    params: list[object] = []
    where = ""
    if provider_type:
        where = "WHERE provider_type IN (?, 'mixed')"
        params.append(validate_provider_type(provider_type))
    rows = get_db().execute(
        f"""
        SELECT *
        FROM api_providers
        {where}
        ORDER BY provider_type ASC, priority ASC, id ASC
        """,
        params,
    ).fetchall()
    result=[normalize_provider(row) for row in rows]
    if provider_type and provider_type!='mixed':
        from huishi.provider_catalog import provider_view
        result=[provider_view(p,provider_type) if p['provider_type']=='mixed' else p for p in result]
    return [p for p in result if p is not None]


def list_enabled_providers(provider_type: str) -> list[dict[str, Any]]:
    from huishi.provider_catalog import local_candidates
    return local_candidates(validate_provider_type(provider_type))


def get_provider(provider_id: int):
    row = get_db().execute("SELECT * FROM api_providers WHERE id = ?", (int(provider_id),)).fetchone()
    return normalize_provider(row)


def validate_provider_endpoint(api_format, base_url):
    from urllib.parse import urlsplit
    parsed=urlsplit(str(base_url).strip())
    if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('接口地址必须是有效的 HTTP(S) 地址，不能包含账号密码')
    if api_format in ('gemini','banana') and parsed.hostname in ('api.openai.com','api.x.ai'):
        raise ValueError('Gemini 协议与此供应商地址不匹配，请确认 Key 所属渠道')
    if api_format not in ('gemini','banana') and parsed.hostname=='generativelanguage.googleapis.com':
        raise ValueError('Google Gemini 地址需要选择 Gemini 协议')


def save_provider(
    *,
    provider_type: str,
    name: str,
    base_url: str,
    api_key: str,
    model: str,
    priority: int,
    enabled: bool,
    resolutions: object = None,
    provider_id: int | None = None,
    api_format: str = "openai",
    capabilities: object = None,
    models: object = None,
    settings: object = None,
) -> int:
    now = utc_now()
    provider_type = validate_provider_type(provider_type)
    api_format = normalize_provider_api_format(api_format, provider_type)
    validate_provider_endpoint(api_format, base_url)
    if provider_type == "image":
        validate_image_model_protocol(model, api_format)
    normalized_resolutions = normalize_provider_resolutions(resolutions, provider_type)
    if provider_type == "image" and api_format == "grok":
        normalized_resolutions = [value for value in normalized_resolutions if value in provider_supported_resolutions("grok")]
        if not normalized_resolutions:
            normalized_resolutions = ["1K", "2K"]
    normalized_capabilities = normalize_provider_capabilities(capabilities, provider_type)
    normalized_models = normalize_provider_models(models, provider_type=provider_type, model=model)
    from huishi.provider_catalog import model_type, invalidate_catalog
    for entry in normalized_models:
        from huishi.model_lifecycle import validate_binding
        validate_binding(entry)
        kind=model_type(entry,provider_type)
        family='audio' if kind in ('speech','music') else kind
        if provider_type!='mixed' and family!=provider_type:
            raise ValueError('添加其他类型模型前，请先扩展为多类型渠道')
        if provider_type=='mixed':
            if not kind and entry.get('enabled',True):
                raise ValueError('启用模型前必须选择模型类型')
            entry['media_type']=kind
        entry_type='audio' if kind in ('speech','music') else kind
        protocol=entry.get('api_format') or api_format
        if provider_type=='mixed' and kind:
            if entry_type=='prompt' and protocol not in {'openai', 'jiasuapi'}:
                raise ValueError('对话模型当前需要 OpenAI 兼容协议')
            normalize_provider_api_format(protocol,entry_type)
            validate_provider_endpoint(protocol,base_url)
        if entry.get('api_format'):
            entry['api_format']=normalize_provider_api_format(entry['api_format'],entry_type or provider_type)
            validate_provider_endpoint(entry['api_format'],base_url)
    if provider_type=='mixed':
        normalized_capabilities=list(dict.fromkeys(e['media_type'] for e in normalized_models if e.get('media_type')))
        model=str(model or '') if any(e['id']==model for e in normalized_models) else ''
    normalized_settings = dict(settings) if isinstance(settings, dict) else {}
    raw_proxy_url = decrypt_secret(str(normalized_settings.get("proxy_url") or ""))
    normalized_proxy_url = normalize_proxy_url(raw_proxy_url)
    if normalized_proxy_url:
        normalized_settings["proxy_url"] = encrypt_secret(normalized_proxy_url)
    else:
        normalized_settings.pop("proxy_url", None)
    display_name = name.strip() or ("Image Provider" if provider_type == "image" else ("Video Provider" if provider_type == "video" else "Prompt Provider"))
    existing = get_provider(int(provider_id)) if provider_id is not None else None
    connection_changed=bool(existing and any(str(existing.get(key) or '')!=str(value or '') for key,value in
        (('api_key',api_key.strip()),('base_url',base_url.strip()),('api_format',api_format),('proxy_url',normalized_proxy_url))))
    if existing:
        previous_settings={k:v for k,v in existing.get('settings',{}).items() if k!='proxy_url'}
        new_settings={k:v for k,v in normalized_settings.items() if k!='proxy_url'}
        connection_changed=connection_changed or previous_settings!=new_settings or existing.get('resolutions')!=normalized_resolutions
    if existing:
        old_models={e['id']:e for e in existing['models']}
        call_fields=('upstream_id','api_format','media_type','capabilities','resolutions','durations','duration_seconds')
        for entry in normalized_models:
            old=old_models.get(entry['id'],{})
            changed=connection_changed or any(entry.get(k)!=old.get(k) for k in call_fields)
            entry['verification']=dict(old.get('verification') or {})
            if changed and entry['verification']: entry['verification']['stale']=True
        if connection_changed: require_no_active_provider_tasks(int(provider_id))
    values = (
        provider_type,
        display_name,
        base_url.strip(),
        encrypt_secret(api_key.strip()),
        model.strip(),
        api_format,
        serialize_provider_resolutions(normalized_resolutions, provider_type),
        json.dumps(normalized_capabilities, ensure_ascii=False, separators=(",", ":")),
        json.dumps(normalized_models, ensure_ascii=False, separators=(",", ":")),
        json.dumps(normalized_settings, ensure_ascii=False, separators=(",", ":")),
        int(priority),
        1 if enabled else 0,
    )
    if provider_id is None:
        cursor = get_db().execute(
            """
            INSERT INTO api_providers
            (provider_type, name, base_url, api_key, model, api_format, resolutions, capabilities, models_json, settings_json, priority, enabled, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (*values, now, now),
        )
        invalidate_catalog()
        return int(cursor.lastrowid)
    existing = get_provider(int(provider_id))
    if existing and any(str(existing.get(key) or '') != str(value or '') for key,value in (
        ('api_key',api_key.strip()),('base_url',base_url.strip()),('api_format',api_format))):
        require_no_active_provider_tasks(int(provider_id))
    get_db().execute(
        """
        UPDATE api_providers
        SET provider_type = ?,
            name = ?,
            base_url = ?,
            api_key = ?,
            model = ?,
            api_format = ?,
            resolutions = ?,
            capabilities = ?,
            models_json = ?,
            settings_json = ?,
            priority = ?,
            enabled = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (*values, now, int(provider_id)),
    )
    invalidate_catalog()
    if connection_changed:
        get_db().execute("UPDATE api_providers SET last_error='',last_checked_at='' WHERE id=?",(int(provider_id),))
    return int(provider_id)


def disable_provider(provider_id: int, error_message: str) -> None:
    from huishi.provider_catalog import invalidate_catalog
    invalidate_catalog()
    now = utc_now()
    get_db().execute(
        """
        UPDATE api_providers
        SET enabled = 0,
            last_error = ?,
            disabled_at = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (str(error_message), now, now, int(provider_id)),
    )


def delete_provider(provider_id: int) -> None:
    require_no_active_provider_tasks(provider_id)
    get_db().execute("DELETE FROM api_providers WHERE id = ?", (int(provider_id),))
    from huishi.provider_catalog import invalidate_catalog
    invalidate_catalog()


def require_no_active_provider_tasks(provider_id):
    row=get_db().execute("SELECT id FROM generation_tasks WHERE provider_id=? AND status IN ('queued','running') LIMIT 1",(provider_id,)).fetchone()
    if row:
        raise ValueError('此渠道有未完成任务，暂不能删除或修改地址、密钥和协议；可以停用新任务')


def mark_provider_check_result(
    provider_id: int,
    *,
    ok: bool,
    message: str,
    enable_on_success: bool = False,
) -> None:
    from huishi.provider_catalog import invalidate_catalog
    invalidate_catalog()
    now = utc_now()
    if ok:
        get_db().execute(
            """
            UPDATE api_providers
            SET last_error = '',
                last_checked_at = ?,
                disabled_at = CASE WHEN ? THEN '' ELSE disabled_at END,
                enabled = CASE WHEN ? THEN 1 ELSE enabled END,
                updated_at = ?
            WHERE id = ?
            """,
            (now, bool(enable_on_success), bool(enable_on_success), now, int(provider_id)),
        )
        return
    provider = get_provider(provider_id)
    get_db().execute(
        """
        UPDATE api_providers
        SET enabled = 0,
            last_error = ?,
            disabled_at = ?,
            last_checked_at = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (str(message), now, now, now, int(provider_id)),
    )
    if provider is not None:
        notify_provider_disabled(provider, str(message))


def check_provider_connectivity(provider: dict[str, Any], mode: str = "probe") -> tuple[bool, str]:
    if not str(provider.get("base_url") or "").strip():
        return False, "Base URL cannot be empty"
    if not str(provider.get("api_key") or "").strip():
        return False, "API Key cannot be empty"
    if provider.get("provider_type") in {"prompt", "video"} and not str(provider.get("model") or "").strip():
        return False, "Prompt model cannot be empty"
    try:
        try:
            validate_provider_endpoint(provider.get('api_format') or 'openai',provider['base_url'])
            probe_provider_connectivity(provider, mode=mode)
        except TypeError:
            # Keep compatibility with integrations that wrap the legacy one-argument probe.
            probe_provider_connectivity(provider)
    except Exception as exc:
        return False, redact_sensitive_text(str(exc), provider.get("api_key"), provider.get("base_url"))
    return True, "connection ok"


def fetch_provider_models(provider: dict[str, Any]) -> list[dict[str, str]]:
    base_url = str(provider.get("base_url") or "").rstrip("/")
    api_format = str(provider.get("api_format") or "openai").lower()
    validate_provider_endpoint(api_format,base_url)
    if api_format == "seedance_media":
        from huishi.video_adapters.seedance_media import models
        return models(provider)
    if api_format == "dmc_h3":
        from huishi.media_capabilities import video_capabilities
        return [{"id": "MiniMax-H3", "label": "MiniMax H3", "media_type": "video", "api_format": "dmc_h3",
                 "capabilities": video_capabilities("dmc_h3", "MiniMax-H3"), "capability_source": "builtin", "enabled": False}]
    payload = None
    if api_format in {"gemini", "banana"}:
        # Gemini REST exposes /v1beta/models and returns {"models": [...]};
        # accept a configured proxy first, then fall back to the official host.
        candidates = []
        if base_url:
            candidates.append(f"{base_url}/models" if base_url.endswith("/v1beta") else f"{base_url}/v1beta/models")
        if not candidates:
            raise ValueError("请填写 Gemini 渠道地址")
        response = None
        for endpoint in dict.fromkeys(candidates):
            candidate = requests.get(endpoint, params={"key": provider.get("api_key") or ""}, headers={"Accept": "application/json"}, timeout=15, **request_proxy_kwargs(provider.get("proxy_url")))
            response = candidate
            if candidate.status_code != 404:
                break
    elif api_format == "jiasuapi":
        candidates = [f"{base_url}/models" if base_url.endswith("/v1") else f"{base_url}/v1/models"]
        response = None
        for endpoint in candidates:
            response = requests.get(
                endpoint,
                headers={"Authorization": f"Bearer {provider.get('api_key') or ''}", "Accept": "application/json"},
                timeout=15,
                **request_proxy_kwargs(provider.get("proxy_url")),
            )
            if 200 <= response.status_code < 300:
                try:
                    payload = response.json()
                except ValueError:
                    pass
                else:
                    break
    else:
        candidates = [f"{base_url}/models"]
        if not base_url.endswith("/v1"):
            candidates.append(f"{base_url}/v1/models")
        response = None
        for endpoint in dict.fromkeys(candidates):
            candidate = requests.get(
                endpoint,
                headers={"Authorization": f"Bearer {provider.get('api_key') or ''}", "Accept": "application/json"},
                timeout=15,
                **request_proxy_kwargs(provider.get("proxy_url")),
            )
            response = candidate
            if candidate.status_code < 200 or candidate.status_code >= 300:
                continue
            try:
                payload = candidate.json()
            except ValueError:
                continue
            break
    if response is None or response.status_code < 200 or response.status_code >= 300:
        status = response.status_code if response is not None else "unknown"
        try:
            detail = str(response.json().get("error", {}).get("message") or response.json().get("message") or "")
        except Exception:
            detail = ""
        raise RuntimeError(f"models endpoint returned HTTP {status}{': ' + detail if detail else ''}")
    if payload is None:
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError("models endpoint did not return JSON") from exc
    if isinstance(payload, dict):
        entries = payload.get("data") or payload.get("models") or []
    else:
        entries = payload
    if not isinstance(entries, list):
        raise RuntimeError("models endpoint returned an unsupported JSON payload")
    result = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("id") or item.get("name") or "").strip()
        if model_id.startswith("models/"):
            model_id = model_id[7:]
        if model_id:
            entry={"id": model_id, "label": str(item.get("label") or item.get("displayName") or item.get("name") or model_id).removeprefix("models/")}
            if provider.get('provider_type')=='mixed':
                from huishi.provider_catalog import suggested_model_type
                entry.update(media_type=suggested_model_type({**item,'id':model_id}),enabled=False)
            if api_format == "jiasuapi":
                entry.update(api_format="jiasuapi", enabled=False)
                media_type = str(entry.get("media_type") or "")
                if media_type == "image":
                    match = re.search(r"-(1k|2k|4k)$", model_id, re.IGNORECASE)
                    if match:
                        entry["resolutions"] = [match.group(1).upper()]
                elif media_type == "video":
                    from huishi.media_capabilities import video_capabilities
                    capabilities = video_capabilities("jiasuapi", model_id)
                    if capabilities:
                        entry.update(capabilities=capabilities, capability_source="builtin")
            result.append(entry)
    return result


def probe_provider_connectivity(provider: dict[str, Any], mode: str = "generate") -> None:
    from huishi.model_lifecycle import upstream_model
    provider_type = str(provider.get("provider_type") or "image").strip().lower()
    if provider_type == "video" and mode == "generate":
        from huishi.video_api import VideoApiError, create_video_task, download_video_result, poll_video_task
        from flask import current_app
        task = create_video_task(provider, {"model": provider.get("model"), "prompt": "连接测试视频", "duration_seconds": 2, "ratio": "16:9"})
        provider["_test_video_task"] = task.provider_task_id
        deadline = time.monotonic() + max(30, min(300, int(current_app.config.get("VIDEO_TEST_TIMEOUT_SECONDS", 120))))
        interval = max(1, min(10, int((provider.get("settings") or {}).get("poll_interval", 3))))
        state = None
        while time.monotonic() < deadline:
            state = poll_video_task(provider, task.provider_task_id)
            if state.status in {"completed", "failed"}:
                break
            time.sleep(interval)
        if state and state.status == "completed":
            content = download_video_result(provider, state, timeout=120)
            from huishi.upload_storage import get_upload_storage
            public_path = get_upload_storage().save_bytes(f"provider_test_{secrets.token_urlsafe(8)}.mp4", content, "video/mp4")
            provider["_test_video_url"] = public_path
            provider["_test_video_status"] = "completed"
        elif state and state.status == "failed":
            raise VideoApiError(state.error or "视频测试任务失败")
        else:
            provider["_test_video_status"] = "pending"
        return
    if provider_type == "audio" and mode == "generate":
        from huishi.audio_api import generate_music, generate_speech
        from huishi.upload_storage import get_upload_storage

        model = str(provider.get("model") or "").strip()
        entry = _provider_model_entry(provider, model) or {}
        capability = str(entry.get("media_type") or entry.get("capability") or "").strip().lower()
        if capability not in {"speech", "music"}:
            capability = "music" if model.lower().startswith("music-") else "speech"
        request_payload = {
            "model": upstream_model(provider,model),
            "text": "连接测试，请返回一段简短语音。" if capability == "speech" else "",
            "prompt": "连接测试音频" if capability == "music" else "",
            "voice_id": "male-qn-qingse",
            "output_format": "mp3",
            "lyrics": "",
            "is_instrumental": True,
        }
        result = generate_speech(provider, request_payload) if capability == "speech" else generate_music(provider, request_payload)
        content = bytes(result.get("content") or b"")
        if not content:
            raise RuntimeError("音频接口未返回内容")
        extension = str(result.get("extension") or "mp3").strip().lower() or "mp3"
        mime_type = str(result.get("mime_type") or "audio/mpeg")
        provider["_test_audio_url"] = get_upload_storage().save_bytes(
            f"provider_test_{secrets.token_urlsafe(8)}.{extension}",
            content,
            mime_type,
        )
        provider["_test_audio_kind"] = capability
        return
    if mode == "probe":
        base_url = str(provider.get("base_url") or "").rstrip("/")
        probe_url = f"{base_url}/models" if provider_type in {"prompt", "video"} else base_url
        response = requests.get(
            probe_url,
            headers={"Authorization": f"Bearer {provider.get('api_key') or ''}", "Accept": "application/json"},
            timeout=10,
            **request_proxy_kwargs(provider.get("proxy_url")),
        )
        if response.status_code < 200 or response.status_code >= 300:
            raise RuntimeError(f"probe endpoint returned HTTP {response.status_code}")
        return
    if provider_type == "image":
        result = generate_image(
            prompt="connection test",
            mode="text",
            ratio="1:1",
            resolution="1K",
            count=1,
            quality="low",
            output_format="png",
            reference_images=[],
            api_key=str(provider.get("api_key") or ""),
            base_url=str(provider.get("base_url") or ""),
            model=upstream_model(provider) or 'gpt-image-2',
            api_format=str(provider.get("api_format") or "openai"),
            proxy_url=str(provider.get("proxy_url") or ""),
        )
        provider["_test_image"] = result.get("image_path") if isinstance(result, dict) else None
        return

    if provider_type == "prompt":
        base_url = str(provider.get("base_url") or "").rstrip("/")
        endpoints = [f"{base_url}/chat/completions"]
        if not base_url.endswith("/v1"):
            endpoints.append(f"{base_url}/v1/chat/completions")
        payload = None
        last_status = None
        saw_non_json = False
        for endpoint in dict.fromkeys(endpoints):
            response = requests.post(
                endpoint,
                headers={"Authorization": f"Bearer {provider.get('api_key') or ''}", "Content-Type": "application/json"},
                json={"model": upstream_model(provider), "messages": [{"role": "user", "content": "连接测试，请只回复：OK"}], "max_tokens": 8},
                timeout=30,
                **request_proxy_kwargs(provider.get("proxy_url")),
            )
            last_status = response.status_code
            if response.status_code < 200 or response.status_code >= 300:
                continue
            try:
                payload = response.json()
            except ValueError:
                saw_non_json = True
                continue
            break
        if payload is None:
            if last_status is not None and (last_status < 200 or last_status >= 300):
                raise RuntimeError(f"chat endpoint returned HTTP {last_status}")
            if saw_non_json:
                raise RuntimeError("对话接口没有返回 JSON")
            raise RuntimeError("对话接口没有返回结果")
        choices = payload.get("choices") if isinstance(payload, dict) else []
        message = choices[0].get("message") if choices and isinstance(choices[0], dict) else {}
        text = message.get("content") if isinstance(message, dict) else ""
        if isinstance(text, list):
            text = "".join(str(item.get("text") or "") for item in text if isinstance(item, dict))
        fallback_text = payload.get("output_text") if isinstance(payload, dict) else ""
        provider["_test_text"] = str(text or fallback_text or "收到成功响应").strip()
        return

    if provider_type == "video":
        api_format = str(provider.get("api_format") or "openai").strip().lower()
        base_url = str(provider.get("base_url") or "").rstrip("/")
        if api_format in {"openai", "grok"}:
            probe_url = f"{base_url}/models"
        else:
            probe_url = base_url
        response = requests.get(
            probe_url,
            headers={"Authorization": f"Bearer {provider.get('api_key') or ''}", "Accept": "application/json"},
            timeout=10,
            **request_proxy_kwargs(provider.get("proxy_url")),
        )
        if response.status_code < 200 or response.status_code >= 300:
            raise RuntimeError(f"video endpoint returned HTTP {response.status_code}")
        return

    base_url = str(provider.get("base_url") or "").rstrip("/")
    response = requests.get(
        f"{base_url}/models",
        headers={
            "Authorization": f"Bearer {provider.get('api_key') or ''}",
            "Accept": "application/json",
        },
        timeout=10,
        **request_proxy_kwargs(provider.get("proxy_url")),
    )
    if response.status_code < 200 or response.status_code >= 300:
        raise RuntimeError(f"models endpoint returned HTTP {response.status_code}")
    try:
        payload = response.json()
    except ValueError as exc:
        content_type = response.headers.get("content-type", "")
        raise RuntimeError(f"models endpoint did not return JSON ({content_type or 'unknown content type'})") from exc
    if not isinstance(payload, (dict, list)):
        raise RuntimeError("models endpoint returned an unsupported JSON payload")


def _resolution_tier_for_request(resolution: str) -> str:
    try:
        return tier_for_size(resolution)
    except ValueError:
        candidate = str(resolution or "").strip().upper()
        if candidate in IMAGE_RESOLUTION_TIERS:
            return candidate
        return candidate


def _provider_exists(provider_type: str, base_url: str, api_key: str, model: str) -> bool:
    normalized_type = validate_provider_type(provider_type)
    normalized_base_url = base_url.strip()
    normalized_api_key = api_key.strip()
    normalized_model = model.strip()
    rows = get_db().execute(
        """
        SELECT *
        FROM api_providers
        WHERE provider_type = ?
          AND base_url = ?
          AND model = ?
        """,
        (normalized_type, normalized_base_url, normalized_model),
    ).fetchall()
    return any(str(normalize_provider(row).get("api_key") or "").strip() == normalized_api_key for row in rows)


def import_legacy_providers_from_settings() -> int:
    imported = 0
    legacy_image = legacy_image_provider_from_settings()
    if legacy_image and (
        str(legacy_image.get("base_url") or "").strip() or str(legacy_image.get("api_key") or "").strip()
    ):
        if not _provider_exists(
            "image",
            str(legacy_image.get("base_url") or ""),
            str(legacy_image.get("api_key") or ""),
            str(legacy_image.get("model") or "gpt-image-2"),
        ):
            save_provider(
                provider_type="image",
                name="默认生图配置",
                base_url=str(legacy_image.get("base_url") or ""),
                api_key=str(legacy_image.get("api_key") or ""),
                model=str(legacy_image.get("model") or "gpt-image-2"),
                priority=int(legacy_image.get("priority") or 9999),
                enabled=True,
            )
            imported += 1

    legacy_prompt = legacy_prompt_provider_from_settings()
    if legacy_prompt and (
        str(legacy_prompt.get("base_url") or "").strip()
        or str(legacy_prompt.get("api_key") or "").strip()
        or str(legacy_prompt.get("model") or "").strip()
    ):
        if not _provider_exists(
            "prompt",
            str(legacy_prompt.get("base_url") or ""),
            str(legacy_prompt.get("api_key") or ""),
            str(legacy_prompt.get("model") or ""),
        ):
            save_provider(
                provider_type="prompt",
                name="默认提示词优化配置",
                base_url=str(legacy_prompt.get("base_url") or ""),
                api_key=str(legacy_prompt.get("api_key") or ""),
                model=str(legacy_prompt.get("model") or ""),
                priority=int(legacy_prompt.get("priority") or 9999),
                enabled=True,
            )
            imported += 1

    return imported


def legacy_image_provider_from_settings() -> dict[str, Any] | None:
    settings = get_app_settings("image_base_url", "image_api_key")
    base_url = settings.get("image_base_url", "")
    api_key = settings.get("image_api_key", "")
    return {
        "id": None,
        "provider_type": "image",
        "name": "Legacy Image Provider",
        "base_url": base_url,
        "api_key": api_key,
        "model": "gpt-image-2",
        "api_format": "openai",
        "resolutions": list(DEFAULT_IMAGE_PROVIDER_RESOLUTIONS),
        "priority": 9999,
        "enabled": 1,
    }


def _provider_model_entry(provider: dict[str, Any], model_id: str) -> dict[str, Any] | None:
    """Return one enabled model entry from a provider's normalized catalog."""
    requested = str(model_id or "").strip()
    for entry in provider.get("models") or []:
        if str(entry.get("id") or "").strip() == requested:
            if entry.get("enabled", True) is False:
                return None
            return entry
    default_model = str(provider.get("model") or "").strip()
    if requested and requested == default_model:
        return {"id": default_model, "label": default_model}
    return None


def _provider_supports_image_model(provider: dict[str, Any], model_id: str, resolution: str | None = None) -> bool:
    entry = _provider_model_entry(provider, model_id)
    if entry is None or entry.get('media_type','image') != 'image':
        return False
    if not resolution:
        return True
    raw_resolutions = entry.get("resolutions")
    configured = normalize_provider_resolutions(
        raw_resolutions if raw_resolutions is not None else provider.get("resolutions"),
        "image",
    )
    tier = _resolution_tier_for_request(resolution)
    if entry.get('managed'):
        from huishi.model_lifecycle import exact_prices
        if not any(r['mode']=='text' and r['resolution']==tier for r in exact_prices('image',model_id)):
            return False
    api_format = str(entry.get('api_format') or provider.get('connection_api_format') or provider.get("api_format") or "openai")
    return tier in configured and tier in set(provider_supported_resolutions(api_format))


def image_provider_candidates(resolution: str | None = None, model: object = None) -> list[dict[str, Any]]:
    from huishi.provider_catalog import local_candidates
    configured = local_candidates('image',model)
    requested_model = str(model or "").strip()
    if configured:
        if resolution:
            tier = _resolution_tier_for_request(resolution)
            if requested_model and requested_model != "*":
                configured = [provider for provider in configured if _provider_supports_image_model(provider, requested_model, resolution)]
            else:
                configured = [provider for provider in configured if tier in normalize_provider_resolutions(provider.get("resolutions"), "image")]
        if requested_model and requested_model != "*":
            configured = [provider for provider in configured if _provider_supports_image_model(provider, requested_model, resolution)]
            configured = [{**provider,'api_format':_provider_model_entry(provider,requested_model).get('api_format') or provider['api_format']} for provider in configured]
        return configured
    return []


def video_provider_candidates(model: object = None) -> list[dict[str, Any]]:
    """Return enabled video providers, optionally narrowed to a model id."""
    from huishi.provider_catalog import local_candidates
    from huishi.provider_catalog import model_type
    configured = local_candidates('video',model)
    requested_model = str(model or "").strip()
    if requested_model and requested_model != "*":
        configured = [
            item
            for item in configured
            if _provider_model_entry(item, requested_model) is not None
            and model_type(_provider_model_entry(item, requested_model), item.get('provider_type', 'mixed')) == "video"
        ]
        configured = [{**item, "api_format": _provider_model_entry(item, requested_model).get("api_format") or item["api_format"]} for item in configured]
    return configured


def selectable_video_models() -> list[dict[str, object]]:
    from huishi.media_capabilities import video_capabilities
    from huishi.provider_catalog import model_type
    models: list[dict[str, object]] = []
    seen: set[str] = set()
    for provider in video_provider_candidates():
        entries = provider.get("models") or normalize_provider_models(None, provider_type="video", model=provider.get("model"))
        for entry in entries:
            model_id = str(entry.get("id") or "").strip()
            if not model_id or model_id in seen or entry.get("enabled", True) is False or model_type(entry, provider.get('provider_type', 'mixed')) != "video":
                continue
            seen.add(model_id)
            protocol = entry.get("api_format") or provider.get("connection_api_format") or provider.get("api_format")
            canonical_label = video_model_label(model_id)
            stored_label = str(entry.get("label") or "").strip()
            # Official ids keep a stable product name even when an older
            # channel record saved the raw upstream id as its label.
            label = canonical_label if canonical_label and canonical_label != model_id else (stored_label or model_id)
            item={"id": model_id, "label": label}
            caps=video_capabilities(protocol, entry.get('upstream_id') or model_id, entry.get("capabilities"))
            if caps:
                item.update(api_format=protocol,capabilities=caps)
            models.append(item)
    return models


def _audio_provider_supports(provider: dict[str, Any], model_id: str, capability: str) -> bool:
    requested = str(model_id or "").strip()
    wanted = str(capability or "").strip().lower()
    if wanted not in {"speech", "music"}:
        return False
    capabilities = set(normalize_provider_capabilities(provider.get("capabilities"), "audio"))
    if wanted not in capabilities:
        return False
    entry = _provider_model_entry(provider, requested)
    if entry is None:
        return False
    entry_capability = str(entry.get("media_type") or entry.get("capability") or "").strip().lower()
    return not entry_capability or entry_capability == wanted


def audio_provider_candidates(capability: str, model: object = None) -> list[dict[str, Any]]:
    """Return enabled audio providers for one capability and optional model."""
    wanted = str(capability or "").strip().lower()
    if wanted not in {"speech", "music"}:
        return []
    from huishi.provider_catalog import local_candidates
    configured = local_candidates(wanted,model)
    requested_model = str(model or "").strip()
    result = []
    for provider in configured:
        capabilities = set(normalize_provider_capabilities(provider.get("capabilities"), "audio"))
        if wanted not in capabilities:
            continue
        if requested_model and requested_model != "*" and not _audio_provider_supports(provider, requested_model, wanted):
            continue
        result.append(provider)
    return result


def selectable_audio_models(capability: str) -> list[dict[str, object]]:
    models: list[dict[str, object]] = []
    seen: set[str] = set()
    wanted = str(capability or "").strip().lower()
    for provider in audio_provider_candidates(wanted):
        entries = provider.get("models") or audio_model_options(provider.get("api_format"), capability=wanted)
        for entry in entries:
            entry_capability = str(entry.get("media_type") or entry.get("capability") or "").strip().lower()
            if entry_capability and entry_capability != wanted:
                continue
            model_id = str(entry.get("id") or "").strip()
            if not model_id or model_id in seen or entry.get("enabled", True) is False:
                continue
            seen.add(model_id)
            models.append({"id": model_id, "label": str(entry.get("label") or audio_model_label(model_id))})
    return models


def selectable_speech_models() -> list[dict[str, object]]:
    return selectable_audio_models("speech")


def selectable_music_models() -> list[dict[str, object]]:
    return selectable_audio_models("music")


def image_model_for_request(resolution: str | None = None) -> str:
    """Return the model used for a platform generation cost estimate.

    Provider priority is the scheduler's selection order, so the first
    compatible enabled provider is the stable model recorded on a task.
    """
    candidates = image_provider_candidates(resolution)
    if not candidates:
        return "*"
    return _default_image_model_for_provider(candidates[0], resolution)


def _default_image_model_for_provider(provider: dict[str, Any], resolution: str | None = None) -> str:
    for entry in provider.get("models") or []:
        model_id = str(entry.get("id") or "").strip()
        if not model_id or entry.get("enabled", True) is False or entry.get("media_type") not in (None, "", "image"):
            continue
        if _provider_supports_image_model(provider, model_id, resolution):
            return model_id
    return str(provider.get("model") or "*").strip() or "*"


def selectable_image_models() -> list[dict[str, object]]:
    """Return enabled image models in stable provider priority order."""
    from huishi.model_lifecycle import exact_prices

    models: list[dict[str, object]] = []
    by_id: dict[str, dict[str, object]] = {}
    for provider in image_provider_candidates():
        api_format = str(provider.get("api_format") or "openai")
        configured = normalize_provider_resolutions(provider.get("resolutions"), "image")
        protocol_resolutions = set(provider_supported_resolutions(api_format))
        for entry in provider.get("models") or []:
            protocol_resolutions = set(provider_supported_resolutions(entry.get('api_format') or provider.get('connection_api_format') or api_format))
            if entry.get("enabled", True) is False:
                continue
            if entry.get("media_type") not in (None, "", "image"):
                continue
            model_id = str(entry.get("id") or "").strip()
            if not model_id:
                continue
            entry_configured = normalize_provider_resolutions(
                entry.get("resolutions") if entry.get("resolutions") is not None else configured,
                "image",
            )
            resolutions = [tier for tier in IMAGE_RESOLUTION_TIERS if tier in entry_configured and tier in protocol_resolutions]
            priced = {rule['resolution'] for rule in exact_prices('image', model_id) if rule['mode'] == 'text'}
            resolutions = [tier for tier in resolutions if tier in priced]
            if not resolutions:
                continue
            existing = by_id.get(model_id)
            if existing is None:
                canonical_label = image_model_label(model_id)
                existing = {
                    "id": model_id,
                    "label": canonical_label if canonical_label and canonical_label != model_id else str(entry.get("label") or model_id),
                    "resolutions": resolutions,
                }
                by_id[model_id] = existing
                models.append(existing)
                continue
            existing_resolutions = list(existing["resolutions"])
            existing["resolutions"] = [
                tier for tier in IMAGE_RESOLUTION_TIERS if tier in existing_resolutions or tier in resolutions
            ]
    return models


def resolve_image_model_for_request(model: object = None, resolution: str | None = None) -> str:
    """Resolve a selected enabled model, defaulting only when no model was supplied."""
    requested_model = str(model or "").strip()
    resolution_tier = _resolution_tier_for_request(str(resolution or "2K"))
    models = selectable_image_models()
    if requested_model:
        selected = next((item for item in models if item["id"] == requested_model), None)
        if selected is None:
            raise ConfigurationError("所选生图模型未启用")
        if resolution_tier not in selected["resolutions"]:
            raise ConfigurationError(f"所选生图模型不支持 {resolution_tier} 分辨率")
        return requested_model
    selected = next((item for item in models if resolution_tier in item["resolutions"]), None)
    if selected is None:
        raise ConfigurationError(f"没有支持 {resolution_tier} 分辨率的已启用生图模型")
    return str(selected["id"])


def _round_robin_provider(provider_type: str, resolution: str, priority: int, providers: list[dict[str, Any]]) -> dict[str, Any]:
    key = (provider_type, resolution, int(priority))
    with _round_robin_lock:
        offset = _round_robin_offsets.get(key, 0)
        if not providers:
            raise ValueError("No providers available")
        provider = providers[offset % len(providers)]
        _round_robin_offsets[key] = (offset + 1) % len(providers)
        return provider


def parse_alert_emails(raw_value: str) -> list[str]:
    candidates = [item.strip() for item in re.split(r"[,;\n\r]+", raw_value or "")]
    return [item for item in candidates if item and "@" in item]


def save_app_alert_emails(value: str) -> None:
    save_app_setting("alert_emails", value)


def alert_email_recipients() -> list[str]:
    settings = get_app_settings("alert_emails")
    return parse_alert_emails(settings.get("alert_emails", ""))


def send_alert_email(recipients: list[str], subject: str, body: str) -> None:
    for recipient in recipients:
        message = EmailMessage()
        prepare_email_message(message, subject, recipient)
        message.set_content(body)
        send_email_message(message)


def notify_provider_disabled(provider: dict[str, Any], error_message: str) -> None:
    safe_error = redact_sensitive_text(error_message, provider.get("api_key"))
    safe_base_url = redact_url(str(provider.get("base_url") or ""))
    recipients = alert_email_recipients()
    if not recipients:
        logger.warning(
            "provider disabled without alert recipients name=%s type=%s error=%s",
            provider.get("name"),
            provider.get("provider_type"),
            safe_error,
        )
        return
    subject = f"绘世 API 配置已停用：{provider.get('name')}"
    body = "\n".join(
        [
            f"配置类型：{provider.get('provider_type')}",
            f"配置名称：{provider.get('name')}",
            f"Base URL：{safe_base_url}",
            f"错误信息：{safe_error}",
            "系统已自动停用该配置，并会尝试切换到下一条启用配置。",
        ]
    )
    try:
        send_alert_email(recipients, subject, body)
    except Exception:
        logger.exception("failed to send provider disable alert name=%s", provider.get("name"))


def disable_provider_for_runtime_failure(provider: dict[str, Any], error_message: str) -> None:
    if provider.get("id") is None:
        return
    safe_error = redact_sensitive_text(error_message, provider.get("api_key"), provider.get("base_url"))
    disable_provider(int(provider["id"]), safe_error)
    notify_provider_disabled(provider, safe_error)


def generate_image_with_failover(**kwargs) -> dict[str, object]:
    resolution = str(kwargs.get("resolution") or "")
    resolution_tier = _resolution_tier_for_request(resolution)
    requested_model = str(kwargs.get("model") or "").strip()
    candidates = image_provider_candidates(resolution, requested_model)
    generation_kwargs = dict(kwargs)
    generation_kwargs.pop("model", None)
    if not candidates:
        raise ConfigurationError("没有可用的生图配置，请到设置页添加并启用生图配置")
    last_error: str = ""
    tried_provider_ids: set[object] = set()
    while True:
        remaining = [
            provider
            for provider in candidates
            if (provider.get("id") if provider.get("id") is not None else id(provider)) not in tried_provider_ids
        ]
        if not remaining:
            break
        priority = min(int(provider.get("priority") or 100) for provider in remaining)
        group = [provider for provider in remaining if int(provider.get("priority") or 100) == priority]
        provider = _round_robin_provider("image", resolution_tier, priority, group)
        provider_key = provider.get("id") if provider.get("id") is not None else id(provider)
        tried_provider_ids.add(provider_key)
        for attempt in range(1):
            started_at = time.monotonic()
            try:
                selected_model = requested_model if requested_model and requested_model != "*" else _default_image_model_for_provider(provider, resolution)
                from huishi.model_lifecycle import upstream_model
                result = generate_image(
                    **generation_kwargs,
                    api_key=str(provider.get("api_key") or ""),
                    base_url=str(provider.get("base_url") or ""),
                    model=upstream_model(provider,selected_model),
                    api_format=str((_provider_model_entry(provider,selected_model) or {}).get('api_format') or provider.get('connection_api_format') or provider.get("api_format") or "openai"),
                    proxy_url=str(provider.get("proxy_url") or ""),
                )
                result['model_source']=selected_model
                _log_provider_call(provider, selected_model, kwargs, 'succeeded',
                    latency_ms=(time.monotonic()-started_at)*1000)
                return result
            except ConfigurationError as exc:
                safe_error = redact_sensitive_text(str(exc), provider.get("api_key"), provider.get("base_url"))
                last_error = safe_error
                _log_provider_call(provider, requested_model, kwargs, 'failed',
                    error_class='configuration', error_message=safe_error,
                    latency_ms=(time.monotonic()-started_at)*1000)
                break
            except (RuntimeError, OpenAIError) as exc:
                safe_error = redact_sensitive_text(str(exc), provider.get("api_key"), provider.get("base_url"))
                logger.warning('image response uncertain provider_id=%s error=%s',provider.get('id'),safe_error)
                _log_provider_call(provider, requested_model, kwargs, 'failed',
                    error_class='upstream', error_message=safe_error,
                    latency_ms=(time.monotonic()-started_at)*1000)
                raise RuntimeError('本次生图未取得完整结果，已停止自动重试；请核对渠道任务与扣费后再生成') from exc
    raise RuntimeError(last_error or "所有生图配置均调用失败")


def _log_provider_call(provider: dict[str, Any], model: str, call_kwargs: dict[str, Any],
                       outcome: str, *, error_class: str = '', error_message: str = '',
                       latency_ms: float = 0.0) -> None:
    """Record one image call attempt for the channel health page.

    ``record_provider_call`` already swallows its own errors, but this is called
    from inside an ``except`` block where a raise would replace the real upstream
    failure with a telemetry error, so the guarantee is enforced here too.
    """
    try:
        from huishi.provider_metrics import record_provider_call
        record_provider_call(
            provider_id=provider.get('id'),
            provider_name=str(provider.get('name') or ''),
            api_format=str(provider.get('api_format') or ''),
            media_type='image',
            model=model,
            task_id=call_kwargs.get('task_id'),
            outcome=outcome,
            error_class=error_class,
            error_message=error_message,
            latency_ms=latency_ms,
            attempt_index=0,
        )
    except Exception:
        logger.debug('provider call telemetry skipped', exc_info=True)


def legacy_prompt_provider_from_settings() -> dict[str, Any] | None:
    settings = get_app_settings("prompt_base_url", "prompt_api_key", "prompt_model")
    base_url = settings.get("prompt_base_url", "")
    api_key = settings.get("prompt_api_key", "")
    model = settings.get("prompt_model", "")
    if not base_url and not api_key and not model:
        return None
    return {
        "id": None,
        "provider_type": "prompt",
        "name": "Legacy Prompt Provider",
        "base_url": base_url,
        "api_key": api_key,
        "model": model,
        "priority": 9999,
        "enabled": 1,
    }


def prompt_provider_candidates() -> list[dict[str, Any]]:
    configured = list_enabled_providers("prompt")
    return configured


def optimize_prompt_with_failover(*, prompt: str, style: str) -> str:
    from huishi.model_lifecycle import upstream_model
    candidates = prompt_provider_candidates()
    if not candidates:
        raise ValueError("暂未启用 Prompt 优化")
    last_error: str = ""
    for provider in candidates:
        try:
            return optimize_prompt(
                prompt=prompt,
                style=style,
                api_key=str(provider.get("api_key") or ""),
                base_url=str(provider.get("base_url") or ""),
                model=upstream_model(provider),
                proxy_url=str(provider.get("proxy_url") or ""),
            )
        except (RuntimeError, OpenAIError, ValueError) as exc:
            safe_error = redact_sensitive_text(str(exc), provider.get("api_key"), provider.get("base_url"))
            last_error = safe_error
            logger.warning("prompt provider failed name=%s error=%s", provider.get("name"), safe_error)
            continue
    raise RuntimeError(last_error or "所有 Prompt 优化配置均调用失败")
