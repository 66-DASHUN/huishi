from __future__ import annotations

from app import create_app
from huishi.db import init_db


app = create_app()

with app.app_context():
    init_db()
