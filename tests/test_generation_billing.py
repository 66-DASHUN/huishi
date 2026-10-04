import zipfile
from io import BytesIO
from pathlib import Path

import pytest

from app import create_app
from huishi.db import get_db
import huishi.routes_workspace as routes_workspace
from huishi.records import create_record, list_records_for_user
from huishi.routes_workspace import _finalize_generation


def test_image_model_catalog_exposes_current_gemini_and_grok_models():
    from huishi.providers import image_model_options

    gemini_models = [item["id"] for item in image_model_options("gemini")]
    grok_models = [item["id"] for item in image_model_options("grok")]

    assert len(gemini_models) >= 2
    assert "gemini-3.1-flash-image" in gemini_models
    assert grok_models == ["grok-imagine-image-2.0"]
    from huishi.providers import image_model_label
    assert image_model_label("grok-imagine-image-2.0") == "grok-imagine 2.0"


def test_banana_catalog_exposes_only_named_models_and_keeps_api_ids():
    from huishi.providers import image_model_label, image_model_options

    banana_options = image_model_options("banana")

    assert banana_options == [
        {"id": "gemini-3.1-flash-image", "label": "Nano Banana 2"},
        {"id": "gemini-3-pro-image", "label": "Nano Banana Pro"},
    ]
    assert image_model_label("gemini-3.1-flash-image") == "Nano Banana 2"
    assert image_model_label("gemini-3-pro-image") == "Nano Banana Pro"
    assert image_model_label("custom-image-model") == "custom-image-model"


def test_calculate_cost_prefers_exact_model_price_over_wildcard(app):
    from huishi.billing import calculate_cost

    with app.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO pricing_rules (mode, model, resolution, points_per_image, enabled) VALUES (?, ?, ?, ?, 1)",
            ("text", "gemini-test-model", "2K", 7),
        )
        db.commit()

        assert calculate_cost("text", "2K", 1, model="gemini-test-model") == 7
        assert calculate_cost("text", "2K", 1, model="unknown-model") == 2


def test_deducts_independent_exact_prices_for_banana_pro_and_grok(app):
    from huishi.billing import calculate_cost, deduct_points_if_sufficient

    with app.app_context():
        db = get_db()
        db.execute(
            "UPDATE pricing_rules SET points_per_image = 11 WHERE mode = 'text' AND model = 'gemini-3-pro-image' AND resolution = '2K'"
        )
        db.execute(
            "UPDATE pricing_rules SET points_per_image = 5 WHERE mode = 'text' AND model = 'grok-imagine-image-2.0' AND resolution = '2K'"
        )
        cursor = db.execute(
            "INSERT INTO users (username, email, password_hash, role, email_verified, points, created_at) VALUES ('priced', '', 'hash', 'user', 1, 30, 'now')"
        )
        user_id = int(cursor.lastrowid)
        banana_cost = calculate_cost("text", "2K", 1, model="gemini-3-pro-image")
        grok_cost = calculate_cost("text", "2K", 1, model="grok-imagine-image-2.0")
        deduct_points_if_sufficient(user_id, banana_cost, reason="banana")
        deduct_points_if_sufficient(user_id, grok_cost, reason="grok")
        db.commit()

        balance = db.execute("SELECT points FROM users WHERE id = ?", (user_id,)).fetchone()["points"]
        ledger = db.execute("SELECT delta, reason FROM point_ledger WHERE user_id = ? ORDER BY id", (user_id,)).fetchall()

    assert (banana_cost, grok_cost) == (11, 5)
    assert balance == 14
    assert [tuple(row) for row in ledger] == [(-11, "banana"), (-5, "grok")]


def test_calculate_cost_rejects_existing_zero_price_rule(app):
    from huishi.billing import calculate_cost

    with app.app_context():
        get_db().execute(
            "UPDATE pricing_rules SET points_per_image = 0 WHERE mode = 'text' AND model = 'gemini-3-pro-image' AND resolution = '2K'"
        )
        get_db().commit()

        with pytest.raises(ValueError, match="至少为 1"):
            calculate_cost("text", "2K", 1, model="gemini-3-pro-image")


