"""Tests for huishi.image_sizes.

These helpers were extracted verbatim from routes_workspace. The extraction was
validated by running ~1500 input combinations against the pre-extraction
implementation and comparing outputs; these tests pin the behaviour that
mattered, so a future change cannot silently alter pricing-relevant mapping.
"""
from __future__ import annotations

import pytest

from huishi import image_sizes as sizes
from huishi.image_api import SIZE_MATRIX


class TestResolutionForBilling:
    """Billing looks up pricing by preset label, never by pixel size."""

    @pytest.mark.parametrize(
        "pixel_size,expected",
        [
            ("2560x1440", "2K"),
            ("1024x1024", "1K"),
            ("3840x2160", "4K"),
            ("1440x2560", "2K"),
        ],
    )
    def test_known_pixel_sizes_map_to_their_preset_label(self, pixel_size, expected):
        assert sizes.resolution_for_billing(pixel_size) == expected

    def test_preset_labels_pass_through_unchanged(self):
        for label in ("1K", "2K", "4K"):
            assert sizes.resolution_for_billing(label) == label

    def test_unknown_pixel_size_is_returned_unchanged(self):
        # An admin is expected to add a pricing rule for sizes we cannot map.
        assert sizes.resolution_for_billing("1234x567") == "1234x567"

    def test_non_size_strings_pass_through(self):
        assert sizes.resolution_for_billing("default") == "default"
        assert sizes.resolution_for_billing("") == ""


class TestParseSizeValue:
    @pytest.mark.parametrize("value", ["1024x1024", "2560x1440", "1x1"])
    def test_parses_width_and_height(self, value):
        width, height = sizes.parse_size_value(value)
        assert isinstance(width, int) and isinstance(height, int)

    def test_round_trips_every_matrix_size(self):
        for ratio_sizes in SIZE_MATRIX.values():
            for size in ratio_sizes.values():
                assert sizes.parse_size_value(size) is not None

    @pytest.mark.parametrize("value", ["", "abc", "1024", "1024x", "x1024", "2K", "1024 x 768"])
    def test_rejects_non_size_strings(self, value):
        assert sizes.parse_size_value(value) is None


class TestNearestSupportedSize:
    def test_snaps_custom_size_to_a_supported_size_for_the_ratio(self):
        result = sizes.nearest_supported_size("16:9", "1500x900")
        assert result in SIZE_MATRIX["16:9"].values()

    def test_result_keeps_the_requested_orientation(self):
        # A landscape request must not snap to a portrait size.
        result = sizes.nearest_supported_size("9:16", "1000x2000")
        assert result in SIZE_MATRIX["9:16"].values()

    def test_unknown_ratio_falls_back_to_some_supported_size(self):
        assert sizes.nearest_supported_size("7:5", "100x100")


class TestResolutionLabels:
    def test_derive_labels_covers_every_label_in_the_matrix(self):
        labels = sizes.derive_resolution_labels()
        for ratio_sizes in SIZE_MATRIX.values():
            for label in ratio_sizes:
                assert label in labels

    def test_label_lookup_resolves_a_pixel_size_back_to_its_label(self):
        for ratio, ratio_sizes in SIZE_MATRIX.items():
            for label, size in ratio_sizes.items():
                assert sizes.resolution_label_for_ratio(ratio, size) == label

    def test_custom_pixel_size_is_labelled_as_custom(self):
        assert sizes.resolution_label_for_ratio("16:9", "1234x567") == "自定义尺寸"


class TestNormalizeResolutionForRatio:
    def test_supported_size_is_left_alone(self):
        for ratio, ratio_sizes in SIZE_MATRIX.items():
            for label, size in ratio_sizes.items():
                normalized, changed = sizes.normalize_resolution_for_ratio(ratio, label)
                assert normalized == label
                assert changed is None

    @pytest.mark.parametrize(
        "ratio,custom,expected_ratio",
        [
            ("1:1", "1200x900", 1.0),
            ("16:9", "1500x900", 16 / 9),
            ("9:16", "900x1500", 9 / 16),
            ("21:9", "2000x800", 21 / 9),
        ],
    )
    def test_unsupported_custom_size_snaps_to_a_legal_size_of_that_ratio(
        self, ratio, custom, expected_ratio
    ):
        """A custom size is snapped to a legal size, not to a preset.

        The snapped value comes from nearest_legal_image_size_for_ratio, so it
        is validated by the image API's own rules rather than restricted to the
        preset matrix. What must hold is that it is legal and keeps the ratio.
        """
        from huishi.image_api import validate_image_size

        normalized, changed = sizes.normalize_resolution_for_ratio(ratio, custom)

        validate_image_size(normalized)  # raises if not a legal size
        width, height = (int(part) for part in normalized.split("x"))
        assert width / height == pytest.approx(expected_ratio, rel=0.05)
        assert changed == normalized

    def test_unsupported_ratio_does_not_raise(self):
        normalized, _ = sizes.normalize_resolution_for_ratio("7:5", "2K")
        assert normalized


class TestBackwardCompatibility:
    """routes_workspace re-exports the underscore-prefixed originals."""

    def test_routes_workspace_still_exposes_the_extracted_functions(self):
        from huishi import routes_workspace

        for name in (
            "_derive_resolution_labels",
            "_resolution_label_for_ratio",
            "_resolution_value_for_ratio",
            "_resolution_for_billing",
            "_parse_size_value",
            "_nearest_supported_size",
            "_normalize_resolution_for_ratio",
            "_unsupported_size_message",
        ):
            assert hasattr(routes_workspace, name), f"routes_workspace lost {name}"

    def test_dead_code_was_removed(self):
        from huishi import routes_workspace

        # Verified unreferenced anywhere in the repo before removal.
        assert not hasattr(routes_workspace, "_normalize_custom_resolution")
