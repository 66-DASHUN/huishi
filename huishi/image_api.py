from __future__ import annotations

import base64
import binascii
import html
import io
import logging
import mimetypes
import os
import re
import secrets
import time
import ipaddress
import requests
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from pathlib import Path
from typing import Any

from flask import current_app
from openai import OpenAI
from werkzeug.datastructures import FileStorage

from huishi.upload_storage import get_upload_storage
from huishi.network import openai_http_client, request_proxy_kwargs
from huishi.secrets import redact_sensitive_text, redact_url


logger = logging.getLogger(__name__)

SIZE_MATRIX = {
    "21:9": {"1K": "1680x720", "2K": "3360x1440"},
    "1:1": {"1K": "1024x1024", "2K": "2048x2048"},
    "16:9": {"1K": "1536x864", "2K": "2560x1440", "4K": "3840x2160"},
    "9:16": {"1K": "864x1536", "2K": "1440x2560", "4K": "2160x3840"},
    "3:2": {"1K": "1536x1024", "2K": "2160x1440"},
    "2:3": {"1K": "1024x1536", "2K": "1440x2160"},
    "4:3": {"1K": "1365x1024", "2K": "2048x1536"},
    "3:4": {"1K": "1024x1365", "2K": "1536x2048"},
}

CUSTOM_SIZE_PATTERN = re.compile(r"^\d+x\d+$")
GPT_IMAGE_2_MAX_EDGE = 3840
GPT_IMAGE_2_MIN_ASPECT_RATIO = 1 / 3
GPT_IMAGE_2_MAX_ASPECT_RATIO = 3
GPT_IMAGE_2_MIN_PIXELS = 655_360
GPT_IMAGE_2_MAX_PIXELS = 8_294_400
GPT_IMAGE_2_EXPERIMENTAL_PIXELS = 2560 * 1440

PLACEHOLDER_API_KEYS = {"sk-test", "test", "demo", "changeme", "your-api-key", "your_api_key"}


class ConfigurationError(ValueError):
    """Raised when local image generation configuration is missing or invalid."""


def is_placeholder_api_key(api_key: str) -> bool:
    normalized = (api_key or "").strip().lower()
    return normalized in PLACEHOLDER_API_KEYS or normalized.startswith("sk-test-")


def resolve_size(ratio: str, resolution: str) -> str:
    """Resolve a resolution label or WxH string to a concrete size string."""
    # Concrete WxH values are accepted only after validate_image_size has validated them.
    if CUSTOM_SIZE_PATTERN.match(resolution):
        return resolution
    ratio_sizes = SIZE_MATRIX.get(ratio) or SIZE_MATRIX["16:9"]
    if resolution in ratio_sizes:
        return ratio_sizes[resolution]
    if "2K" in ratio_sizes:
        return ratio_sizes["2K"]
    if "1K" in ratio_sizes:
        return ratio_sizes["1K"]
    return next(iter(ratio_sizes.values()))


def supported_size_values() -> set[str]:
    """Return every concrete WxH size supported by the image2 size matrix."""
    return {size for ratio_sizes in SIZE_MATRIX.values() for size in ratio_sizes.values()}


def validate_image_size(size: str) -> None:
    """Validate custom gpt-image-2 output dimensions against official model limits."""
    match = CUSTOM_SIZE_PATTERN.fullmatch(size or "")
    if match is None:
        raise ValueError("自定义尺寸必须使用 宽x高 格式")

    width, height = (int(part) for part in size.split("x", 1))
    if width <= 0 or height <= 0:
        raise ValueError("自定义尺寸必须大于 0")
    if width > GPT_IMAGE_2_MAX_EDGE or height > GPT_IMAGE_2_MAX_EDGE:
        raise ValueError("自定义尺寸单边最大 3840px")
    if width % 16 != 0 or height % 16 != 0:
        raise ValueError("自定义尺寸宽高都必须是 16 的倍数")

    aspect_ratio = width / height
    if aspect_ratio < GPT_IMAGE_2_MIN_ASPECT_RATIO or aspect_ratio > GPT_IMAGE_2_MAX_ASPECT_RATIO:
        raise ValueError("自定义尺寸宽高比必须在 1:3 到 3:1 之间")

    pixels = width * height
    if pixels < GPT_IMAGE_2_MIN_PIXELS:
        raise ValueError("自定义尺寸总像素不能低于 655,360")
    if pixels > GPT_IMAGE_2_MAX_PIXELS:
        raise ValueError("自定义尺寸总像素不能超过 8,294,400")


