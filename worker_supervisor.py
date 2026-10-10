"""容器入口：按配置以「N 进程 × M 线程」运行一个队列组。

用法（由 compose 的 command 指定）：
    python worker_supervisor.py image     # 图片/音频队列
    python worker_supervisor.py video     # 视频队列

进程数与线程数全部来自环境变量，**调并发不需要改容器数量**：
    HUISHI_GENERATION_IMAGE_PROCESSES / HUISHI_GENERATION_IMAGE_THREADS
    HUISHI_GENERATION_VIDEO_PROCESSES / HUISHI_GENERATION_VIDEO_THREADS

之所以不直接用 `rq` 自带的 worker 命令：RQ 一个进程只能跑一个任务
（`Worker.work()` 是单任务循环且要装信号），要提到几百并发就得开几百个
容器。这里把并发做进进程内部，容器数固定为 2 个。
"""
from __future__ import annotations

import sys

from app import create_app
from huishi.generation_queue import generation_queue_names
from huishi.threaded_worker import run_slot


def main() -> int:
    slot = (sys.argv[1] if len(sys.argv) > 1 else "image").strip().lower()
    if slot not in {"image", "video"}:
        print(f"未知的 worker 角色: {slot!r}（应为 image 或 video）", file=sys.stderr)
        return 2

    app = create_app()
    image_queue, video_queue = generation_queue_names(app)

    if slot == "video":
        queue_names = [video_queue]
        processes = int(app.config.get("GENERATION_VIDEO_PROCESSES", 2))
        threads = int(app.config.get("GENERATION_VIDEO_THREADS", 8))
    else:
        queue_names = [image_queue]
        processes = int(app.config.get("GENERATION_IMAGE_PROCESSES", 8))
        threads = int(app.config.get("GENERATION_IMAGE_THREADS", 32))

    return run_slot(app, slot=slot, queue_names=queue_names, processes=processes, threads=threads)


if __name__ == "__main__":
    raise SystemExit(main())
