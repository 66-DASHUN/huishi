
"""Generate /opt/huishi/releases/index.json -- the machine-readable release ledger.

这是 RELEASES.md 的机器可读版本，供脚本消费（例如发布前检查回滚 tag 是否存在）。

部署到服务器（保持与 releases/ 同级，但本文件在版本控制内，不会随
.gitignore 忽略的 releases/ 一起丢失）::

    scp -P 7080 deploy/release_index.py root@<host>:/opt/huishi/releases/_index.py

每次发布后运行::

    ssh -p 7080 root@<host> python3 /opt/huishi/releases/_index.py

它会重写 index.json 并列出不完整的 release（缺 Dockerfile / 脚本 / manifest）。
"""
import json, os, re, subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path("/opt/huishi")
RELEASES = ROOT / "releases"

# 与 RELEASES.md 保持一致的版本类型；未列出的按目录形态推断。
KIND_OVERRIDES = {
    "channel-health-20261006": "正式",
    "duration-range-20260923-1916": "正式",
    "video-pricing-fix-20261002": "正式",
}

def _images(release_dir: Path) -> dict:
    """Read the image tags a release pins from its compose.release.yml."""
    compose = release_dir / "compose.release.yml"
    images = {}
    if not compose.exists():
        return images
    service = None
    for line in compose.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^  (\w[\w-]*):\s*$", line)
        if m:
            service = m.group(1); continue
        m = re.match(r"^\s+image:\s*(\S+)\s*$", line)
        if m and service:
            images[service] = m.group(1)
    return images

def _running() -> dict:
    out = subprocess.run(
        ["docker", "compose", "-f", "compose.prod.yml", "ps", "--format", "{{.Service}} {{.Image}}"],
        cwd=ROOT, capture_output=True, text=True,
    ).stdout
    result = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 2:
            result[parts[0]] = parts[1]
    return result

def _rollback_tags() -> set:
    out = subprocess.run(
        ["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"],
        capture_output=True, text=True,
    ).stdout
    return {line.strip() for line in out.splitlines() if ":rollback" in line}

running = _running()
rollbacks = _rollback_tags()
entries = []
for name in sorted(os.listdir(RELEASES)):
    path = RELEASES / name
    if not path.is_dir() or name.startswith("_"):
        continue
    files = sorted(p.name for p in path.iterdir())
    images = _images(path)
    rollback_tag = next((t for t in rollbacks if name in t), "")
    status = "已取代"
    if any(running.get(svc) in images.values() for svc in images):
        status = "在跑" if any(running.get(svc) == img for svc, img in images.items()) else "部分在跑"
    entries.append({
        "name": name,
        "kind": KIND_OVERRIDES.get(name, "正式"),
        "created_at": datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds"),
        "file_count": len(files),
        "has_dockerfile": any(f.startswith("Dockerfile") for f in files),
        "has_scripts": "prepare.sh" in files and "deploy.sh" in files,
        "has_manifest": any(f.startswith("manifest") for f in files) or "manifest.sha256" in files,
        "images": images,
        "rollback_tag": rollback_tag,
        "status": status,
    })

payload = {
    "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    "running": running,
    "rollback_tags": sorted(rollbacks),
    "releases": entries,
}
target = RELEASES / "index.json"
target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
incomplete = [e["name"] for e in entries if not (e["has_dockerfile"] and e["has_scripts"] and e["has_manifest"])]
print(f"wrote {target} ({len(entries)} releases)")
print(f"不完全的 release（缺 Dockerfile/脚本/manifest）：{len(incomplete)}")
for n in incomplete:
    print("  -", n)
