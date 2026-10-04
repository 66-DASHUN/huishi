from pathlib import Path

import pytest

from app import create_app
from huishi.db import get_db


@pytest.fixture()
def app(tmp_path: Path):
    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "test.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"
    with app.app_context():
        from huishi.db import init_db

        init_db()
    return app


def test_user_key_global_toggle_disables_user_provider(app):
    from huishi.providers import get_app_settings, save_app_setting, save_provider
    from huishi.user_key import get_user_provider, save_user_api_key

    with app.app_context():
        settings = get_app_settings("user_key_enabled")
        assert settings.get("user_key_enabled") == "1"

        cursor = get_db().execute(
            """
            INSERT INTO users (username, email, password_hash, role, email_verified, points, created_at)
            VALUES ('user-key-toggle', '', 'hash', 'user', 1, 20, 'now')
            """
        )
        user_id = int(cursor.lastrowid)
        save_user_api_key(user_id, "sk-user")
        save_provider(
            provider_type="image",
            name="platform",
            base_url="https://generativelanguage.googleapis.com",
            api_key="sk-platform",
            model="gemini-3.1-flash-image",
            api_format="gemini",
            priority=100,
            enabled=True,
            resolutions=["1K", "2K", "4K"],
        )
        get_db().commit()

        user_provider = get_user_provider(user_id)
        assert user_provider["api_key"] == "sk-user"
        assert user_provider["api_format"] == "gemini"

        save_app_setting("user_key_enabled", "0")
        get_db().commit()

        assert get_user_provider(user_id) is None


def test_user_key_provider_uses_selected_model_from_channel_catalog(app):
    from huishi.providers import save_provider
    from huishi.user_key import get_user_provider, save_user_api_key

    with app.app_context():
        user_id = int(
            get_db().execute(
                """
                INSERT INTO users (username, email, password_hash, role, email_verified, points, created_at)
                VALUES ('user-key-model', '', 'hash', 'user', 1, 20, 'now')
                """
            ).lastrowid
        )
        save_user_api_key(user_id, "sk-user")
        save_provider(
            provider_type="image",
            name="multi-model-platform",
            base_url="https://platform.example",
            api_key="sk-platform",
            model="gpt-image-2",
            api_format="openai",
            priority=10,
            enabled=True,
            resolutions=["1K", "2K"],
            models=[
                {"id": "gpt-image-2", "label": "GPT Image 2"},
                {"id": "gpt-image-2.5-flare", "label": "GPT Image 2.5 Flare"},
            ],
        )
        get_db().commit()

        provider = get_user_provider(user_id, model="gpt-image-2.5-flare", resolution="2K")

        assert provider["model"] == "gpt-image-2.5-flare"
        assert provider["base_url"] == "https://platform.example"


def test_admin_settings_submission_saves_user_key_toggle(app):
    from huishi.providers import get_app_settings

    with app.app_context():
        admin = get_db().execute("SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1").fetchone()

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = admin["id"]

        response = client.post(
            "/admin/config/settings",
            data={
                "csrf_token": "test",
                "user_key_enabled_submitted": "1",
                "user_key_enabled": "1",
            },
            follow_redirects=False,
        )

    assert response.status_code == 302
    with app.app_context():
        assert get_app_settings("user_key_enabled").get("user_key_enabled") == "1"

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = admin["id"]

        response = client.post(
            "/admin/config/settings",
            data={"csrf_token": "test"},
            follow_redirects=False,
        )

    assert response.status_code == 302
    with app.app_context():
        assert get_app_settings("user_key_enabled").get("user_key_enabled") == "1"


def test_admin_settings_submission_saves_user_key_disabled_when_section_submitted(app):
    from huishi.providers import get_app_settings

    with app.app_context():
        admin = get_db().execute("SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1").fetchone()

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = admin["id"]

        response = client.post(
            "/admin/config/settings",
            data={"csrf_token": "test", "user_key_enabled_submitted": "1"},
            follow_redirects=False,
        )

    assert response.status_code == 302
    with app.app_context():
        assert get_app_settings("user_key_enabled").get("user_key_enabled") == "0"
