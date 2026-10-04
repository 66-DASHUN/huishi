from __future__ import annotations

from tools.db_smoke import configure_smoke_environment


def test_configure_smoke_environment_routes_postgres_to_testing_config():
    dsn = "postgresql://huishi:secret@127.0.0.1:5432/huishi_restore"
    environment: dict[str, str] = {}

    configure_smoke_environment(dsn, environment)

    assert environment["HUISHI_TEST_DATABASE_URL"] == dsn
    assert environment["HUISHI_TEST_REQUIRE_POSTGRES"] == "1"
