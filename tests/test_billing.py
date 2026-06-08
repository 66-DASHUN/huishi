import pytest

from huishi import billing
from huishi.db import get_db


def test_billing_tier_uses_longest_edge(app):
    from huishi.billing import tier_for_size

    assert tier_for_size("1536x864") == "1K"
    assert tier_for_size("2048x2048") == "2K"
    assert tier_for_size("3840x2160") == "4K"


def test_reference_and_text_custom_size_share_price(app):
    from huishi import billing

    with app.app_context():
        text_cost = billing.calculate_cost("text", "2048x2048", 1)
        reference_cost = billing.calculate_cost("reference", "2048x2048", 1)

    assert text_cost == 2
    assert reference_cost == text_cost


def test_size_above_4k_tier_is_rejected():
    from huishi.billing import tier_for_size

    with pytest.raises(ValueError, match="分辨率"):
        tier_for_size("5000x3000")


def test_size_with_non_positive_edge_is_rejected():
    from huishi.billing import tier_for_size

    with pytest.raises(ValueError, match="分辨率"):
        tier_for_size("-1x100")


def test_default_text_generation_2k_costs_two_points(app):
    with app.app_context():
        cost = billing.calculate_cost("text", "2K", 1)
        assert cost == 2


def test_default_reference_edit_4k_costs_four_points(app):
    with app.app_context():
        cost = billing.calculate_cost("reference", "4K", 1)
        assert cost == 4


def test_default_text_generation_4k_is_enabled(app):
    with app.app_context():
        cost = billing.calculate_cost("text", "4K", 1)
        assert cost == 4


def test_cost_multiplies_by_count(app):
    with app.app_context():
        cost = billing.calculate_cost("text", "1K", 3)
        assert cost == 3


def test_disabled_pricing_rule_rejects_generation(app):
    with app.app_context():
        db = get_db()
        db.execute(
            "UPDATE pricing_rules SET enabled = 0 WHERE mode = ? AND resolution = ?",
            ("text", "4K"),
        )
        db.commit()
        try:
            billing.calculate_cost("text", "4K", 1)
        except ValueError as exc:
            assert "未启用" in str(exc)
        else:
            raise AssertionError("disabled pricing rule should raise ValueError")


def test_successful_generation_creates_record_and_deducts_points(client, app, monkeypatch):
    client.post("/register", data={"username": "genuser", "password": "secret123"}, follow_redirects=True)

    def fake_generate_image(**kwargs):
        return {
            "image_path": "/static/uploads/fake.png",
            "actual_size": "1024x1024",
            "model_source": "fake",
            "elapsed_seconds": 0.1,
        }

    monkeypatch.setattr("huishi.routes_workspace.generate_image", fake_generate_image)
    response = client.post(
        "/generate",
        data={"prompt": "一座发光的城市", "mode": "text", "resolution": "1K", "count": "1"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "一座发光的城市" in text
    assert "19 点" in text


def test_email_user_must_verify_before_generation(client, monkeypatch):
    monkeypatch.setattr("huishi.auth.send_verification_email", lambda email, code: None)
    client.post(
        "/register",
        data={"email": "verifygen@example.com", "username": "verifygen", "password": "secret123"},
        follow_redirects=True,
    )

    def fake_generate_image(**kwargs):
        raise AssertionError("unverified email users should not reach image generation")

    monkeypatch.setattr("huishi.routes_workspace.generate_image", fake_generate_image)
    response = client.post(
        "/generate",
        data={"prompt": "verify first", "mode": "text", "resolution": "1K", "count": "1"},
        headers={"X-Requested-With": "fetch", "Accept": "application/json"},
    )

    assert response.status_code == 403
    assert response.get_json()["ok"] is False


def test_generation_rejects_insufficient_balance(client, app, monkeypatch):
    from huishi.db import get_db

    client.post("/register", data={"username": "poor", "password": "secret123"}, follow_redirects=True)
    with app.app_context():
        db = get_db()
        db.execute("UPDATE users SET points = 0 WHERE username = 'poor'")
        db.commit()

    def fake_generate_image(**kwargs):
        raise AssertionError("image generation should not be called without balance")

    monkeypatch.setattr("huishi.routes_workspace.generate_image", fake_generate_image)
    response = client.post(
        "/generate",
        data={"prompt": "余额不足测试", "mode": "text", "resolution": "1K", "count": "1"},
    )
    assert response.status_code == 400
    assert "积分余额不足" in response.get_data(as_text=True)


def test_resolution_size_matrix_matches_reference_project():
    from huishi.image_api import resolve_size

    assert resolve_size("16:9", "4K") == "3840x2160"
    assert resolve_size("9:16", "2K") == "1440x2560"
    assert resolve_size("3:2", "1K") == "1536x1024"
    assert resolve_size("2:3", "4K") == "1440x2160"
    assert resolve_size("4:3", "2K") == "2048x1536"
    assert resolve_size("3:4", "2K") == "1536x2048"


def test_unsupported_ratio_resolution_is_rejected(client):
    client.post("/register", data={"username": "badsize", "password": "secret123"}, follow_redirects=True)
    response = client.post(
        "/generate",
        data={"prompt": "不支持尺寸", "mode": "text", "ratio": "1:1", "resolution": "4K", "count": "1"},
        headers={"X-Requested-With": "fetch", "Accept": "application/json"},
    )
    assert response.status_code == 400
    assert "不支持" in response.get_json()["error"]


def test_invalid_generation_count_is_rejected(client):
    client.post("/register", data={"username": "badcount", "password": "secret123"}, follow_redirects=True)
    response = client.post(
        "/generate",
        data={"prompt": "非法数量", "mode": "text", "ratio": "16:9", "resolution": "1K", "count": "abc"},
        headers={"X-Requested-With": "fetch", "Accept": "application/json"},
    )
    assert response.status_code == 400
    assert "数量" in response.get_json()["error"]


def test_generate_image_calls_openai_compatible_client_and_saves_b64(app, monkeypatch):
    import base64

    from huishi import image_api

    tiny_png = base64.b64encode(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
        b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    ).decode("ascii")
    calls = {}

    class FakeResponse:
        def to_dict(self):
            return {"data": [{"b64_json": tiny_png}]}

    class FakeImages:
        def generate(self, **kwargs):
            calls["kwargs"] = kwargs
            return FakeResponse()

    class FakeClient:
        def __init__(self, api_key, base_url):
            calls["api_key"] = api_key
            calls["base_url"] = base_url
            self.images = FakeImages()

    monkeypatch.setattr(image_api, "OpenAI", FakeClient)
    with app.app_context():
        result = image_api.generate_image(
            prompt="真实接口测试",
            mode="text",
            ratio="16:9",
            resolution="2K",
            count=2,
            api_key="sk-test",
            base_url="https://example.com/v1",
            quality="auto",
            output_format="png",
        )

    assert calls["api_key"] == "sk-test"
    assert calls["base_url"] == "https://example.com/v1"
    assert calls["kwargs"]["model"] == "gpt-image-2"
    assert calls["kwargs"]["prompt"] == "真实接口测试"
    assert calls["kwargs"]["size"] == "2560x1440"
    assert calls["kwargs"]["n"] == 2
    assert result["image_path"].startswith("/static/uploads/")
    assert result["actual_size"] == "2560x1440"
    assert result["model_source"] == "gpt-image-2"
