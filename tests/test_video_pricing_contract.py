import huishi.model_lifecycle as lifecycle
import huishi.model_management as management


def test_unbounded_request_price_matches_all_model_durations():
    original_exact_prices = lifecycle.exact_prices
    lifecycle.exact_prices = lambda kind, model: [
        {
            "mode": "video",
            "resolution": "720p",
            "billing_unit": "per_request",
            "duration_seconds": 0,
            "points": 300,
        }
    ]
    try:
        provider = {"api_format": "seedance_media"}
        entry = {
            "id": "seedance2.0",
            "upstream_id": "seedance2.0",
            "api_format": "seedance_media",
        }
        prices = lifecycle.compatible_prices(provider, entry, "video")
        assert len(prices) == 1
    finally:
        lifecycle.exact_prices = original_exact_prices


def test_model_admin_accepts_unbounded_request_price():
    original_specs = management._specs
    management._specs = lambda provider, entry, kind: {
        "resolutions": ["720p"],
        "durations": [5, 10, 15],
        "ratios": ["16:9"],
    }
    try:
        prices = management._validated_prices(
            "video",
            [
                {
                    "resolution": "720p",
                    "mode": "video",
                    "points": 300,
                    "enabled": True,
                    "billing_unit": "per_request",
                    "duration_seconds": 0,
                }
            ],
            [({}, {})],
        )
        assert len(prices) == 1
        assert prices[0]["duration_seconds"] == 0
    finally:
        management._specs = original_specs


if __name__ == "__main__":
    test_unbounded_request_price_matches_all_model_durations()
    test_model_admin_accepts_unbounded_request_price()
    print("video pricing contract regression passed")
