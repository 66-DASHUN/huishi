"""验证 ThreadedConsumers 真的并发执行任务。

地基验证：如果线程不能真并发（例如被 GIL 串行化），
"8 进程 × 32 线程 = 256 并发"就是空话。

做法：往独立测试队列塞 N 个"睡 2 秒"的任务，测总墙钟时间。
    串行 => N × 2 秒
    并发 => 约 2 秒

注意：RQ 拒绝入队 __main__ 里的函数（worker 无法 import）。所以用真实
模块中的函数 run_generation_task_from_import_path 的替身——
`huishi.threaded_worker` 里的探针函数。
"""
from __future__ import annotations

import os
import time

os.environ.setdefault("HUISHI_ENV", "test")

from app import create_app
from huishi.threaded_worker import ThreadedConsumers

TEST_QUEUE = "huishi-selftest-threads"
JOBS = 16
SLEEP_SECONDS = 2.0


def main() -> int:
    app = create_app()
    from redis import Redis
    from rq import Queue

    redis_url = str(app.config.get("REDIS_URL") or "").strip()
    if not redis_url:
        print("需要 REDIS_URL")
        return 1
    connection = Redis.from_url(redis_url)
    queue = Queue(TEST_QUEUE, connection=connection)
    queue.empty()

    # 用模块级函数（huishi.selftest_tasks.sleep_echo），worker 才能 import
    for _ in range(JOBS):
        queue.enqueue("huishi.selftest_tasks.sleep_echo", SLEEP_SECONDS,
                      job_timeout=60, result_ttl=10)

    threads = int(os.environ.get("SELFTEST_THREADS", "16"))
    consumers = ThreadedConsumers(app, [TEST_QUEUE], threads=threads, slot="selftest")
    started = time.monotonic()
    consumers.start()

    # 等「完成计数」而不是「队列为空」：任务被认领后队列立刻就空了，
    # 但线程还在执行（每个要睡 2 秒）。等错了指标会立刻判定完成，
    # 得到的计数永远是 0~1。
    deadline = time.monotonic() + 90
    finished = 0
    while time.monotonic() < deadline:
        finished = int(connection.get("huishi:selftest:done") or 0)
        if finished >= JOBS:
            break
        time.sleep(0.2)

    elapsed = time.monotonic() - started
    consumers.stop(timeout=5)

    remaining = int(connection.llen(f"rq:queue:{TEST_QUEUE}"))
    serial = JOBS * SLEEP_SECONDS
    print(f"任务数     : {JOBS}")
    print(f"每任务等待 : {SLEEP_SECONDS}s")
    print(f"线程数     : {threads}")
    print(f"墙钟耗时   : {elapsed:.2f}s")
    print(f"串行预期   : {serial:.1f}s")
    print(f"队列剩余   : {remaining}")
    print(f"完成计数   : {finished}")
    print()

    ok = True
    if remaining != 0:
        print(f"FAIL 还有 {remaining} 个任务没被消费")
        ok = False
    if finished < JOBS:
        print(f"FAIL 只完成 {finished}/{JOBS}")
        ok = False
    if elapsed > serial * 0.5:
        print(f"FAIL 耗时 {elapsed:.1f}s 接近串行（{serial:.1f}s）——线程没有并发")
        ok = False

    queue.empty()
    connection.delete("huishi:selftest:done")
    print("PASS 线程确实并发执行" if ok else "FAIL 见上")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
