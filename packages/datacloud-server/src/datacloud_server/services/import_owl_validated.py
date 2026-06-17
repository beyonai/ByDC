"""ImportOwlValidated — OWL import + cross-reference validation.

Orchestration use case verifying OntologySearchService + OntologyResourceService composition.
Validation failure raises without writing, not polluting atomic Services.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datacloud_server.services.ontology_resource_service import OntologyResourceService
    from datacloud_server.services.ontology_search_service import OntologySearchService


class ValidationError(Exception):
    """Import validation failure: contains all error items."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("\n".join(errors))


@dataclass
class ImportResult:
    """Import result: counts of each resource type written."""

    objects: int = 0
    views: int = 0
    relations: int = 0


@dataclass
class ImportOwlValidated:
    """OWL import -> cross-reference validation -> return result. ValidationError on failure."""

    _search: OntologySearchService
    _resource: OntologyResourceService

    def __call__(self, base_id: str, scene_id: str, zip_bytes: bytes) -> ImportResult:
        # 1. Import OWL
        raw = self._search.import_owl(base_id, scene_id, zip_bytes)
        result = ImportResult(
            objects=raw.get("objects", 0),
            views=raw.get("views", 0),
            relations=raw.get("relations", 0),
        )

        # 2. Cross-reference validation: Property's termBinding must reference
        #    a ValueType that exists within the imported object set
        objects = self._resource.get_objects(base_id, scene_id)
        object_codes: set[str] = {o["objectCode"] for o in objects}

        errors: list[str] = []
        for obj_dict in objects:
            obj_code = obj_dict.get("objectCode", "?")
            for prop in obj_dict.get("properties", []):
                # Property binds to ValueType via terminology.typeCode
                # ValueType is a conceptual ObjectType, referenced by objectCode
                term = prop.get("terminology")
                if term is None:
                    continue
                type_code = term.get("termTypeCode") or term.get("typeCode")
                if type_code and type_code not in object_codes:
                    errors.append(
                        f"Property '{obj_code}.{prop.get('propertyCode', '?')}' "
                        f"termBinding '{type_code}' -> unknown ValueType"
                    )

        if errors:
            raise ValidationError(errors)

        return result
