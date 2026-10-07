from __future__ import annotations

from datetime import date
import logging

from app import DailyFileHandler, configure_daily_file_logging


def test_daily_file_logging_writes_to_date_named_file(tmp_path):
    log_dir = tmp_path / "logs"

    handler = configure_daily_file_logging(log_dir=log_dir, today=lambda: date(2026, 6, 18))
    try:
        logging.getLogger("huishi.test").error("daily file probe")
    finally:
        logging.getLogger().removeHandler(handler)
        handler.close()

    log_file = log_dir / "huishi-2026-06-18.log"
    assert log_file.exists()
    assert "daily file probe" in log_file.read_text(encoding="utf-8")


def test_repeated_configuration_does_not_stack_handlers(tmp_path):
    """反复调用不能堆积文件 handler。

    缺陷背景：RQ 的 job 是 ``run_generation_task_from_import_path('app:create_app', ...)``，
    **每个任务都会 create_app() 一次**，而 root logger 的 handler 是进程级的、
    不会被回收。原先无条件 addHandler，于是每处理一个任务就多一个文件 handler：
    日志被写 N 遍（2026-10-06 的生产日志里同一条 traceback 出现两次），
    每个 handler 还各持一个打开的文件流。worker 长期运行，只增不减。
    """
    log_dir = tmp_path / "logs"
    root = logging.getLogger()
    before = [h for h in root.handlers if isinstance(h, DailyFileHandler)]
    try:
        for _ in range(5):
            configure_daily_file_logging(log_dir=log_dir, today=lambda: date(2026, 6, 18))

        ours = [h for h in root.handlers if isinstance(h, DailyFileHandler)]
        assert len(ours) == 1, f"应只保留一个文件 handler，实际 {len(ours)} 个"
    finally:
        for handler in [h for h in root.handlers if isinstance(h, DailyFileHandler)]:
            root.removeHandler(handler)
            handler.close()
        for handler in before:
            root.addHandler(handler)


def test_repeated_configuration_writes_each_record_once(tmp_path):
    """重复配置后，一条日志在文件里只应出现一次。"""
    log_dir = tmp_path / "logs"
    root = logging.getLogger()
    before = [h for h in root.handlers if isinstance(h, DailyFileHandler)]
    try:
        for _ in range(4):
            configure_daily_file_logging(log_dir=log_dir, today=lambda: date(2026, 6, 18))
        logging.getLogger("huishi.test").error("dedupe probe")
    finally:
        for handler in [h for h in root.handlers if isinstance(h, DailyFileHandler)]:
            root.removeHandler(handler)
            handler.close()
        for handler in before:
            root.addHandler(handler)

    text = (log_dir / "huishi-2026-06-18.log").read_text(encoding="utf-8")
    assert text.count("dedupe probe") == 1, text


def test_old_handler_is_closed_when_reconfigured(tmp_path):
    """被摘掉的 handler 必须关闭，否则文件流会泄漏。"""
    log_dir = tmp_path / "logs"
    root = logging.getLogger()
    before = [h for h in root.handlers if isinstance(h, DailyFileHandler)]
    try:
        first = configure_daily_file_logging(log_dir=log_dir, today=lambda: date(2026, 6, 18))
        logging.getLogger("huishi.test").error("open the stream")
        assert first.stream is not None, "写日志后文件流应已打开"

        configure_daily_file_logging(log_dir=log_dir, today=lambda: date(2026, 6, 18))
        assert first.stream is None, "重建时旧 handler 的文件流必须关闭"
    finally:
        for handler in [h for h in root.handlers if isinstance(h, DailyFileHandler)]:
            root.removeHandler(handler)
            handler.close()
        for handler in before:
            root.addHandler(handler)


def test_unexpected_generation_failure_records_a_diagnosable_reason():
    """未预期异常不能只留一句没有信息量的兜底文案。

    缺陷背景：`generation_queue` 的 catch-all 分支原先写死
    "生成结果保存失败"，真实堆栈只进容器日志。2026-10-06 排查一批失败时，
    只能靠翻 worker 的按天日志才定位到是 task_id 被透传进 generate_image()
    引发 TypeError——而日志一旦轮转或容器重建，现场就没了。

    这里只验证"文案里带上了异常类型"这一契约；落库与展示的脱敏由
    ``sanitize_generation_error_message`` 负责（既有路径本来就把异常原文写进
    error_message，展示时才脱敏）。
    """
    import inspect

    import huishi.generation_queue as gq

    source = inspect.getsource(gq.run_generation_task)
    # 用异常类型拼出可诊断的细节
    assert "type(exc).__name__" in source, "兜底分支应带上异常类型"
    # 入库前必须过脱敏
    assert "sanitize_generation_error_message" in source, "入库前必须脱敏"
    # 定性说明仍保留，便于用户理解
    assert "生成结果保存失败" in source
