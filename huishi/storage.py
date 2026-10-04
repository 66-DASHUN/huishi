from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from sqlite3 import Connection


UPLOAD_PREFIX = "/static/uploads/"


@dataclass
class StorageSweepResult:
    total_files: int = 0
    total_bytes: int = 0
    referenced_files: int = 0
    hidden_files: int = 0
    orphan_files: int = 0
    deleted_files: list[str] = field(default_factory=list)
    deleted_bytes: int = 0
    retained_orphan_files: list[str] = field(default_factory=list)
    retained_hidden_files: list[str] = field(default_factory=list)
    max_bytes: int | None = None
    max_delete_files: int | None = None
    min_age_seconds: int = 300
    delete_limit_reached: bool = False
    remaining_deletable_files: int = 0
    retained_due_to_delete_limit: list[str] = field(default_factory=list)
    over_capacity_bytes: int = 0
    capacity_warning: bool = False
    dry_run: bool = False


def sweep_local_uploads(
    output_dir: Path | str,
    db: Connection,
    *,
    retention_seconds: int,
    orphan_retention_seconds: int | None = None,
    hidden_retention_seconds: int | None = None,
    max_bytes: int | None = None,
    batch_size: int | None = None,
    max_delete_files: int | None = None,
    min_age_seconds: int = 300,
    dry_run: bool = False,
    now: float | None = None,
    storage=None,
) -> StorageSweepResult:
    output_path = Path(output_dir).resolve()
    if max_delete_files is None:
        max_delete_files = 20000
    delete_limit = None if int(max_delete_files) <= 0 else int(max_delete_files)
    min_age = max(0, int(min_age_seconds))
    result = StorageSweepResult(max_bytes=max_bytes, max_delete_files=delete_limit, min_age_seconds=min_age, dry_run=dry_run)
    if not output_path.exists():
        return result

    protected_names, hidden_names = upload_reference_names(db)
    now_value = time.time() if now is None else now
    orphan_cutoff = now_value - max(0, int(orphan_retention_seconds if orphan_retention_seconds is not None else retention_seconds))
    hidden_cutoff = now_value - max(0, int(hidden_retention_seconds if hidden_retention_seconds is not None else retention_seconds))
    files = sorted(
        (path for path in output_path.iterdir() if path.is_file() and not path.name.startswith(".")),
        key=lambda item: item.stat().st_mtime,
    )
    result.total_files = len(files)

    for file_path in files:
        stat = file_path.stat()
        result.total_bytes += stat.st_size
        upload_path = path_to_upload_url(output_path, file_path)
        if file_path.name in protected_names:
            result.referenced_files += 1
            continue

        is_hidden = file_path.name in hidden_names
        cutoff = hidden_cutoff if is_hidden else orphan_cutoff
        retained_files = result.retained_hidden_files if is_hidden else result.retained_orphan_files
        if is_hidden:
            result.hidden_files += 1
        else:
            result.orphan_files += 1

        if now_value - stat.st_mtime < min_age:
            retained_files.append(upload_path)
            continue
        if stat.st_mtime > cutoff:
            retained_files.append(upload_path)
            continue
        if delete_limit is not None and len(result.deleted_files) >= delete_limit:
            result.delete_limit_reached = True
            result.remaining_deletable_files += 1
            result.retained_due_to_delete_limit.append(upload_path)
            retained_files.append(upload_path)
            continue
        result.deleted_files.append(upload_path)
        result.deleted_bytes += stat.st_size
        if not dry_run:
            if storage is None:
                file_path.unlink(missing_ok=True)
            else:
                storage.delete(file_path.name)

    if max_bytes is not None and result.total_bytes - result.deleted_bytes > int(max_bytes):
        result.capacity_warning = True
        result.over_capacity_bytes = result.total_bytes - result.deleted_bytes - int(max_bytes)
    return result


def referenced_upload_names(db: Connection) -> set[str]:
    protected_names, _hidden_names = upload_reference_names(db)
    return protected_names


def upload_reference_names(db: Connection) -> tuple[set[str], set[str]]:
    protected_names: set[str] = set()
    hidden_names: set[str] = set()
    for row in db.execute("SELECT image_path, image_paths, reference_paths, hidden FROM records"):
        row_names = set()
        row_names.update(upload_names_from_value(row["image_path"]))
        row_names.update(upload_names_from_value(row["image_paths"]))
        row_names.update(upload_names_from_value(row["reference_paths"]))
        if int(row["hidden"] or 0):
            hidden_names.update(row_names)
        else:
            protected_names.update(row_names)
    for row in db.execute("SELECT id, reference_paths FROM generation_tasks WHERE status IN ('queued', 'running')"):
        protected_names.update(upload_names_from_value(row["reference_paths"]))
        protected_names.add(f"video_task_{row['id']}.mp4")
    from huishi.db_backend import PostgreSQLConnection
    table_sql = "SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name='media_reference_assets'" if isinstance(db, PostgreSQLConnection) else "SELECT name FROM sqlite_master WHERE type='table' AND name='media_reference_assets'"
    if db.execute(table_sql).fetchone():
        for row in db.execute('SELECT storage_key FROM media_reference_assets'):
            protected_names.add(row['storage_key'])
    for row in db.execute("SELECT asset_ref FROM canvas_project_assets"):
        protected_names.update(upload_names_from_value(row["asset_ref"]))
    return protected_names, hidden_names - protected_names


def _referenced_upload_names_legacy(db: Connection) -> set[str]:
    names: set[str] = set()
    for row in db.execute("SELECT image_path, image_paths, reference_paths FROM records WHERE hidden = 0"):
        names.update(upload_names_from_value(row["image_path"]))
        names.update(upload_names_from_value(row["image_paths"]))
        names.update(upload_names_from_value(row["reference_paths"]))
    for row in db.execute("SELECT reference_paths FROM generation_tasks WHERE status IN ('queued', 'running')"):
        names.update(upload_names_from_value(row["reference_paths"]))
    return names


def upload_names_from_value(value) -> set[str]:
    paths: list[str] = []
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                parsed = []
            if isinstance(parsed, list):
                paths.extend(str(item) for item in parsed)
        else:
            paths.append(stripped)
    elif isinstance(value, list):
        paths.extend(str(item) for item in value)
    return {Path(path.removeprefix(UPLOAD_PREFIX)).name for path in paths if path.startswith(UPLOAD_PREFIX)}


def path_to_upload_url(output_dir: Path, file_path: Path) -> str:
    try:
        relative = file_path.resolve().relative_to(output_dir.resolve())
    except ValueError:
        return f"{UPLOAD_PREFIX}{file_path.name}"
    return f"{UPLOAD_PREFIX}{relative.as_posix()}"
