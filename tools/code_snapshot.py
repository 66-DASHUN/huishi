from __future__ import annotations

import gzip
import hashlib
import re
import tarfile
from pathlib import Path


EXCLUDED_PARTS = {
    ".git",
    ".venv",
    ".bun",
    ".cache",
    ".next",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    "uploads",
}
EXCLUDED_ROOT_PARTS = {"data", "logs"}
SAFE_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def include_path(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    if not relative.parts:
        return True
    if relative.parts[0] in EXCLUDED_ROOT_PARTS:
        return False
    for part in relative.parts:
        if part in EXCLUDED_PARTS or part == ".env" or part.startswith(".env."):
            return False
    return True


def _normalized_tar_info(info: tarfile.TarInfo) -> tarfile.TarInfo:
    info.uid = 0
    info.gid = 0
    info.uname = "root"
    info.gname = "root"
    info.mtime = 0
    return info


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_snapshot(source: Path, backup_dir: Path, label: str) -> Path:
    source = source.resolve()
    backup_dir = backup_dir.resolve()
    if not source.is_dir():
        raise ValueError(f"source directory does not exist: {source}")
    if backup_dir == source or backup_dir.is_relative_to(source):
        raise ValueError("backup directory must be outside the source tree")
    if SAFE_LABEL.fullmatch(label) is None:
        raise ValueError("snapshot label must contain only letters, numbers, dots, dashes, or underscores")

    backup_dir.mkdir(parents=True, exist_ok=True)
    archive = backup_dir / f"huishi-code-{label}.tar.gz"
    partial = Path(f"{archive}.part")
    partial.unlink(missing_ok=True)

    try:
        with partial.open("wb") as raw_stream:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw_stream, mtime=0) as gzip_stream:
                with tarfile.open(fileobj=gzip_stream, mode="w") as tar:
                    tar.add(source, arcname=source.name, recursive=False, filter=_normalized_tar_info)
                    for path in sorted(source.rglob("*"), key=lambda item: item.as_posix()):
                        if include_path(path, source):
                            tar.add(
                                path,
                                arcname=f"{source.name}/{path.relative_to(source).as_posix()}",
                                recursive=False,
                                filter=_normalized_tar_info,
                            )
        partial.replace(archive)
    except Exception:
        partial.unlink(missing_ok=True)
        raise

    digest = _sha256(archive)
    checksum_path = Path(f"{archive}.sha256")
    checksum_partial = Path(f"{checksum_path}.part")
    checksum_partial.write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    checksum_partial.replace(checksum_path)
    return archive


def verify_snapshot(archive: Path) -> str:
    if not archive.is_file() or archive.stat().st_size == 0:
        raise RuntimeError(f"snapshot is missing or empty: {archive}")
    checksum_path = Path(f"{archive}.sha256")
    if not checksum_path.is_file():
        raise RuntimeError(f"snapshot checksum is missing: {checksum_path}")
    fields = checksum_path.read_text(encoding="ascii").strip().split()
    if len(fields) != 2 or fields[1] != archive.name:
        raise RuntimeError(f"invalid snapshot checksum file: {checksum_path}")
    actual = _sha256(archive)
    if fields[0] != actual:
        raise RuntimeError(f"snapshot checksum mismatch: {archive}")
    return actual
