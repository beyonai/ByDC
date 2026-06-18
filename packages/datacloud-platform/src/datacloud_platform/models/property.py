"""Property definition and TermMeta Pydantic models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TermMeta(BaseModel):
    """Terminology metadata bound to a property."""

    term_master_type: str = Field(alias="termMasterType")
    term_type_code: str = Field(alias="termTypeCode")
    term_field: str = Field(alias="termField")

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class Property(BaseModel):
    """Property definition (24 fields, matching API docs)."""

    property_name: str = Field(alias="propertyName")
    property_code: str = Field(alias="propertyCode")
    property_desc: str | None = Field(default=None, alias="propertyDesc")
    data_type: str | None = Field(default=None, alias="dataType")
    data_format: str | None = Field(default=None, alias="dataFormat")
    is_required: int = Field(default=0, alias="isRequired")
    is_instantiation: int = Field(default=0, alias="isInstantiation")
    is_name: int = Field(default=0, alias="isName")
    business_definition: str | None = Field(default=None, alias="businessDefinition")
    technical_definition: str | None = Field(default=None, alias="technicalDefinition")
    terminology: TermMeta | None = Field(default=None, alias="terminology")
    synonyms: str | None = Field(default=None, alias="synonyms")
    property_type: str | None = Field(default=None, alias="propertyType")
    property_type_code: str | None = Field(default=None, alias="propertyTypeCode")
    property_sub_type: str | None = Field(default=None, alias="propertySubType")
    property_sub_type_code: str | None = Field(
        default=None, alias="propertySubTypeCode"
    )
    business_key: int = Field(default=0, alias="businessKey")
    sort_no: int = Field(default=0, alias="sortNo")
    status: int = Field(default=0, alias="status")
    db_id: str | None = Field(default=None, alias="dbId")
    column_id: str | None = Field(default=None, alias="columnId")
    source_column: str | None = Field(default=None, alias="sourceColumn")
    api_id: str | None = Field(default=None, alias="apiId")
    api_source: str | None = Field(default=None, alias="apiSource")
    doc_id: str | None = Field(default=None, alias="docId")

    model_config = ConfigDict(populate_by_name=True, extra="allow")
