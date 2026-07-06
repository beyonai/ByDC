"""Tests for SceneCreate.scene_code Pydantic validator.

Validates: SCENE_CODE_PATTERN = re.compile(r"^[a-zA-Z0-9_\\-\\.\u4e00-\u9fff]+$")
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from datacloud_platform.models.scene import SceneCreate


class TestSceneCodeValidator:
    """Tests for SceneCreate.validate_scene_code."""

    def test_valid_ascii_scene_code(self) -> None:
        """ASCII-only scene_code passes validation."""
        scene = SceneCreate(sceneName="销售", sceneCode="sales")
        assert scene.scene_code == "sales"

    def test_valid_cjk_scene_code(self) -> None:
        """CJK scene_code passes validation."""
        scene = SceneCreate(sceneName="销售领域", sceneCode="销售领域")
        assert scene.scene_code == "销售领域"

    def test_valid_with_version_suffix(self) -> None:
        """scene_code with dots and underscores passes validation."""
        scene = SceneCreate(sceneName="测试", sceneCode="test_v1.0")
        assert scene.scene_code == "test_v1.0"

    def test_valid_with_hyphen(self) -> None:
        """scene_code with hyphen passes validation."""
        scene = SceneCreate(sceneName="带连字符", sceneCode="my-scene-01")
        assert scene.scene_code == "my-scene-01"

    def test_valid_mixed_cjk_and_ascii(self) -> None:
        """Mixed CJK + ASCII scene_code passes."""
        scene = SceneCreate(sceneName="混合", sceneCode="CRM客户_v2")
        assert scene.scene_code == "CRM客户_v2"

    def test_none_scene_code_accepted(self) -> None:
        """None scene_code is allowed (optional field)."""
        scene = SceneCreate(sceneName="无代码")
        assert scene.scene_code is None

    def test_contains_slash_raises(self) -> None:
        """scene_code containing '/' raises ValidationError."""
        with pytest.raises(ValidationError):
            SceneCreate(sceneName="斜杠", sceneCode="sales/marketing")

    def test_empty_string_raises(self) -> None:
        """Empty scene_code raises ValidationError."""
        with pytest.raises(ValidationError):
            SceneCreate(sceneName="空", sceneCode="")

    def test_whitespace_only_raises(self) -> None:
        """Whitespace-only scene_code raises ValidationError."""
        with pytest.raises(ValidationError):
            SceneCreate(sceneName="空格", sceneCode="   ")

    def test_over_128_chars_raises(self) -> None:
        """scene_code > 128 chars raises ValidationError."""
        long_code = "a" * 129
        with pytest.raises(ValidationError):
            SceneCreate(sceneName="超长", sceneCode=long_code)

    def test_exactly_128_chars_passes(self) -> None:
        """scene_code exactly 128 chars passes validation."""
        code_128 = "a" * 128
        scene = SceneCreate(sceneName="128字符", sceneCode=code_128)
        assert len(scene.scene_code) == 128

    def test_special_chars_not_in_pattern_raises(self) -> None:
        """scene_code with special chars like @, #, $ raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            SceneCreate(sceneName="特符", sceneCode="sales@domain")
        assert "invalid" in str(exc_info.value).lower()

    def test_contains_space_raises(self) -> None:
        """scene_code with spaces raises ValidationError."""
        with pytest.raises(ValidationError):
            SceneCreate(sceneName="含空格", sceneCode="sales area")

    def test_strips_whitespace(self) -> None:
        """Leading/trailing whitespace is stripped before validation."""
        scene = SceneCreate(sceneName="去空格", sceneCode="  sales  ")
        assert scene.scene_code == "sales"
