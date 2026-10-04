from __future__ import annotations

from pathlib import Path

import pytest

from app import create_app
from huishi.upload_storage import UploadStorage


@pytest.fixture()
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HUISHI_OUTPUT_DIR", str(tmp_path / "uploads"))
    application = create_app(testing=True)
    application.config["OUTPUT_DIR"] = tmp_path / "uploads"
    application.config["OUTPUT_DIR"].mkdir(parents=True, exist_ok=True)
    return application


@pytest.fixture()
def client(app):
    return app.test_client()


def test_upload_route_serves_configured_output_dir(app, client):
    target = app.config["OUTPUT_DIR"] / "existing.png"
    target.write_bytes(b"\x89PNG\r\n\x1a\ncontent")

    response = client.get("/static/uploads/existing.png")

    assert response.status_code == 200
    assert response.mimetype == "image/png"
    assert response.headers["Cache-Control"] == "public, max-age=604800"
    assert response.data == target.read_bytes()


def test_upload_route_rejects_traversal(client):
    assert client.get("/static/uploads/..%2F.env").status_code == 404


def test_upload_route_rehydrates_remote_only_asset(app, client):
    class Remote:
        def get(self, key: str) -> bytes:
            assert key == "uploads/remote.png"
            return b"\x89PNG\r\n\x1a\nremote"

        def exists(self, key: str) -> bool:
            return key == "uploads/remote.png"

    app.extensions["upload_storage"] = UploadStorage(
        app.config["OUTPUT_DIR"],
        remote=Remote(),
    )

    response = client.get("/static/uploads/remote.png")

    assert response.status_code == 200
    assert response.data.endswith(b"remote")
    assert (app.config["OUTPUT_DIR"] / "remote.png").is_file()
