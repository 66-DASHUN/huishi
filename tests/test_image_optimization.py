from __future__ import annotations

import io
from pathlib import Path

import pytest

from app import create_app
from huishi.db import init_db
from huishi.image_api import optimize_image_bytes, save_binary_image
from huishi.upload_storage import get_upload_storage


PIL = pytest.importorskip("PIL")
from PIL import Image


@pytest.fixture()
def app(tmp_path: Path):
    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "test.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"
    app.config["IMAGE_OPTIMIZE_ENABLED"] = True
    app.config["IMAGE_PNG_COMPRESS_LEVEL"] = 9
    with app.app_context():
        init_db()
    return app


def _png_bytes(*, optimize: bool = False) -> bytes:
    image = Image.new("RGB", (64, 64), "white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=optimize, compress_level=0)
    return buffer.getvalue()


def test_optimize_image_bytes_reduces_png_size():
    original = _png_bytes()
    optimized = optimize_image_bytes(original, ".png", enabled=True, png_compress_level=9)

    assert len(optimized) < len(original)
    with Image.open(io.BytesIO(optimized)) as image:
        assert image.size == (64, 64)


def test_save_binary_image_writes_optimized_bytes(app):
    original = _png_bytes()
    with app.app_context():
        filename = save_binary_image(original, "image.png")

    saved = (app.config["OUTPUT_DIR"] / filename).read_bytes()
    assert len(saved) < len(original)


def test_save_binary_image_enforces_expected_size(app):
    original = _png_bytes()
    with app.app_context():
        filename = save_binary_image(original, "image.png", expected_size="96x48")

    saved = (app.config["OUTPUT_DIR"] / filename).read_bytes()
    with Image.open(io.BytesIO(saved)) as image:
        assert image.size == (96, 48)


def test_save_binary_image_is_persisted_by_upload_storage(app, monkeypatch):
    saved: list[tuple[str, str]] = []
    with app.app_context():
        storage = get_upload_storage()
        original_save = storage.save_bytes

        def capture(key, data, content_type):
            saved.append((str(key), str(content_type)))
            return original_save(key, data, content_type)

        monkeypatch.setattr(storage, "save_bytes", capture)
        filename = save_binary_image(_png_bytes(), "image.png")

    assert saved == [(filename, "image/png")]
