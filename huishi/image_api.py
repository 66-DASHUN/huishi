from __future__ import annotations

import base64
import binascii
import html
import mimetypes
import os
import re
import secrets
import time
from pathlib import Path
from typing import Any

from flask import current_app
from openai import OpenAI
from werkzeug.datastructures import FileStorage


SIZE_MATRIX = {
    "1:1": {"1K": "1024x1024", "2K": "2048x2048"},
    "16:9": {"1K": "1536x864", "2K": "2560x1440", "4K": "3840x2160"},
    "9:16": {"1K": "864x1536", "2K": "1440x2560", "4K": "2160x3840"},
    "3:2": {"1K": "1536x1024", "2K": "2160x1440"},
    "2:3": {"1K": "1024x1536", "2K": "1440x2160"},
    "4:3": {"1K": "1365x1024", "2K": "2048x1536"},
    "3:4": {"1K": "1024x1365", "2K": "1536x2048"},
}


def resolve_size(ratio: str, resolution: str) -> str:
    """Resolve a resolution label or WxH string to a concrete size string."""
    # If resolution is already a WxH string (e.g. "2560x1440"), use it directly
    if re.match(r"^\d+x\d+$", resolution):
        return resolution
    ratio_sizes = SIZE_MATRIX.get(ratio) or SIZE_MATRIX["16:9"]
    if resolution in ratio_sizes:
        return ratio_sizes[resolution]
    if "2K" in ratio_sizes:
        return ratio_sizes["2K"]
    if "1K" in ratio_sizes:
        return ratio_sizes["1K"]
    return next(iter(ratio_sizes.values()))


def supports_size(ratio: str, resolution: str) -> bool:
    """Check if a ratio+resolution combination is supported."""
    # WxH strings are always valid (custom dimensions)
    if re.match(r"^\d+x\d+$", resolution):
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


def save_binary_image(data: bytes, name_hint: str = "image.png") -> str:
    suffix = Path(name_hint).suffix or infer_extension_from_bytes(data)
    output_dir: Path = current_app.config["OUTPUT_DIR"]
    output_dir.mkdir(parents=True, exist_ok=True)
    candidate = output_dir / f"huishi_{secrets.token_urlsafe(12)}{suffix}"
    while candidate.exists():
        candidate = output_dir / f"huishi_{secrets.token_urlsafe(12)}{suffix}"
    candidate.write_bytes(data)
    return candidate.name


def images_from_payload(payload: dict[str, Any]) -> list[str]:
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
            filename = save_binary_image(decoded, f"image_{index}.png")
            image_paths.append(f"/static/uploads/{filename}")
            continue

        url = item.get("url")
        if isinstance(url, str) and url:
            image_paths.append(url)

    if image_paths:
        return image_paths
    raise RuntimeError("接口调用成功，但没有解析到图片结果")


def first_image_from_payload(payload: dict[str, Any]) -> str:
    return images_from_payload(payload)[0]


def placeholder_image(*, prompt: str, ratio: str, resolution: str) -> dict[str, object]:
    started = time.monotonic()
    size = resolve_size(ratio, resolution)
    output_dir: Path = current_app.config["OUTPUT_DIR"]
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_prompt = html.escape(prompt[:18])
    placeholder = output_dir / "demo-generated.svg"
    placeholder.write_text(
        f"""<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024">
<rect width="1024" height="1024" fill="#050708"/>
<path d="M80 700 C280 520 520 830 944 320" stroke="#8ee7ff" stroke-width="8" fill="none"/>
<text x="80" y="450" fill="#ffffff" font-size="86" font-family="sans-serif">绘世</text>
<text x="80" y="540" fill="#8ee7ff" font-size="34" font-family="sans-serif">{safe_prompt}</text>
</svg>""",
        encoding="utf-8",
    )
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
) -> dict[str, object]:
    if current_app.config.get("TESTING") and os.environ.get("USE_PLACEHOLDER_IMAGES") == "1":
        return placeholder_image(prompt=prompt, ratio=ratio, resolution=resolution)

    started = time.monotonic()
    key = api_key or current_app.config.get("DEFAULT_API_KEY", "")
    url = base_url or current_app.config.get("DEFAULT_BASE_URL", "")
    if not key:
        raise ValueError("缺少 API Key，请先到设置页保存 API Key，或在服务器环境变量 API_KEY 中配置")
    if not url:
        raise ValueError("缺少接口地址，请先到设置页保存 Base URL，或在服务器环境变量 BASE_URL 中配置")

    size = resolve_size(ratio, resolution)
    request_kwargs: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "n": count,
        "size": size,
        "quality": quality,
        "output_format": output_format,
        "response_format": "b64_json",
    }
    client = OpenAI(api_key=key, base_url=url)

    references = reference_images or []
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
        payload = response.to_dict()
        image_paths = images_from_payload(payload)
        return {
            "image_path": image_paths[0],
            "image_paths": image_paths,
            "actual_size": size,
            "model_source": model,
            "elapsed_seconds": time.monotonic() - started,
        }

    response = client.images.generate(**request_kwargs)
    payload = response.to_dict()
    image_paths = images_from_payload(payload)
    return {
        "image_path": image_paths[0],
        "image_paths": image_paths,
        "actual_size": size,
        "model_source": model,
        "elapsed_seconds": time.monotonic() - started,
    }
