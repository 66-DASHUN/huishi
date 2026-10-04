from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path


TEXT_SUFFIXES = {".css", ".html", ".js", ".json", ".md", ".mjs", ".ts", ".tsx"}
SKIP_PARTS = {".git", ".next", ".venv", "node_modules", "__pycache__"}
HOME_ASSET_BUDGETS = {
    "static/js/home.compiled.js": 300_000,
    "static/css/home-tailwind.css": 40_000,
    "static/media/shouyeshipin-sea.mp4": 9_000_000,
    "static/media/shouyeshipin-poster.jpg": 180_000,
    "static/media/huishi-workflow.mp4": 6_700_000,
    "static/media/huishi-workflow-poster.jpg": 180_000,
}


def check_budgets(root: Path, budgets: Mapping[str, int]) -> list[str]:
    failures: list[str] = []
    for relative_name, limit in sorted(budgets.items()):
        path = root / relative_name
        if not path.is_file():
            failures.append(f"{relative_name}: missing")
            continue
        size = path.stat().st_size
        if size > limit:
            failures.append(f"{relative_name}: {size} bytes exceeds {limit}")
    return failures


def find_references(roots: Iterable[Path], needle: str) -> list[str]:
    references: list[str] = []
    for root in roots:
        candidates = [root] if root.is_file() else root.rglob("*")
        for path in sorted(candidates, key=lambda item: item.as_posix()):
            if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            if any(part in SKIP_PARTS for part in path.parts):
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if needle in content:
                references.append(path.as_posix())
    return references


def main() -> int:
    failures = check_budgets(Path.cwd(), HOME_ASSET_BUDGETS)
    references = find_references(
        [Path("templates"), Path("static/js"), Path("static/css")],
        "shouyeshipin-home.mp4",
    )
    failures.extend(f"legacy video reference: {path}" for path in references)
    if failures:
        print("\n".join(failures))
        return 1
    for relative_name, limit in sorted(HOME_ASSET_BUDGETS.items()):
        size = (Path.cwd() / relative_name).stat().st_size
        print(f"{relative_name}: {size}/{limit} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
