def test_home_page_renders(client):
    response = client.get("/")
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "绘世" in text
    assert '<div id="root"></div>' in text
    assert 'type="module"' in text
    assert "/assets/index-" in text


def test_home_assets_are_served(client):
    response = client.get("/")
    text = response.get_data(as_text=True)
    asset_path = text.split('src="', 1)[1].split('"', 1)[0]

    asset_response = client.get(asset_path)

    assert asset_response.status_code == 200
    assert asset_response.mimetype in {"text/javascript", "application/javascript"}


def test_home_bundle_uses_workspace_account_and_recharge_navigation(client):
    response = client.get("/")
    text = response.get_data(as_text=True)
    asset_path = text.split('src="', 1)[1].split('"', 1)[0]

    asset_response = client.get(asset_path)
    bundle_text = asset_response.get_data(as_text=True)

    assert response.status_code == 200
    assert "/history" not in text
    assert "/history" not in bundle_text
    assert "/assets" not in bundle_text
    assert "/workspace" in bundle_text
    assert "/account" in bundle_text
    assert "/pricing" in bundle_text
    assert "充值" in bundle_text
    assert "计费" not in bundle_text


def test_workspace_js_dynamic_detail_link_uses_asset_route():
    from pathlib import Path

    script = Path("static/js/workspace.js").read_text(encoding="utf-8")

    assert 'href="/image/' not in script
    assert "/image/${record.id}" not in script
    assert "/assets/${record.id}" in script


def test_security_headers_are_applied(client):
    response = client.get("/")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_home_page_falls_back_when_dist_index_disappears(client, monkeypatch):
    def fake_send_from_directory(*args, **kwargs):
        raise FileNotFoundError("dist/index.html was rebuilt")

    monkeypatch.setattr("app.send_from_directory", fake_send_from_directory)
    response = client.get("/")

    assert response.status_code == 200
    assert "绘世" in response.get_data(as_text=True)


def test_logged_in_home_still_renders_landing_page(client):
    client.post("/register", data={"username": "homegoesworkspace", "password": "secret123"}, follow_redirects=True)

    response = client.get("/", follow_redirects=False)
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert '<div id="root"></div>' in text
    assert "Location" not in response.headers


def test_session_api_reports_anonymous_user(client):
    response = client.get("/api/session")

    assert response.status_code == 200
    assert response.get_json() == {"authenticated": False}


def test_session_api_reports_logged_in_user(client):
    login_admin(client)
    response = client.get("/api/session")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["authenticated"] is True
    assert payload["user"]["username"] == "admin"
    assert payload["user"]["role"] == "admin"
    assert payload["user"]["points"] == 1000


def login_admin(client):
    return client.post(
        "/login",
        data={"username": "admin", "password": "admin123"},
        follow_redirects=True,
    )


def test_admin_dashboard_shows_operational_summary(client):
    login_admin(client)
    response = client.get("/admin/")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "管理总览" in text
    assert "用户总数" in text
    assert "积分余额" in text
    assert "最近生成" in text
    assert "最近积分流水" in text