def test_pricing_schema_keeps_model_dimension_and_wildcard_defaults(app):
    with app.app_context():
        columns = {row["name"] for row in get_db().execute("PRAGMA table_info(pricing_rules)").fetchall()}
        wildcard = get_db().execute(
            "SELECT model, points_per_image FROM pricing_rules WHERE mode = 'text' AND model = '*' AND resolution = '1K'"
        ).fetchone()

    assert "model" in columns
    assert wildcard is not None
    assert wildcard["points_per_image"] == 1


@pytest.fixture()
def app(tmp_path: Path):
    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "test.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"
    with app.app_context():
        from huishi.db import init_db

        init_db()
    return app


def login(client, user_id: int) -> None:
    with client.session_transaction() as session:
        session["user_id"] = user_id


def create_user(points: int = 20, username: str = "u") -> int:
    cursor = get_db().execute(
        """
        INSERT INTO users (username, email, password_hash, role, email_verified, points, created_at)
        VALUES (?, '', 'hash', 'user', 1, ?, 'now')
        """,
        (username, points),
    )
    get_db().commit()
    return int(cursor.lastrowid)


def test_multi_image_generation_creates_one_ledger_entry_per_record(app):
    with app.app_context():
        db = get_db()
        cursor = db.execute(
            """
            INSERT INTO users (username, email, password_hash, role, points, created_at)
            VALUES ('u', 'u@example.com', 'hash', 'user', 20, 'now')
            """
        )
        user_id = int(cursor.lastrowid)
        db.commit()

        _finalize_generation(
            user_id=user_id,
            prompt="two images",
            mode="text",
            ratio="16:9",
            resolution="2560x1440",
            count=2,
            quality="auto",
            output_format="png",
            result={
                "image_paths": ["/static/uploads/a.png", "/static/uploads/b.png"],
                "actual_size": "2560x1440",
                "model_source": "gpt-image-2",
                "elapsed_seconds": 1.2,
            },
            reference_paths=[],
        )

        records = db.execute("SELECT id, points_charged FROM records ORDER BY id").fetchall()
        ledger = db.execute("SELECT delta, record_id FROM point_ledger ORDER BY id").fetchall()
        user = db.execute("SELECT points FROM users WHERE id = ?", (user_id,)).fetchone()

        assert [row["points_charged"] for row in records] == [2, 2]
        assert [(row["delta"], row["record_id"]) for row in ledger] == [
            (-2, records[0]["id"]),
            (-2, records[1]["id"]),
        ]
        assert user["points"] == 16


def test_finalize_generation_uses_transaction_helper(app, monkeypatch):
    calls = []
    real_transaction = routes_workspace.transaction

    def tracking_transaction():
        calls.append("transaction")
        return real_transaction()

    monkeypatch.setattr(routes_workspace, "transaction", tracking_transaction)

    with app.app_context():
        user_id = create_user(points=20)

        record_id = _finalize_generation(
            user_id=user_id,
            prompt="transaction boundary",
            mode="text",
            ratio="16:9",
            resolution="2560x1440",
            count=1,
            quality="auto",
            output_format="png",
            result={
                "image_paths": ["/static/uploads/tx.png"],
                "actual_size": "2560x1440",
                "model_source": "gpt-image-2",
                "elapsed_seconds": 1.2,
            },
            reference_paths=[],
        )

        assert record_id > 0
        assert calls == ["transaction"]


def test_finalize_generation_rolls_back_records_and_billing_when_later_image_fails(app):
    with app.app_context():
        user_id = create_user(points=3)
        upload_dir = app.config["OUTPUT_DIR"]
        upload_dir.mkdir(parents=True, exist_ok=True)
        first_image = upload_dir / "first.png"
        second_image = upload_dir / "second.png"
        first_image.write_bytes(b"first")
        second_image.write_bytes(b"second")

        with pytest.raises(ValueError, match="积分|points|余额|不足"):
            _finalize_generation(
                user_id=user_id,
                prompt="rollback all images",
                mode="text",
                ratio="16:9",
                resolution="2560x1440",
                count=2,
                quality="auto",
                output_format="png",
                result={
                    "image_paths": ["/static/uploads/first.png", "/static/uploads/second.png"],
                    "actual_size": "2560x1440",
                    "model_source": "gpt-image-2",
                    "elapsed_seconds": 1.2,
                },
                reference_paths=[],
            )

        db = get_db()
        records = db.execute("SELECT id FROM records WHERE user_id = ?", (user_id,)).fetchall()
        ledger = db.execute("SELECT id FROM point_ledger WHERE user_id = ?", (user_id,)).fetchall()
        user = db.execute("SELECT points FROM users WHERE id = ?", (user_id,)).fetchone()

        assert records == []
        assert ledger == []
        assert user["points"] == 3
        assert not first_image.exists()
        assert not second_image.exists()


