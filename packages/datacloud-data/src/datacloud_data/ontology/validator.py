"""OntologyValidator: 校验 property_kind 与配置一致性。"""

from __future__ import annotations

from datacloud_data.ontology.loader import OntologyLoader
from datacloud_data.ontology.models import OntologyClass, OntologyRelation


class OntologyValidator:
    """校验本体 property_kind 与配置一致性。

    校验规则（简化版）：
    - derived: 必有 derived_config
    - linked: 必有 relation_ref；API 对象需 Relation 或字段级 resolve_action_code
    """

    @classmethod
    def validate(cls, loader: OntologyLoader) -> list[str]:
        """校验 loader 中全部对象与关联，返回错误列表。"""
        errors: list[str] = []
        classes = {c.object_code: c for c in loader.get_ontology_classes()}
        relations_map = {r.relation_code: r for r in loader.get_ontology_relations()}

        for ontology_class in classes.values():
            errors.extend(cls._validate_class(ontology_class, relations_map, classes))

        for rel in loader.get_ontology_relations():
            errors.extend(cls._validate_relation(rel, classes))

        return errors

    @classmethod
    def _validate_class(
        cls,
        ontology_class: OntologyClass,
        relations_map: dict[str, OntologyRelation],
        classes: dict[str, OntologyClass],
    ) -> list[str]:
        """校验单个 OntologyClass 的字段。"""
        errors: list[str] = []
        obj_code = ontology_class.object_code

        for field in ontology_class.fields:
            kind = field.property_kind or "physical"

            if kind == "derived":
                if not field.derived_config:
                    errors.append(
                        f"{obj_code}.{field.field_code}: property_kind=derived 必须有 derived_config"
                    )

            elif kind == "linked":
                if not field.relation_ref:
                    errors.append(
                        f"{obj_code}.{field.field_code}: property_kind=linked 必须有 relation_ref"
                    )
                elif ontology_class.source_type == "API":
                    rel = relations_map.get(field.relation_ref)
                    field_resolve = field.resolve_action_code
                    rel_resolve = rel.resolve_action_code if rel else None
                    if not field_resolve and not rel_resolve:
                        errors.append(
                            f"{obj_code}.{field.field_code}: API 对象 linked 字段需 Relation 或字段级 resolve_action_code"
                        )

        return errors

    @classmethod
    def _validate_relation(
        cls,
        rel: OntologyRelation,
        classes: dict[str, OntologyClass],
    ) -> list[str]:
        """校验 Relation 的 resolve 引用（可选，当前简化实现不强制）。"""
        errors: list[str] = []
        # 设计文档 5.2：resolve_action_code 必须是 source_class 所属对象的 action
        # 当前简化：仅依赖 _validate_class 中对 API linked 的 resolve 校验
        return errors
