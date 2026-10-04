from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


Runner = Callable[..., subprocess.CompletedProcess]


def build_pg_dump_command(database_url: str, target: Path) -> list[str]:
    return [
        "pg_dump",
        "--format=custom",
        "--no-owner",
        "--no-acl",
        f"--file={target}",
        database_url,
    ]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_text_atomic(path: Path, text: str, *, encoding: str) -> None:
    partial = path.with_name(f".{path.name}.part")
    partial.write_text(text, encoding=encoding)
    partial.replace(path)


def write_status(
    backup_dir: Path,
    *,
    ok: bool,
    path: Path | None,
    error: str,
    digest: str = "",
) -> None:
    payload = {
        "ok": ok,
        "path": str(path) if path is not None else "",
        "size_bytes": path.stat().st_size if ok and path is not None else 0,
        "sha256": digest if ok else "",
        "error": error,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_text_atomic(
        backup_dir / "status.json",
        json.dumps(payload, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )


def prune_backups(backup_dir: Path, keep: int) -> list[Path]:
    if keep < 1:
        raise ValueError("keep must be at least 1")
    backups = sorted(backup_dir.glob("huishi-*.dump"))
    removed = backups[:-keep]
    for path in removed:
        path.unlink(missing_ok=True)
        path.with_suffix(".dump.sha256").unlink(missing_ok=True)
    return removed


def verify_backup(path: Path) -> str:
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(f"backup is missing or empty: {path}")
    checksum_path = path.with_suffix(".dump.sha256")
    if not checksum_path.is_file():
        raise RuntimeError(f"backup checksum is missing: {checksum_path}")
    fields = checksum_path.read_text(encoding="ascii").strip().split()
    if len(fields) != 2 or fields[1] != path.name:
        raise RuntimeError(f"invalid checksum file: {checksum_path}")
    actual = _sha256(path)
    if fields[0] != actual:
        raise RuntimeError(f"backup checksum mismatch: {path}")
    return actual


def create_backup(
    database_url: str,
    backup_dir: Path,
    keep: int,
    *,
    runner: Runner = subprocess.run,
    now: datetime | None = None,
) -> Path:
    if not database_url.startswith(("postgresql://", "postgres://")):
        raise ValueError("DATABASE_URL must point to PostgreSQL")
    if keep < 1:
        raise ValueError("keep must be at least 1")

    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    final_path = backup_dir / f"huishi-{stamp}.dump"
    partial_path = final_path.with_suffix(".dump.part")
    partial_path.unlink(missing_ok=True)

    try:
        runner(build_pg_dump_command(database_url, partial_path), check=True, timeout=1800)
        if not partial_path.is_file() or partial_path.stat().st_size == 0:
            raise RuntimeError("pg_dump produced an empty backup")
        partial_path.replace(final_path)
        digest = _sha256(final_path)
        _write_text_atomic(
            final_path.with_suffix(".dump.sha256"),
            f"{digest}  {final_path.name}\n",
            encoding="ascii",
        )
        verify_backup(final_path)
        write_status(backup_dir, ok=True, path=final_path, error="", digest=digest)
        prune_backups(backup_dir, keep=keep)
        return final_path
    except Exception as exc:
        partial_path.unlink(missing_ok=True)
        write_status(
            backup_dir,
            ok=False,
            path=None,
            error=f"pg_dump failed: {type(exc).__name__}",
        )
        raise
