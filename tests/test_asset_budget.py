from __future__ import annotations

from pathlib import Path

from tools.check_asset_budget import check_budgets, find_references


def test_home_assets_fit_budget():
    failures = check_budgets(
        Path("."),
        {
            "static/js/home.compiled.js": 300_000,
            "static/css/home-tailwind.css": 40_000,
            "static/media/shouyeshipin-sea.mp4": 9_000_000,
            "static/media/shouyeshipin-poster.jpg": 180_000,
            "static/media/huishi-workflow-cloud.mp4": 6_700_000,
            "static/media/huishi-workflow-cloud-poster.jpg": 180_000,
        },
    )

    assert failures == []


def test_person_containing_home_video_is_not_referenced():
    references = find_references(
        [Path("templates"), Path("static/js"), Path("static/css")],
        "shouyeshipin-home.mp4",
    )

    assert references == []