def test_finalize_generation_preserves_original_error_when_upload_cleanup_fails(app, monkeypatch):
    def fail_cleanup(_image_paths):
        raise RuntimeError("cleanup exploded")

    monkeypatch.setattr(routes_workspace, "cleanup_local_uploads", fail_cleanup)

    with app.app_context():
        user_id = create_user(points=3)

        with pytest.raises(ValueError, match="积分|points|余额|不足"):
            _finalize_generation(
                user_id=user_id,
                prompt="preserve billing failure",
                mode="text",
                ratio="16:9",
                resolution="2560x1440",
                count=2,
                quality="auto",
                output_format="png",
                result={
                    "image_paths": ["/static/uploads/a.png", "/static/uploads/b.png"],
                    "actual_size": "2560x1440",
                    "model_source": "gpt-image-2",
                    "elapsed_seconds": 1.2,
                },
                reference_paths=[],
            )


def test_asset_record_list_excludes_missing_local_uploads(app):
    with app.app_context():
        db = get_db()
        cursor = db.execute(
            """
            INSERT INTO users (username, email, password_hash, role, points, created_at)
            VALUES ('u', 'u@example.com', 'hash', 'user', 20, 'now')
            """
        )
        user_id = int(cursor.lastrowid)
        upload_dir = app.config["OUTPUT_DIR"]
        upload_dir.mkdir(parents=True, exist_ok=True)
        (upload_dir / "present.png").write_bytes(b"png")

        visible_id = create_record(
            user_id=user_id,
            prompt="present",
            image_path="/static/uploads/present.png",
            mode="text",
            ratio="16:9",
            resolution="2K",
            actual_size="2560x1440",
            quality="auto",
            output_format="png",
            count=1,
            model_source="gpt-image-2",
            elapsed_seconds=1,
            points_charged=2,
            image_paths=["/static/uploads/present.png"],
        )
        create_record(
            user_id=user_id,
            prompt="missing",
            image_path="/static/uploads/missing.png",
            mode="text",
            ratio="16:9",
            resolution="2K",
            actual_size="2560x1440",
            quality="auto",
            output_format="png",
            count=1,
            model_source="gpt-image-2",
            elapsed_seconds=1,
            points_charged=2,
            image_paths=["/static/uploads/missing.png"],
        )
        db.commit()

        records = list_records_for_user(user_id)

        assert [record["id"] for record in records] == [visible_id]


