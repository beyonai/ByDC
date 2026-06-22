"""Scene definition Pydantic model."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Scene(BaseModel):
    """Scene definition (4 fields)."""

    scene_id: str = Field(alias="sceneId")
    scene_name: str = Field(alias="sceneName")
    scene_code: str = Field(alias="sceneCode")
    scene_desc: str | None = Field(default=None, alias="sceneDesc")

    model_config = ConfigDict(populate_by_name=True, extra="allow")
