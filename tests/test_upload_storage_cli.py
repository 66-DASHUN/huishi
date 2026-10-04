from __future__ import annotations

from pathlib import Path
import subprocess
import sys

from huishi.upload_storage import UploadStorage
from tools.upload_storage_cli import (
    compare_storage,
    migrate_local,
    restore_missing,
    sync_to_remote,
)


ROOT = Path(__file__).resolve().parents[1]


class FakeRemote:
    def __init__(self, objects: dict[str, bytes] | None = None):
        self.objects = dict(objects or {})

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.objects[key] = data

    def get(self, key: str) -> bytes:
        if key not in self.objects:
            raise FileNotFoundError(key)
        return self.objects[key]

    def exists(self, key: str) -> bool:
        return key in self.objects

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)

    def iter_keys(self):
        return iter(sorted(self.objects))

    def healthcheck(self) -> None:
        return None


def test_migrate_copies_without_overwriting_conflict(tmp_path: Path):
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    (source / "new.png").write_bytes(b"new")
    (source / "same-name.png").write_bytes(b"source")
    (target / "same-name.png").write_bytes(b"target")

    result = migrate_local(source, target)

    assert result.copied == 1
    assert result.conflicts == ["same-name.png"]
    assert (target / "new.png").read_bytes() == b"new"
    assert (target / "same-name.png").read_bytes() == b"target"
    assert (source / "same-name.png").exists()


def test_migrate_is_idempotent_for_identical_files(tmp_path: Path):
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    (source / "same.png").write_bytes(b"same")

    first = migrate_local(source, target)
    second = migrate_local(source, target)

    assert first.copied == 1
    assert second.copied == 0
    assert second.skipped == 1
    assert second.conflicts == []


def test_sync_is_idempotent(tmp_path: Path):
    (tmp_path / "a.png").write_bytes(b"a")
    remote = FakeRemote()

    first = sync_to_remote(tmp_path, remote)
    second = sync_to_remote(tmp_path, remote)

    assert first.copied == 1
    assert second.copied == 0
    assert second.skipped == 1
    assert remote.objects == {"uploads/a.png": b"a"}


def test_sync_dry_run_does_not_write(tmp_path: Path):
    (tmp_path / "a.png").write_bytes(b"a")
    remote = FakeRemote()

    result = sync_to_remote(tmp_path, remote, dry_run=True)

    assert result.copied == 1
    assert remote.objects == {}


def test_compare_and_restore_missing_local_objects(tmp_path: Path):
    (tmp_path / "local.png").write_bytes(b"local")
    remote = FakeRemote(
        {
            "uploads/local.png": b"local",
            "uploads/remote.png": b"remote",
        }
    )
    storage = UploadStorage(tmp_path, remote=remote)

    comparison = compare_storage(storage)
    restored = restore_missing(storage)

    assert comparison.local_only == []
    assert comparison.remote_only == ["remote.png"]
    assert restored.copied == 1
    assert (tmp_path / "remote.png").read_bytes() == b"remote"


def test_cli_can_run_from_outside_project_directory(tmp_path: Path):
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "upload_storage_cli.py"), "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "migrate-local" in result.stdout
