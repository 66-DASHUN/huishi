from __future__ import annotations

from tools.check_encoding import find_encoding_errors


def test_find_encoding_errors_reports_invalid_utf8(tmp_path):
    (tmp_path / "good.py").write_text("绘世", encoding="utf-8")
    (tmp_path / "bad.txt").write_bytes(b"\xff\xfe")

    assert find_encoding_errors(tmp_path) == ["bad.txt: invalid UTF-8"]


def test_find_encoding_errors_skips_generated_directories(tmp_path):
    generated = tmp_path / "node_modules" / "bad.js"
    generated.parent.mkdir()
    generated.write_bytes(b"\xff")

    assert find_encoding_errors(tmp_path) == []
