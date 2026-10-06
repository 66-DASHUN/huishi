from pathlib import Path
from io import BytesIO

import pytest
from werkzeug.datastructures import FileStorage

from huishi import image_api


def test_reference_mode_does_not_pass_output_format_to_images_edit(monkeypatch, tmp_path: Path):
    captured = {}
    client_kwargs = {}

    class DummyImages:
        def edit(self, **kwargs):
            captured.update(kwargs)
            raise RuntimeError("stop")

    class DummyClient:
        images = DummyImages()

    def fake_openai(**kwargs):
        client_kwargs.update(kwargs)
        return DummyClient()

    monkeypatch.setattr(image_api, "OpenAI", fake_openai)
    monkeypatch.setattr(
        image_api,
        "current_app",
        type("App", (), {"config": {"IMAGE_API_TIMEOUT": 180, "IMAGE_API_MAX_RETRIES": 2}})(),
    )

    ref = tmp_path / "ref.png"
    ref.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde")

    reference_images = [FileStorage(stream=BytesIO(ref.read_bytes()), filename="ref.png", content_type="image/png")]

    with pytest.raises(RuntimeError, match="stop"):
        image_api.generate_image(
            prompt="test",
            mode="reference",
            ratio="16:9",
            resolution="2560x1440",
            count=1,
            api_key="sk-real",
            base_url="https://api.example.com",
            quality="auto",
            output_format="png",
            reference_images=reference_images,
        )

    assert "output_format" not in captured
    # 生图 POST 绝不隐式重试：超时或响应丢失时上游可能已经计费，
    # 重试会造成重复生成与重复扣费。生产代码因此固定 max_retries=0，
    # 不采纳配置里的 IMAGE_API_MAX_RETRIES。
    assert client_kwargs["max_retries"] == 0
