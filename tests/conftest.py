from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit

import pytest

# 画布前端契约测试（test_canvas_embed_mode_contract / test_canvas_identity_phase1_external）
# 需要 HUISHI_CANVAS_PROJECT_DIR 才能读到画布源码，否则整组静默 skip —— 静默跳过比
# 失败更危险，因为"没覆盖"看起来和"通过"一样。画布源码就在本仓库内，所以这里默认
# 指向它，让这些契约默认参与回归；也仍允许用环境变量覆盖为外部路径。
_CANVAS_SOURCE = Path(__file__).resolve().parent.parent / "infinite-canvas"
if _CANVAS_SOURCE.is_dir():
    os.environ.setdefault("HUISHI_CANVAS_PROJECT_DIR", str(_CANVAS_SOURCE))


def _postgres_test_dsn() -> str:
    dsn = os.environ.get("HUISHI_TEST_DATABASE_URL", "").strip()
    if not dsn.startswith(("postgresql://", "postgres://")):
        return ""

    database_name = urlsplit(dsn).path.rsplit("/", 1)[-1].lower()
    if not any(marker in database_name for marker in ("test", "pytest", "rehearsal")):
        raise RuntimeError("HUISHI_TEST_DATABASE_URL must name an isolated test database")
    return dsn


@pytest.fixture(autouse=True)
def reset_postgres_schema_between_tests():
    dsn = _postgres_test_dsn()
    if not dsn:
        yield
        return

    import psycopg

    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute("DROP SCHEMA IF EXISTS public CASCADE")
        connection.execute("CREATE SCHEMA public")

    yield
