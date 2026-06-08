import os
import tempfile

import pytest

from app import create_app
from huishi.db import close_db


@pytest.fixture()
def app():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["HUISHI_DATABASE"] = os.path.join(tmp, "test.sqlite3")
        os.environ["HUISHI_OUTPUT_DIR"] = os.path.join(tmp, "output")
        os.environ["HUISHI_SECRET_KEY"] = "test-secret"
        os.environ["HUISHI_ADMIN_PASSWORD"] = "admin123"
        flask_app = create_app(testing=True)
        yield flask_app
        with flask_app.app_context():
            close_db()


@pytest.fixture()
def client(app):
    return app.test_client()
