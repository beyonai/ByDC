"""Scene definition and auxiliary Pydantic models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


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
