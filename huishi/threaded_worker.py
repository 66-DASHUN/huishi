"""并发生成 worker：一容器内 N 进程 × M 线程。

## 为什么需要这个文件

RQ 2.1 **没有**线程池（`rq` 顶层与 `rq.worker` 里都没有 Pool 类），
它的 `Worker.work()` 是单任务循环，而且会注册信号处理——
信号只能装在主线程，所以连"把 work() 丢进线程池"这条路也走不通。

而我们要的是两件事同时成立：
  * **线程扛等待**：一次生成 99% 的时间在等上游，等 socket 时 GIL 会释放，
    线程几乎零成本。256 个并发等待用线程很便宜。
  * **进程扛 CPU**：落盘前要做 decode + PNG 编码（实测约 0.42 秒纯 CPU），
    线程受 GIL 限制无法并行，必须靠多进程吃满多核。

所以这里自己写循环，复用 RQ 的 `Queue.dequeue_any` + `Worker.perform_job`，
保留 RQ 的任务状态、心跳和失败记录，行为与自带 worker 保持一致。

## 形态

    worker_supervisor.py     ← 容器入口：拉起 N 个子进程，子进程死了补一个
        └─ 子进程 × N         ← 每个进程内跑 M 个线程
              └─ 线程 × M      ← 各自从 Redis 认领并执行任务

并发上限 = N × M，全部来自配置：
    HUISHI_GENERATION_IMAGE_PROCESSES / _THREADS   （图片/音频）
    HUISHI_GENERATION_VIDEO_PROCESSES / _THREADS   （视频）

调并发只改环境变量，**不需要改容器数量**。
"""
from __future__ import annotations

import logging
import os
import signal
import sys
import threading
import time
from typing import Any

LOG = logging.getLogger("huishi.worker")


class NoopDeathPenalty:
    """替代 RQ 默认的 `UnixSignalDeathPenalty`。

    后者的 `setup_death_penalty()` 调 `signal.signal` / `signal.alarm`，
    而这两个函数**只能从主线程调用**。我们的任务执行在工作线程里，
    用它会让每个任务立刻抛 ValueError 而全部失败。

    这个空实现不做超时强杀；生成链路本身有上游超时兜底
    （`IMAGE_API_TIMEOUT` / `RQ_JOB_TIMEOUT_SECONDS`）。
    """

    def __init__(self, timeout, exception_class, job_id=None):
        self.timeout = timeout
        self.exception_class = exception_class
        self.job_id = job_id

    def __enter__(self):
        return self

    def __exit__(self, *_exc_info):
        return False


def _make_thread_safe_worker_class():
    """构造一个把 death_penalty_class 换成 noop 的 SimpleWorker 子类。

    延迟到函数里 import，避免模块导入期就依赖 rq（测试环境可能没装）。
    """
    from rq.worker import SimpleWorker

    class ThreadSafeWorker(SimpleWorker):
        death_penalty_class = NoopDeathPenalty

    return ThreadSafeWorker


_ThreadSafeWorker = None


def thread_safe_worker_class():
    global _ThreadSafeWorker
    if _ThreadSafeWorker is None:
        _ThreadSafeWorker = _make_thread_safe_worker_class()
    return _ThreadSafeWorker


def _setup_logging() -> None:
    if not logging.getLogger().handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.INFO)


