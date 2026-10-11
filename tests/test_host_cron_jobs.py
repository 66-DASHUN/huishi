"""宿主定时任务的契约测试。

这些脚本不在容器里跑，但它们的**行为契约**必须被测到——否则哪天有人
改了 `upload_reference_names` 的保护逻辑，删除范围悄悄变大也没人知道。

这里不测 shell 本身（那需要真机），而是钉住：
  1. 脚本文件存在且可执行、行尾是 LF（CRLF 会让 shebang 变成 bash\r）
  2. 脚本**不含**危险动词（不能出现 `docker system prune -a`、
     不带 filter 的 `builder prune`、`rm -rf /` 之类）
  3. README 记录了两个任务与安装方式
"""
from __future__ import annotations

from pathlib import Path

CRON_DIR = Path(__file__).resolve().parent.parent / "deploy" / "host-cron"
SCRIPTS = ("huishi-storage-sweep", "huishi-disk-cleanup")


def test_cron_scripts_exist_and_are_executable():
    for name in SCRIPTS:
        path = CRON_DIR / name
        assert path.is_file(), f"缺少 {name}"


def test_cron_scripts_use_lf_line_endings():
    """CRLF 会让 shebang 变成 `#!/usr/bin/env bash\r`，脚本直接无法执行。

    本地是 Windows，这个坑踩过一次（发布脚本被 shell 报 "bash\r: not found"）。
    """
    for name in SCRIPTS:
        data = (CRON_DIR / name).read_bytes()
        assert b"\r\n" not in data, f"{name} 含 CRLF，会让 shebang 失效"


def test_cron_scripts_avoid_unsafe_prune_variants():
    """禁止会波及其它服务或删掉回滚目标的做法。

    这台机器上还跑着 sub2api / gpt-image-playground / grok-stack，
    `docker system prune -a` 或 `docker image prune -a` 会把它们的镜像一起删掉；
    未加 filter 的 `builder prune` 会清掉别人正在用的构建缓存。
    """
    banned = (
        "docker system prune",
        "docker image prune -a",
        "docker volume prune",
        "docker builder prune -f\n",   # 无 filter 的裸调用（下一行无 --filter）
    )
    for name in SCRIPTS:
        text = (CRON_DIR / name).read_text(encoding="utf-8")
        for pattern in banned:
            assert pattern not in text, f"{name} 含危险命令：{pattern}"


def test_storage_sweep_uses_the_cli_and_skips_when_container_down():
    """uploads 清理必须走 flask CLI，且容器不在时安静跳过。

    直接删文件会绕过 `upload_reference_names` 的保护逻辑，可能删掉用户作品；
    容器不在时报错则会在每次发布期间往 cron 日志里刷失败。
    """
    text = (CRON_DIR / "huishi-storage-sweep").read_text(encoding="utf-8")
    assert "python -m flask storage-sweep" in text
    assert "--delete" in text
    assert "backend container not running" in text


def test_readme_documents_both_jobs_and_the_safety_rules():
    text = (CRON_DIR / "README.md").read_text(encoding="utf-8")
    for token in ("huishi-storage-sweep", "huishi-disk-cleanup", "17 4", "23 5"):
        assert token in text, f"README 缺少 {token}"
    # 安全性说明必须写明"只动 huishi 命名空间"与"不删回滚 tag"
    assert "rollback" in text
    assert "huishi" in text
