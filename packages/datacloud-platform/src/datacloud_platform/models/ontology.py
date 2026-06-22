"""OntologySummary Pydantic model for queryOntologiesByScene response."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class OntologySummary(BaseModel):
    """Ontology summary (9 fields)."""

    ontology_id: str = Field(alias="ontologyId")
    scene_id: str = Field(alias="sceneId")
    ontology_name: str = Field(alias="ontologyName")
    ontology_code: str = Field(alias="ontologyCode")
    ontology_source: str | None = Field(default=None, alias="ontologySource")
    ontology_desc: str | None = Field(default=None, alias="ontologyDesc")
    concept_type: str | None = Field(default=None, alias="conceptType")
    ontology_type: str | None = Field(default=None, alias="ontologyType")
    domain_type: str | None = Field(default=None, alias="domainType")

    model_config = ConfigDict(populate_by_name=True, extra="allow")