def nearest_legal_image_size(width: int, height: int) -> str:
    """Return the nearest legal gpt-image-2 WxH size by smallest dimension change."""
    target_width = max(1, int(width or 0))
    target_height = max(1, int(height or 0))
    target_pixels = target_width * target_height
    target_is_landscape = target_width >= target_height
    best_size = ""
    best_score: tuple[int, int, int, int] | None = None

    for candidate_width in range(16, GPT_IMAGE_2_MAX_EDGE + 1, 16):
        for candidate_height in range(16, GPT_IMAGE_2_MAX_EDGE + 1, 16):
            aspect_ratio = candidate_width / candidate_height
            if aspect_ratio < GPT_IMAGE_2_MIN_ASPECT_RATIO or aspect_ratio > GPT_IMAGE_2_MAX_ASPECT_RATIO:
                continue
            pixels = candidate_width * candidate_height
            if pixels < GPT_IMAGE_2_MIN_PIXELS or pixels > GPT_IMAGE_2_MAX_PIXELS:
                continue
            orientation_penalty = 0 if (candidate_width >= candidate_height) == target_is_landscape else 1
            score = (
                abs(candidate_width - target_width) + abs(candidate_height - target_height),
                abs(pixels - target_pixels),
                orientation_penalty,
                abs(candidate_width - target_width),
            )
            if best_score is None or score < best_score:
                best_score = score
                best_size = f"{candidate_width}x{candidate_height}"

    return best_size


