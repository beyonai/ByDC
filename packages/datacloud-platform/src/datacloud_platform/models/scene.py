"""Scene definition and auxiliary Pydantic models."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

SCENE_CODE_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\.\u4e00-\u9fff]+$")


class Scene(BaseModel):
    """Scene definition — pure grouping container, does not own resources."""

    scene_id: str = Field(alias="sceneId")
    scene_name: str = Field(alias="sceneName")
    scene_code: str = Field(alias="sceneCode")
    scene_desc: str | None = Field(default=None, alias="sceneDesc")
    base_id: str = Field(alias="baseId")
    member_object_codes: list[str] = Field(
        default_factory=list, alias="memberObjectCodes"
    )
    member_view_codes: list[str] = Field(default_factory=list, alias="memberViewCodes")

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class SceneCreate(BaseModel):
    """Scene creation request body."""

    scene_name: str = Field(alias="sceneName")
    scene_code: str | None = Field(default=None, alias="sceneCode")
    scene_desc: str | None = Field(default=None, alias="sceneDesc")

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    @field_validator("scene_code")
    @classmethod
    def validate_scene_code(cls, v: str | None) -> str | None:
        """Validate scene_code format.

        Rules:
        - None is allowed (optional field).
        - Must not be empty after stripping whitespace.
        - Must not contain "/".
        - Must match SCENE_CODE_PATTERN (alphanumeric + common symbols + CJK).
        - Must not exceed 128 characters.
        """
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("scene_code cannot be empty or whitespace only")
        if "/" in v:
            raise ValueError("scene_code cannot contain '/'")
        if not SCENE_CODE_PATTERN.match(v):
            raise ValueError(
                "scene_code contains invalid characters; allowed: "
                "a-z, A-Z, 0-9, underscore, hyphen, dot, CJK"
            )
        if len(v) > 128:
            raise ValueError("scene_code must not exceed 128 characters")
        return v


class SceneUpdate(BaseModel):
    """Scene update request body — only non-None fields are applied."""

    scene_name: str | None = Field(default=None, alias="sceneName")
    scene_desc: str | None = Field(default=None, alias="sceneDesc")

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class SceneMembersRequest(BaseModel):
    """Scene member add/remove request body."""

    object_codes: list[str] = Field(default_factory=list, alias="objectCodes")
    view_codes: list[str] = Field(default_factory=list, alias="viewCodes")

    model_config = ConfigDict(populate_by_name=True, extra="forbid")