class ThreadedConsumers:
    """在一个进程里用 M 个线程消费一组队列。"""

    def __init__(
        self,
        app,
        queue_names: list[str],
        *,
        threads: int,
        slot: str,
        dequeue_timeout: int = 2,
    ) -> None:
        self.app = app
        self.queue_names = list(queue_names)
        self.threads = max(1, int(threads))
        self.slot = slot
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._queues: list[Any] = []
        self._workers: list[Any] = []
        # 维护任务（视频租约恢复）只让 0 号线程做，避免 N 个线程重复执行。
        self._last_maintenance = 0.0
        # dequeue_any 的阻塞超时（秒）。取小值是为了让停止信号能在秒级生效，
        # 不会卡在某个长任务上导致容器停不下来。
        self.dequeue_timeout = max(1, int(dequeue_timeout))

    def start(self) -> None:
        from redis import Redis
        from rq import Queue
        from rq.worker import SimpleWorker

        redis_url = str(self.app.config.get("REDIS_URL") or "").strip()
        if not redis_url:
            raise RuntimeError("HUISHI_REDIS_URL must be set before starting generation workers")
        connection = Redis.from_url(redis_url)
        self._queues = [Queue(name, connection=connection) for name in self.queue_names]

        for index in range(self.threads):
            # 每个线程一个 SimpleWorker：SimpleWorker 不 fork，正是"同进程多线程执行"。
            #
            # 用子类把 death_penalty_class 换成 noop。
            #
            # RQ 默认是 `UnixSignalDeathPenalty`，它内部调 `signal.alarm` /
            # `signal.signal`——**只能在主线程调用**。我们的任务在工作线程里跑，
            # 于是每个任务一开始就抛
            # "ValueError: signal only works in main thread of the main interpreter"，
            # 实测四个任务全军覆没。
            #
            # 注：`death_penalty_class` 是**类属性**，不是 `__init__` 参数
            # （传参方式会报 BaseWorker.__init__() got an unexpected keyword），
            # 所以只能用子类覆盖。
            #
            # 代价：失去 RQ 的单任务超时强杀。生成链路本身有上游超时
            # （IMAGE_API_TIMEOUT / RQ_JOB_TIMEOUT_SECONDS）兜底，可以接受。
            worker = thread_safe_worker_class()(
                self._queues,
                connection=connection,
                name=f"{self.slot}-{os.getpid()}-{index}",
            )
            worker.app = self.app
            self._workers.append(worker)
            thread = threading.Thread(
                target=self._consume,
                args=(worker, index),
                name=f"{self.slot}-t{index}",
                daemon=True,
            )
            self._threads.append(thread)
            thread.start()

        LOG.info(
            "%s ready: queues=%s threads=%d pid=%d",
            self.slot, ",".join(self.queue_names), self.threads, os.getpid(),
        )

    def stop(self, timeout: float = 30.0) -> None:
        """通知所有线程退出，并等待它们把手上的任务做完。"""
        self._stop.set()
        deadline = time.monotonic() + max(1.0, timeout)
        for thread in self._threads:
            remaining = max(0.1, deadline - time.monotonic())
            thread.join(timeout=remaining)

    def alive_threads(self) -> int:
        return sum(1 for thread in self._threads if thread.is_alive())

    def _consume(self, worker: Any, thread_index: int) -> None:
        """单线程的任务循环。

        用 `dequeue_any` 配 2 秒超时轮询，而不是阻塞式长等待：
        这样停止信号能在秒级生效，容器不会被某个长任务卡住停不下来。
        """
        import rq
        from rq.exceptions import DequeueTimeout

        while not self._stop.is_set():
            try:
                claimed = rq.Queue.dequeue_any(
                    self._queues,
                    timeout=self.dequeue_timeout,
                    connection=worker.connection,
                    # 同样用 noop：dequeue 阶段虽然不执行死刑，但保持一致，
                    # 免得任务对象上挂着会调 signal 的实现。
                    death_penalty_class=NoopDeathPenalty,
                )
            except DequeueTimeout:
                # **正常情况**：队列空时 dequeue_any 就是抛这个。
                # 早先这里用 except Exception 统一记 exception()，
                # 结果空闲状态下每个线程每个超时周期都刷一条 ERROR 堆栈，
                # 会把真正的错误淹掉。这里单独接住并保持安静。
                self._maintenance(thread_index)
                continue
            except Exception:
                LOG.exception("dequeue failed; retrying shortly")
                self._stop.wait(2.0)
                continue

            if claimed is None:
                self._maintenance(thread_index)
                continue

            job, queue = claimed
            try:
                with self.app.app_context():
                    worker.prepare_job_execution(job)
                    worker.perform_job(job, queue)
            except Exception:
                # 单个任务失败不能让线程退出——否则并发会随时间衰减。
                LOG.exception("job execution failed job_id=%s", getattr(job, "id", "?"))
            finally:
                try:
                    with self.app.app_context():
                        from huishi.db import close_db

                        close_db()
                except Exception:
                    pass

    def _maintenance(self, thread_index: int) -> None:
        """空闲时做周期性维护（每个进程只让 0 号线程做，避免重复执行）。

        这里承担了一件**不能省**的事：`recover_video_tasks` —— 视频任务
        在 worker 崩溃后留下的租约需要被回收重排，否则那条任务永远卡在
        running。原先由 `worker.py` 的 `RecoveringWorker.run_maintenance_tasks`
        负责（每 60 秒一次）；这个自建循环绕过了 RQ 的维护钩子，所以必须
        在这里补回来，否则视频恢复机制会静默失效。
        """
        if thread_index != 0:
            return
        now = time.monotonic()
        if now - self._last_maintenance < 60:
            return
        self._last_maintenance = now
        try:
            from huishi.media_tasks import recover_video_tasks

            with self.app.app_context():
                recover_video_tasks(self.app)
        except Exception:
            # 临时数据库/队列故障不能让线程退出。
            LOG.exception("video recovery maintenance deferred")
        finally:
            try:
                with self.app.app_context():
                    from huishi.db import close_db

                    close_db()
            except Exception:
                pass


