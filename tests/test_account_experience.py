from __future__ import annotations

from pathlib import Path

import pytest

from app import create_app
from huishi.db import get_db, init_db


@pytest.fixture()
def app(tmp_path: Path):
    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "test.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"
    with app.app_context():
        init_db()
    return app


def _login(client, user_id: int) -> None:
    with client.session_transaction() as session:
        session["user_id"] = user_id


def test_account_ledger_uses_product_labels_and_local_time(app):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO users (username, email, password_hash, role, points, email_verified, created_at)
            VALUES ('creator', 'creator@example.com', 'hash', 'user', 98, 1, '2026-07-09T08:00:00+00:00')
            """
        )
        user_id = db.execute("SELECT id FROM users WHERE username = 'creator'").fetchone()["id"]
        db.execute(
            """
            INSERT INTO records (id, user_id, prompt, image_path, mode, ratio, resolution, actual_size, quality, output_format, count, created_at)
            VALUES (12, ?, 'prompt', '/static/test.png', 'text', '1:1', '2048x2048', '2048x2048', 'auto', 'png', 1, '2026-07-09T16:24:36.645777+00:00')
            """,
            (user_id,),
        )
        db.execute(
            """
            INSERT INTO point_ledger (user_id, delta, reason, record_id, admin_note, created_at)
            VALUES (?, -2, 'generation', 12, '2K · 1 张', '2026-07-09T16:24:36.645777+00:00')
            """,
            (user_id,),
        )
        db.execute(
            """
            INSERT INTO point_ledger (user_id, delta, reason, record_id, admin_note, created_at)
            VALUES (?, 100, 'admin_adjust', NULL, '管理员充值', '2026-07-09T15:00:00+00:00')
            """,
            (user_id,),
        )
        db.commit()

    with app.test_client() as client:
        _login(client, user_id)
        response = client.get('/account')

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert '生成扣费' in body
    assert '管理员调整' in body
    assert 'generation' not in body
    assert 'admin_adjust' not in body
    assert '2026-07-10 00:24' in body
    assert '2026-07-09T16:24:36' not in body
    assert '账户状态' in body
    assert '积分流水' in body
    assert 'account-ledger-row' in body


def test_account_api_key_page_explains_shared_billing_mode(app):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO users (username, email, password_hash, role, points, email_verified, created_at)
            VALUES ('creator', 'creator@example.com', 'hash', 'user', 50, 1, 'now')
            """
        )
        user_id = db.execute("SELECT id FROM users WHERE username = 'creator'").fetchone()["id"]
        db.commit()

    with app.test_client() as client:
        _login(client, user_id)
        response = client.get('/account/api-key')

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert '共享资源（消耗积分）' in body
    assert '与系统配置中的“用户自备 Key”策略保持一致' in body
    assert 'account-key-panel' in body

def test_account_api_key_save_is_blocked_when_user_keys_are_disabled(app):
    from huishi.providers import save_app_setting
    from huishi.user_key import get_user_api_key

    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO users (username, email, password_hash, role, points, email_verified, created_at)
            VALUES ('disabled-key-user', 'disabled@example.com', 'hash', 'user', 50, 1, 'now')
            """
        )
        user_id = db.execute("SELECT id FROM users WHERE username = 'disabled-key-user'").fetchone()["id"]
        save_app_setting("user_key_enabled", "0")
        db.commit()

    with app.test_client() as client:
        _login(client, user_id)
        response = client.post(
            '/account/api-key',
            data={'api_key': 'sk-user-disabled'},
            follow_redirects=True,
        )

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert '管理员已禁用用户自备 Key' in body
    with app.app_context():
        assert get_user_api_key(user_id) is None

def test_account_api_key_page_reflects_disabled_user_key_policy(app):
    from huishi.providers import save_app_setting
    from huishi.user_key import save_user_api_key

    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO users (username, email, password_hash, role, points, email_verified, created_at)
            VALUES ('key-disabled-existing', 'existing@example.com', 'hash', 'user', 50, 1, 'now')
            """
        )
        user_id = db.execute("SELECT id FROM users WHERE username = 'key-disabled-existing'").fetchone()["id"]
        save_user_api_key(user_id, "sk-existing-user")
        save_app_setting("user_key_enabled", "0")
        db.commit()

    with app.test_client() as client:
        _login(client, user_id)
        response = client.get('/account/api-key')

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert '管理员已禁用用户自备 Key' in body
    assert '自备 Key（不消耗积分）' not in body
    assert '共享资源（消耗积分）' in body

