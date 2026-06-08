from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


class Config:
    SECRET_KEY = os.environ.get("HUISHI_SECRET_KEY", "dev-change-me")
    ADMIN_PASSWORD = os.environ.get("HUISHI_ADMIN_PASSWORD", "")
    DATABASE = Path(os.environ.get("HUISHI_DATABASE", BASE_DIR / "data" / "huishi.sqlite3"))
    OUTPUT_DIR = Path(os.environ.get("HUISHI_OUTPUT_DIR", BASE_DIR / "static" / "uploads"))
    DEFAULT_BASE_URL = os.environ.get("BASE_URL", "https://qa.dashun9527.com")
    DEFAULT_GENERATION_PATH = os.environ.get("GENERATION_PATH", "/v1/images/generations")
    DEFAULT_EDIT_PATH = os.environ.get("EDIT_PATH", "/v1/images/edits")
    DEFAULT_API_KEY = os.environ.get("API_KEY", "")
    SMTP_HOST = os.environ.get("SMTP_HOST", "")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
    SMTP_USER = os.environ.get("SMTP_USER", "")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
    SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER)
    SMTP_TLS = os.environ.get("SMTP_TLS", "1") != "0"
    SMTP_TIMEOUT = int(os.environ.get("HUISHI_SMTP_TIMEOUT", "10"))

    # --- generation limits ---
    MAX_GENERATION_COUNT = int(os.environ.get("HUISHI_MAX_GENERATION_COUNT", "8"))
    MAX_REFERENCE_IMAGES = int(os.environ.get("HUISHI_MAX_REFERENCE_IMAGES", "16"))

    # --- pagination / listing limits ---
    DASHBOARD_RECENT_RECORDS_LIMIT = 6
    DASHBOARD_RECENT_LEDGER_LIMIT = 8
    USER_LEDGER_LIMIT = 200
    USER_RECORDS_LIMIT = 50
    ADMIN_RECORDS_LIMIT = 100
    ADMIN_LEDGER_LIMIT = 100

    # --- security display ---
    MASK_KEY_VISIBLE_CHARS = 4
