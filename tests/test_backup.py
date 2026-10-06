from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app import create_app
from huishi.backup import (
    PG_DUMP_MISSING_HINT,
    build_pg_dump_command,
    create_backup,
    pg_dump_available,
    prune_backups,
    redact_database_url,
    verify_backup,
)


def test_build_pg_dump_command_uses_custom_format(tmp_path: Path):
    target = tmp_path / "huishi-20260710T120000Z.dump.part"

    command = build_pg_dump_command("postgresql://u:p@127.0.0.1/db", target)

    assert command == [
        "pg_dump",
        "--format=custom",
        "--no-owner",
        "--no-acl",
        f"--file={target}",
        "postgresql://u:p@127.0.0.1/db",
    ]


def test_prune_backups_keeps_newest_files_and_sidecars(tmp_path: Path):
    paths = []
    for index in range(5):
        path = tmp_path / f"huishi-2026070{index + 1}T000000Z.dump"
        path.write_bytes(str(index).encode())
        path.with_suffix(".dump.sha256").write_text("digest\n", encoding="ascii")
        paths.append(path)

    removed = prune_backups(tmp_path, keep=2)

    assert [path.name for path in removed] == [path.name for path in paths[:3]]
    assert paths[3].exists() and paths[4].exists()
    assert not paths[0].with_suffix(".dump.sha256").exists()
    assert paths[4].with_suffix(".dump.sha256").exists()


def test_create_backup_is_atomic_and_records_verified_status(tmp_path: Path):
    database_url = "postgresql://u:p@127.0.0.1/db"

    def runner(command, **kwargs):
        target = Path(next(part.split("=", 1)[1] for part in command if part.startswith("--file=")))
        target.write_bytes(b"valid custom dump")
        return subprocess.CompletedProcess(command, 0)

    path = create_backup(
        database_url,
        tmp_path,
        keep=14,
        runner=runner,
        now=datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc),
        probe=lambda: True,
    )

    assert path.name == "huishi-20260710T120000Z.dump"
    assert path.read_bytes() == b"valid custom dump"
    assert not path.with_suffix(".dump.part").exists()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert path.with_suffix(".dump.sha256").read_text(encoding="ascii") == f"{digest}  {path.name}\n"
    status = json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))
    assert status["ok"] is True
    assert status["path"] == str(path)
    assert status["size_bytes"] == path.stat().st_size
    assert status["sha256"] == digest
    assert verify_backup(path) == digest


def test_create_backup_failure_removes_partial_and_redacts_database_url(tmp_path: Path):
    database_url = "postgresql://secret-user:secret-password@127.0.0.1/db"

    def runner(command, **kwargs):
        target = Path(next(part.split("=", 1)[1] for part in command if part.startswith("--file=")))
        target.write_bytes(b"partial")
        raise subprocess.CalledProcessError(
            1, command, stderr=b"FATAL:  password authentication failed for user \"secret-user\""
        )

    with pytest.raises(subprocess.CalledProcessError):
        create_backup(database_url, tmp_path, keep=14, runner=runner, probe=lambda: True)

    assert not list(tmp_path.glob("*.part"))
    status_text = (tmp_path / "status.json").read_text(encoding="utf-8")
    status = json.loads(status_text)
    assert status["ok"] is False
    # 关键：错误信息必须带真实原因（否则运维无从下手），但不能带口令。
    assert status["error"].startswith("pg_dump failed: CalledProcessError: FATAL:")
    assert "secret-password" not in status_text
    assert "postgresql://secret-user:***@" not in status_text  # 连用户名也不整段回显
    assert redact_database_url(database_url) == "postgresql://secret-user:***@127.0.0.1/db"


def test_create_backup_without_pg_dump_fails_with_actionable_error(tmp_path: Path):
    """容器里没有 pg_dump 时，必须给出可读原因，而不是一行异常类型名。

    背景：backend 镜像基于 python:3.12-slim，只装了 ffmpeg，容器内没有
    pg_dump。改动前 `flask backup-postgres` 会以 CalledProcessError 失败，
    只在 status.json 留一行 "pg_dump failed: FileNotFoundError"。
    """
    called = []

    def runner(command, **kwargs):  # pragma: no cover - 不应被调用
        called.append(command)
        return subprocess.CompletedProcess(command, 0)

    with pytest.raises(RuntimeError, match="pg_dump"):
        create_backup(
            "postgresql://u:p@127.0.0.1/db",
            tmp_path,
            keep=14,
            runner=runner,
            probe=lambda: False,
        )

    assert called == [], "缺少 pg_dump 时不应尝试执行命令"
    status = json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))
    assert status["ok"] is False
    assert status["error"] == "pg_dump not installed"
    assert PG_DUMP_MISSING_HINT  # 常量存在于模块中（供 CLI/文档复用）


def test_redact_database_url_keeps_host_and_database():
    assert (
        redact_database_url("postgresql://user:s3cr3t@db.internal:5432/huishi")
        == "postgresql://user:***@db.internal:5432/huishi"
    )
    # 无口令的连接串原样保留
    assert redact_database_url("postgresql://user@db/huishi") == "postgresql://user@db/huishi"


def test_pg_dump_available_reflects_path_lookup(monkeypatch):
    from huishi import backup

    monkeypatch.setattr(backup.shutil, "which", lambda name: "/usr/bin/pg_dump")
    assert pg_dump_available() is True
    monkeypatch.setattr(backup.shutil, "which", lambda name: None)
    assert pg_dump_available() is False


def test_verify_backup_rejects_checksum_mismatch(tmp_path: Path):
    path = tmp_path / "huishi-20260710T120000Z.dump"
    path.write_bytes(b"dump")
    path.with_suffix(".dump.sha256").write_text(f"{'0' * 64}  {path.name}\n", encoding="ascii")

    with pytest.raises(RuntimeError, match="checksum mismatch"):
        verify_backup(path)


def test_backup_cli_uses_application_configuration(monkeypatch, tmp_path: Path):
    app = create_app(testing=True)
    app.config.update(
        DATABASE_URL="postgresql://u:p@127.0.0.1/db",
        BACKUP_DIR=tmp_path,
        BACKUP_KEEP=7,
    )
    expected = tmp_path / "huishi-20260710T120000Z.dump"
    calls = []

    def fake_create_backup(database_url, backup_dir, keep):
        calls.append((database_url, backup_dir, keep))
        return expected

    monkeypatch.setattr("app.create_backup", fake_create_backup)

    result = app.test_cli_runner().invoke(args=["backup-postgres"])

    assert result.exit_code == 0
    assert result.output.strip() == str(expected)
    assert calls == [("postgresql://u:p@127.0.0.1/db", tmp_path, 7)]
