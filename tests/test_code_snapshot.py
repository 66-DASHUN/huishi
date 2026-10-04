from __future__ import annotations

import hashlib
import tarfile
from pathlib import Path

import pytest

from tools.code_snapshot import create_snapshot, verify_snapshot


def test_snapshot_excludes_secrets_dependencies_and_runtime_data(tmp_path: Path):
    project = tmp_path / "app"
    (project / "static/uploads").mkdir(parents=True)
    (project / "node_modules/pkg").mkdir(parents=True)
    (project / "data").mkdir()
    (project / "logs").mkdir()
    (project / ".env").write_text("SECRET=x", encoding="utf-8")
    (project / "static/uploads/private.png").write_bytes(b"private")
    (project / "node_modules/pkg/index.js").write_text("dependency", encoding="utf-8")
    (project / "data/runtime.sqlite3").write_bytes(b"runtime")
    (project / "logs/app.log").write_text("runtime", encoding="utf-8")
    (project / "app.py").write_text("print('ok')", encoding="utf-8")

    archive = create_snapshot(project, tmp_path / "backups", "test")

    with tarfile.open(archive, "r:gz") as tar:
        names = tar.getnames()
    assert "app/app.py" in names
    assert "app/.env" not in names
    assert not any("static/uploads" in name for name in names)
    assert not any("node_modules" in name for name in names)
    assert not any("data/runtime.sqlite3" in name for name in names)
    assert not any("logs/app.log" in name for name in names)


def test_snapshot_writes_matching_checksum(tmp_path: Path):
    project = tmp_path / "app"
    project.mkdir()
    (project / "app.py").write_text("print('ok')", encoding="utf-8")

    archive = create_snapshot(project, tmp_path / "backups", "release-1")

    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    checksum_path = Path(f"{archive}.sha256")
    assert checksum_path.read_text(encoding="ascii") == f"{digest}  {archive.name}\n"
    assert verify_snapshot(archive) == digest


def test_snapshot_refuses_output_directory_inside_source(tmp_path: Path):
    project = tmp_path / "app"
    project.mkdir()

    with pytest.raises(ValueError, match="outside the source tree"):
        create_snapshot(project, project / "backups", "unsafe")


def test_snapshot_rejects_unsafe_label(tmp_path: Path):
    project = tmp_path / "app"
    project.mkdir()

    with pytest.raises(ValueError, match="snapshot label"):
        create_snapshot(project, tmp_path / "backups", "../unsafe")
