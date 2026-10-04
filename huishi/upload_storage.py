from __future__ import annotations

import mimetypes
import os
import shutil
import uuid
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Protocol


PUBLIC_UPLOAD_PREFIX = "/static/uploads/"
SUPPORTED_STORAGE_MODES = {"local", "s3", "r2", "oss"}
STORAGE_SETTING_KEYS = {
    "storage_mode",
    "storage_bucket",
    "storage_access_key_id",
    "storage_secret_access_key",
    "storage_endpoint_url",
    "storage_region",
    "storage_prefix",
}


class StorageUnavailable(RuntimeError):
    pass


class RemoteObjectStore(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> None: ...

    def get(self, key: str) -> bytes: ...

    def exists(self, key: str) -> bool: ...

    def delete(self, key: str) -> None: ...

    def iter_keys(self) -> Iterable[str]: ...

    def healthcheck(self) -> None: ...


def validate_upload_key(key: object) -> str:
    normalized = str(key or "").strip()
    if (
        not normalized
        or normalized in {".", ".."}
        or Path(normalized).name != normalized
        or "/" in normalized
        or "\\" in normalized
    ):
        raise ValueError("invalid upload key")
    return normalized


def normalize_prefix(prefix: object) -> str:
    normalized = str(prefix or "").strip().strip("/")
    return f"{normalized}/" if normalized else ""


class UploadStorage:
    def __init__(
        self,
        local_dir: Path | str,
        *,
        remote: RemoteObjectStore | None = None,
        prefix: str = "uploads/",
    ) -> None:
        self.local_dir = Path(local_dir)
        self.local_dir.mkdir(parents=True, exist_ok=True)
        self.remote = remote
        self.prefix = normalize_prefix(prefix)

    def object_key(self, key: object) -> str:
        return f"{self.prefix}{validate_upload_key(key)}"

    def public_path(self, key: object) -> str:
        return f"{PUBLIC_UPLOAD_PREFIX}{validate_upload_key(key)}"

    def local_path(self, key: object) -> Path:
        return self.local_dir / validate_upload_key(key)

    def save_bytes(self, key: object, data: bytes, content_type: str = "") -> str:
        normalized = validate_upload_key(key)
        target = self.local_path(normalized)
        partial = self._partial_path(normalized)
        payload = bytes(data)
        try:
            partial.write_bytes(payload)
            if self.remote is not None:
                self.remote.put(
                    self.object_key(normalized),
                    payload,
                    content_type or mimetypes.guess_type(normalized)[0] or "application/octet-stream",
                )
            os.replace(partial, target)
        except Exception:
            partial.unlink(missing_ok=True)
            raise
        return self.public_path(normalized)

    def save_file(self, key: object, source: Path | str, content_type: str = "") -> str:
        normalized=validate_upload_key(key)
        target=self.local_path(normalized)
        partial=self._partial_path(normalized)
        mime=content_type or mimetypes.guess_type(normalized)[0] or 'application/octet-stream'
        try:
            shutil.copyfile(source,partial)
            if self.remote is not None:
                if hasattr(self.remote,'put_file'):
                    self.remote.put_file(self.object_key(normalized),partial,mime)
                else:
                    self.remote.put(self.object_key(normalized),partial.read_bytes(),mime)
            os.replace(partial,target)
        except Exception:
            partial.unlink(missing_ok=True)
            raise
        return self.public_path(normalized)

    def ensure_local(self, key: object) -> Path:
        normalized = validate_upload_key(key)
        target = self.local_path(normalized)
        if target.is_file():
            return target
        if self.remote is None:
            raise FileNotFoundError(normalized)
        partial = self._partial_path(normalized)
        try:
            partial.write_bytes(self.remote.get(self.object_key(normalized)))
            os.replace(partial, target)
        except Exception:
            partial.unlink(missing_ok=True)
            raise
        return target

    def exists(self, key: object) -> bool:
        normalized = validate_upload_key(key)
        if self.local_path(normalized).is_file():
            return True
        return bool(self.remote is not None and self.remote.exists(self.object_key(normalized)))

    def delete(self, key: object) -> None:
        normalized = validate_upload_key(key)
        if self.remote is not None:
            self.remote.delete(self.object_key(normalized))
        self.local_path(normalized).unlink(missing_ok=True)

    def iter_objects(self) -> Iterable[str]:
        keys = {item.name for item in self.local_dir.iterdir() if item.is_file() and not item.name.endswith(".partial")}
        if self.remote is not None:
            for object_key in self.remote.iter_keys():
                if self.prefix and not object_key.startswith(self.prefix):
                    continue
                candidate = object_key[len(self.prefix) :] if self.prefix else object_key
                try:
                    keys.add(validate_upload_key(candidate))
                except ValueError:
                    continue
        return iter(sorted(keys))

    def healthcheck(self) -> None:
        self.local_dir.mkdir(parents=True, exist_ok=True)
        probe = self._partial_path("healthcheck")
        try:
            probe.write_bytes(b"")
        finally:
            probe.unlink(missing_ok=True)
        if self.remote is not None:
            self.remote.healthcheck()

    def _partial_path(self, key: str) -> Path:
        return self.local_dir / f".{key}.{uuid.uuid4().hex}.partial"


def _is_not_found(exc: BaseException) -> bool:
    response = getattr(exc, "response", None)
    if not isinstance(response, Mapping):
        return False
    error = response.get("Error", {})
    code = str(error.get("Code", "")) if isinstance(error, Mapping) else ""
    status = response.get("ResponseMetadata", {})
    http_status = status.get("HTTPStatusCode") if isinstance(status, Mapping) else None
    return code in {"404", "NoSuchKey", "NotFound", "NoSuchBucket"} or http_status == 404


class S3RemoteStore:
    def put_file(self,key,path,content_type):
        try:
            with Path(path).open('rb') as body:
                self.client.put_object(Bucket=self.bucket,Key=key,Body=body,ContentType=content_type)
        except Exception as exc:
            raise StorageUnavailable('object storage write failed') from exc

    def __init__(
        self,
        *,
        bucket: str,
        access_key_id: str,
        secret_access_key: str,
        endpoint_url: str = "",
        region_name: str = "",
        client=None,
    ) -> None:
        self.bucket = bucket
        if client is None:
            import boto3

            options = {
                "aws_access_key_id": access_key_id,
                "aws_secret_access_key": secret_access_key,
            }
            if endpoint_url:
                options["endpoint_url"] = endpoint_url
            if region_name:
                options["region_name"] = region_name
            client = boto3.client("s3", **options)
        self.client = client

    def put(self, key: str, data: bytes, content_type: str) -> None:
        try:
            self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)
        except Exception as exc:
            raise StorageUnavailable("object storage write failed") from exc

    def get(self, key: str) -> bytes:
        try:
            return bytes(self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read())
        except Exception as exc:
            if _is_not_found(exc):
                raise FileNotFoundError(key) from exc
            raise StorageUnavailable("object storage read failed") from exc

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception as exc:
            if _is_not_found(exc):
                return False
            raise StorageUnavailable("object storage lookup failed") from exc

    def delete(self, key: str) -> None:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            raise StorageUnavailable("object storage delete failed") from exc

    def iter_keys(self) -> Iterable[str]:
        try:
            paginator = self.client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self.bucket):
                for item in page.get("Contents", []):
                    key = str(item.get("Key") or "")
                    if key:
                        yield key
        except Exception as exc:
            raise StorageUnavailable("object storage inventory failed") from exc

    def healthcheck(self) -> None:
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except Exception as exc:
            raise StorageUnavailable("object storage healthcheck failed") from exc