def nearest_legal_image_size_for_ratio(ratio: str, width: int, height: int) -> str:
    """Return the nearest legal WxH size that preserves a fixed ratio."""
    if ratio not in SIZE_MATRIX:
        raise ValueError("不支持的画面比例")
    try:
        ratio_width_raw, ratio_height_raw = ratio.split(":", 1)
        ratio_width = int(ratio_width_raw)
        ratio_height = int(ratio_height_raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("不支持的画面比例") from exc
    if ratio_width <= 0 or ratio_height <= 0:
        raise ValueError("不支持的画面比例")

    target_width = max(1, int(width or 0))
    target_height = max(1, int(height or 0))
    target_pixels = target_width * target_height
    max_unit = GPT_IMAGE_2_MAX_EDGE // max(ratio_width, ratio_height)
    best_size = ""
    best_score: tuple[int, int, int] | None = None

    for unit in range(1, max_unit + 1):
        candidate_width = ratio_width * unit
        candidate_height = ratio_height * unit
        if candidate_width % 16 != 0 or candidate_height % 16 != 0:
            continue
        pixels = candidate_width * candidate_height
        if pixels < GPT_IMAGE_2_MIN_PIXELS or pixels > GPT_IMAGE_2_MAX_PIXELS:
            continue
        score = (
            abs(candidate_width - target_width) + abs(candidate_height - target_height),
            abs(pixels - target_pixels),
            abs(candidate_width - target_width),
        )
        if best_score is None or score < best_score:
            best_score = score
            best_size = f"{candidate_width}x{candidate_height}"

    if best_size:
        return best_size

    ratio_sizes = SIZE_MATRIX.get(ratio) or {}
    if ratio_sizes:
        target = f"{target_width}x{target_height}"
        return min(ratio_sizes.values(), key=lambda size: (
            abs(int(size.split("x", 1)[0]) - target_width) + abs(int(size.split("x", 1)[1]) - target_height),
            size != target,
        ))
    return nearest_legal_image_size(target_width, target_height)


def supports_size(ratio: str, resolution: str) -> bool:
    """Check if a ratio+resolution combination is supported."""
    if CUSTOM_SIZE_PATTERN.match(resolution):
        try:
            validate_image_size(resolution)
        except ValueError:
            return False
        return True
    return resolution in (SIZE_MATRIX.get(ratio) or {})


def infer_extension_from_bytes(data: bytes) -> str:
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith(b"RIFF") and b"WEBP" in data[:16]:
        return ".webp"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    return ".png"


def optimize_image_bytes(
    data: bytes,
    suffix: str,
    *,
    enabled: bool = True,
    jpeg_quality: int = 88,
    webp_quality: int = 86,
    png_compress_level: int = 9,
) -> bytes:
    if not enabled:
        return data
    suffix = suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        return data
    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError:
        logger.warning("Pillow is not installed; generated image optimization skipped")
        return data

    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            output = io.BytesIO()
            if suffix in {".jpg", ".jpeg"}:
                if image.mode not in {"RGB", "L"}:
                    image = image.convert("RGB")
                image.save(output, format="JPEG", optimize=True, progressive=True, quality=max(1, min(95, int(jpeg_quality))))
            elif suffix == ".webp":
                image.save(output, format="WEBP", method=6, quality=max(1, min(100, int(webp_quality))))
            else:
                image.save(output, format="PNG", optimize=True, compress_level=max(0, min(9, int(png_compress_level))))
    except (OSError, ValueError, UnidentifiedImageError) as exc:
        logger.warning("generated image optimization skipped: %s", exc)
        return data

    optimized = output.getvalue()
    return optimized if optimized and len(optimized) < len(data) else data


def fit_image_bytes_to_size(data: bytes, suffix: str, expected_size: str = "") -> bytes:
    match = CUSTOM_SIZE_PATTERN.fullmatch(expected_size or "")
    if match is None:
        return data
    target_size = tuple(int(part) for part in expected_size.split("x", 1))
    if target_size[0] <= 0 or target_size[1] <= 0:
        return data
    try:
        from PIL import Image, ImageOps, UnidentifiedImageError
    except ImportError:
        logger.warning("Pillow is not installed; generated image size correction skipped")
        return data

    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            if image.size == target_size:
                return data
            original_size = image.size
            fitted = ImageOps.fit(image, target_size, method=Image.Resampling.LANCZOS)
            output = io.BytesIO()
            normalized_suffix = suffix.lower()
            if normalized_suffix in {".jpg", ".jpeg"}:
                if fitted.mode not in {"RGB", "L"}:
                    fitted = fitted.convert("RGB")
                fitted.save(output, format="JPEG", quality=95)
            elif normalized_suffix == ".webp":
                fitted.save(output, format="WEBP", quality=95)
            else:
                fitted.save(output, format="PNG", compress_level=6)
    except (OSError, ValueError, UnidentifiedImageError) as exc:
        logger.warning("generated image size correction skipped: %s", exc)
        return data

    corrected = output.getvalue()
    if corrected:
        logger.info("generated image size corrected from %sx%s to %s", original_size[0], original_size[1], expected_size)
        return corrected
    return data


def save_binary_image(data: bytes, name_hint: str = "image.png", *, expected_size: str = "") -> str:
    suffix = Path(name_hint).suffix or infer_extension_from_bytes(data)
    storage = get_upload_storage()
    filename = f"huishi_{secrets.token_urlsafe(12)}{suffix}"
    while storage.exists(filename):
        filename = f"huishi_{secrets.token_urlsafe(12)}{suffix}"
    fitted_data = fit_image_bytes_to_size(data, suffix, expected_size)
    optimized_data = optimize_image_bytes(
        fitted_data,
        suffix,
        enabled=bool(current_app.config.get("IMAGE_OPTIMIZE_ENABLED", True)),
        jpeg_quality=int(current_app.config.get("IMAGE_JPEG_QUALITY", 88)),
        webp_quality=int(current_app.config.get("IMAGE_WEBP_QUALITY", 86)),
        png_compress_level=int(current_app.config.get("IMAGE_PNG_COMPRESS_LEVEL", 9)),
    )
    storage.save_bytes(
        filename,
        optimized_data,
        mimetypes.guess_type(filename)[0] or "application/octet-stream",
    )
    return filename


def images_from_payload(payload: dict[str, Any], *, expected_size: str = "", proxy_url: str = "") -> list[str]:
    # 有些网关在路径写错时返回 HTTP 200 + 一个 HTML 落地页（或纯字符串），
    # 而不是 JSON。不在这里拦住的话，下面 payload.get() 会抛 AttributeError，
    # 而 AttributeError 不在 failover 捕获的异常里——结果既不切换下一个渠道、
    # 也不写渠道埋点，用户只看到"生成结果保存失败"。
    # 2026-10-06 渠道 ai.junze.me 即如此（base_url 缺 /v1）。
    if not isinstance(payload, dict):
        text = payload if isinstance(payload, str) else repr(payload)
        if looks_like_html_response(text):
            raise RuntimeError(
                "生图接口返回了网页而不是图片数据，请检查 Base URL 是否指向 OpenAI 兼容图片接口"
                "（常见原因：缺少 /v1 路径段）"
            )
        raise RuntimeError(
            f"生图接口返回了不支持的数据格式（{type(payload).__name__}），期望 JSON 对象"
        )
    image_paths = []
    for index, item in enumerate(payload.get("data", []), start=1):
        if not isinstance(item, dict):
            continue
        b64_value = item.get("b64_json")
        if isinstance(b64_value, str) and b64_value:
            try:
                decoded = base64.b64decode(b64_value, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise RuntimeError("接口返回了无效的 base64 图片") from exc
            filename = save_binary_image(decoded, f"image_{index}.png", expected_size=expected_size)
            image_paths.append(f"/static/uploads/{filename}")
            continue

        url = item.get("url")
        if isinstance(url, str) and url:
            parsed = urlsplit(url)
            hostname = parsed.hostname or ""
            if parsed.scheme not in {"http", "https"} or not hostname:
                raise RuntimeError("接口返回了不安全的图片地址")
            try:
                address = ipaddress.ip_address(hostname)
                if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved:
                    raise RuntimeError("接口返回了不安全的图片地址")
            except ValueError:
                pass
            try:
                headers = {"User-Agent": "HuishiImageFetcher/1.0", "Accept": "image/*"}
                if proxy_url:
                    response = requests.get(url, headers=headers, timeout=20, **request_proxy_kwargs(proxy_url))
                    if response.status_code < 200 or response.status_code >= 300:
                        raise RuntimeError(f"图片下载返回 HTTP {response.status_code}")
                    content_type = str(response.headers.get("Content-Type") or "").split(";", 1)[0].lower()
                    if not content_type.startswith("image/"):
                        raise RuntimeError("接口返回的图片类型无效")
                    data = response.content[: 20 * 1024 * 1024 + 1]
                else:
                    request = Request(url, headers=headers)
                    with urlopen(request, timeout=20) as response:
                        content_type = str(response.headers.get("Content-Type") or "").split(";", 1)[0].lower()
                        if not content_type.startswith("image/"):
                            raise RuntimeError("接口返回的图片类型无效")
                        data = response.read(20 * 1024 * 1024 + 1)
            except RuntimeError:
                raise
            except Exception as exc:
                raise RuntimeError("接口返回的图片无法下载") from exc
            if len(data) > 20 * 1024 * 1024:
                raise RuntimeError("接口返回的图片过大")
            filename = save_binary_image(data, "remote_image.png", expected_size=expected_size)
            image_paths.append(f"/static/uploads/{filename}")

    if image_paths:
        return image_paths
    raise RuntimeError("接口调用成功，但没有解析到图片结果")


def looks_like_html_response(content: str) -> bool:
    text = (content or "").lstrip().lower()
    return (
        text.startswith("<!doctype html")
        or text.startswith("<html")
        or "<body" in text
        or "<head" in text
        or "just a moment" in text
        or "enable javascript and cookies" in text
    )


def normalize_generation_error(exc: Exception) -> RuntimeError | None:
    message = str(exc).strip()
    if message and looks_like_html_response(message):
        return RuntimeError(
            "生图接口返回了网页校验页，请检查 Base URL 是否指向 OpenAI 兼容图片接口，或确认服务端未被 Cloudflare 拦截"
        )
    return None


def provider_json_url(base_url: str, path: str) -> str:
    normalized = str(base_url or "").strip().rstrip("/")
    if normalized.lower().endswith(path.lower()):
        return normalized
    if path.startswith("/v1/") and normalized.lower().endswith("/v1"):
        return f"{normalized}{path[3:]}"
    if path.startswith("/v1beta/") and normalized.lower().endswith("/v1beta"):
        return f"{normalized}{path[7:]}"
    return f"{normalized}{path}"


def provider_endpoint_path(api_format: str, mode: str = "text", model: str = "") -> str:
    from huishi.providers import provider_endpoint_path as _provider_endpoint_path
    return _provider_endpoint_path(api_format, mode, model)


def post_provider_json(url: str, *, headers: dict[str, str], payload: dict[str, Any], timeout: float, proxy_url: str = "") -> dict[str, Any]:
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=timeout, **request_proxy_kwargs(proxy_url))
    except requests.RequestException as exc:
        raise RuntimeError("生图接口连接失败") from exc
    if response.status_code < 200 or response.status_code >= 300:
        detail = str(response.text or "").strip()
        if looks_like_html_response(detail):
            raise RuntimeError("生图接口返回了网页校验页，请检查 Base URL 或服务端访问限制")
        try:
            body = response.json()
        except ValueError:
            body = {}
        message = str((body.get("error") or {}).get("message") or body.get("message") or detail or "请求失败")
        header_secrets = [value.split(" ", 1)[1] for key, value in headers.items() if key.lower() == "authorization" and " " in value]
        header_secrets.extend(value for key, value in headers.items() if key.lower() in {"x-goog-api-key", "api-key"})
        message = redact_sensitive_text(message, *header_secrets)
        raise RuntimeError(f"生图接口返回 HTTP {response.status_code}: {message}")
    try:
        body = response.json()
    except ValueError as exc:
        raise RuntimeError("生图接口没有返回 JSON") from exc
    if not isinstance(body, dict):
        raise RuntimeError("生图接口返回了不支持的数据格式")
    return body


def gemini_payload_as_image_data(payload: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    images: list[dict[str, str]] = []

    def append_image(item: object) -> None:
        if not isinstance(item, dict):
            return
        data = item.get("data")
        if isinstance(data, str) and data:
            images.append({"b64_json": data})

    append_image(payload.get("output_image"))
    for step in payload.get("steps") or []:
        if not isinstance(step, dict):
            continue
        for block in step.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "image":
                append_image(block)
    if not images:
        raise RuntimeError("Gemini 接口调用成功，但没有返回图片")
    return {"data": images}


def gemini_generate_content_url(base_url: str, model: str) -> str:
    """Legacy Gemini REST endpoint: /v1beta/models/<model>:generateContent.

    The newer ``/v1beta/interactions`` path is not offered by every gateway
    (New API style gateways only expose the classic models/* path), so the
    caller falls back to this one when interactions returns 404.
    """
    root = str(base_url or "").strip().rstrip("/")
    if root.lower().endswith("/v1beta"):
        root = root[: -len("/v1beta")]
    return f"{root}/v1beta/models/{str(model or '').strip()}:generateContent"


def gemini_generate_content_payload(*, prompt: str, ratio: str, resolution: str,
                                    output_format: str, reference_images: list[FileStorage]) -> dict[str, Any]:
    """Build a classic generateContent body (contents[].parts[])."""
    parts: list[dict[str, Any]] = [{"text": prompt}]
    for item, data_url in zip(reference_images, reference_image_data_urls(reference_images)):
        _, encoded = data_url.split(",", 1)
        parts.append({
            "inlineData": {
                "mimeType": item.mimetype or "application/octet-stream",
                "data": encoded,
            }
        })
    body: dict[str, Any] = {"contents": [{"role": "user", "parts": parts}]}
    # 仅传比例；像素档位由上游按模型默认决定（与新版 interactions 的
    # response_format.image_size 不同，旧式端点没有等价字段）。
    if ratio:
        body["generationConfig"] = {"imageConfig": {"aspectRatio": ratio}}
    return body


def gemini_candidates_as_image_data(payload: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    """Normalize a classic generateContent reply into the images_from_payload shape."""
    images: list[dict[str, str]] = []
    for candidate in payload.get("candidates") or []:
        if not isinstance(candidate, dict):
            continue
        content = candidate.get("content") if isinstance(candidate.get("content"), dict) else {}
        for block in content.get("parts") or []:
            if not isinstance(block, dict):
                continue
            inline = block.get("inlineData") or block.get("inline_data")
            if not isinstance(inline, dict):
                continue
            data = inline.get("data")
            if isinstance(data, str) and data:
                images.append({"b64_json": data})
    if not images:
        raise RuntimeError("Gemini 接口调用成功，但没有返回图片")
    return {"data": images}


def reference_image_data_urls(reference_images: list[FileStorage]) -> list[str]:
    result: list[str] = []
    for item in reference_images:
        mime_type = item.mimetype or "application/octet-stream"
        result.append(f"data:{mime_type};base64,{base64.b64encode(item.read()).decode('ascii')}")
    return result


def image_resolution_tier(ratio: str, resolution: str) -> str:
    normalized = str(resolution or "1K").strip().upper()
    if normalized in {"1K", "2K", "4K"}:
        return normalized
    for tier, size in (SIZE_MATRIX.get(ratio) or {}).items():
        if size.upper() == normalized:
            return tier
    if CUSTOM_SIZE_PATTERN.fullmatch(normalized.lower()):
        width, height = (int(part) for part in normalized.lower().split("x", 1))
        longest_edge = max(width, height)
        if longest_edge <= 1560:
            return "1K"
        if longest_edge <= 2440:
            return "2K"
        return "4K"
    return "1K"


def grok_extra_body(*, ratio: str, resolution: str, quality: str) -> dict[str, str]:
    body = {"aspect_ratio": ratio or "auto"}
    resolution_tier = image_resolution_tier(ratio, resolution)
    from huishi.providers import provider_supported_resolutions
    if resolution_tier not in provider_supported_resolutions("grok"):
        raise ConfigurationError("Grok 官方生图仅支持 1K 或 2K")
    body["resolution"] = "2k" if resolution_tier == "2K" else "1k"
    normalized_quality = str(quality or "").strip().lower()
    if normalized_quality in {"low", "medium"}:
        body["quality"] = normalized_quality
    elif normalized_quality == "high":
        body["quality"] = "medium"
    return body


def generate_gemini_images(
    *, prompt: str, ratio: str, resolution: str, count: int, api_key: str, base_url: str,
    model: str, output_format: str, reference_images: list[FileStorage], timeout: float, api_format: str = "gemini", proxy_url: str = "",
) -> list[str]:
    image_size = image_resolution_tier(ratio, resolution)
    input_value: object = prompt
    if reference_images:
        input_value = [{"type": "text", "text": prompt}]
        for item, data_url in zip(reference_images, reference_image_data_urls(reference_images)):
            _, encoded = data_url.split(",", 1)
            input_value.append({"type": "image", "data": encoded, "mime_type": item.mimetype or "application/octet-stream"})
    image_paths: list[str] = []
    for _ in range(count):
        payload = {
            "model": model,
            "input": input_value,
            "response_format": {
                "type": "image",
                "mime_type": f"image/{output_format}",
                "aspect_ratio": ratio,
                "image_size": image_size,
            },
            "store": False,
        }
        headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}
        try:
            response_payload = post_provider_json(
                provider_json_url(base_url, provider_endpoint_path(api_format, "text", model)),
                headers=headers,
                payload=payload,
                timeout=timeout,
                proxy_url=proxy_url,
            )
        except RuntimeError as exc:
            # 部分网关（New API 系）不提供 /v1beta/interactions，只暴露经典
            # /v1beta/models/<model>:generateContent。此时按旧式协议重试一次，
            # 而不是让整个渠道不可用。
            if "404" not in str(exc):
                raise
            legacy_payload = gemini_generate_content_payload(
                prompt=prompt, ratio=ratio, resolution=resolution,
                output_format=output_format, reference_images=reference_images,
            )
            legacy = post_provider_json(
                gemini_generate_content_url(base_url, model),
                headers=headers,
                payload=legacy_payload,
                timeout=timeout,
                proxy_url=proxy_url,
            )
            image_paths.extend(images_from_payload(gemini_candidates_as_image_data(legacy), proxy_url=proxy_url))
            continue
        image_paths.extend(images_from_payload(gemini_payload_as_image_data(response_payload), proxy_url=proxy_url))
    return image_paths[:count]


def generate_grok_reference_images(
    *, prompt: str, ratio: str, resolution: str, count: int, quality: str, api_key: str,
    base_url: str, model: str, reference_images: list[FileStorage], timeout: float, proxy_url: str = "",
) -> list[str]:
    data_urls = reference_image_data_urls(reference_images)
    image_value = [{"type": "image_url", "url": value} for value in data_urls]
    image_paths: list[str] = []
    for _ in range(count):
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "response_format": "b64_json",
            **grok_extra_body(ratio=ratio, resolution=resolution, quality=quality),
        }
        if len(image_value) == 1:
            payload["image"] = image_value[0]
        else:
            payload["images"] = image_value
        response_payload = post_provider_json(
            provider_json_url(base_url, provider_endpoint_path("grok", "reference")),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
            payload=payload,
            timeout=timeout,
            proxy_url=proxy_url,
        )
        image_paths.extend(images_from_payload(response_payload, proxy_url=proxy_url))
    return image_paths[:count]


def first_image_from_payload(payload: dict[str, Any]) -> str:
    return images_from_payload(payload)[0]


def placeholder_image(*, prompt: str, ratio: str, resolution: str) -> dict[str, object]:
    started = time.monotonic()
    size = resolve_size(ratio, resolution)
    safe_prompt = html.escape(prompt[:18])
    content = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024">
<rect width="1024" height="1024" fill="#050708"/>
<path d="M80 700 C280 520 520 830 944 320" stroke="#8ee7ff" stroke-width="8" fill="none"/>
<text x="80" y="450" fill="#ffffff" font-size="86" font-family="sans-serif">绘世</text>
<text x="80" y="540" fill="#8ee7ff" font-size="34" font-family="sans-serif">{safe_prompt}</text>
</svg>"""
    get_upload_storage().save_bytes("demo-generated.svg", content.encode("utf-8"), "image/svg+xml")
    return {
        "image_path": "/static/uploads/demo-generated.svg",
        "image_paths": ["/static/uploads/demo-generated.svg"],
        "actual_size": size,
        "model_source": "local-placeholder",
        "elapsed_seconds": time.monotonic() - started,
    }


def generate_image(
    *,
    prompt: str,
    mode: str,
    resolution: str,
    count: int,
    ratio: str = "16:9",
    api_key: str = "",
    base_url: str = "",
    model: str = "gpt-image-2",
    quality: str = "auto",
    output_format: str = "png",
    reference_images: list[FileStorage] | None = None,
    api_format: str = "openai",
    proxy_url: str = "",
) -> dict[str, object]:
    if current_app.config.get("TESTING") and os.environ.get("USE_PLACEHOLDER_IMAGES") == "1":
        return placeholder_image(prompt=prompt, ratio=ratio, resolution=resolution)

    started = time.monotonic()
    key = api_key or current_app.config.get("DEFAULT_API_KEY", "")
    url = base_url or current_app.config.get("DEFAULT_BASE_URL", "")
    if not key:
        raise ConfigurationError("缺少 API Key，请先到设置页保存 API Key，或在服务器环境变量 API_KEY 中配置")
    if is_placeholder_api_key(key):
        raise ConfigurationError("当前 API Key 是测试占位值，请在设置页保存真实 API Key 后再生图")
    if not url:
        raise ConfigurationError("缺少接口地址，请先到设置页保存 Base URL，或在服务器环境变量 BASE_URL 中配置")

    size = resolve_size(ratio, resolution)
    normalized_api_format = str(api_format or "openai").strip().lower()
    if normalized_api_format not in {"openai", "gemini", "banana", "grok", "jiasuapi"}:
        raise ConfigurationError("不支持的生图调用协议")
    timeout = float(current_app.config.get("IMAGE_API_TIMEOUT", 1200))
    references = reference_images or []
    if normalized_api_format == "jiasuapi":
        from huishi import jiasuapi
        image_paths = jiasuapi.generate_images(
            provider={"base_url": url, "api_key": key, "proxy_url": proxy_url, "settings": {"poll_interval": 3}},
            prompt=prompt,
            model=model,
            ratio=ratio,
            resolution=image_resolution_tier(ratio, resolution),
            count=count,
            quality=quality,
            reference_images=references,
            timeout=timeout,
        )
        return {
            "image_path": image_paths[0],
            "image_paths": image_paths,
            "actual_size": resolution,
            "model_source": model,
            "elapsed_seconds": time.monotonic() - started,
        }
    if normalized_api_format in {"gemini", "banana"}:
        image_paths = generate_gemini_images(
            prompt=prompt,
            ratio=ratio,
            resolution=resolution,
            count=count,
            api_key=key,
            base_url=url,
            model=model,
            output_format=output_format,
            reference_images=references,
            timeout=timeout,
            api_format=normalized_api_format,
            proxy_url=proxy_url,
        )
        return {
            "image_path": image_paths[0],
            "image_paths": image_paths,
            "actual_size": resolution,
            "model_source": model,
            "elapsed_seconds": time.monotonic() - started,
        }
    if normalized_api_format == "grok" and mode == "reference":
        if not references:
            raise ValueError("参考图编辑需要先上传参考图")
        image_paths = generate_grok_reference_images(
            prompt=prompt,
            ratio=ratio,
            resolution=resolution,
            count=count,
            quality=quality,
            api_key=key,
            base_url=url,
            model=model,
            reference_images=references,
            timeout=timeout,
            proxy_url=proxy_url,
        )
        return {
            "image_path": image_paths[0],
            "image_paths": image_paths,
            "actual_size": resolution,
            "model_source": model,
            "elapsed_seconds": time.monotonic() - started,
        }
    request_kwargs: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "n": count,
        "response_format": "b64_json",
    }
    if normalized_api_format == "grok":
        request_kwargs["extra_body"] = grok_extra_body(ratio=ratio, resolution=resolution, quality=quality)
    else:
        request_kwargs["size"] = size
        request_kwargs["quality"] = quality
    # A timed-out generation may already be billed. Never retry POST implicitly.
    max_retries = 0
    http_client = openai_http_client(proxy_url, timeout=timeout)
    client_kwargs: dict[str, Any] = {"api_key": key, "base_url": url, "timeout": timeout, "max_retries": max(0, max_retries)}
    if http_client is not None:
        client_kwargs["http_client"] = http_client
    client = OpenAI(**client_kwargs)
    logger.info(
        "image generation request started mode=%s ratio=%s resolution=%s size=%s count=%s base_url=%s timeout=%ss",
        mode,
        ratio,
        resolution,
        size,
        count,
        redact_url(url),
        timeout,
    )

    try:
        if mode == "reference":
            if not references:
                raise ValueError("参考图编辑需要先上传参考图")
            image_files = [
                (
                    item.filename or "reference.png",
                    item.read(),
                    item.mimetype or "application/octet-stream",
                )
                for item in references
            ]
            request_kwargs["image"] = image_files[0] if len(image_files) == 1 else image_files
            response = client.images.edit(**request_kwargs)
            payload = response.to_dict() if hasattr(response, "to_dict") else (response.model_dump() if hasattr(response, "model_dump") else response)
            image_paths = images_from_payload(payload, expected_size=size, proxy_url=proxy_url)
            logger.info("image generation request finished elapsed=%.2fs images=%s", time.monotonic() - started, len(image_paths))
            return {
                "image_path": image_paths[0],
                "image_paths": image_paths,
                "actual_size": size,
                "model_source": model,
                "elapsed_seconds": time.monotonic() - started,
            }

        if normalized_api_format == "openai":
            request_kwargs["output_format"] = output_format
        response = client.images.generate(**request_kwargs)
        payload = response.to_dict() if hasattr(response, "to_dict") else (response.model_dump() if hasattr(response, "model_dump") else response)
        image_paths = images_from_payload(payload, expected_size=size, proxy_url=proxy_url)
        logger.info("image generation request finished elapsed=%.2fs images=%s", time.monotonic() - started, len(image_paths))
        return {
            "image_path": image_paths[0],
            "image_paths": image_paths,
            "actual_size": size,
            "model_source": model,
            "elapsed_seconds": time.monotonic() - started,
        }
    except Exception as exc:
        friendly_exc = normalize_generation_error(exc)
        if friendly_exc is not None:
            logger.error("image generation request failed with html response elapsed=%.2fs", time.monotonic() - started)
            raise friendly_exc from exc
        logger.error("image generation request failed elapsed=%.2fs error=%s", time.monotonic() - started, redact_sensitive_text(str(exc), key, url))
        raise
    finally:
        if http_client is not None:
            http_client.close()