def test_canvas_asset_import_creates_canvas_source_record(app):
    png_data_url = (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/"
        "x8AAwMCAO6Gx4sAAAAASUVORK5CYII="
    )

    with app.app_context():
        db = get_db()
        cursor = db.execute(
            """
            INSERT INTO users (username, email, password_hash, role, points, created_at)
            VALUES ('u', 'u@example.com', 'hash', 'user', 20, 'now')
            """
        )
        user_id = int(cursor.lastrowid)
        db.commit()

    with app.test_client() as client:
        login(client, user_id)
        response = client.post(
            "/api/canvas/assets/import",
            json={
                "assets": [
                    {
                        "title": "canvas result",
                        "dataUrl": png_data_url,
                        "width": 1,
                        "height": 1,
                    }
                ]
            },
            headers={"X-Requested-With": "fetch", "Accept": "application/json"},
        )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["created"] == 1

    with app.app_context():
        record = get_db().execute(
            "SELECT prompt, asset_source, actual_size, mode, points_charged, image_path FROM records ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert record["prompt"] == "canvas result"
        assert record["asset_source"] == "canvas"
        assert record["actual_size"] == "1x1"
        assert record["mode"] == "reference"
        assert record["points_charged"] == 0
        assert record["image_path"].startswith("/static/uploads/")
        assert (app.config["OUTPUT_DIR"] / Path(record["image_path"]).name).exists()


def test_bulk_asset_actions_scope_ids_to_current_user(app):
    with app.app_context():
        user_id = create_user(username="asset-owner")
        other_user_id = create_user(username="asset-other")
        upload_dir = app.config["OUTPUT_DIR"]
        upload_dir.mkdir(parents=True, exist_ok=True)
        (upload_dir / "own-a.png").write_bytes(b"a")
        (upload_dir / "own-b.png").write_bytes(b"b")
        (upload_dir / "other.png").write_bytes(b"other")

        own_a = create_record(
            user_id=user_id,
            prompt="own a",
            image_path="/static/uploads/own-a.png",
            mode="text",
            ratio="16:9",
            resolution="2K",
            actual_size="2560x1440",
            quality="auto",
            output_format="png",
            count=1,
            model_source="gpt-image-2",
            elapsed_seconds=1,
            points_charged=0,
            image_paths=["/static/uploads/own-a.png"],
        )
        own_b = create_record(
            user_id=user_id,
            prompt="own b",
            image_path="/static/uploads/own-b.png",
            mode="text",
            ratio="16:9",
            resolution="2K",
            actual_size="2560x1440",
            quality="auto",
            output_format="png",
            count=1,
            model_source="gpt-image-2",
            elapsed_seconds=1,
            points_charged=0,
            image_paths=["/static/uploads/own-b.png"],
        )
        other_record = create_record(
            user_id=other_user_id,
            prompt="other",
            image_path="/static/uploads/other.png",
            mode="text",
            ratio="16:9",
            resolution="2K",
            actual_size="2560x1440",
            quality="auto",
            output_format="png",
            count=1,
            model_source="gpt-image-2",
            elapsed_seconds=1,
            points_charged=0,
            image_paths=["/static/uploads/other.png"],
        )
        get_db().commit()

    with app.test_client() as client:
        login(client, user_id)
        favorite_response = client.post(
            "/assets/bulk/favorite",
            json={"ids": [own_a, own_b, other_record], "favorite": True},
            headers={"X-Requested-With": "fetch", "Accept": "application/json"},
        )
        delete_response = client.post(
            "/assets/bulk/delete",
            json={"ids": [own_b, other_record]},
            headers={"X-Requested-With": "fetch", "Accept": "application/json"},
        )
        download_response = client.post(
            "/assets/bulk/download",
            json={"ids": [own_a, own_b, other_record]},
            headers={"X-Requested-With": "fetch", "Accept": "application/zip"},
        )

    assert favorite_response.status_code == 200
    assert favorite_response.get_json()["updated"] == 2
    assert delete_response.status_code == 200
    assert delete_response.get_json()["deleted"] == 1
    assert download_response.status_code == 200

    with app.app_context():
        rows = {
            row["id"]: row
            for row in get_db()
            .execute("SELECT id, favorite, hidden FROM records WHERE id IN (?, ?, ?)", (own_a, own_b, other_record))
            .fetchall()
        }
        assert rows[own_a]["favorite"] == 1
        assert rows[own_a]["hidden"] == 0
        assert rows[own_b]["favorite"] == 1
        assert rows[own_b]["hidden"] == 1
        assert rows[other_record]["favorite"] == 0
        assert rows[other_record]["hidden"] == 0

    with zipfile.ZipFile(BytesIO(download_response.data)) as archive:
        assert sorted(archive.namelist()) == ["own-a.png", "own-b.png"]


def test_assets_page_exposes_canvas_filter_and_canvas_tiles(app):
    with app.app_context():
        user_id = create_user()
        upload_dir = app.config["OUTPUT_DIR"]
        upload_dir.mkdir(parents=True, exist_ok=True)
        (upload_dir / "canvas.png").write_bytes(b"png")
        create_record(
            user_id=user_id,
            prompt="canvas asset",
            image_path="/static/uploads/canvas.png",
            mode="reference",
            ratio="1:1",
            resolution="1x1",
            actual_size="1x1",
            quality="auto",
            output_format="png",
            count=1,
            model_source="canvas-export",
            elapsed_seconds=0,
            points_charged=0,
            image_paths=["/static/uploads/canvas.png"],
            asset_source="canvas",
        )
        get_db().commit()

    with app.test_client() as client:
        login(client, user_id)
        response = client.get("/assets")
        slash_response = client.get("/assets/")

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert slash_response.status_code == 200
    assert 'data-asset-filter="canvas"' in html
    assert 'data-asset-filter="image"' in html
    assert 'data-asset-source="canvas"' in html
    assert "画布" in html
