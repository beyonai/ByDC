"""KnowledgeMixin — 术语消歧 / 澄清 / 字段别名 / 评分 / 维度解析 编排层。

不再依赖任何 KnowledgeBackend。
编排逻辑全部在此 Mixin 内，直接调用 datacloud_knowledge SDK 函数。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from datacloud_platform.models.shared import (
        DimensionProperty,
        MatchCandidate,
        MatchResult,
        ReferenceProperty,
        ScoreUpdateRecord,
    )


class KnowledgeMixin:
    """术语消歧 / 澄清 / 字段别名 / 评分 / 维度解析 编排层。

    所有方法组合 OntologyBackend + TermBackend 的原子能力完成编排，
    或直接调用 datacloud_knowledge SDK。
    """

    # ── Search & Disambiguate ────────────────────────

    def search_candidates(
        self,
        base_id: str,
        query: str,
        *,
        scope: str = "all",
        limit: int = 20,
    ) -> list[MatchCandidate]:
        """多策略候选搜索。

        编排: 调用 datacloud_knowledge SDK 的 search_all_candidates_with_name_id。
        """
        del scope  # reserved for future use (scope filtering at SDK level)

        if not query.strip():
            return []

        from datacloud_knowledge.retrieval.candidate_search import (
            search_all_candidates_with_name_id,
        )

        from datacloud_platform.models.shared import MatchCandidate

        raw: dict[str, list[dict[str, Any]]] = search_all_candidates_with_name_id(
            [query], top_k=limit
        )
        result: list[MatchCandidate] = []
        for candidates in raw.values():
            result.extend(
                MatchCandidate(
                    term_id=str(c.get("term_id", "")),
                    term_name=str(c.get("term_name", "")),
                    term_type_code=str(c.get("term_type_code", "")),
                    match_type=str(c.get("match_type", "")),
                    confidence=float(c.get("confidence", 0)),
                    score=float(c.get("score", 0)),
                )
                for c in candidates
            )
        return result[:limit]

    def disambiguate(
        self,
        base_id: str,
        candidates: list[MatchCandidate],
        query: str,
    ) -> list[MatchResult]:
        """候选消歧。

        编排: 调用 datacloud_knowledge SDK 的消歧函数。
        """
        from datacloud_knowledge.contracts.types import (
            MatchCandidate as SdkMatchCandidate,
        )
        from datacloud_knowledge.contracts.types import (
            MatchResult as SdkMatchResult,
        )
        from datacloud_knowledge.intent import disambiguate as sdk_disambiguate

        from datacloud_platform.models.shared import MatchCandidate, MatchResult

        if not candidates:
            return [MatchResult(exact={}, fuzzy={})]

        exact_cands: list[SdkMatchCandidate] = []
        fuzzy_cands: list[SdkMatchCandidate] = []
        for c in candidates:
            sdk_c = SdkMatchCandidate(
                term_id=c.term_id,
                term_name=c.term_name,
                term_type_code=c.term_type_code,
                match_type=c.match_type,
                confidence=c.confidence,
                score=c.score,
            )
            if c.match_type == "exact":
                exact_cands.append(sdk_c)
            else:
                fuzzy_cands.append(sdk_c)

        key = query or "query"
        sdk_match = SdkMatchResult(
            exact={key: tuple(exact_cands)},
            fuzzy={key: tuple(fuzzy_cands)},
        )
        sdk_result = sdk_disambiguate(match_result=sdk_match, session=None)

        platform_exact: dict[str, tuple[MatchCandidate, ...]] = {}
        platform_fuzzy: dict[str, tuple[MatchCandidate, ...]] = {}

        for mention_text, sdk_c in sdk_result.confirmed.items():
            platform_exact[mention_text] = (
                MatchCandidate(
                    term_id=sdk_c.term_id,
                    term_name=sdk_c.term_name,
                    term_type_code=sdk_c.term_type_code,
                    match_type=sdk_c.match_type,
                    confidence=sdk_c.confidence,
                    score=sdk_c.score,
                ),
            )

        for mention_text, sdk_cs in sdk_result.ambiguous.items():
            platform_fuzzy[mention_text] = tuple(
                MatchCandidate(
                    term_id=sc.term_id,
                    term_name=sc.term_name,
                    term_type_code=sc.term_type_code,
                    match_type=sc.match_type,
                    confidence=sc.confidence,
                    score=sc.score,
                )
                for sc in sdk_cs
            )

        return [MatchResult(exact=platform_exact, fuzzy=platform_fuzzy)]

    def search(
        self,
        base_id: str,
        query: str,
        *,
        scope: str = "all",
        limit: int = 20,
    ) -> list[MatchResult]:
        """便利方法: candidates → disambiguate。

        编排: search_candidates + disambiguate
        """
        candidates = self.search_candidates(base_id, query, scope=scope, limit=limit)
        return self.disambiguate(base_id, candidates, query)

    # ── Clarification ─────────────────────────────────

    def prepare_clarification(
        self,
        base_id: str,
        query: str,
        slots: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """准备澄清流程。

        编排: 调用 datacloud_knowledge SDK 的 prepare_query_clarification。
        """
        from datacloud_knowledge.provider import (
            prepare_query_clarification as sdk_prepare,
        )

        structured_input: dict[str, Any] = (
            {"slots": slots} if slots else {"query": query}
        )
        analysis = sdk_prepare(
            query=query,
            ontology_code="",
            structured_input=structured_input,
            mode="query",
        )
        return {
            "needs_clarification": analysis.needs_clarification,
            "form": analysis.form,
            "metadata": analysis.metadata,
        }

    def finalize_clarification(
        self,
        base_id: str,
        *,
        query: str,
        ontology_code: str,
        structured_input: dict[str, Any],
        mode: str,
        needs_clarification: bool,
        form: Any = None,
        metadata: Any = None,
        user_id: str | None = None,
        persist_confirmed_synonyms: bool = True,
        language: str = "zh_CN",
    ) -> dict[str, Any]:
        """完成澄清。

        编排: 调用 datacloud_knowledge SDK 的 finalize_query_clarification。
        """
        from datacloud_knowledge.provider import (
            finalize_query_clarification as sdk_finalize,
        )

        result = sdk_finalize(
            query=query,
            ontology_code=ontology_code,
            structured_input=structured_input,
            mode=mode,
            needs_clarification=needs_clarification,
            form=form,
            metadata=metadata,
            user_id=user_id,
            persist_confirmed_synonyms=persist_confirmed_synonyms,
            language=language,
        )
        persisted = result.persisted_synonyms
        return {
            "structured_input": result.structured_input,
            "persisted_synonyms": (
                {"created_ids": getattr(persisted, "created_ids", [])}
                if persisted is not None
                else None
            ),
        }

    # ── Field Aliases ────────────────────────────────

    def resolve_field_aliases(
        self,
        base_id: str,
        field_aliases: dict[str, list[str]],
    ) -> dict[str, list[tuple[str, str]]]:
        """字段别名解析。

        编排: 调用 datacloud_knowledge SDK。
        """
        from datacloud_knowledge.provider import (
            resolve_field_aliases as sdk_resolve,
        )

        return sdk_resolve(terms=list(field_aliases.keys()), scope_code="")  # type: ignore[no-any-return]

    # ── Clarification Results ────────────────────────

    def store_clarification_results(
        self,
        base_id: str,
        results: dict[str, Any],
        user_id: str,
    ) -> list[str]:
        """持久化澄清结果。

        编排: 调用 datacloud_knowledge adapter。
        """
        from datacloud_knowledge.adapters import (
            store_clarification_results as sdk_store,
        )

        return sdk_store(results, user_id)  # type: ignore[no-any-return]

    # ── Scoring ──────────────────────────────────────

    def update_scores(
        self,
        base_id: str,
        records: list[ScoreUpdateRecord],
    ) -> None:
        """批量更新术语评分。

        编排: 调用 datacloud_knowledge SDK。
        """
        from datacloud_knowledge.adapters import create_writer
        from datacloud_knowledge.intent.score_update import (
            batch_update_scores as sdk_batch_update,
        )
        from datacloud_knowledge.intent.types import (
            ScoreUpdateRecord as SdkScoreUpdateRecord,
        )

        sdk_records = tuple(
            SdkScoreUpdateRecord(name_id=r.name_id, success=r.success) for r in records
        )
        sdk_batch_update(records=sdk_records, writer=create_writer())

    # ── Dimension Resolution ─────────────────────────

    def resolve_dimension_value(
        self,
        base_id: str,
        value_term_id: str,
    ) -> DimensionProperty:
        """维度值 → 属性+对象。

        编排: 调用 datacloud_knowledge SDK 的 DimensionValueResolver。
        """
        from datacloud_knowledge.retrieval.dimension_values import (
            DimensionValueResolver,
        )

        from datacloud_platform.models.shared import DimensionProperty

        raw: dict[str, str] = (
            DimensionValueResolver.get_instance().resolve_value_to_property(
                value_term_id
            )
        )
        return DimensionProperty(
            property_code=raw.get("propertyCode", ""),
            object_code=raw.get("objectCode", ""),
        )

    def get_referenced_by(
        self,
        base_id: str,
        value_term_id: str,
    ) -> list[ReferenceProperty]:
        """查询引用某枚举/维度值的属性列表。

        编排: 调用 datacloud_knowledge SDK 的 DimensionValueResolver。
        """
        from datacloud_knowledge.retrieval.dimension_values import (
            DimensionValueResolver,
        )

        from datacloud_platform.models.shared import ReferenceProperty

        raw: list[dict[str, str]] = (
            DimensionValueResolver.get_instance().get_referenced_by(value_term_id)
        )
        return [
            ReferenceProperty(
                property_code=r.get("propertyCode", r.get("property_code", "")),
                property_name=r.get("propertyName", r.get("property_name", "")),
                object_code=r.get("objectCode", r.get("object_code", "")),
                object_name=r.get("objectName", r.get("object_name", "")),
            )
            for r in raw
        ]

    def resolve_object_for_property(
        self,
        base_id: str,
        property_code: str,
    ) -> str | None:
        """属性 → 所属对象编码。

        编排: 调用 datacloud_knowledge SDK。
        """
        from datacloud_knowledge.retrieval.owl_relation_resolver import (
            resolve_object_for_property as sdk_resolve,
        )

        return sdk_resolve(property_code)  # type: ignore[no-any-return]