def test_admin_can_update_pricing_rule(client):
    login_admin(client)
    response = client.post(
        "/admin/pricing",
        data={"mode": "text", "resolution": "2K", "points_per_image": "3", "enabled": "on"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "3 点/张" in response.get_data(as_text=True)


def test_admin_pricing_rejects_negative_points(client):
    login_admin(client)
    response = client.post(
        "/admin/pricing",
        data={"mode": "text", "resolution": "2K", "points_per_image": "-1", "enabled": "on"},
    )

    assert response.status_code == 400


def test_admin_user_adjustment_rejects_missing_user(client):
    login_admin(client)
    response = client.post(
        "/admin/users",
        data={"user_id": "999999", "delta": "10", "admin_note": "missing"},
    )

    assert response.status_code == 400


def test_admin_users_page_has_user_management_actions(client):
    login_admin(client)
    response = client.get("/admin/users")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "充值/扣费" in text
    assert "查看流水" in text
    assert "/admin/users/1/ledger" in text
    assert "/admin/users/1/password" in text
    assert "/admin/users/1/role" in text
    assert "admin-user-table" in text
    assert "/admin/users/export" in text
    assert "/admin/users/import" in text
    assert "/admin/users/import-template" in text
    assert "修改密码" in text
    assert "保存角色" in text


def test_admin_can_export_users_csv(client):
    login_admin(client)

    response = client.get("/admin/users/export")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert response.mimetype == "text/csv"
    assert "id,email,username,role,email_verified,points,created_at" in text
    assert "admin" in text


def test_admin_can_import_users_csv(client, app):
    from io import BytesIO

    login_admin(client)
    csv_payload = "email,password,username,role,points,email_verified\nimported@example.com,secret123,imported,user,88,1\n"

    response = client.post(
        "/admin/users/import",
        data={"file": (BytesIO(csv_payload.encode("utf-8")), "users.csv")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    with app.app_context():
        from huishi.db import get_db
        from werkzeug.security import check_password_hash

        user = get_db().execute("SELECT * FROM users WHERE email = ?", ("imported@example.com",)).fetchone()
    assert user["username"] == "imported"
    assert user["points"] == 88
    assert user["email_verified"] == 1
    assert check_password_hash(user["password_hash"], "secret123")


def test_admin_can_recharge_user_from_dedicated_endpoint(client, app):
    client.post("/register", data={"username": "rechargeuser", "password": "secret123"}, follow_redirects=True)
    client.get("/logout")
    login_admin(client)

    response = client.post(
        "/admin/users/2/adjust",
        data={"delta": "50", "admin_note": "manual recharge"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "70 点" in response.get_data(as_text=True)
    with app.app_context():
        from huishi.db import get_db

        ledger = get_db().execute(
            "SELECT * FROM point_ledger WHERE user_id = ? AND reason = 'admin_adjust' ORDER BY id DESC",
            (2,),
        ).fetchone()
    assert ledger["delta"] == 50
    assert ledger["admin_note"] == "manual recharge"


def test_admin_cannot_deduct_more_than_user_balance(client):
    client.post("/register", data={"username": "deductuser", "password": "secret123"}, follow_redirects=True)
    client.get("/logout")
    login_admin(client)

    response = client.post(
        "/admin/users/2/adjust",
        data={"delta": "-999", "admin_note": "too much"},
    )

    assert response.status_code == 400


def test_admin_can_reset_user_password(client, app):
    client.post("/register", data={"username": "resetuser", "password": "oldpass123"}, follow_redirects=True)
    client.get("/logout")
    login_admin(client)

    response = client.post(
        "/admin/users/2/password",
        data={"password": "newpass123"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    with app.app_context():
        from huishi.db import get_db
        from werkzeug.security import check_password_hash

        user = get_db().execute("SELECT * FROM users WHERE username = 'resetuser'").fetchone()
    assert check_password_hash(user["password_hash"], "newpass123")

    client.get("/logout")
    old_login = client.post("/login", data={"username": "resetuser", "password": "oldpass123"}, follow_redirects=False)
    assert old_login.status_code == 200
    new_login = client.post("/login", data={"username": "resetuser", "password": "newpass123"}, follow_redirects=False)
    assert new_login.status_code == 302


def test_admin_password_reset_rejects_short_password(client):
    client.post("/register", data={"username": "shortpass", "password": "oldpass123"}, follow_redirects=True)
    client.get("/logout")
    login_admin(client)

    response = client.post("/admin/users/2/password", data={"password": "123"})

    assert response.status_code == 400


def test_admin_can_change_user_role(client, app):
    client.post("/register", data={"username": "promoteuser", "password": "secret123"}, follow_redirects=True)
    client.get("/logout")
    login_admin(client)

    response = client.post(
        "/admin/users/2/role",
        data={"role": "admin"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    with app.app_context():
        from huishi.db import get_db

        user = get_db().execute("SELECT role FROM users WHERE username = 'promoteuser'").fetchone()
    assert user["role"] == "admin"


def test_admin_role_update_rejects_invalid_role(client):
    client.post("/register", data={"username": "badrole", "password": "secret123"}, follow_redirects=True)
    client.get("/logout")
    login_admin(client)

    response = client.post("/admin/users/2/role", data={"role": "owner"})

    assert response.status_code == 400


def test_admin_user_ledger_page_shows_user_transactions(client):
    client.post("/register", data={"username": "ledgeruser", "password": "secret123"}, follow_redirects=True)
    client.get("/logout")
    login_admin(client)

    response = client.get("/admin/users/2/ledger")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "ledgeruser" in text
    assert "用户流水" in text
    assert "register_bonus" in text


def test_admin_package_rejects_invalid_values(client):
    login_admin(client)
    response = client.post(
        "/admin/packages",
        data={"name": " ", "price": "-1", "points": "0", "description": ""},
    )

    assert response.status_code == 400


def test_non_admin_cannot_access_admin(client):
    client.post("/register", data={"username": "bob", "password": "secret123"}, follow_redirects=True)
    response = client.get("/admin/pricing")
    assert response.status_code == 403


def test_login_next_does_not_redirect_to_external_site(client):
    login_admin(client)
    client.get("/logout")
    response = client.post(
        "/login?next=https://evil.example/phish",
        data={"username": "admin", "password": "admin123"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/account")


def test_pricing_page_shows_resolution_rules(client):
    response = client.get("/pricing")
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "1K" in text
    assert "2K" in text
    assert "4K" in text
    assert "套餐" not in text


def test_recharge_page_uses_recharge_wording(client):
    response = client.get("/pricing")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "充值" in text
    assert "会员" not in text


def test_logged_in_pricing_page_shows_current_balance(client):
    client.post("/register", data={"username": "pricing-balance", "password": "secret123"}, follow_redirects=True)

    response = client.get("/pricing")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "当前余额" in text
    assert "20 点" in text
    assert "去生成" in text


def test_estimate_rejects_invalid_count(client):
    client.post("/register", data={"username": "estimatebad", "password": "secret123"}, follow_redirects=True)
    response = client.get("/api/estimate?mode=text&resolution=1K&count=abc")
    assert response.status_code == 400
    assert "数量" in response.get_json()["error"]


def test_estimate_prices_custom_dimensions_by_longest_edge(client):
    client.post("/register", data={"username": "estimate-custom", "password": "secret123"}, follow_redirects=True)

    response = client.get("/api/estimate?mode=text&width=2048&height=2048&count=2")

    assert response.status_code == 200
    assert response.get_json()["cost"] == 4


def test_generation_rejects_count_above_limit(client):
    client.post("/register", data={"username": "toomany", "password": "secret123"}, follow_redirects=True)
    response = client.post(
        "/generate",
        data={"prompt": "太多图片", "mode": "text", "resolution": "1K", "ratio": "16:9", "count": "9"},
        headers={"X-Requested-With": "fetch", "Accept": "application/json"},
    )
    assert response.status_code == 400
    assert "最多" in response.get_json()["error"]


def test_generation_ignores_posted_mode_and_derives_text_without_references(client, monkeypatch):
    client.post("/register", data={"username": "postedmode", "password": "secret123"}, follow_redirects=True)
    calls = {}

    def fake_generate_image(**kwargs):
        calls["mode"] = kwargs["mode"]
        return {
            "image_path": "/static/uploads/posted-mode.png",
            "actual_size": "1536x864",
            "model_source": "fake",
            "elapsed_seconds": 0.2,
        }

    monkeypatch.setattr("huishi.routes_workspace.generate_image", fake_generate_image)
    response = client.post(
        "/generate",
        data={"prompt": "bad mode", "mode": "admin", "resolution": "1K", "ratio": "16:9", "count": "1"},
        headers={"X-Requested-With": "fetch", "Accept": "application/json"},
    )

    assert response.status_code == 200
    assert calls["mode"] == "text"


def test_generation_rejects_custom_resolution_above_4k_before_api_call(client, monkeypatch):
    client.post("/register", data={"username": "oversize", "password": "secret123"}, follow_redirects=True)

    def fake_generate_image(**kwargs):
        raise AssertionError("oversized custom dimensions should not call the image API")

    monkeypatch.setattr("huishi.routes_workspace.generate_image", fake_generate_image)
    response = client.post(
        "/generate",
        data={"prompt": "oversized", "ratio": "16:9", "width": "5000", "height": "3000", "count": "1"},
        headers={"X-Requested-With": "fetch", "Accept": "application/json"},
    )

    assert response.status_code == 400
    assert "分辨率" in response.get_json()["error"]


def test_generation_rejects_invalid_quality_and_format(client, monkeypatch):
    client.post("/register", data={"username": "badformat", "password": "secret123"}, follow_redirects=True)

    def fake_generate_image(**kwargs):
        raise AssertionError("invalid options should not call the image API")

    monkeypatch.setattr("huishi.routes_workspace.generate_image", fake_generate_image)
    response = client.post(
        "/generate",
        data={
            "prompt": "bad format",
            "mode": "text",
            "resolution": "1K",
            "ratio": "16:9",
            "quality": "ultra",
            "output_format": "exe",
            "count": "1",
        },
        headers={"X-Requested-With": "fetch", "Accept": "application/json"},
    )

    assert response.status_code == 400


def test_reference_generation_rejects_non_image_upload(client, monkeypatch):
    from io import BytesIO

    client.post("/register", data={"username": "badupload", "password": "secret123"}, follow_redirects=True)

    def fake_generate_image(**kwargs):
        raise AssertionError("invalid upload should not call the image API")

    monkeypatch.setattr("huishi.routes_workspace.generate_image", fake_generate_image)
    response = client.post(
        "/generate",
        data={
            "prompt": "bad upload",
            "mode": "reference",
            "resolution": "1K",
            "ratio": "16:9",
            "count": "1",
            "reference_images": (BytesIO(b"not an image"), "notes.txt"),
        },
        headers={"X-Requested-With": "fetch", "Accept": "application/json"},
        content_type="multipart/form-data",
    )

    assert response.status_code == 400


def test_workspace_generation_json_updates_current_canvas(client, monkeypatch):
    client.post("/register", data={"username": "jsonuser", "password": "secret123"}, follow_redirects=True)

    def fake_generate_image(**kwargs):
        return {
            "image_path": "/static/uploads/json.png",
            "actual_size": "1536x864",
            "model_source": "fake",
            "elapsed_seconds": 0.2,
        }

    monkeypatch.setattr("huishi.routes_workspace.generate_image", fake_generate_image)
    response = client.post(
        "/generate",
        data={"prompt": "异步生成测试", "mode": "text", "resolution": "1K", "ratio": "16:9", "count": "1"},
        headers={"X-Requested-With": "fetch", "Accept": "application/json"},
    )
    payload = response.get_json()
    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["record"]["prompt"] == "异步生成测试"
    assert payload["record"]["image_path"] == "/static/uploads/json.png"
    assert payload["record"]["mode"] == "text"
    assert payload["record"]["resolution"] == "1K"
    assert payload["record"]["actual_size"] == "1536x864"
    assert payload["record"]["points_charged"] > 0


def test_reference_mode_post_without_material_generates_text_image(client, monkeypatch):
    client.post("/register", data={"username": "refmissing", "password": "secret123"}, follow_redirects=True)
    calls = {}

    def fake_generate_image(**kwargs):
        calls["mode"] = kwargs["mode"]
        calls["reference_images"] = kwargs["reference_images"]
        return {
            "image_path": "/static/uploads/text-from-ref-post.png",
            "actual_size": "1536x864",
            "model_source": "fake",
            "elapsed_seconds": 0.2,
        }

    monkeypatch.setattr("huishi.routes_workspace.generate_image", fake_generate_image)
    response = client.post(
        "/generate",
        data={"prompt": "参考图测试", "mode": "reference", "resolution": "1K", "count": "1"},
        headers={"X-Requested-With": "fetch", "Accept": "application/json"},
    )
    assert response.status_code == 200
    assert calls == {"mode": "text", "reference_images": []}


def test_reference_generation_passes_uploaded_images(client, monkeypatch):
    from io import BytesIO

    client.post("/register", data={"username": "refuser", "password": "secret123"}, follow_redirects=True)
    calls = {}

    def fake_generate_image(**kwargs):
        calls["mode"] = kwargs["mode"]
        calls["references"] = kwargs["reference_images"]
        return {
            "image_path": "/static/uploads/ref.png",
            "actual_size": "1536x864",
            "model_source": "fake",
            "elapsed_seconds": 0.2,
        }

    monkeypatch.setattr("huishi.routes_workspace.generate_image", fake_generate_image)
    response = client.post(
        "/generate",
        data={
            "prompt": "参考图测试",
            "mode": "reference",
            "resolution": "1K",
            "ratio": "16:9",
            "count": "1",
            "reference_images": (BytesIO(b"fake image"), "ref.png"),
        },
        headers={"X-Requested-With": "fetch", "Accept": "application/json"},
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    assert response.get_json()["record"]["image_path"] == "/static/uploads/ref.png"
    assert calls["mode"] == "reference"
    assert len(calls["references"]) == 1


def test_reference_generation_persists_reference_paths(client, app, monkeypatch):
    import json
    from io import BytesIO

    from huishi.db import get_db

    client.post("/register", data={"username": "refpersist", "password": "secret123"}, follow_redirects=True)
    source_bytes = b"\x89PNG\r\n\x1a\nsource-reference-bytes"
    calls = {}

    def fake_generate_image(**kwargs):
        references = kwargs["reference_images"]
        calls["reference_bytes"] = references[0].read()
        return {
            "image_path": "/static/uploads/generated-ref.png",
            "actual_size": "1440x2560",
            "model_source": "fake",
            "elapsed_seconds": 0.2,
        }

    monkeypatch.setattr("huishi.routes_workspace.generate_image", fake_generate_image)
    response = client.post(
        "/generate",
        data={
            "prompt": "persist refs",
            "mode": "reference",
            "resolution": "2K",
            "ratio": "9:16",
            "count": "1",
            "reference_images": (BytesIO(source_bytes), "source-ref.png", "image/png"),
        },
        headers={"X-Requested-With": "fetch", "Accept": "application/json"},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert calls["reference_bytes"] == source_bytes
    with app.app_context():
        record = get_db().execute("SELECT * FROM records WHERE prompt = ?", ("persist refs",)).fetchone()
    reference_paths = json.loads(record["reference_paths"])

    assert record["ratio"] == "9:16"
    assert len(reference_paths) == 1
    assert reference_paths[0].startswith("/static/uploads/")
    assert "source-ref" in reference_paths[0]
    saved_name = reference_paths[0].rsplit("/", 1)[-1]
    assert (app.config["OUTPUT_DIR"] / saved_name).read_bytes() == source_bytes


def test_admin_records_page_renders(client):
    login_admin(client)
    response = client.get("/admin/records")
    assert response.status_code == 200
    assert "生成记录" in response.get_data(as_text=True)
