from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


Runner = Callable[..., subprocess.CompletedProcess]


# 连接串里的口令绝不能进 status.json —— 该文件留在磁盘上、也可能被后台页面读走。
# 注意捕获组只留 scheme://user:，把口令整段替换掉。
_URL_PASSWORD_PATTERN = re.compile(r"(?P<prefix>[a-zA-Z][a-zA-Z0-9+.-]*://[^:/@\s]+):[^@/\s]*@")


def redact_database_url(text: str) -> str:
    """把连接串里的口令替换为 ***，其余原样保留。"""
    return _URL_PASSWORD_PATTERN.sub(lambda m: f"{m.group('prefix')}:***@", text or "")


def _pg_dump_failure_detail(exc: BaseException) -> str:
    """提炼可行动的错误描述，并保证不泄露连接串口令。

    只写异常类型名/只写 ``CalledProcessError`` 是没有信息量的——运维看到
    status.json 里那一行无法判断是口令错了、库不存在，还是磁盘满了。
    pg_dump 的真实原因在 stderr，所以优先取它；取不到再退回 str(exc)。
    绝不用 ``exc.cmd``：那是完整命令行，含 DATABASE_URL。
    """
    detail = ""
    if isinstance(exc, subprocess.CalledProcessError):
        stderr = exc.stderr or b""
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", "replace")
        detail = str(stderr).strip()
    if not detail:
        detail = str(exc).strip()
    # 压缩成单行，避免 status.json 里塞进多行堆栈。
    detail = " ".join(detail.split())
    if len(detail) > 500:
        detail = detail[:500] + "..."
    return redact_database_url(detail)


# backend 镜像基于 python:3.12-slim，只装了 ffmpeg —— 容器内**没有**
# pg_dump。因此 `flask backup-postgres` 在这里必然失败。生产备份走宿主侧
# 的 /usr/local/bin/huishi-db-backup（见 docs/product/runbooks/backup-restore.md）。
PG_DUMP_MISSING_HINT = (
    "容器内没有 pg_dump，无法在此执行 PostgreSQL 备份。"
    "生产备份由宿主侧脚本 /usr/local/bin/huishi-db-backup 完成"
    "（cron 每天 10:40 本地时间），恢复步骤见 "
    "docs/product/runbooks/backup-restore.md。"
)


def pg_dump_available() -> bool:
    """pg_dump 是否可在当前环境执行（用于在失败前给出可读原因）。"""
    return shutil.which("pg_dump") is not None


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
    probe: Callable[[], bool] = pg_dump_available,
) -> Path:
    if not database_url.startswith(("postgresql://", "postgres://")):
        raise ValueError("DATABASE_URL must point to PostgreSQL")
    if keep < 1:
        raise ValueError("keep must be at least 1")

    # 显式前置检查：原先这里会直接 subprocess.run 失败，只在 status.json 里
    # 留下一行 "pg_dump failed: FileNotFoundError"，运维看不出原因也无法行动。
    if not probe():
        write_status(backup_dir, ok=False, path=None, error="pg_dump not installed")
        raise RuntimeError(PG_DUMP_MISSING_HINT)

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
            error=f"pg_dump failed: {type(exc).__name__}: {_pg_dump_failure_detail(exc)}",
        )
        raise
