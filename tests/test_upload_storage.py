from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from huishi.upload_storage import StorageUnavailable, UploadStorage, build_upload_storage


class FakeRemoteStore:
    def __init__(self, objects: dict[str, bytes] | None = None):
        self.objects = dict(objects or {})
        self.deleted: list[str] = []

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.objects[key] = data

    def get(self, key: str) -> bytes:
        if key not in self.objects:
            raise FileNotFoundError(key)
        return self.objects[key]

    def exists(self, key: str) -> bool:
        return key in self.objects

    def delete(self, key: str) -> None:
        self.deleted.append(key)
        self.objects.pop(key, None)

    def iter_keys(self):
        return iter(self.objects)

    def healthcheck(self) -> None:
        return None


class FailingRemoteStore(FakeRemoteStore):
    def put(self, key: str, data: bytes, content_type: str) -> None:
        raise StorageUnavailable("remote unavailable")


def test_local_storage_saves_and_restores(tmp_path: Path):
    storage = UploadStorage(tmp_path)

    public_path = storage.save_bytes("a.png", b"png", "image/png")

    assert public_path == "/static/uploads/a.png"
    assert storage.ensure_local("a.png").read_bytes() == b"png"


def test_remote_storage_rehydrates_missing_local(tmp_path: Path):
    remote = FakeRemoteStore({"uploads/a.png": b"png"})
    storage = UploadStorage(tmp_path, remote=remote, prefix="uploads/")

    restored = storage.ensure_local("a.png")

    assert restored.read_bytes() == b"png"
    assert not list(tmp_path.glob("*.partial"))


def test_remote_write_failure_removes_uncommitted_local_file(tmp_path: Path):
    storage = UploadStorage(tmp_path, remote=FailingRemoteStore())

    with pytest.raises(StorageUnavailable, match="remote unavailable"):
        storage.save_bytes("a.png", b"png", "image/png")

    assert not (tmp_path / "a.png").exists()
    assert not list(tmp_path.glob("*.partial"))


def test_delete_removes_local_and_remote_copies(tmp_path: Path):
    remote = FakeRemoteStore()
    storage = UploadStorage(tmp_path, remote=remote)
    storage.save_bytes("a.png", b"png", "image/png")

    storage.delete("a.png")

    assert not (tmp_path / "a.png").exists()
    assert remote.deleted == ["uploads/a.png"]


@pytest.mark.parametrize("key", ["", "../a.png", "nested/a.png", "nested\\a.png", "."])
def test_storage_rejects_non_basename_keys(tmp_path: Path, key: str):
    storage = UploadStorage(tmp_path)

    with pytest.raises(ValueError, match="invalid upload key"):
        storage.save_bytes(key, b"png", "image/png")


def test_builds_aws_s3_client_from_configuration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, object] = {}
    client = object()

    def make_client(service_name: str, **kwargs):
        captured.update(service_name=service_name, **kwargs)
        return client

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=make_client))
    storage = build_upload_storage(
        {
            "OUTPUT_DIR": tmp_path,
            "STORAGE_MODE": "s3",
            "STORAGE_BUCKET": "assets",
            "STORAGE_ACCESS_KEY_ID": "access",
            "STORAGE_SECRET_ACCESS_KEY": "secret",
            "STORAGE_REGION": "ap-southeast-1",
            "STORAGE_PREFIX": "huishi",
        }
    )

    assert storage.remote is not None
    assert captured == {
        "service_name": "s3",
        "aws_access_key_id": "access",
        "aws_secret_access_key": "secret",
        "region_name": "ap-southeast-1",
    }
    assert storage.prefix == "huishi/"


def test_builds_r2_client_with_endpoint_and_auto_region(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, object] = {}

    def make_client(service_name: str, **kwargs):
        captured.update(service_name=service_name, **kwargs)
        return object()

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=make_client))
    build_upload_storage(
        {
            "OUTPUT_DIR": tmp_path,
            "STORAGE_MODE": "r2",
            "STORAGE_BUCKET": "assets",
            "STORAGE_ACCESS_KEY_ID": "access",
            "STORAGE_SECRET_ACCESS_KEY": "secret",
            "STORAGE_ENDPOINT_URL": "https://account.r2.cloudflarestorage.com",
        }
    )

    assert captured["endpoint_url"] == "https://account.r2.cloudflarestorage.com"
    assert captured["region_name"] == "auto"


def test_builds_native_oss_bucket(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, object] = {}

    class FakeAuth:
        def __init__(self, access_key_id: str, access_key_secret: str):
            captured["credentials"] = (access_key_id, access_key_secret)

    def make_bucket(auth, endpoint: str, bucket_name: str):
        captured.update(auth=auth, endpoint=endpoint, bucket_name=bucket_name)
        return object()

    monkeypatch.setitem(sys.modules, "oss2", SimpleNamespace(Auth=FakeAuth, Bucket=make_bucket))
    storage = build_upload_storage(
        {
            "OUTPUT_DIR": tmp_path,
            "STORAGE_MODE": "oss",
            "STORAGE_BUCKET": "assets",
            "STORAGE_ACCESS_KEY_ID": "access",
            "STORAGE_SECRET_ACCESS_KEY": "secret",
            "STORAGE_ENDPOINT_URL": "https://oss-cn-hangzhou.aliyuncs.com",
        }
    )

    assert storage.remote is not None
    assert captured["credentials"] == ("access", "secret")
    assert captured["endpoint"] == "https://oss-cn-hangzhou.aliyuncs.com"
    assert captured["bucket_name"] == "assets"
