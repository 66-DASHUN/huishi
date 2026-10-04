from __future__ import annotations

import logging
import re
from urllib.parse import urlsplit, urlunsplit

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app


logger = logging.getLogger(__name__)
ENCRYPTED_PREFIX = "enc:v1:"
SECRET_APP_SETTING_KEYS = {
    "image_api_key",
    "prompt_api_key",
    "smtp_password",
    "canvas_agent_token",
    "storage_access_key_id",
    "storage_secret_access_key",
}

_SECRET_TOKEN_PATTERN = re.compile(r"(?i)\b(?:sk|sess)[-_A-Za-z0-9]{8,}\b")
_URL_PATTERN = re.compile(r"https?://[^\s<>'\")]+")


def redact_url(value: str) -> str:
    try:
        parts = urlsplit(value)
    except ValueError:
        return "[redacted-url]"
    if not parts.scheme or not parts.netloc:
        return value
    # urlsplit().hostname/port exclude userinfo; never log credentials from netloc.
    host = parts.hostname or ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    try:
        port = f":{parts.port}" if parts.port is not None else ""
    except ValueError:
        port = ""
    return urlunsplit((parts.scheme, host + port, parts.path, "", ""))


def redact_sensitive_text(value: object, *secrets: object) -> str:
    text = str(value or "")
    for secret in secrets:
        candidate = str(secret or "")
        if candidate:
            text = text.replace(candidate, "[redacted]")
    text = _URL_PATTERN.sub(lambda match: redact_url(match.group(0)), text)
    text = re.sub(r"(?i)(authorization\s*:\s*bearer\s+)[^\s,;]+", r"\1[redacted]", text)
    text = re.sub(r"(?i)(authorization\s*:\s*(?:apikey|api-key)\s+)[^\s,;]+", r"\1[redacted]", text)
    text = re.sub(r"(?i)(\b(?:api[_-]?key|token|secret)\s*[:=])\s*[^\s,;]+", r"\1[redacted]", text)
    return _SECRET_TOKEN_PATTERN.sub("[redacted]", text)


def _fernet() -> Fernet | None:
    key = str(current_app.config.get("ENCRYPTION_KEY") or "").strip()
    if not key:
        return None
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, TypeError) as exc:
        raise RuntimeError("HUISHI_ENCRYPTION_KEY must be a valid Fernet key") from exc


def is_encrypted_secret(value: str) -> bool:
    return str(value or "").startswith(ENCRYPTED_PREFIX)


def encrypt_secret(value: str) -> str:
    if not value or is_encrypted_secret(value):
        return value
    fernet = _fernet()
    if fernet is None:
        return value
    token = fernet.encrypt(value.encode("utf-8")).decode("ascii")
    return f"{ENCRYPTED_PREFIX}{token}"


def decrypt_secret(value: str) -> str:
    if not value or not is_encrypted_secret(value):
        return value
    fernet = _fernet()
    if fernet is None:
        logger.error("encrypted secret cannot be decrypted because HUISHI_ENCRYPTION_KEY is not configured")
        return ""
    token = value[len(ENCRYPTED_PREFIX) :]
    try:
        return fernet.decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken:
        logger.error("encrypted secret could not be decrypted")
        return ""


def store_secret_app_setting_value(key: str, value: str) -> str:
    if key in SECRET_APP_SETTING_KEYS:
        return encrypt_secret(value)
    return value


def load_secret_app_setting_value(key: str, value: str) -> str:
    if key in SECRET_APP_SETTING_KEYS:
        return decrypt_secret(value)
    return value