class OssRemoteStore:
    def __init__(
        self,
        *,
        bucket: str,
        access_key_id: str,
        secret_access_key: str,
        endpoint_url: str,
        client=None,
    ) -> None:
        self.bucket_name = bucket
        if client is None:
            import oss2

            auth = oss2.Auth(access_key_id, secret_access_key)
            client = oss2.Bucket(auth, endpoint_url, bucket)
        self.client = client

    def put(self, key: str, data: bytes, content_type: str) -> None:
        try:
            self.client.put_object(key, data, headers={"Content-Type": content_type})
        except Exception as exc:
            raise StorageUnavailable("object storage write failed") from exc

    def put_file(self,key,path,content_type):
        try:
            self.client.put_object_from_file(key,str(path),headers={'Content-Type':content_type})
        except Exception as exc:
            raise StorageUnavailable('object storage write failed') from exc

    def get(self, key: str) -> bytes:
        try:
            return bytes(self.client.get_object(key).read())
        except Exception as exc:
            if getattr(exc, "status", None) == 404:
                raise FileNotFoundError(key) from exc
            raise StorageUnavailable("object storage read failed") from exc

    def exists(self, key: str) -> bool:
        try:
            return bool(self.client.object_exists(key))
        except Exception as exc:
            raise StorageUnavailable("object storage lookup failed") from exc

    def delete(self, key: str) -> None:
        try:
            self.client.delete_object(key)
        except Exception as exc:
            raise StorageUnavailable("object storage delete failed") from exc

    def iter_keys(self) -> Iterable[str]:
        try:
            import oss2

            for item in oss2.ObjectIteratorV2(self.client):
                key = str(getattr(item, "key", ""))
                if key:
                    yield key
        except Exception as exc:
            raise StorageUnavailable("object storage inventory failed") from exc

    def healthcheck(self) -> None:
        try:
            self.client.get_bucket_info()
        except Exception as exc:
            raise StorageUnavailable("object storage healthcheck failed") from exc


