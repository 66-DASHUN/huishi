"""Tests for validation module."""

import pytest
from werkzeug.datastructures import FileStorage
from io import BytesIO

from huishi.validation import (
    ValidationError,
    validate_reference_image_file,
    validate_generation_count,
    validate_resolution_format,
    validate_api_keys,
    validate_http_url,
    sanitize_filename,
)


class TestValidateReferenceImageFile:
    """Test file validation for reference images."""

    def test_valid_jpeg_image(self):
        """Valid JPEG should pass."""
        data = b"\xff\xd8\xff\xe0" + b"x" * 100  # JPEG magic bytes
        file = FileStorage(
            stream=BytesIO(data),
            filename="test.jpg",
            content_type="image/jpeg",
        )
        validate_reference_image_file(file)  # Should not raise

    def test_valid_png_image(self):
        """Valid PNG should pass."""
        data = b"\x89PNG\r\n\x1a\n" + b"x" * 100
        file = FileStorage(
            stream=BytesIO(data),
            filename="test.png",
            content_type="image/png",
        )
        validate_reference_image_file(file)  # Should not raise

    def test_invalid_mime_type(self):
        """Invalid MIME type should raise ValidationError."""
        data = b"x" * 100
        file = FileStorage(
            stream=BytesIO(data),
            filename="test.txt",
            content_type="text/plain",
        )
        with pytest.raises(ValidationError, match="Invalid file type"):
            validate_reference_image_file(file)

    def test_invalid_extension(self):
        """Invalid file extension should raise ValidationError."""
        data = b"\xff\xd8\xff\xe0" + b"x" * 100
        file = FileStorage(
            stream=BytesIO(data),
            filename="test.gif",
            content_type="image/jpeg",
        )
        with pytest.raises(ValidationError, match="Invalid file extension"):
            validate_reference_image_file(file)

    def test_file_too_large(self):
        """File larger than 20MB should raise ValidationError."""
        # Create 21MB of data
        data = b"x" * (21 * 1024 * 1024)
        file = FileStorage(
            stream=BytesIO(data),
            filename="large.png",
            content_type="image/png",
        )
        with pytest.raises(ValidationError, match="File too large"):
            validate_reference_image_file(file)

    def test_empty_file(self):
        """Empty file should raise ValidationError."""
        file = FileStorage(
            stream=BytesIO(b""),
            filename="empty.png",
            content_type="image/png",
        )
        with pytest.raises(ValidationError, match="File is empty"):
            validate_reference_image_file(file)

    def test_no_filename(self):
        """File with no filename should raise ValidationError."""
        data = b"\x89PNG\r\n\x1a\n" + b"x" * 100
        file = FileStorage(
            stream=BytesIO(data),
            filename=None,
            content_type="image/png",
        )
        with pytest.raises(ValidationError, match="File has no name"):
            validate_reference_image_file(file)


class TestValidateGenerationCount:
    """Test generation count validation."""

    def test_valid_count(self):
        """Valid count should return integer."""
        assert validate_generation_count("1") == 1
        assert validate_generation_count("4") == 4
        assert validate_generation_count("8") == 8

    def test_default_count(self):
        """None should default to 1."""
        assert validate_generation_count(None) == 1

    def test_invalid_count_string(self):
        """Non-numeric string should raise ValidationError."""
        with pytest.raises(ValidationError, match="必须是有效数字"):
            validate_generation_count("abc")

    def test_count_too_small(self):
        """Count less than 1 should raise ValidationError."""
        with pytest.raises(ValidationError, match="必须大于 0"):
            validate_generation_count("0")

    def test_count_too_large(self):
        """Count larger than max should raise ValidationError."""
        with pytest.raises(ValidationError, match="最多支持 8"):
            validate_generation_count("10", max_count=8)

    def test_custom_max_count(self):
        """Custom max_count should be respected."""
        assert validate_generation_count("5", max_count=5) == 5
        with pytest.raises(ValidationError, match="最多支持 5"):
            validate_generation_count("6", max_count=5)


class TestValidateResolutionFormat:
    """Test resolution format validation."""

    def test_valid_resolution(self):
        """Valid WxH format should pass."""
        validate_resolution_format("1024x1024")
        validate_resolution_format("2560x1440")
        validate_resolution_format("3840x2160")

    def test_invalid_format(self):
        """Invalid format should raise ValidationError."""
        with pytest.raises(ValidationError, match="Invalid resolution format"):
            validate_resolution_format("1024")

    def test_invalid_format_with_letters(self):
        """Format with letters should raise ValidationError."""
        with pytest.raises(ValidationError, match="Invalid resolution format"):
            validate_resolution_format("1024x1024p")


class TestValidateApiKeys:
    """Test API key validation."""

    def test_valid_keys(self):
        """Valid keys should pass."""
        validate_api_keys("key123", "https://api.example.com")

    def test_missing_api_key(self):
        """Missing API key should raise ValidationError."""
        with pytest.raises(ValidationError, match="缺少 API Key"):
            validate_api_keys("", "https://api.example.com")

    def test_missing_base_url(self):
        """Missing base URL should raise ValidationError."""
        with pytest.raises(ValidationError, match="缺少接口地址"):
            validate_api_keys("key123", "")


class TestValidateHttpUrl:
    """Test HTTP URL validation."""

    def test_valid_https_url(self):
        """Valid HTTPS URL should pass."""
        validate_http_url("https://api.example.com")

    def test_valid_http_url(self):
        """Valid HTTP URL should pass."""
        validate_http_url("http://api.example.com")

    def test_invalid_url_no_scheme(self):
        """URL without scheme should raise ValidationError."""
        with pytest.raises(ValidationError, match="must start with"):
            validate_http_url("api.example.com")

    def test_invalid_url_wrong_scheme(self):
        """URL with non-HTTP scheme should raise ValidationError."""
        with pytest.raises(ValidationError, match="must start with"):
            validate_http_url("ftp://api.example.com")


class TestSanitizeFilename:
    """Test filename sanitization."""

    def test_normal_filename(self):
        """Normal filename should be preserved."""
        assert sanitize_filename("image.jpg") == "image.jpg"

    def test_filename_with_spaces(self):
        """Filename with spaces should be preserved."""
        assert sanitize_filename("my image.png") == "my_image.png"

    def test_filename_with_path_traversal(self):
        """Path traversal attempt should be sanitized."""
        result = sanitize_filename("../../../etc/passwd")
        assert ".." not in result
        assert "/" not in result

    def test_none_filename(self):
        """None should return default."""
        assert sanitize_filename(None) == "file"

    def test_empty_filename(self):
        """Empty string should return default."""
        assert sanitize_filename("") == "file"
