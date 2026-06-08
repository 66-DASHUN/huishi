"""Input validation and file validation utilities for huishi."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from werkzeug.datastructures import FileStorage

logger = logging.getLogger(__name__)

# File upload constraints
ALLOWED_REFERENCE_MIMETYPES = {"image/png", "image/jpeg", "image/webp"}
ALLOWED_REFERENCE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
MAX_UPLOAD_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB


class ValidationError(ValueError):
    """Raised when validation fails."""

    pass


def validate_reference_image_file(file_storage: FileStorage) -> None:
    """
    Validate a reference image file for upload.

    Args:
        file_storage: Werkzeug FileStorage object

    Raises:
        ValidationError: If file is invalid (type, size, etc.)
    """
    if not file_storage.filename:
        raise ValidationError("File has no name")

    # Check MIME type
    if file_storage.mimetype not in ALLOWED_REFERENCE_MIMETYPES:
        raise ValidationError(
            f"Invalid file type: {file_storage.mimetype}. "
            f"Allowed types: {', '.join(sorted(ALLOWED_REFERENCE_MIMETYPES))}"
        )

    # Check file extension
    suffix = Path(file_storage.filename).suffix.lower()
    if suffix not in ALLOWED_REFERENCE_SUFFIXES:
        raise ValidationError(
            f"Invalid file extension: {suffix}. "
            f"Allowed: {', '.join(sorted(ALLOWED_REFERENCE_SUFFIXES))}"
        )

    # Check file size
    file_storage.stream.seek(0, 2)  # Seek to end
    file_size = file_storage.stream.tell()
    file_storage.stream.seek(0)  # Reset to start

    if file_size > MAX_UPLOAD_SIZE_BYTES:
        max_mb = MAX_UPLOAD_SIZE_BYTES / (1024 * 1024)
        raise ValidationError(
            f"File too large: {file_size / (1024 * 1024):.1f} MB. "
            f"Maximum size: {max_mb:.0f} MB"
        )

    if file_size == 0:
        raise ValidationError("File is empty")

    logger.debug(
        "Reference image validation passed",
        extra={
            "filename": file_storage.filename,
            "mimetype": file_storage.mimetype,
            "size_bytes": file_size,
        },
    )


def validate_generation_count(raw_count: str | None, max_count: int = 8) -> int:
    """
    Validate and parse generation count.

    Args:
        raw_count: String representation of count
        max_count: Maximum allowed count (default 8)

    Returns:
        Validated integer count

    Raises:
        ValidationError: If count is invalid
    """
    try:
        count = int(raw_count or "1")
    except (TypeError, ValueError) as exc:
        raise ValidationError("生成数量必须是有效数字") from exc

    if count < 1:
        raise ValidationError("生成数量必须大于 0")

    if count > max_count:
        raise ValidationError(f"单次生成最多支持 {max_count} 张图片")

    return count


def validate_resolution_format(resolution: str) -> None:
    """
    Validate resolution string format (WxH).

    Args:
        resolution: Resolution string like "2560x1440"

    Raises:
        ValidationError: If format is invalid
    """
    if not re.match(r"^\d+x\d+$", resolution):
        raise ValidationError(f"Invalid resolution format: {resolution}. Expected: WIDTHxHEIGHT")


def validate_api_keys(api_key: str, base_url: str) -> None:
    """
    Validate API configuration.

    Args:
        api_key: API key string
        base_url: API base URL

    Raises:
        ValidationError: If keys are missing
    """
    if not api_key:
        raise ValidationError(
            "缺少 API Key，请先到设置页保存 API Key，或在服务器环境变量 API_KEY 中配置"
        )
    if not base_url:
        raise ValidationError(
            "缺少接口地址，请先到设置页保存 Base URL，或在服务器环境变量 BASE_URL 中配置"
        )


def validate_http_url(raw_url: str) -> None:
    """
    Validate HTTP/HTTPS URL format.

    Args:
        raw_url: URL string

    Raises:
        ValidationError: If URL is not valid HTTP/HTTPS
    """
    from urllib.parse import urlsplit

    parsed = urlsplit(raw_url)
    if not (parsed.scheme in {"http", "https"} and parsed.netloc):
        raise ValidationError(f"URL must start with http:// or https://: {raw_url}")


def sanitize_filename(filename: str | None) -> str:
    """
    Sanitize filename to prevent directory traversal and other issues.

    Args:
        filename: Original filename

    Returns:
        Sanitized filename safe for filesystem storage
    """
    if not filename:
        return "file"

    from werkzeug.utils import secure_filename

    return secure_filename(filename) or "file"
