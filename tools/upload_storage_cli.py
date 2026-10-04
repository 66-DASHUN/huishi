from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import shutil
import sys
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from huishi.upload_storage import UploadStorage, normalize_prefix, validate_upload_key


@dataclass
class TransferResult:
    copied: int = 0
    skipped: int = 0
    copied_bytes: int = 0
    conflicts: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)


@dataclass
class ComparisonResult:
    local_only: list[str] = field(default_factory=list)
    remote_only: list[str] = field(default_factory=list)
    matching: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _upload_files(directory: Path | str) -> list[Path]:
    root = Path(directory)
    if not root.exists():
        return []
    return sorted(
        item
        for item in root.iterdir()
        if item.is_file() and not item.name.startswith(".") and not item.name.endswith(".partial")
    )


def migrate_local(source: Path | str, target: Path | str) -> TransferResult:
    source_dir = Path(source)
    target_dir = Path(target)
    target_dir.mkdir(parents=True, exist_ok=True)
    result = TransferResult()
    for source_path in _upload_files(source_dir):
        try:
            filename = validate_upload_key(source_path.name)
            target_path = target_dir / filename
            if target_path.exists():
                if sha256_path(source_path) == sha256_path(target_path):
                    result.skipped += 1
                else:
                    result.conflicts.append(filename)
                continue
            partial = target_dir / f".{filename}.{uuid.uuid4().hex}.partial"
            try:
                shutil.copy2(source_path, partial)
                os.replace(partial, target_path)
            finally:
                partial.unlink(missing_ok=True)
            result.copied += 1
            result.copied_bytes += source_path.stat().st_size
        except Exception:
            result.failed.append(source_path.name)
    return result


def sync_to_remote(
    upload_dir: Path | str,
    remote,
    *,
    prefix: str = "uploads/",
    dry_run: bool = False,
) -> TransferResult:
    result = TransferResult()
    object_prefix = normalize_prefix(prefix)
    for local_path in _upload_files(upload_dir):
        try:
            filename = validate_upload_key(local_path.name)
            object_key = f"{object_prefix}{filename}"
            data = local_path.read_bytes()
            if remote.exists(object_key):
                if remote.get(object_key) == data:
                    result.skipped += 1
                else:
                    result.conflicts.append(filename)
                continue
            if not dry_run:
                remote.put(
                    object_key,
                    data,
                    mimetypes.guess_type(filename)[0] or "application/octet-stream",
                )
            result.copied += 1
            result.copied_bytes += len(data)
        except Exception:
            result.failed.append(local_path.name)
    return result


def _remote_names(storage: UploadStorage) -> set[str]:
    if storage.remote is None:
        return set()
    names: set[str] = set()
    for object_key in storage.remote.iter_keys():
        if storage.prefix and not object_key.startswith(storage.prefix):
            continue
        candidate = object_key[len(storage.prefix) :] if storage.prefix else object_key
        try:
            names.add(validate_upload_key(candidate))
        except ValueError:
            continue
    return names


def compare_storage(storage: UploadStorage) -> ComparisonResult:
    if storage.remote is None:
        raise ValueError("remote storage is not configured")
    local_names = {item.name for item in _upload_files(storage.local_dir)}
    remote_names = _remote_names(storage)
    result = ComparisonResult(
        local_only=sorted(local_names - remote_names),
        remote_only=sorted(remote_names - local_names),
    )
    for filename in sorted(local_names & remote_names):
        local_data = (storage.local_dir / filename).read_bytes()
        if storage.remote.get(storage.object_key(filename)) == local_data:
            result.matching.append(filename)
        else:
            result.conflicts.append(filename)
    return result


def restore_missing(storage: UploadStorage, *, dry_run: bool = False) -> TransferResult:
    if storage.remote is None:
        raise ValueError("remote storage is not configured")
    result = TransferResult()
    for filename in sorted(_remote_names(storage)):
        target = storage.local_path(filename)
        if target.is_file():
            result.skipped += 1
            continue
        if not dry_run:
            restored = storage.ensure_local(filename)
            result.copied_bytes += restored.stat().st_size
        result.copied += 1
    return result


def _configured_storage_context():
    from app import create_app
    from huishi.db import init_db
    from huishi.upload_storage import get_upload_storage

    app = create_app()
    context = app.app_context()
    context.push()
    init_db()
    return context, get_upload_storage()


def _print_result(result) -> None:
    print(json.dumps(asdict(result), ensure_ascii=False, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="upload-storage")
    commands = parser.add_subparsers(dest="command", required=True)
    migrate = commands.add_parser("migrate-local")
    migrate.add_argument("--source", required=True)
    migrate.add_argument("--target", required=True)
    sync = commands.add_parser("sync")
    sync.add_argument("--direction", choices=["local-to-remote"], required=True)
    sync.add_argument("--dry-run", action="store_true")
    commands.add_parser("compare")
    restore = commands.add_parser("restore")
    restore.add_argument("--missing-only", action="store_true")
    restore.add_argument("--dry-run", action="store_true")
    commands.add_parser("healthcheck")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "migrate-local":
        result = migrate_local(args.source, args.target)
        _print_result(result)
        return 2 if result.conflicts or result.failed else 0

    context, storage = _configured_storage_context()
    try:
        if args.command == "sync":
            if storage.remote is None:
                raise ValueError("remote storage is not configured")
            _print_result(
                sync_to_remote(
                    storage.local_dir,
                    storage.remote,
                    prefix=storage.prefix,
                    dry_run=args.dry_run,
                )
            )
        elif args.command == "compare":
            _print_result(compare_storage(storage))
        elif args.command == "restore":
            _print_result(restore_missing(storage, dry_run=args.dry_run))
        else:
            storage.healthcheck()
            print(json.dumps({"ok": True}, sort_keys=True))
    finally:
        context.pop()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1) from exc
