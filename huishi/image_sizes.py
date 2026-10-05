"""Image resolution and size arithmetic.

These helpers translate between the three shapes a resolution takes in this
codebase and its pricing/routing layers:

* a preset label, e.g. ``"2K"``
* a concrete pixel size, e.g. ``"2560x1440"``
* a custom ``WxH`` string the caller typed, e.g. ``"1200x900"``

They are pure: no request context, no database, no configuration. They live in
their own module because both the workspace routes and the billing layer need
them, and because they were previously buried in ``routes_workspace`` where
they could not be tested or reused without importing the whole route module.

The leading underscores are kept on the original names so existing callers and
tests keep working unchanged; the unsuffixed aliases at the bottom are the
names new code should use.
"""
from __future__ import annotations

import re

from huishi.image_api import (
    CUSTOM_SIZE_PATTERN,
    SIZE_MATRIX,
    nearest_legal_image_size,
    nearest_legal_image_size_for_ratio,
    supported_size_values,
    supports_size,
    validate_image_size,
)


def _derive_resolution_labels():
    labels = set()
    for ratio_sizes in SIZE_MATRIX.values():
        labels.update(ratio_sizes.keys())
    return {k: k for k in sorted(labels)}


def _resolution_label_for_ratio(ratio: str, resolution: str, actual_size: str = "") -> str:
    value = str(resolution or "").strip()
    size_value = str(actual_size or "").strip()
    if value in {"1K", "2K", "4K"}:
        return value
    if size_value and size_value in {"1K", "2K", "4K"}:
        return size_value
    if not size_value:
        size_value = value
    ratio_sizes = SIZE_MATRIX.get(ratio) or {}
    for label, size in ratio_sizes.items():
        if size == value or size == size_value:
            return label
    if re.match(r"^\d+x\d+$", value):
        return "自定义尺寸"
    return value or "自定义尺寸"


def _resolution_value_for_ratio(ratio: str, resolution: str, actual_size: str = "") -> str:
    value = str(resolution or "").strip()
    size_value = str(actual_size or "").strip()
    if value in {"1K", "2K", "4K"}:
        return value
    if size_value in {"1K", "2K", "4K"}:
        return size_value
    for label, size in (SIZE_MATRIX.get(ratio) or {}).items():
        if size == value or size == size_value:
            return label
    return value or size_value or "2K"


def _resolution_for_billing(resolution: str) -> str:
    """Map a WxH resolution string to a known preset label for pricing lookup.
    Returns the original string if no match found (admin should add a pricing rule)."""
    if not re.match(r"^\d+x\d+$", resolution):
        return resolution
    for ratio_sizes in SIZE_MATRIX.values():
        for label, size in ratio_sizes.items():
            if size == resolution:
                return label
    return resolution


def _parse_size_value(size: str) -> tuple[int, int] | None:
    if not re.match(r"^\d+x\d+$", size or ""):
        return None
    width_raw, height_raw = size.split("x", 1)
    return int(width_raw), int(height_raw)


def _custom_size_error_message(resolution: str, exc: ValueError) -> str:
    parsed = _parse_size_value(resolution)
    if parsed is None:
        return str(exc)
    nearest = nearest_legal_image_size(*parsed)
    nearest_hint = f" 最近合法尺寸建议：{nearest}。" if nearest else ""
    return f"{exc}{nearest_hint}"


def _normalize_target_resolution_for_ratio(ratio: str, width: int, height: int) -> str:
    if ratio not in SIZE_MATRIX:
        raise ValueError("不支持的画面比例")
    return nearest_legal_image_size_for_ratio(ratio, width, height)


def _nearest_supported_size(ratio: str, resolution: str) -> str:
    target = _parse_size_value(resolution)
    if target is None:
        fallback = SIZE_MATRIX.get(ratio) or {}
        if resolution in fallback:
            return fallback[resolution]
        if "2K" in fallback:
            return fallback["2K"]
        if "1K" in fallback:
            return fallback["1K"]
        all_sizes = sorted(supported_size_values())
        return all_sizes[0] if all_sizes else ""

    candidate_sizes = list((SIZE_MATRIX.get(ratio) or {}).values()) or sorted(supported_size_values())
    target_width, target_height = target

    def score(size: str) -> tuple[int, int, int]:
        width, height = _parse_size_value(size) or (0, 0)
        pixel_delta = abs((width * height) - (target_width * target_height))
        edge_delta = abs(width - target_width) + abs(height - target_height)
        orientation_penalty = 0 if (width >= height) == (target_width >= target_height) else 1
        return (orientation_penalty, pixel_delta, edge_delta)

    return min(candidate_sizes, key=score) if candidate_sizes else ""


def _unsupported_size_message(ratio: str, resolution: str) -> str:
    if CUSTOM_SIZE_PATTERN.match(resolution):
        try:
            validate_image_size(resolution)
        except ValueError as exc:
            return _custom_size_error_message(resolution, exc)
    supported = sorted(
        {label for label in (SIZE_MATRIX.get(ratio) or {})}
        or {size for size in supported_size_values()}
    )
    hint = "、".join(supported[:6])
    nearest = _nearest_supported_size(ratio, resolution)
    nearest_hint = f" 最近可用尺寸建议：{nearest}。" if nearest else ""
    return f"当前 image2 模型不支持 {resolution}，请在参数面板选择标准比例和清晰度（可选：{hint}）。{nearest_hint}"


def _normalize_resolution_for_ratio(ratio: str, resolution: str) -> tuple[str, str | None]:
    if CUSTOM_SIZE_PATTERN.match(resolution):
        parsed = _parse_size_value(resolution)
        if parsed is None:
            return resolution, None
        nearest = _normalize_target_resolution_for_ratio(ratio, *parsed)
        return nearest, None if nearest == resolution else nearest
    if supports_size(ratio, resolution):
        return resolution, None
    nearest = _nearest_supported_size(ratio, resolution)
    if nearest:
        for label, size in (SIZE_MATRIX.get(ratio) or {}).items():
            if size == nearest:
                return label, nearest
        return nearest, nearest
    return resolution, None


# Public aliases: the names new code should import. The underscore-prefixed
# originals remain so existing call sites keep working.
derive_resolution_labels = _derive_resolution_labels
resolution_label_for_ratio = _resolution_label_for_ratio
resolution_value_for_ratio = _resolution_value_for_ratio
resolution_for_billing = _resolution_for_billing
parse_size_value = _parse_size_value
nearest_supported_size = _nearest_supported_size
normalize_resolution_for_ratio = _normalize_resolution_for_ratio
