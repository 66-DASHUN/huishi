from __future__ import annotations

import os
import re
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
SIZE_PATTERN = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([KMG]?)\s*$", re.IGNORECASE)


def _load_dotenv_file(env_path: Path) -> None:
    if not env_path.exists():
        return
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except PermissionError:
        return
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().lstrip("\ufeff")
        if not key or key in os.environ:
            continue
        os.environ[key] = value.strip().strip('"').strip("'")


def parse_size_bytes(value: str | int | float) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    match = SIZE_PATTERN.fullmatch(str(value or ""))
    if match is None:
        raise ValueError(f"invalid size value: {value}")
    number = float(match.group(1))
    unit = match.group(2).upper()
    multipliers = {
        "": 1,
        "K": 1024,
        "M": 1024 * 1024,
        "G": 1024 * 1024 * 1024,
    }
    return int(number * multipliers[unit])


def parse_optional_size_bytes(value: str | int | float | None) -> int:
    if value in (None, ""):
        return 0
    return parse_size_bytes(value)


def load_dotenv(path: Path | None = None) -> None:
    if path is not None:
        _load_dotenv_file(path)
        return
    cwd_env = Path.cwd() / ".env"
    _load_dotenv_file(cwd_env)
    base_env = BASE_DIR / ".env"
    if base_env != cwd_env:
        _load_dotenv_file(base_env)


if os.environ.get("HUISHI_ENV", "").strip().lower() != "test":
    load_dotenv()


