"""Shared network helpers for provider requests."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit


SUPPORTED_PROXY_SCHEMES = {"http", "https", "socks5", "socks5h"}


def normalize_proxy_url(value: object = "") -> str:
    """Validate and normalize an optional HTTP(S)/SOCKS proxy URL."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlsplit(raw)
    except ValueError as exc:
        raise ValueError("代理地址格式无效") from exc
    scheme = parsed.scheme.lower()
    if scheme not in SUPPORTED_PROXY_SCHEMES or not parsed.hostname:
        raise ValueError("代理地址必须使用 http、https、socks5 或 socks5h 协议")
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError("代理端口无效") from exc
    return raw


def proxy_mapping(value: object = "") -> dict[str, str] | None:
    proxy_url = normalize_proxy_url(value)
    if not proxy_url:
        return None
    return {"http": proxy_url, "https": proxy_url}


def request_proxy_kwargs(value: object = "") -> dict[str, Any]:
    proxies = proxy_mapping(value)
    return {"proxies": proxies} if proxies else {}


def openai_http_client(value: object = "", *, timeout: float):
    """Return an OpenAI-compatible httpx client when a proxy is configured."""
    proxy_url = normalize_proxy_url(value)
    if not proxy_url:
        return None
    try:
        from openai import DefaultHttpxClient
    except ImportError as exc:  # pragma: no cover - openai is a runtime dependency
        raise RuntimeError("当前环境不支持 OpenAI 代理客户端") from exc
    return DefaultHttpxClient(proxy=proxy_url, timeout=timeout)
