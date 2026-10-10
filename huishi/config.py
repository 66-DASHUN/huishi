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


# 开发/测试用的占位凭据。生产环境**必须**改成真实值，否则启动即失败
# （见 app.py 中对两个 DEFAULT_* 常量的校验）。
#
# 这两个值只有一处定义：早先 app.py 与 config.py 各写了一份字面量，
# 改其中一处不会生效——校验用的是 app.py 那份，配置文件用的是这份，
# 两边一旦漂移，"默认值检查"就会静默失效。现在 app.py 从这里导入。
DEFAULT_SECRET_KEY = "dev-change-me"
DEFAULT_ADMIN_PASSWORD = "1qaz@WSX"


class Config:
    # --- production secrets ---
    # Flask 会话密钥；生产环境必须设置为强随机值。
    SECRET_KEY = os.environ.get("HUISHI_SECRET_KEY", DEFAULT_SECRET_KEY)
    # 用于加密数据库中保存的 API Key、SMTP 密码等敏感配置。
    ENCRYPTION_KEY = os.environ.get("HUISHI_ENCRYPTION_KEY", "")
    # 首次初始化默认管理员密码；生产环境必须覆盖默认值。
    ADMIN_PASSWORD = os.environ.get("HUISHI_ADMIN_PASSWORD", DEFAULT_ADMIN_PASSWORD)

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
    # PNG 重编码档位。默认 6 而非 9：实测同一张 2048x2048 出图，
    # 档位 9 与 6 的产物体积几乎相同（都被"不小于原图就丢弃"的规则吃掉），
    # 但 9 要多花大量 CPU。这是高并发下的关键参数——单张本地 CPU 从
    # 约 3.5 秒降到约 0.4 秒，8 核可支撑的并发生成量因此提高近 10 倍。
    IMAGE_PNG_COMPRESS_LEVEL = int(os.environ.get("HUISHI_IMAGE_PNG_COMPRESS_LEVEL", "6"))

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
    # 画布生图的单用户提交频率上限（次 / 窗口秒）。
    #
    # 为什么需要：画布是**在 Web 线程里同步等上游**的（实测生图平均 22.9s、
    # 最长 43.8s，见 provider_call_logs），而 gunicorn 只有 -w 2 --threads 4
    # 共 8 个单元。工作台那条路径把生成丢进 RQ 队列、由 RedisGenerationLimiter
    # 统一限流（UPSTREAM_MAX_CONCURRENCY/RPM），画布则完全没有闸门——
    # 一个用户连点几下就能把 8 个 Web 单元全部占住，其他用户一律排队。
    #
    # 取值低于 8：单用户最多占满 Web 池，不应独占。这是**保护性**上限，
    # 正常人类操作（一次一单、等结果）远达不到。
    CANVAS_GENERATE_RATE_LIMIT = int(os.environ.get("HUISHI_CANVAS_GENERATE_RATE_LIMIT", "6"))
    CANVAS_GENERATE_RATE_WINDOW_SECONDS = int(
        os.environ.get("HUISHI_CANVAS_GENERATE_RATE_WINDOW_SECONDS", "60")
    )

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
    # 视频走独立队列，避免长任务把图片生成的槽位全部占住
    # （一条视频最长可在 worker 里轮询 20 分钟，而图片只要几十秒）。
    RQ_VIDEO_QUEUE_NAME = os.environ.get("HUISHI_RQ_VIDEO_QUEUE_NAME", "huishi-video")

    # --- 并发生成参数（引擎无关：RQ 与内建线程池共用）---
    #
    # 调并发只改这几个环境变量，不要改容器数量。
    #
    # 为什么分"进程 × 线程"两层：
    #   * 等上游占一次生成 99% 的时间，等待时 GIL 释放，线程成本近乎为零；
    #   * 但落盘前要做 decode + PNG 编码，实测约 0.42 秒**纯 CPU**，
    #     线程受 GIL 限制无法并行，必须靠多进程吃满多核。
    # 所以 process 数贴近 CPU 核数，thread 数用来把并发上限抬上去。
    #
    # 并发上限 = PROCESSES × THREADS。
    #
    # 默认值取 8 × 32 = 256：8 核在本机实测下能支撑约 500 并发（单张
    # 本地 CPU 0.42s，8/0.42 ≈ 19 张/秒，× 27 秒生成时长 ≈ 509），
    # 256 留了约 2 倍余量。
    GENERATION_IMAGE_PROCESSES = int(os.environ.get("HUISHI_GENERATION_IMAGE_PROCESSES", "8"))
    GENERATION_IMAGE_THREADS = int(os.environ.get("HUISHI_GENERATION_IMAGE_THREADS", "32"))
    # 视频默认 2 × 8 = 16：视频 CPU 极低，但**每个在跑的任务会长时间持有
    # 一个数据库连接**（轮询循环里 sleep），所以它的上限由连接预算和
    # 单条成本（400~700 积分）决定，而不是 CPU。可随时放宽。
    GENERATION_VIDEO_PROCESSES = int(os.environ.get("HUISHI_GENERATION_VIDEO_PROCESSES", "2"))
    GENERATION_VIDEO_THREADS = int(os.environ.get("HUISHI_GENERATION_VIDEO_THREADS", "8"))

    # 注意：这里用**显式常量**而不是 @property。
    # app.py 走的是 app.config.from_object(Config)，它只复制类属性；
    # property 在类上取到的是描述符对象本身而不是算好的值，会被装进 config
    # 变成一个没用的 property 对象。所以并发上限在 create_app 里算好写回。

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