class Config:
    # --- production secrets ---
    # Flask 会话密钥；生产环境必须设置为强随机值。
    SECRET_KEY = os.environ.get("HUISHI_SECRET_KEY", "dev-change-me")
    # 用于加密数据库中保存的 API Key、SMTP 密码等敏感配置。
    ENCRYPTION_KEY = os.environ.get("HUISHI_ENCRYPTION_KEY", "")
    # 首次初始化默认管理员密码；生产环境必须覆盖默认值。
    ADMIN_PASSWORD = os.environ.get("HUISHI_ADMIN_PASSWORD", "1qaz@WSX")

    # --- storage paths ---
    # SQLite 数据库文件路径。
    DATABASE = Path(os.environ.get("HUISHI_DATABASE", BASE_DIR / "data" / "huishi.sqlite3"))
    DATABASE_URL = os.environ.get("DATABASE_URL", "")
    # When enabled, startup fails unless DATABASE_URL points at PostgreSQL. Use it for PG-first deployments.
    REQUIRE_POSTGRES = os.environ.get("HUISHI_REQUIRE_POSTGRES", "0") == "1"
    # 上传参考图和生成图片的本地保存目录。
    OUTPUT_DIR = Path(os.environ.get("HUISHI_OUTPUT_DIR", BASE_DIR / "static" / "uploads"))
    STORAGE_MODE = os.environ.get("HUISHI_STORAGE_MODE", "local").strip().lower()
    STORAGE_BUCKET = os.environ.get("HUISHI_STORAGE_BUCKET", "")
    STORAGE_ACCESS_KEY_ID = os.environ.get("HUISHI_STORAGE_ACCESS_KEY_ID", "")
    STORAGE_SECRET_ACCESS_KEY = os.environ.get("HUISHI_STORAGE_SECRET_ACCESS_KEY", "")
    STORAGE_ENDPOINT_URL = os.environ.get("HUISHI_STORAGE_ENDPOINT_URL", "")
    STORAGE_REGION = os.environ.get("HUISHI_STORAGE_REGION", "")
    STORAGE_PREFIX = os.environ.get("HUISHI_STORAGE_PREFIX", "uploads/")
    BACKUP_DIR = Path(os.environ.get("HUISHI_BACKUP_DIR", "/var/backups/huishi/postgres"))
    BACKUP_KEEP = int(os.environ.get("HUISHI_BACKUP_KEEP", "14"))
    STORAGE_RETENTION_DAYS = int(os.environ.get("HUISHI_STORAGE_RETENTION_DAYS", "14"))
    STORAGE_ORPHAN_RETENTION_DAYS = int(os.environ.get("HUISHI_STORAGE_ORPHAN_RETENTION_DAYS", "7"))
    STORAGE_HIDDEN_RETENTION_DAYS = int(os.environ.get("HUISHI_STORAGE_HIDDEN_RETENTION_DAYS", os.environ.get("HUISHI_STORAGE_RETENTION_DAYS", "14")))
    STORAGE_MAX_BYTES = parse_optional_size_bytes(os.environ.get("HUISHI_STORAGE_MAX_BYTES", "0"))
    STORAGE_SWEEP_BATCH = int(os.environ.get("HUISHI_STORAGE_SWEEP_BATCH", "5000"))
    STORAGE_SWEEP_MAX_DELETE_FILES = int(os.environ.get("HUISHI_STORAGE_SWEEP_MAX_DELETE_FILES", "20000"))
    STORAGE_SWEEP_MIN_AGE_SECONDS = int(os.environ.get("HUISHI_STORAGE_SWEEP_MIN_AGE_SECONDS", "300"))
    IMAGE_OPTIMIZE_ENABLED = os.environ.get("HUISHI_IMAGE_OPTIMIZE_ENABLED", "1") != "0"
    IMAGE_JPEG_QUALITY = int(os.environ.get("HUISHI_IMAGE_JPEG_QUALITY", "88"))
    IMAGE_WEBP_QUALITY = int(os.environ.get("HUISHI_IMAGE_WEBP_QUALITY", "86"))
    IMAGE_PNG_COMPRESS_LEVEL = int(os.environ.get("HUISHI_IMAGE_PNG_COMPRESS_LEVEL", "9"))

    # --- provider defaults ---
    # 默认 OpenAI 兼容图片接口 Base URL；后台 provider 配置会优先用于实际生成。
    DEFAULT_BASE_URL = os.environ.get("BASE_URL", "https://qa.dashun9527.com")
    # 默认文生图接口路径，保留给兼容 provider 使用。
    DEFAULT_GENERATION_PATH = os.environ.get("GENERATION_PATH", "/v1/images/generations")
    # 默认参考图编辑接口路径，保留给兼容 provider 使用。
    DEFAULT_EDIT_PATH = os.environ.get("EDIT_PATH", "/v1/images/edits")
    # 默认图片 API Key；也可以在后台 provider 中配置。
    DEFAULT_API_KEY = os.environ.get("API_KEY", "")
    # 默认画布应用地址；用于 /canvas 独立页的初始嵌入目标。
    CANVAS_APP_URL = os.environ.get("HUISHI_CANVAS_APP_URL", "http://127.0.0.1:3000")
    # 主站签发给画布的短时会话 token TTL，单位秒。
    CANVAS_SESSION_TTL_SECONDS = int(os.environ.get("HUISHI_CANVAS_SESSION_TTL_SECONDS", "86400"))

    # --- SMTP email ---
    # SMTP 服务器地址。
    SMTP_HOST = os.environ.get("SMTP_HOST", "")
    # SMTP 端口；常用 587 STARTTLS 或 465 SSL。
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
    # SMTP 登录账号。
    SMTP_USER = os.environ.get("SMTP_USER", "")
    # SMTP 登录密码或邮箱授权码。
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
    # 邮件发件人；默认使用 SMTP_USER。
    SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER)
    # 是否使用 SMTP_SSL；未设置时会根据端口自动判断。
    SMTP_SSL = os.environ.get("SMTP_SSL")
    SMTP_SSL = None if SMTP_SSL is None else SMTP_SSL != "0"
    # 是否使用 STARTTLS；设置为 0 可关闭。
    SMTP_TLS = os.environ.get("SMTP_TLS", "1") != "0"
    # SMTP 连接超时时间，单位秒。
    SMTP_TIMEOUT = int(os.environ.get("HUISHI_SMTP_TIMEOUT", "10"))

    # --- timeouts and workers ---
    # 注册邮箱验证码有效期，单位秒。
    REGISTRATION_EMAIL_CODE_TTL_SECONDS = int(os.environ.get("HUISHI_REGISTRATION_EMAIL_CODE_TTL_SECONDS", "600"))
    # 图片 API 请求超时时间，单位秒。
    IMAGE_API_TIMEOUT = float(os.environ.get("HUISHI_IMAGE_API_TIMEOUT", "180"))
    IMAGE_API_MAX_RETRIES = int(os.environ.get("HUISHI_IMAGE_API_MAX_RETRIES", "0"))
    # 全站同时执行的后台生图 worker 数。
    GENERATION_WORKERS = int(os.environ.get("HUISHI_GENERATION_WORKERS", "3"))
    GENERATION_QUEUE_BACKEND = os.environ.get("HUISHI_GENERATION_QUEUE_BACKEND", "thread").strip().lower()
    REDIS_URL = os.environ.get("HUISHI_REDIS_URL", "")
    REQUIRE_REDIS_LIMITS = os.environ.get("HUISHI_REQUIRE_REDIS_LIMITS", "1" if os.environ.get("HUISHI_ENV", "").strip().lower() == "production" else "0") == "1"
    RQ_QUEUE_NAME = os.environ.get("HUISHI_RQ_QUEUE_NAME", "huishi-generation")
    RQ_JOB_TIMEOUT_SECONDS = int(os.environ.get("HUISHI_RQ_JOB_TIMEOUT_SECONDS", "1200"))
    RQ_RESULT_TTL_SECONDS = int(os.environ.get("HUISHI_RQ_RESULT_TTL_SECONDS", "60"))
    RQ_FAILURE_TTL_SECONDS = int(os.environ.get("HUISHI_RQ_FAILURE_TTL_SECONDS", "86400"))
    APP_IMPORT_PATH = os.environ.get("HUISHI_APP_IMPORT_PATH", "app:create_app")
    UPSTREAM_MAX_CONCURRENCY = int(os.environ.get("HUISHI_UPSTREAM_MAX_CONCURRENCY", "240"))
    UPSTREAM_RPM_LIMIT = int(os.environ.get("HUISHI_UPSTREAM_RPM_LIMIT", "300"))
    GENERATION_LIMIT_WAIT_TIMEOUT_SECONDS = float(os.environ.get("HUISHI_GENERATION_LIMIT_WAIT_TIMEOUT_SECONDS", "840"))
    GENERATION_LIMIT_WAIT_SLEEP_SECONDS = float(os.environ.get("HUISHI_GENERATION_LIMIT_WAIT_SLEEP_SECONDS", "1"))
    # 生成任务超过该时间仍未完成时视为过期；默认覆盖限流等待窗口和图片 API 超时。
    GENERATION_TASK_STALE_SECONDS = float(
        os.environ.get(
            "HUISHI_GENERATION_TASK_STALE_SECONDS",
            str(IMAGE_API_TIMEOUT + GENERATION_LIMIT_WAIT_TIMEOUT_SECONDS + 60),
        )
    )
    RATE_LIMIT_NAMESPACE = os.environ.get("HUISHI_RATE_LIMIT_NAMESPACE", "huishi")
    # 测试/调试用：为 1 时不进线程池，直接同步生成。
    GENERATION_INLINE = os.environ.get("HUISHI_GENERATION_INLINE", "0") == "1"
    # Prompt 优化 API 请求超时时间，单位秒。
    PROMPT_API_TIMEOUT = float(os.environ.get("HUISHI_PROMPT_API_TIMEOUT", "20"))
    # Flask 请求体最大大小，支持纯字节数或 K/M/G 后缀。
    MAX_CONTENT_LENGTH = parse_size_bytes(os.environ.get("HUISHI_MAX_CONTENT_LENGTH", "64M"))

    # --- session cookies ---
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # 是否强制 Secure Cookie；生产环境 app.py 会自动开启。
    SESSION_COOKIE_SECURE = os.environ.get("HUISHI_SESSION_COOKIE_SECURE", "0") == "1"

    # --- abuse protection ---
    # 登录限流：窗口期内允许失败次数。
    LOGIN_RATE_LIMIT_ATTEMPTS = int(os.environ.get("HUISHI_LOGIN_RATE_LIMIT_ATTEMPTS", "5"))
    # 登录限流窗口，单位秒。
    LOGIN_RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get("HUISHI_LOGIN_RATE_LIMIT_WINDOW_SECONDS", "300"))
    # 登录失败锁定时长，单位秒。
    LOGIN_LOCKOUT_SECONDS = int(os.environ.get("HUISHI_LOGIN_LOCKOUT_SECONDS", "900"))
    # 邮箱验证码每分钟发送上限。
    EMAIL_CODE_RATE_LIMIT_PER_MINUTE = int(os.environ.get("HUISHI_EMAIL_CODE_RATE_LIMIT_PER_MINUTE", "1"))
    # 邮箱验证码每小时发送上限。
    EMAIL_CODE_RATE_LIMIT_PER_HOUR = int(os.environ.get("HUISHI_EMAIL_CODE_RATE_LIMIT_PER_HOUR", "5"))
    # 找回密码限流：窗口期内允许尝试次数。
    PASSWORD_RESET_RATE_LIMIT_ATTEMPTS = int(os.environ.get("HUISHI_PASSWORD_RESET_RATE_LIMIT_ATTEMPTS", "5"))
    # 找回密码限流窗口，单位秒。
    PASSWORD_RESET_RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get("HUISHI_PASSWORD_RESET_RATE_LIMIT_WINDOW_SECONDS", "300"))
    # 后台 CSV 导入文件最大大小，支持纯字节数或 K/M/G 后缀。
    ADMIN_IMPORT_MAX_BYTES = parse_size_bytes(os.environ.get("HUISHI_ADMIN_IMPORT_MAX_BYTES", "2M"))
    # 后台 CSV 导入最大行数。
    ADMIN_IMPORT_MAX_ROWS = int(os.environ.get("HUISHI_ADMIN_IMPORT_MAX_ROWS", "2000"))
    # 后台 CSV 单字段最大长度。
    ADMIN_IMPORT_MAX_FIELD_LENGTH = int(os.environ.get("HUISHI_ADMIN_IMPORT_MAX_FIELD_LENGTH", "256"))

    # --- generation limits ---
    # 单次生成最多图片张数。
    MAX_GENERATION_COUNT = int(os.environ.get("HUISHI_MAX_GENERATION_COUNT", "10"))
    # 单个用户同时允许处于 queued / running 状态的生成任务数上限；0 表示不限制。
    MAX_ACTIVE_GENERATION_TASKS_PER_USER = int(os.environ.get("HUISHI_MAX_ACTIVE_GENERATION_TASKS_PER_USER", "2"))
    # 单次最多参考图张数。
    MAX_REFERENCE_IMAGES = int(os.environ.get("HUISHI_MAX_REFERENCE_IMAGES", "16"))
    # 单张参考图最大大小，支持纯字节数或 K/M/G 后缀。
    MAX_REFERENCE_IMAGE_BYTES = parse_size_bytes(os.environ.get("HUISHI_MAX_REFERENCE_IMAGE_BYTES", "12M"))

    # --- pagination / listing limits ---
    DASHBOARD_RECENT_RECORDS_LIMIT = 6
    DASHBOARD_RECENT_LEDGER_LIMIT = 8
    USER_LEDGER_LIMIT = 200
    USER_RECORDS_LIMIT = 50
    ADMIN_RECORDS_LIMIT = 100
    ADMIN_LEDGER_LIMIT = 100

    # --- security display ---
    MASK_KEY_VISIBLE_CHARS = 4