def _configured_value(
    config: Mapping[str, object],
    settings: Mapping[str, object],
    config_key: str,
    settings_key: str,
    default: str = "",
) -> str:
    setting_value = str(settings.get(settings_key) or "").strip()
    if setting_value:
        return setting_value
    return str(config.get(config_key) or default).strip()


def build_upload_storage(
    config: Mapping[str, object],
    settings: Mapping[str, object] | None = None,
) -> UploadStorage:
    settings = settings or {}
    mode = _configured_value(config, settings, "STORAGE_MODE", "storage_mode", "local").lower()
    if mode not in SUPPORTED_STORAGE_MODES:
        raise ValueError(f"unsupported storage mode: {mode}")
    local_dir = Path(config["OUTPUT_DIR"])
    prefix = _configured_value(config, settings, "STORAGE_PREFIX", "storage_prefix", "uploads/")
    if mode == "local":
        return UploadStorage(local_dir, prefix=prefix)

    bucket = _configured_value(config, settings, "STORAGE_BUCKET", "storage_bucket")
    access_key_id = _configured_value(config, settings, "STORAGE_ACCESS_KEY_ID", "storage_access_key_id")
    secret_access_key = _configured_value(
        config,
        settings,
        "STORAGE_SECRET_ACCESS_KEY",
        "storage_secret_access_key",
    )
    endpoint_url = _configured_value(config, settings, "STORAGE_ENDPOINT_URL", "storage_endpoint_url")
    region_name = _configured_value(config, settings, "STORAGE_REGION", "storage_region")
    required = {
        "bucket": bucket,
        "access key": access_key_id,
        "secret key": secret_access_key,
    }
    if mode in {"r2", "oss"}:
        required["endpoint"] = endpoint_url
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise ValueError(f"missing {mode} storage configuration: {', '.join(missing)}")

    if mode in {"s3", "r2"}:
        remote: RemoteObjectStore = S3RemoteStore(
            bucket=bucket,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            endpoint_url=endpoint_url,
            region_name=region_name or ("auto" if mode == "r2" else ""),
        )
    else:
        remote = OssRemoteStore(
            bucket=bucket,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            endpoint_url=endpoint_url,
        )
    return UploadStorage(local_dir, remote=remote, prefix=prefix)


def storage_configuration_signature(
    config: Mapping[str, object],
    settings: Mapping[str, object] | None = None,
) -> tuple[str, ...]:
    settings = settings or {}
    return (
        str(Path(config["OUTPUT_DIR"]).resolve()),
        _configured_value(config, settings, "STORAGE_MODE", "storage_mode", "local").lower(),
        _configured_value(config, settings, "STORAGE_BUCKET", "storage_bucket"),
        _configured_value(config, settings, "STORAGE_ACCESS_KEY_ID", "storage_access_key_id"),
        _configured_value(config, settings, "STORAGE_SECRET_ACCESS_KEY", "storage_secret_access_key"),
        _configured_value(config, settings, "STORAGE_ENDPOINT_URL", "storage_endpoint_url"),
        _configured_value(config, settings, "STORAGE_REGION", "storage_region"),
        normalize_prefix(_configured_value(config, settings, "STORAGE_PREFIX", "storage_prefix", "uploads/")),
    )


def get_upload_storage() -> UploadStorage:
    from flask import current_app

    existing = current_app.extensions.get("upload_storage")
    signature = current_app.extensions.get("upload_storage_signature")
    if existing is not None and signature is None:
        return existing

    settings: Mapping[str, object] = {}
    try:
        from huishi.providers import get_app_settings

        settings = get_app_settings(*STORAGE_SETTING_KEYS)
    except Exception as exc:
        if exc.__class__.__name__ not in {"OperationalError", "UndefinedTable"}:
            raise

    next_signature = storage_configuration_signature(current_app.config, settings)
    if existing is None or signature != next_signature:
        existing = build_upload_storage(current_app.config, settings)
        current_app.extensions["upload_storage"] = existing
        current_app.extensions["upload_storage_signature"] = next_signature
    return existing
