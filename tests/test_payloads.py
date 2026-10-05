"""Tests for huishi.payloads.

These functions define the JSON the frontend receives and how form strings are
coerced. The extraction from routes_workspace was validated by comparing
outputs before and after across dict and sqlite3.Row inputs; these tests pin
the parts that are easy to break, especially the difference between ``row[...]``
and ``row.get(...)`` — a sqlite3.Row supports the former but not the latter.
"""
from __future__ import annotations

import sqlite3

import pytest

from huishi import payloads

RECORD_COLUMNS = [
    "id", "dialogue_id", "generation_group_id", "group_index", "prompt",
    "image_path", "image_paths", "mode", "ratio", "resolution", "actual_size",
    "quality", "output_format", "count", "model_source", "elapsed_seconds",
    "points_charged", "reference_paths", "asset_source", "media_type",
    "mime_type", "duration_ms", "favorite", "created_at",
]

FULL_RECORD = {
    "id": 1, "dialogue_id": 5, "generation_group_id": "g1", "group_index": 0,
    "prompt": "p", "image_path": "/a.png", "image_paths": '["/a.png"]',
    "mode": "text", "ratio": "16:9", "resolution": "2K",
    "actual_size": "2560x1440", "quality": "auto", "output_format": "png",
    "count": 1, "model_source": "gpt-image-2", "elapsed_seconds": 1.5,
    "points_charged": 3, "reference_paths": "[]", "asset_source": "image",
    "media_type": "image", "mime_type": "image/png", "duration_ms": 0,
    "favorite": 0, "created_at": "2026-01-01",
}


def sqlite_row(record: dict):
    """Build a real sqlite3.Row, which supports [] and keys() but not .get()."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    columns = list(record.keys())
    conn.execute(f"CREATE TABLE t ({','.join(columns)})")
    conn.execute(
        f"INSERT INTO t VALUES ({','.join('?' * len(columns))})", list(record.values())
    )
    return conn.execute("SELECT * FROM t").fetchone()


class TestSerializeRecord:
    def test_serializes_a_full_row(self):
        result = payloads.serialize_record(dict(FULL_RECORD))
        assert result["id"] == 1
        assert result["dialogue_id"] == 5
        assert result["images"] == FULL_RECORD["image_paths"]
        assert result["duration_ms"] == 0

    def test_requires_a_mapping_that_supports_get(self):
        """The serializer reads optional fields with .get().

        Production uses PostgreSQL with ``row_factory=dict_row``, so rows are
        plain dicts and support .get(). A bare sqlite3.Row does not, so this
        documents the contract rather than asserting Row compatibility.
        """
        result = payloads.serialize_record(dict(FULL_RECORD))
        assert result["id"] == 1
        assert result["media_type"] == "image"
        with pytest.raises(AttributeError):
            payloads.serialize_record(sqlite_row(FULL_RECORD))

    def test_optional_asset_fields_fall_back_when_absent(self):
        minimal = {k: v for k, v in FULL_RECORD.items()
                   if k not in ("dialogue_id", "asset_source", "media_type", "mime_type", "duration_ms")}
        result = payloads.serialize_record(minimal)
        assert result["dialogue_id"] is None
        assert result["asset_source"] == "image"
        assert result["media_type"] == "image"
        assert result["mime_type"] == ""
        assert result["duration_ms"] == 0

    def test_media_type_falls_back_to_asset_source(self):
        record = dict(FULL_RECORD, media_type="", asset_source="video")
        assert payloads.serialize_record(record)["media_type"] == "video"

    def test_duration_ms_is_coerced_to_int(self):
        record = dict(FULL_RECORD, duration_ms="2500")
        assert payloads.serialize_record(record)["duration_ms"] == 2500

    def test_duration_ms_none_becomes_zero(self):
        record = dict(FULL_RECORD, duration_ms=None)
        assert payloads.serialize_record(record)["duration_ms"] == 0

    def test_normalized_row_matches_normalized_dict(self):
        """All normal call sites pass records.normalize_record() output.

        normalize_record does dict(row) and then parses the JSON-encoded
        image_paths/reference_paths columns into lists, so its result differs
        from the raw dict. What must hold is that the same record produces the
        same payload whichever row type the database returned.
        """
        from huishi.records import normalize_record

        from_row = payloads.serialize_record(normalize_record(sqlite_row(FULL_RECORD)))
        from_dict = payloads.serialize_record(normalize_record(dict(FULL_RECORD)))

        assert from_row == from_dict
        # And normalization is visible: JSON columns become lists.
        assert from_row["images"] == ["/a.png"]
        assert from_row["reference_paths"] == []


class TestSerializeDialogue:
    def test_serializes_expected_keys(self):
        result = payloads.serialize_dialogue(
            {"id": 3, "title": "t", "created_at": "c", "updated_at": "u"}
        )
        assert result == {"id": 3, "title": "t", "created_at": "c", "updated_at": "u"}

    def test_works_with_a_sqlite_row_because_it_only_indexes(self):
        """Unlike serialize_record, this one only uses row[...], so a Row is fine."""
        row = sqlite_row({"id": 3, "title": "t", "created_at": "c", "updated_at": "u"})
        assert payloads.serialize_dialogue(row)["id"] == 3


class TestParseOptionalInt:
    def test_empty_values_mean_absent(self):
        for value in (None, "", "   "):
            assert payloads.parse_optional_int(value) is None

    @pytest.mark.parametrize("value,expected", [("1", 1), ("0", 0), ("-5", -5), ("  42  ", 42)])
    def test_parses_integers(self, value, expected):
        assert payloads.parse_optional_int(value) == expected

    @pytest.mark.parametrize("value", ["abc", "3.5"])
    def test_invalid_values_raise_a_stale_form_error(self, value):
        with pytest.raises(ValueError, match="对话参数无效"):
            payloads.parse_optional_int(value)


class TestIsHttpUrl:
    @pytest.mark.parametrize("url", ["http://a.com", "https://b.com/x", "https://x:8080/p?q=1"])
    def test_accepts_http_and_https(self, url):
        assert payloads.is_http_url(url)

    @pytest.mark.parametrize("url", ["ftp://c", "//d.com", "", "not a url", "http://", "javascript:alert(1)"])
    def test_rejects_everything_else(self, url):
        assert not payloads.is_http_url(url)

    def test_handles_none(self):
        assert not payloads.is_http_url(None)


class TestFormatFileSizeLimit:
    @pytest.mark.parametrize(
        "size,expected",
        [(0, "0B"), (512, "512B"), (1024, "1KB"), (1024 * 1024, "1MB"), (12 * 1024 * 1024, "12MB")],
    )
    def test_formats_units(self, size, expected):
        assert payloads.format_file_size_limit(size) == expected

    def test_switches_at_the_megabyte_boundary(self):
        assert payloads.format_file_size_limit(1024 * 1024 - 1).endswith("KB")
        assert payloads.format_file_size_limit(1024 * 1024).endswith("MB")
