"""待核对视频任务的可发现性（需求 ⑥）。

背景：这类任务的**自动恢复是刻意关掉的**——上游受理状态未知（可能已扣费
也可能没有），所以代码既不自动重试也不改投其它渠道，只能由管理员确认原
渠道后手动恢复（`huishi/media_tasks.py::recover_video_tasks` 明确跳过
``phase == 'needs_reconciliation'``）。

问题从来不是"功能缺失"——`resume_media_task` 路由与待核对表格都已存在——
而是**没有任何可发现性**：管理员除非恰好打开业务流水页并往下翻，否则不知道
有任务卡在那里。这里锁住"它在运行总览里可见"这条契约。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app import create_app
from huishi.db import get_db, init_db
from huishi.operations import probe_paused_media_tasks
from huishi.records import create_generation_task


@pytest.fixture()
def app(tmp_path: Path, monkeypatch):
    # 必须**先**设环境变量再 create_app：反过来在 create_app 之后改 config，
    # 会让 init_db 建表的库与请求实际读的库不是同一个（页面级断言会莫名其妙
    # 看不到数据）。仓库里其它 admin 页测试也是这个顺序。
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("HUISHI_DATABASE", str(tmp_path / "test.sqlite3"))
    monkeypatch.setenv("HUISHI_OUTPUT_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("HUISHI_BACKUP_DIR", str(tmp_path / "backups"))
    application = create_app(testing=True)
    with application.app_context():
        init_db()
    return application


def _task(*, media_type: str = "video", phase: str, status: str = "running", **metadata_extra) -> int:
    """建一条生成任务并写入指定 phase。

    metadata 里除 phase 之外还带 ``recovery_error``，与真实写入路径
    （``save_phase`` 失败时记录的恢复错误）保持一致。
    """
    task_id = create_generation_task(
        user_id=1,
        prompt="p",
        mode="video",
        ratio="16:9",
        resolution="720p",
        actual_size="",
        quality="",
        output_format="png",
        count=1,
        cost=0,
        status=status,
        media_type=media_type,
        metadata={"phase": phase, "recovery_error": "上游受理状态未知"},
    )
    # create_generation_task 只负责 INSERT，提交由调用方负责；不提交的话
    # 应用上下文退出时会被丢弃，测试会看到一个空库（而且症状很隐蔽：
    # 同一个上下文里查得到，跨上下文就没了）。
    get_db().commit()
    return task_id


def test_probe_is_ok_when_nothing_is_pending(app):
    with app.app_context():
        result = probe_paused_media_tasks()

    assert result["status"] == "ok"
    assert result["count"] == 0
    # 无任务时不给链接，避免把人引到一个空表格
    assert not result.get("href")


def test_probe_counts_only_paused_video_tasks(app):
    with app.app_context():
        _task(phase="needs_reconciliation")            # 计入
        _task(phase="polling")                         # 正常轮询，不计
        _task(phase="needs_reconciliation", media_type="image")  # 非视频，不计
        _task(phase="needs_reconciliation", status="succeeded")  # 已完成，不计
        result = probe_paused_media_tasks()

    assert result["status"] == "warning"
    assert result["count"] == 1


def test_probe_links_to_the_reconciliation_table(app):
    """探针要能直接跳到待核对表格，否则等于只报数字不给入口。"""
    with app.app_context():
        _task(phase="needs_reconciliation")
        result = probe_paused_media_tasks()

    assert result["href"] == "/admin/records#media-reconciliation"


def test_probe_survives_a_corrupt_metadata_row(app):
    """一条写坏的 metadata_json 不能让整个运行总览探针挂掉。"""
    with app.app_context():
        _task(phase="needs_reconciliation")
        broken_id = _task(phase="bogus")
        get_db().execute(
            "UPDATE generation_tasks SET metadata_json = ? WHERE id = ?",
            ("{not json", broken_id),
        )
        get_db().commit()
        result = probe_paused_media_tasks()

    assert result["status"] == "warning"
    assert result["count"] == 1


def test_probe_count_matches_the_table_it_links_to(app):
    """首页数字与列表条数必须一致。

    两处曾各写一份 SQL，一旦漂移就会出现"首页说有 3 条、点进去只有 2 条"。
    现在共用 ``media_tasks`` 里的同一段查询，这里把它钉住。
    """
    from huishi.media_tasks import needs_reconciliation_tasks

    with app.app_context():
        for _ in range(3):
            _task(phase="needs_reconciliation")
        _task(phase="polling")
        probe = probe_paused_media_tasks()
        listed = needs_reconciliation_tasks()

    assert probe["count"] == len(listed) == 3


def test_collect_operations_health_includes_the_probe(app):
    """探针必须真的被首页汇总函数收录，否则加了也不会显示。"""
    from huishi.operations import collect_operations_health

    with app.app_context():
        _task(phase="needs_reconciliation")
        health = collect_operations_health()

    assert "paused_media_tasks" in health
    assert health["paused_media_tasks"]["count"] == 1


def test_dashboard_renders_the_label_and_link(app):
    """运行总览页面上真的出现"待核对任务"这一行，且带链接。"""
    with app.app_context():
        _task(phase="needs_reconciliation")
        admin_id = get_db().execute(
            "SELECT id FROM users WHERE role='admin' LIMIT 1"
        ).fetchone()["id"]

    client = app.test_client()
    with app.app_context():
        with client.session_transaction() as session:
            session["user_id"] = admin_id
    body = client.get("/admin/").get_data(as_text=True)

    assert "待核对任务" in body
    assert "/admin/records#media-reconciliation" in body


def test_records_page_still_lists_the_paused_tasks(app):
    """共用查询后，业务流水页的待核对表格必须照旧工作。"""
    with app.app_context():
        _task(phase="needs_reconciliation")
        admin_id = get_db().execute(
            "SELECT id FROM users WHERE role='admin' LIMIT 1"
        ).fetchone()["id"]

    client = app.test_client()
    with app.app_context():
        with client.session_transaction() as session:
            session["user_id"] = admin_id
    body = client.get("/admin/records").get_data(as_text=True)

    assert "视频任务待核对" in body
    assert 'id="media-reconciliation"' in body
    assert "恢复原任务" in body
