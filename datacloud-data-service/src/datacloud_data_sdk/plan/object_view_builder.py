"""ObjectViewBuilder: 从 OntologyLoader 构建 ObjectViewPayload。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from datacloud_data_sdk.plan.models import (
    ObjectViewField,
    ObjectViewFunction,
    ObjectViewObject,
    ObjectViewPayload,
    ObjectViewRelation,
    ObjectViewSource,
)

if TYPE_CHECKING:
    from datacloud_data_sdk.ontology.loader import OntologyLoader


class ObjectViewBuilder:
    def __init__(self, loader: OntologyLoader) -> None:
        self._loader = loader

    def build(self, object_ids: list[str], view_id: str = "default") -> ObjectViewPayload:
        sources: dict[str, ObjectViewSource] = {}
        objects: list[ObjectViewObject] = []

        for oid in object_ids:
            cls = self._loader.get_ontology_class(oid)
            source_id = f"SRC_{(cls.datasource_alias or cls.source_type).upper()}"
            if source_id not in sources:
                sources[source_id] = ObjectViewSource(
                    source_id=source_id,
                    source_type=cls.source_type,
                    datasource_alias=cls.datasource_alias or "",
                )
            fields = [
                ObjectViewField(
                    name=f.field_code,
                    type=f.field_type.lower(),
                    description=f.field_name,
                    aliases=f.aliases,
                )
                for f in cls.fields
            ]
            functions = [
                ObjectViewFunction(function_code=fr)
                for a in cls.actions
                for fr in a.function_refs
            ]
            objects.append(
                ObjectViewObject(
                    object_id=oid,
                    object_name=cls.object_name,
                    source_id=source_id,
                    table=cls.table_name or "",
                    description=cls.description,
                    fields=fields,
                    functions=functions,
                )
            )

        object_set = set(object_ids)
        relations = [
            ObjectViewRelation(
                from_object=r.source_class,
                to_object=r.target_class,
                join_keys=r.join_keys,
                cardinality=r.relation_type,
                description=r.description,
            )
            for r in self._loader.get_ontology_relations()
            if r.source_class in object_set and r.target_class in object_set
        ]

        return ObjectViewPayload(
            view_id=view_id,
            sources=list(sources.values()),
            objects=objects,
            relations=relations,
        )
