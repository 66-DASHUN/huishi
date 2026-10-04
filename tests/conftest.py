from __future__ import annotations

import os
from urllib.parse import urlsplit

import pytest


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
