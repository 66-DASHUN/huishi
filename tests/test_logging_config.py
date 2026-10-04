from __future__ import annotations

from datetime import date
import logging

from app import configure_daily_file_logging


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
