"""Action definition and ActionParam Pydantic models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ActionParam(BaseModel):
    """Action parameter definition (6 fields)."""

    param_code: str = Field(alias="paramCode")
    param_name: str | None = Field(default=None, alias="paramName")
    param_type: str | None = Field(default=None, alias="paramType")
    is_required: int = Field(default=0, alias="isRequired")
    direction: str | None = Field(default=None, alias="direction")
    mapping_path: str | None = Field(default=None, alias="mappingPath")

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class Action(BaseModel):
    """Action definition (9 fields)."""

    action_code: str = Field(alias="actionCode")
    action_name: str = Field(default="", alias="actionName")
    action_type: str | None = Field(default=None, alias="actionType")
    belong_object_code: str = Field(default="", alias="belongObjectCode")
    action_desc: str | None = Field(default=None, alias="actionDesc")
    params: list[ActionParam] = Field(default_factory=list, alias="params")
    request_url: str | None = Field(default=None, alias="requestUrl")
    request_method: str | None = Field(default=None, alias="requestMethod")
    script: str | None = Field(default=None, alias="script")
    owner_type: str = Field(default="enterprise", alias="ownerType")
    user_code: str | None = Field(default=None, alias="userCode")

    model_config = ConfigDict(populate_by_name=True, extra="allow")
