from __future__ import annotations

from pathlib import Path


TEXT_SUFFIXES = {
    ".css",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".md",
    ".mjs",
    ".ps1",
    ".py",
    ".service",
    ".sh",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
SKIP_PARTS = {
    ".git",
    ".next",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "node_modules",
}


def find_encoding_errors(root: Path) -> list[str]:
    root = root.resolve()
    errors: list[str] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(root)
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if any(part in SKIP_PARTS for part in relative.parts):
            continue
        if len(relative.parts) >= 2 and relative.parts[:2] == ("static", "uploads"):
            continue
        try:
            path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            errors.append(f"{relative.as_posix()}: invalid UTF-8")
    return errors


def main() -> int:
    errors = find_encoding_errors(Path.cwd())
    if errors:
        print("\n".join(errors))
        return 1
    print("UTF-8 check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
