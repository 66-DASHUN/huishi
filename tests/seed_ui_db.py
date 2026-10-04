from app import create_app
from huishi.db import get_db, init_db
from huishi.providers import save_provider


def main() -> None:
    app = create_app(testing=True)
    with app.app_context():
        init_db()
        save_provider(
            provider_type="image",
            name="UI Image Provider",
            base_url="https://api.example.test",
            api_key="image-key",
            model="gpt-image-2",
            api_format="openai",
            resolutions=["1K", "2K"],
            capabilities=["image"],
            models=[{"id": "gpt-image-2", "label": "GPT Image 2", "media_type": "image"}],
            priority=10,
            enabled=True,
        )
        save_provider(
            provider_type="video",
            name="UI Video Provider",
            base_url="https://video.example.test",
            api_key="video-key",
            model="grok-imagine-video",
            api_format="grok",
            capabilities=["video"],
            models=[{"id": "grok-imagine-video", "label": "Grok Imagine Video", "media_type": "video"}],
            priority=20,
            enabled=True,
        )
        save_provider(
            provider_type="audio",
            name="UI Audio Provider",
            base_url="https://audio.example.test",
            api_key="audio-key",
            model="speech-2.8-hd",
            api_format="minimax",
            capabilities=["audio", "speech", "music"],
            models=[
                {"id": "speech-2.8-hd", "label": "MiniMax Speech 2.8 HD", "media_type": "speech"},
                {"id": "music-3.0", "label": "MiniMax Music 3.0", "media_type": "music"},
            ],
            priority=30,
            enabled=True,
        )
        save_provider(
            provider_type="prompt",
            name="UI Prompt Provider",
            base_url="https://prompt.example.test",
            api_key="prompt-key",
            model="gpt-4.1-mini",
            api_format="openai",
            capabilities=["prompt"],
            models=[{"id": "gpt-4.1-mini", "label": "GPT 4.1 Mini", "media_type": "prompt"}],
            priority=40,
            enabled=True,
        )
        get_db().commit()


if __name__ == "__main__":
    main()