def run_slot(app, *, slot: str, queue_names: list[str], processes: int, threads: int) -> int:
    """以「N 进程 × M 线程」运行一个队列组，直到收到终止信号。

    父进程职责：拉起 N 个子进程；子进程意外退出时补一个（保持并发不衰减）；
    收到 SIGTERM 时通知全部子进程优雅退出，超时后强杀。
    """
    _setup_logging()
    processes = max(1, int(processes))
    threads = max(1, int(threads))
    LOG.info(
        "starting %s: %d process(es) x %d thread(s) = %d concurrent slots, queues=%s",
        slot, processes, threads, processes * threads, ",".join(queue_names),
    )

    stopping = threading.Event()

    def _on_term(_signum, _frame):
        LOG.info("%s received stop signal", slot)
        stopping.set()

    signal.signal(signal.SIGTERM, _on_term)
    signal.signal(signal.SIGINT, _on_term)

    children: set[int] = set()

    def _spawn() -> int:
        pid = os.fork()
        if pid != 0:
            return pid

        # ---- 子进程 ----
        exit_code = 0
        try:
            consumers = ThreadedConsumers(app, queue_names, threads=threads, slot=slot)
            consumers.start()

            child_stop = threading.Event()

            def _child_term(_signum, _frame):
                child_stop.set()

            signal.signal(signal.SIGTERM, _child_term)
            signal.signal(signal.SIGINT, _child_term)

            while not child_stop.is_set() and consumers.alive_threads() > 0:
                time.sleep(0.5)
            consumers.stop()
        except Exception:
            LOG.exception("%s child %d crashed", slot, os.getpid())
            exit_code = 1
        finally:
            os._exit(exit_code)

    try:
        for _ in range(processes):
            children.add(_spawn())

        while not stopping.is_set():
            try:
                pid, status = os.waitpid(-1, os.WNOHANG)
            except ChildProcessError:
                break
            if pid == 0:
                stopping.wait(0.5)
                continue
            children.discard(pid)
            if stopping.is_set():
                break
            LOG.warning("%s child pid=%d exited (status=%s); respawning", slot, pid, status)
            children.add(_spawn())
    finally:
        for pid in list(children):
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

        deadline = time.monotonic() + 30
        while children and time.monotonic() < deadline:
            try:
                pid, _status = os.waitpid(-1, os.WNOHANG)
            except ChildProcessError:
                break
            if pid == 0:
                time.sleep(0.2)
                continue
            children.discard(pid)

        for pid in list(children):
            LOG.warning("%s force-killing child pid=%d", slot, pid)
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    return 0
