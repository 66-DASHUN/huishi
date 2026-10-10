"""并发自检用的模块级任务函数。

为什么要单独放一个模块：RQ 明确拒绝入队 `__main__` 里的函数
（"Functions from the __main__ module cannot be processed by workers"），
因为下游 worker 无法 import 它们。所以自检任务必须是可导入的模块函数。

这个模块只用于自检（`probe/selftest_threads.py`），不参与生产逻辑。
"""
from __future__ import annotations

import time


def sleep_echo(seconds: float) -> str:
    """纯等待，模拟"等上游"：CPU 占用为零，用来验证线程并发。"""
    time.sleep(float(seconds))
    try:
        from redis import Redis
        from flask import current_app

        client = Redis.from_url(str(current_app.config.get("REDIS_URL") or ""))
        client.incr("huishi:selftest:done")
    except Exception:
        pass
    return "ok"


def simulate_generation(seconds: float, record_key: str) -> str:
    """模拟一次生成的完整形状：等上游 → 写一条记录。

    用于端到端自检（tools/probe_e2e.py），验证"队列 + 多线程 + 落库"链路。
    """
    import time as _time

    _time.sleep(float(seconds))
    try:
        from flask import current_app
        from huishi.db import get_db

        db = get_db()
        db.execute("INSERT INTO gen_e2e (task_id) VALUES (?)", (record_key,))
        db.commit()
    except Exception:
        pass
    try:
        from redis import Redis

        client = Redis.from_url(str(current_app.config.get("REDIS_URL") or ""))
        client.incr("huishi:selftest:done")
    except Exception:
        pass
    return "ok"
