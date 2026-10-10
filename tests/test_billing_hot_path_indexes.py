"""计费热路径必须有 user_id 索引。

背景（2026-10-10 生产实测）：37 个索引里，``records`` / ``generation_tasks``
/ ``point_ledger`` / ``dialogues`` / ``canvas_messages`` 的 user_id 索引数为 **0**，
而余额预留（``reserved_generation_points``）、作品列表、积分流水全部按
``user_id`` 过滤。当前库小（cost 12~28），规划器选择顺序扫描看不出问题；
数据长大之后这三张表恰好都是增长最快的。

这组测试是**契约测试**：不测性能，只保证这些索引在 schema 里存在，
并且从 SQLite schema 转成 Postgres DDL 后仍然保留（``CREATE INDEX`` 会经过
``postgres_schema_from_sqlite`` 的处理）。
"""
from __future__ import annotations

import sqlite3

from huishi.db import SCHEMA
from huishi.db_backend import postgres_schema_from_sqlite

EXPECTED_INDEXES = {
    "idx_generation_tasks_user_status",
    "idx_records_user_created",
    "idx_records_user_hidden",
    "idx_point_ledger_user_created",
}


def _sqlite_index_names() -> set[str]:
    db = sqlite3.connect(":memory:")
    try:
        db.executescript(SCHEMA)
        rows = db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index'"
        ).fetchall()
        return {row[0] for row in rows}
    finally:
        db.close()


def test_hot_path_indexes_exist_in_schema():
    names = _sqlite_index_names()
    missing = EXPECTED_INDEXES - names
    assert not missing, f"schema 缺少计费热路径索引：{sorted(missing)}"


def test_hot_path_indexes_survive_postgres_conversion():
    """转成 Postgres DDL 后索引不能丢。

    转换函数会按表名排序重排语句；索引语句必须原样保留，
    否则 SQLite 测试通过而生产（Postgres）上根本没有索引。
    """
    converted = postgres_schema_from_sqlite(SCHEMA)
    for name in EXPECTED_INDEXES:
        assert name in converted, f"Postgres DDL 丢失索引 {name}"


def test_indexes_cover_the_billing_predicates():
    """索引列必须真的覆盖查询里的过滤条件。

    ``reserved_generation_points`` 的谓词是
    ``WHERE user_id = ? AND status IN ('queued','running')``，
    所以 generation_tasks 需要 (user_id, status) 这个顺序——
    把 status 放前面也是错的：单看 status 的选择性太低。
    """
    db = sqlite3.connect(":memory:")
    try:
        db.executescript(SCHEMA)
        rows = db.execute(
            "SELECT name, sql FROM sqlite_master WHERE type = 'index' AND name IN (?, ?)",
            ("idx_generation_tasks_user_status", "idx_records_user_created"),
        ).fetchall()
        by_name = {row[0]: (row[1] or "") for row in rows}
        assert "user_id, status" in by_name["idx_generation_tasks_user_status"].replace("\n", " ")
        assert "user_id, id DESC" in by_name["idx_records_user_created"].replace("\n", " ")
    finally:
        db.close()
