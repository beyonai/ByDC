"""KnowledgeMixin — 术语消歧 / 澄清 / 字段别名 / 评分 / 维度解析 编排层。

联合 OntologyBackend（本体元数据，OWL 内存）和 TermBackend（术语数据，知识 DB）
完成跨领域编排。不再依赖 datacloud_knowledge.provider.* 或 adapters.* 的自管 session wrapper。
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from datacloud_platform.backends._contracts import (
    _HasOntologyAndTermBackend,
    _HasTermBackend,
)

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

    架构原则（两领域模型分离）：
    - OntologyBackend: OWL 内存元数据（field_code/field_name/aliases，零 DB）
    - TermBackend: 知识 DB 术语数据（用户别名、维度值）
    - KnowledgeMixin: 联合双方做跨领域编排

    方法归属：
    - 元数据解析 → OntologyBackend.resolve_property_name()
    - 元数据持久化 → OntologyBackend 校验 + TermBackend.create_term_name()
    - 术语检索 → TermBackend.search_terms()
    - 术语持久化 → TermBackend.create_term_name() / import_terms()
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
        self: _HasOntologyAndTermBackend,
        base_id: str,
        query: str,
        slots: list[dict[str, Any]],
        *,
        ontology_code: str = "",
    ) -> dict[str, Any]:
        """准备澄清流程：6 步编排。

        编排说明：
        - 不再调用 provider.prepare_query_clarification（自管 session 的 wrapper）。
        - 6 步原子编排，每步走对应的 platform backend 或 SDK 纯函数。
        - Step 2（字段预解析）：使用 OntologyBackend 做本体元数据 code/name 映射，
          TermBackend 做 prop_type_map 和枚举值查询。

        Pipeline:
          Step 1: 术语提取 → extract_terms_query（纯函数）
          Step 2: 字段预解析 → _pre_resolve_with_backends（OntologyBackend + TermBackend）
          Step 3: 知识召回 → unified_recall（SDK，TODO: session 管理待平台化）
          Step 4a: LLM 主结构确认（SDK LLM 调用）
          Step 4b: LLM 条件确认（SDK LLM 调用）
          Step 5: 结果合并（SDK 纯函数）
          Step 6: 构建 paradigmList（SDK 纯函数）
        """
        from datacloud_knowledge.intent.clarification._merge import (
            build_main_resolution_hints,
            merge_cc_resolution_hints,
            merge_pre_resolve_hints,
            merge_to_confirmed_query,
            normalize_cc_result_with_hints,
        )
        from datacloud_knowledge.intent.clarification._patch import (
            build_pre_resolved_input,
        )
        from datacloud_knowledge.intent.clarification.cartesian import (
            build_paradigm_list,
            serialize_knowledge_meta,
            serialize_paradigm_payload,
        )
        from datacloud_knowledge.intent.clarification.confirm import (
            format_cc_confirm_context,
            format_main_confirm_context,
            llm_confirm_cc,
            llm_confirm_main,
        )
        from datacloud_knowledge.intent.clarification.extract import (
            extract_terms_complex_conditions,
            extract_terms_query,
        )
        from datacloud_knowledge.intent.clarification.models import (
            ClarificationNoCandidatesError,
        )

        structured_input: dict[str, Any] = (
            {"slots": slots} if slots else {"query": query}
        )

        # ── Step 1: 术语提取（纯函数，无 DB 调用）──
        main_terms = extract_terms_query(structured_input)
        complex_conditions: list[str] = structured_input.get("complex_conditions", [])
        cc_terms = (
            extract_terms_complex_conditions(complex_conditions)
            if complex_conditions
            else []
        )
        all_terms = main_terms + cc_terms
        logger.info(
            "[clarification] Step1 术语提取: main=%d cc=%d",
            len(main_terms),
            len(cc_terms),
        )

        # ── Step 2: 字段预解析（OntologyBackend + TermBackend）──
        # 替换 SDK 的 _pre_resolve_terms（内部 create_reader 自管 session）
        # 使用 platform backend 做本体元数据 code/name 映射
        pre = self._pre_resolve_with_backends(  # type: ignore[attr-defined]
            base_id, main_terms, ontology_code
        )
        cc_pre = self._pre_resolve_with_backends(  # type: ignore[attr-defined]
            base_id, cc_terms, ontology_code
        )
        logger.info(
            "[clarification] Step2 预解析: confirmed=%d unresolved=%d",
            len(pre.confirmed),
            len(pre.unresolved_terms),
        )

        # ── Step 3: 定向召回（按领域拆分）──
        # 定范围: OntologyBackend (OWL metadata，零 DB)
        # select/whereKey → search_ontology(metadata) 搜本体元数据
        # whereValue → search_terms(keyword, term_type) 搜术语实例
        recall_terms = list(pre.unresolved_terms) + list(cc_pre.unresolved_terms)
        recall_map = (
            self._unified_recall_with_backends(  # type: ignore[attr-defined]
                base_id,
                recall_terms,
                pre=pre,
                cc_pre=cc_pre,
                scope_code=ontology_code,
            )
            if recall_terms
            else {}
        )
        logger.info(
            "[clarification] Step3 召回: terms=%d recalled=%d",
            len(recall_terms),
            sum(1 for v in recall_map.values() if v),
        )

        # 召回为空时跳过 LLM 确认
        empty_terms: list[str] = []
        for t in recall_terms:
            key = f"{t.ktype}:{t.raw_text}"
            if not t.search_enabled:
                continue
            if not recall_map.get(key):
                empty_terms.append(t.raw_text)
        if empty_terms and all(
            not recall_map.get(f"{t.ktype}:{t.raw_text}")
            for t in recall_terms
            if t.search_enabled
        ):
            raise ClarificationNoCandidatesError(empty_terms)

        # ── Step 4a: LLM 主结构确认 ──
        pre_resolved_input = build_pre_resolved_input(structured_input, pre, main_terms)
        main_context, term_registry = format_main_confirm_context(
            pre_resolved_input,
            main_terms,
            recall_map,
            pre,
            mode="query",
            language="zh_CN",
        )
        main_result = llm_confirm_main(context=main_context, language="zh_CN")

        resolution_hints = build_main_resolution_hints(main_result, term_registry)
        merge_pre_resolve_hints(resolution_hints, pre, main_terms, force_confirm=True)
        merge_pre_resolve_hints(resolution_hints, cc_pre, cc_terms, force_confirm=True)

        # ── Step 4b: 逐条 cc LLM 确认 ──
        cc_results: list[tuple[Any, Any]] = []
        if complex_conditions and cc_terms:
            cc_by_idx: dict[int, list[Any]] = {}
            for t in cc_terms:
                cc_by_idx.setdefault(t.condition_index, []).append(t)
            for idx, sentence in enumerate(complex_conditions):
                group = cc_by_idx.get(idx, [])
                if not group:
                    continue
                cc_context, cc_registry = format_cc_confirm_context(
                    group,
                    recall_map,
                    sentence,
                    idx,
                    language="zh_CN",
                )
                cc_result = llm_confirm_cc(context=cc_context, language="zh_CN")
                cc_result = normalize_cc_result_with_hints(
                    cc_result,
                    cc_registry,
                    resolution_hints,
                    recall_map,
                )
                merge_cc_resolution_hints(resolution_hints, cc_result, cc_registry)
                cc_results.append((cc_result, cc_registry))

        # ── Step 5: 结果合并 ──
        confirmed = merge_to_confirmed_query(
            pre,
            main_result,
            cc_results,
            term_registry,
            structured_input,
            main_terms,
            recall_map=recall_map,
        )

        # ── Step 6: 构建 paradigmList ──
        paradigm_list, meta = build_paradigm_list(
            confirmed,
            all_terms,
            recall_map,
            language="zh_CN",
            complex_conditions=complex_conditions,
            original_structured=structured_input,
        )
        form_payload = serialize_paradigm_payload(paradigm_list)
        knowledge_payload = serialize_knowledge_meta(meta)

        return {
            "needs_clarification": confirmed.needs_clarification,
            "form": form_payload,
            "metadata": knowledge_payload,
        }

    def _pre_resolve_with_backends(
        self: _HasOntologyAndTermBackend,
        base_id: str,
        terms: list[Any],
        scope_code: str,
    ) -> Any:
        """Step 2 原子: 字段预解析（替换 SDK 的 _pre_resolve_terms）。

        编排说明：
        - 使用 OntologyBackend.resolve_property_names() 做本体元数据 code/name 映射
          替代 SDK 的 reader.resolve_field_aliases_with_names()。
        - 使用 TermBackend.search_terms() 做 prop_type_map 和枚举值查询。
        - 不依赖 create_reader()，所有数据访问走 platform backend。

        Returns:
            PreResolveResult（与 SDK 兼容的结构）。
        """
        from datacloud_knowledge.contracts.intent_types import (
            PreResolveResult,
            find_paired_where_key,
            is_field_code,
            term_key,
        )
        from datacloud_knowledge.contracts.types import ResolvedField

        onto = self._ontology_for(base_id)
        term = self._term_for(base_id)

        confirmed: dict[str, Any] = {}
        provenance: dict[str, str] = {}
        value_enum_map: dict[str, list[str]] = {}

        # ── 收集字段类术语（非 whereValue）──
        field_terms_raw: list[str] = []
        for t in terms:
            if not t.search_enabled:
                continue
            if t.ktype == "whereValue" or t.parent_raw_text is not None:
                continue
            if t.raw_text not in field_terms_raw:
                field_terms_raw.append(t.raw_text)

        # ── 一级：本体元数据（OWL 内存，零 DB）──
        if field_terms_raw and scope_code:
            try:
                resolved_by_text = onto.resolve_property_names(
                    field_terms_raw, scope_code, base_id=base_id
                )
                for t in terms:
                    if t.ktype == "whereValue" or t.parent_raw_text is not None:
                        continue
                    pair = resolved_by_text.get(t.raw_text)
                    if pair:
                        tk = term_key(t)
                        confirmed[tk] = ResolvedField(
                            term_code=str(pair[0]), term_name=str(pair[1])
                        )
                        provenance[tk] = (
                            "field_code" if is_field_code(t.raw_text) else "alias_exact"
                        )
                logger.info(
                    "[pre_resolve] onto resolved: %d/%d terms",
                    len(resolved_by_text),
                    len(field_terms_raw),
                )
            except Exception:
                logger.warning("[pre_resolve] ontology resolve failed", exc_info=True)

        # ── 二级：用户别名兜底（TermBackend，知识 DB）──
        unresolved_field_terms: list[str] = [
            t.raw_text
            for t in terms
            if t.ktype != "whereValue"
            and t.parent_raw_text is None
            and t.search_enabled
            and term_key(t) not in confirmed
        ]
        if unresolved_field_terms and scope_code:
            for raw_text in unresolved_field_terms:
                try:
                    sr = term.search_terms(
                        keyword=raw_text,
                        term_type="prop",
                        query_type="fulltext",
                        top_k=1,
                    )
                    items: list[dict[str, Any]] = sr.get("items", [])
                    if items:
                        matched = items[0]
                        tc = str(matched.get("term_code", ""))
                        tn = str(matched.get("term_name", ""))
                        if tc:
                            for t in terms:
                                if (
                                    t.raw_text == raw_text
                                    and term_key(t) not in confirmed
                                ):
                                    confirmed[term_key(t)] = ResolvedField(
                                        term_code=tc, term_name=tn
                                    )
                except Exception:
                    pass

        # ── 查询 ontology 下所有 prop→type 绑定 ──
        prop_type_map: dict[str, str] = {}
        if scope_code:
            try:
                bindings = onto.get_object_property_term_bindings(
                    [scope_code], base_id=base_id
                )
                for b in bindings:
                    pc = str(b.get("propertyCode", ""))
                    if pc:
                        prop_type_map[pc] = pc
                logger.info(
                    "[pre_resolve] prop_type_map loaded: %d props from ontology",
                    len(prop_type_map),
                )
            except Exception:
                logger.warning("[pre_resolve] prop_type_map failed", exc_info=True)

        # 已确认 whereKey → 查枚举值
        confirmed_key_codes: list[str] = []
        for t in terms:
            if t.ktype == "whereKey" and term_key(t) in confirmed:
                rf = confirmed[term_key(t)]
                code = getattr(rf, "term_code", "")
                if code and code not in confirmed_key_codes:
                    confirmed_key_codes.append(str(code))

        if confirmed_key_codes and scope_code:
            try:
                for key_code in confirmed_key_codes:
                    sr = term.search_terms(term_type=key_code, top_k=200)
                    enum_items: list[dict[str, Any]] = sr.get("items", [])
                    enum_values: list[str] = []
                    for item in enum_items:
                        name = str(item.get("term_name", ""))
                        if name:
                            enum_values.append(name)

                    for t in terms:
                        if t.ktype != "whereValue" or not t.search_enabled:
                            continue
                        key_term = find_paired_where_key(t, terms)
                        if key_term and term_key(key_term) in confirmed:
                            rf = confirmed[term_key(key_term)]
                            code = getattr(rf, "term_code", "")
                            if code and str(code) == key_code:
                                tk = term_key(t)
                                value_enum_map.setdefault(tk, []).extend(enum_values)
                                for ev in enum_values:
                                    if ev == t.raw_text:
                                        confirmed[tk] = ResolvedField(
                                            term_code=ev,
                                            term_name=ev,
                                        )
                                        provenance[tk] = "enum_exact"
                                        break
            except Exception:
                logger.warning("[pre_resolve] enum values failed", exc_info=True)

        # 分拣 unresolved
        unresolved: list[Any] = []
        for t in terms:
            if term_key(t) not in confirmed:
                unresolved.append(t)

        return PreResolveResult(
            confirmed=confirmed,
            unresolved_terms=unresolved,
            value_enum_map=value_enum_map,
            provenance=provenance,
            prop_type_map=prop_type_map,
        )

    def _unified_recall_with_backends(
        self: _HasOntologyAndTermBackend,
        base_id: str,
        terms: list[Any],
        *,
        pre: Any,
        cc_pre: Any,
        scope_code: str,
        top_k: int = 10,
    ) -> dict[str, list[dict[str, Any]]]:
        """等价于 unified_recall，但按领域拆分，走 platform backend。

        编排说明：
        - select/whereKey/groupBy/orderBy（category {3} 本体术语）
          → search_ontology(search_scope="metadata") 搜本体元数据（属性名/对象名）
        - whereValue（category {1,2} 术语实例）
          → search_terms(keyword, term_type=<bound_type>) 搜术语实例
          当 whereKey 已确定时，term_type 精确到一个类型 → 检索范围极窄

        输入格式与输出格式与 unified_recall 完全一致。
        """
        from datacloud_knowledge.contracts.intent_types import find_paired_where_key

        onto = self._ontology_for(base_id)
        term_backend = self._term_for(base_id)

        # ── 构建 whereValue→type_code 映射 ──
        prop_type_map: dict[str, str] = getattr(pre, "prop_type_map", {}) or {}
        cc_prop_type_map: dict[str, str] = getattr(cc_pre, "prop_type_map", {}) or {}
        merged_prop_map = {**prop_type_map, **cc_prop_type_map}

        value_type_map: dict[str, str] = {}
        if merged_prop_map:
            for t in terms:
                if getattr(t, "ktype", "") != "whereValue" or not getattr(
                    t, "search_enabled", True
                ):
                    continue
                key_term = find_paired_where_key(t, terms)
                if key_term is None:
                    continue
                type_code = merged_prop_map.get(key_term.raw_text)
                if type_code:
                    value_type_map[getattr(t, "path", "")] = type_code

        # ── Step 3b: select/whereKey/groupBy/orderBy → 搜本体元数据 ──
        field_terms = [
            t
            for t in terms
            if getattr(t, "search_enabled", True)
            and getattr(t, "ktype", "") in ("select", "whereKey", "groupBy", "orderBy")
        ]

        # ── Step 3c: whereValue → 搜术语实例 ──
        value_terms = [
            t
            for t in terms
            if getattr(t, "search_enabled", True)
            and getattr(t, "ktype", "") == "whereValue"
        ]

        # 英文标识符只走向量
        vector_only_terms = [
            t
            for t in terms
            if getattr(t, "search_enabled", True) and getattr(t, "vector_only", False)
        ]

        result: dict[str, list[dict[str, Any]]] = {}

        # ── 搜本体元数据（select/whereKey 等）──
        seen_field: set[str] = set()
        for t in field_terms:
            key = f"{t.ktype}:{t.raw_text}"
            if key in seen_field:
                continue
            seen_field.add(key)

            try:
                sr = onto.search_ontology(
                    base_id,
                    [scope_code],
                    keyword=t.raw_text,
                    search_scope="metadata",
                    limit=top_k,
                )
                metadata_hits: list[dict[str, Any]] = sr.get("metadata", [])
                field_candidates: list[dict[str, Any]] = []
                for hit in metadata_hits:
                    field_candidates.append(
                        {
                            "term_id": hit.get("termCode", hit.get("objectCode", "")),
                            "term_name": hit.get("nameText", ""),
                            "term_type_code": hit.get("termType", ""),
                            "match_type": "ontology_metadata",
                            "confidence": hit.get("score", 0),
                            "score": hit.get("score", 0),
                        }
                    )
                result[key] = field_candidates[:top_k]
            except Exception:
                result[key] = []
                logger.debug(
                    "[recall] ontology search failed for %s", key, exc_info=True
                )

        # ── 搜术语实例（whereValue）──
        seen_value: set[str] = set()
        for t in value_terms:
            key = f"{t.ktype}:{t.raw_text}"
            if key in seen_value:
                continue
            seen_value.add(key)

            # 确定检索范围: whereKey 已确认 → 精确 term_type
            type_code = value_type_map.get(getattr(t, "path", ""))
            if type_code:
                # 已确认 → 直接按 term_type 搜索，范围极窄
                try:
                    v_sr = term_backend.search_terms(
                        keyword=t.raw_text,
                        term_type=type_code,
                        query_type="fulltext",
                        top_k=top_k,
                    )
                except Exception:
                    result[key] = []
                    continue
                v_raw: list[dict[str, Any]] = v_sr.get("items", [])
                v_out: list[dict[str, Any]] = []
                for v_item in v_raw:
                    v_out.append(
                        {
                            "term_id": str(v_item.get("term_id", "")),
                            "term_name": v_item.get("term_name", ""),
                            "term_type_code": v_item.get("term_type_code", ""),
                            "match_type": "multi_recall",
                            "confidence": 0.5,
                            "score": 0.5,
                        }
                    )
                result[key] = v_out[:top_k]
            else:
                # 未确认 → 跨 scope 搜索
                uv_out: list[dict[str, Any]] = []
                uv_seen: set[str] = set()
                try:
                    uv_sr = term_backend.search_terms(
                        keyword=t.raw_text,
                        query_type="fulltext",
                        top_k=top_k,
                    )
                    uv_raw: list[dict[str, Any]] = uv_sr.get("items", [])
                    for uv_item in uv_raw:
                        uv_tid = str(uv_item.get("term_id", ""))
                        if uv_tid and uv_tid not in uv_seen:
                            uv_seen.add(uv_tid)
                            uv_out.append(
                                {
                                    "term_id": uv_tid,
                                    "term_name": uv_item.get("term_name", ""),
                                    "term_type_code": uv_item.get("term_type_code", ""),
                                    "match_type": "multi_recall",
                                    "confidence": 0.5,
                                    "score": 0.5,
                                }
                            )
                except Exception:
                    logger.debug(
                        "[recall] term search failed for %s", key, exc_info=True
                    )
                result[key] = uv_out[:top_k]

        # ── 英文标识符向量召回 ──
        for t in vector_only_terms:
            key = f"{t.ktype}:{t.raw_text}"
            try:
                sr = term_backend.search_terms(
                    keyword=t.raw_text,
                    query_type="vector",
                    top_k=top_k,
                )
                items_vec: list[dict[str, Any]] = sr.get("items", [])
                vec_candidates: list[dict[str, Any]] = []
                for item in items_vec:
                    vec_candidates.append(
                        {
                            "term_id": str(item.get("term_id", "")),
                            "term_name": item.get("term_name", ""),
                            "term_type_code": item.get("term_type_code", ""),
                            "match_type": "vector_recall",
                            "confidence": 0.5,
                            "score": 0.5,
                        }
                    )
                result[key] = vec_candidates[:top_k]
            except Exception:
                result[key] = []

        logger.info(
            "[recall] unified: field=%d value=%d vector=%d total_results=%d",
            len(field_terms),
            len(value_terms),
            len(vector_only_terms),
            sum(len(v) for v in result.values()),
        )
        return result

    def finalize_clarification(
        self: _HasOntologyAndTermBackend,
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
    ) -> dict[str, Any]:
        """完成澄清：应用用户选择 → 标准化 → 持久化。

        编排说明（按领域拆分）：
        - Step A: format_clarification_query/compute — 纯 JSON 操作，无 DB 调用。
          解析前端 paradigmList，将用户选择写回 structured_input。
        - Step B: normalize_clarification_params — 混合 DB/本体操作。
          内部 alias 解析改走 platform backend 体系（OntologyBackend + TermBackend）。
        - Step C: persist — 按领域拆分持久化：
          ・元数据别名（字段名→code 映射）→ _persist_metadata_alias
          ・术语别名（值→标准术语映射）→ _persist_term_alias_from_name
        """
        from datacloud_knowledge.intent.clarification.api import (
            format_clarification_compute,
            format_clarification_query,
        )
        from datacloud_knowledge.intent.clarification.postprocess import (
            normalize_clarification_params,
        )

        # ── Step A: 应用用户选择（纯函数）──
        if form is None or metadata is None:
            raise ValueError("form and metadata are required")
        form_text = form if isinstance(form, str) else json.dumps(form)
        metadata_text = metadata if isinstance(metadata, str) else json.dumps(metadata)

        if mode == "query":
            formatted = format_clarification_query(
                query, structured_input, form_text, metadata_text
            )
        else:
            formatted = format_clarification_compute(
                query, structured_input, form_text, metadata_text
            )

        # ── Step B: 标准化（内部 alias 解析走 platform backend）──
        normalized = normalize_clarification_params(
            formatted,
            ontology_code=ontology_code,
            user_id=user_id,
        )

        # ── Step C: 持久化（按领域拆分）──
        persisted_ids: list[str] = []
        if persist_confirmed_synonyms and user_id and needs_clarification and form:
            form_data: Any = json.loads(form) if isinstance(form, str) else form
            if isinstance(form_data, list):
                paradigm_list: list[dict[str, Any]] = form_data
            elif isinstance(form_data, dict):
                paradigm_list = form_data.get("paradigmList", [])
            else:
                paradigm_list = []
            for paradigm in paradigm_list:
                for result_item in paradigm.get("paradigmResult", []):
                    persisted_ids.extend(
                        self._dispatch_persist(  # type: ignore[attr-defined]
                            base_id, ontology_code, result_item, user_id
                        )
                    )

        # 返回格式保持兼容（与旧 provider.finalize_query_clarification 一致）
        persisted_synonyms = {"created_ids": persisted_ids} if persisted_ids else None
        return {
            "structured_input": normalized,
            "persisted_synonyms": persisted_synonyms,
        }

    # ── Persistence Dispatch (new) ─────────────────────

    def _dispatch_persist(
        self: _HasOntologyAndTermBackend,
        base_id: str,
        ontology_code: str,
        result_item: dict[str, Any],
        user_id: str,
    ) -> list[str]:
        """按结果类型分发持久化：元数据域 vs 术语域。

        编排说明：
        - predicate 类型（field+value）：字段别名走元数据持久化，值别名走术语持久化
        - 普通 keyword 类型：按 choiceKeyword 是否为已知 field_term 判断领域
        - 全新术语（无 term_id，仅有描述字符串）：走术语持久化创建 USER_DEFINED 术语
        """
        result_type = str(result_item.get("type") or "")
        created_ids: list[str] = []

        if result_type == "predicate":
            # 字段别名 → 元数据域持久化
            raw_field = str(result_item.get("field") or "").strip()
            choice_field = str(result_item.get("choiceField") or "").strip()
            if raw_field and choice_field and raw_field != choice_field:
                nid = self._persist_metadata_alias(  # type: ignore[attr-defined]
                    base_id,
                    ontology_code,
                    choice_field,
                    raw_field,
                    user_id,
                )
                if nid:
                    created_ids.append(nid)

            # 值别名 → 术语域持久化
            raw_value = str(result_item.get("value") or "").strip()
            choice_value = str(result_item.get("choiceValue") or "").strip()
            if raw_value and choice_value and raw_value != choice_value:
                nid = self._persist_term_alias_from_name(  # type: ignore[attr-defined]
                    base_id,
                    ontology_code,
                    choice_value,
                    raw_value,
                    user_id,
                )
                if nid:
                    created_ids.append(nid)

        else:
            # 普通 keyword 类型的别名持久化
            keyword = str(result_item.get("keyword") or "").strip()
            choice_keyword = str(result_item.get("choiceKeyword") or "").strip()
            if not keyword or not choice_keyword or keyword == choice_keyword:
                return created_ids

            # 判断 choiceKeyword 是元数据（字段名）还是术语（值）
            onto = self._ontology_for(base_id)
            is_field = (
                onto.resolve_property_name(
                    choice_keyword, ontology_code, base_id=base_id
                )
                is not None
            )

            if is_field:
                nid = self._persist_metadata_alias(  # type: ignore[attr-defined]
                    base_id,
                    ontology_code,
                    choice_keyword,
                    keyword,
                    user_id,
                )
                if nid:
                    created_ids.append(nid)
            else:
                nid = self._persist_term_alias_from_name(  # type: ignore[attr-defined]
                    base_id,
                    ontology_code,
                    choice_keyword,
                    keyword,
                    user_id,
                )
                if nid:
                    created_ids.append(nid)

        return created_ids

    # ── Metadata Persistence (new) ─────────────────────

    def _persist_metadata_alias(
        self: _HasOntologyAndTermBackend,
        base_id: str,
        scope_code: str,
        standard_name: str,
        alias_name: str,
        user_id: str,
    ) -> str | None:
        """元数据域持久化：字段别名。

        编排说明：
        - Step 1: OntologyBackend.resolve_property_name() 校验标准名确实存在于本体中
        - Step 2: TermBackend.search_terms() 找到该属性在知识库中的 term_id
        - Step 3: TermBackend.create_term_name() 持久化用户别名到 term_name 表
        """
        onto = self._ontology_for(base_id)
        resolved = onto.resolve_property_name(
            standard_name, scope_code, base_id=base_id
        )
        if resolved is None:
            return None

        # 通过 TermBackend.search_terms 找到该属性的 term_id
        field_code, _field_name = resolved
        term = self._term_for(base_id)
        search_result = term.search_terms(
            term_name=field_code,
            term_type="prop",
            query_type="exact",
            top_k=1,
        )
        items: list[dict[str, Any]] = search_result.get("items", [])
        if not items:
            return None

        term_id = items[0].get("term_id", "")
        if not term_id:
            return None

        result = term.create_term_name(
            name={
                "term_id": str(term_id),
                "name_text": alias_name,
                "search_scope": {"scope_user_id": user_id},
                "user_id": user_id,
            }
        )
        name_id: str = str(result.get("name_id", ""))
        return name_id if name_id else None

    # ── Term Alias Persistence (new) ──────────────────

    def _persist_term_alias_from_name(
        self: _HasTermBackend,
        base_id: str,
        scope_code: str,
        standard_name: str,
        alias_name: str,
        user_id: str,
    ) -> str | None:
        """术语域持久化：值别名。

        编排说明：
        - Step 1: TermBackend.search_terms() 查找标准术语的 term_id
        - Step 2: TermBackend.create_term_name() 持久化用户别名
        """
        del scope_code  # reserved for future scope filtering

        term = self._term_for(base_id)
        search_result = term.search_terms(
            keyword=standard_name,
            query_type="fulltext",
            top_k=1,
        )
        items: list[dict[str, Any]] = search_result.get("items", [])
        if not items:
            return None

        term_id = items[0].get("term_id", "")
        if not term_id:
            return None

        result = term.create_term_name(
            name={
                "term_id": str(term_id),
                "name_text": alias_name,
                "search_scope": {"scope_user_id": user_id},
                "user_id": user_id,
            }
        )
        name_id: str = str(result.get("name_id", ""))
        return name_id if name_id else None

    # ── Field Aliases ────────────────────────────────

    def resolve_field_aliases(
        self: _HasOntologyAndTermBackend,
        base_id: str,
        field_aliases: dict[str, list[str]],
        *,
        scope_code: str = "",
    ) -> dict[str, list[tuple[str, str]]]:
        """字段别名解析：两级消歧。

        编排说明：
        - 一级（本体元数据）：OntologyBackend.resolve_property_name()
          从 OWL _classes 读取标准 field_name/aliases 映射，零 DB 开销。
        - 二级（用户别名兜底）：TermBackend.search_terms(keyword=term, term_type="prop")
          查询知识 DB 中用户自定义的属性别名。
        - 两级均未命中 → 返回空列表（unresolved）。

        DSL 对应关系：
        - key（field）来自本体元数据，走 OntologyBackend
        - 用户自定义的别名存储在知识 DB，走 TermBackend 兜底
        """
        onto = self._ontology_for(base_id)
        term = self._term_for(base_id)

        result: dict[str, list[tuple[str, str]]] = {}
        for field_name, aliases_list in field_aliases.items():
            all_terms = [field_name] + aliases_list
            resolved: list[tuple[str, str]] = []

            for term_text in all_terms:
                if not term_text.strip():
                    continue

                # ── 一级：本体元数据（OWL 内存，零 DB）──
                if scope_code:
                    pair = onto.resolve_property_name(
                        term_text, scope_code, base_id=base_id
                    )
                    if pair is not None:
                        resolved.append(pair)
                        continue

                # ── 二级：用户别名兜底（知识 DB）──
                search_result = term.search_terms(
                    keyword=term_text,
                    term_type="prop",
                    query_type="fulltext",
                    top_k=5,
                )
                items: list[dict[str, Any]] = search_result.get("items", [])
                for item in items:
                    code = item.get("term_code", "")
                    name = item.get("term_name", "")
                    if code and code not in {r[0] for r in resolved}:
                        resolved.append((str(code), str(name)))

            result[field_name] = resolved

        return result

    # ── Clarification Results ────────────────────────

    def store_clarification_results(
        self: _HasTermBackend,
        base_id: str,
        results: dict[str, Any],
        user_id: str,
    ) -> list[str]:
        """持久化澄清结果（向后兼容封装）。

        编排说明：
        - 不再调用 adapters.store_clarification_results（自管 session 的 wrapper）
        - 改为遍历 results，按 value 类型分发到 TermBackend 的原子方法
        - dict with "term_id" → 已有标准术语的别名，走 create_term_name
        - str（描述） → 全新用户定义术语，走 import_terms
        """
        term = self._term_for(base_id)
        created_ids: list[str] = []

        for mention_text, value in results.items():
            if isinstance(value, dict) and "term_id" in value:
                result = term.create_term_name(
                    name={
                        "term_id": str(value["term_id"]),
                        "name_text": mention_text,
                        "search_scope": {"scope_user_id": user_id},
                        "user_id": user_id,
                    }
                )
                name_id: str = str(result.get("name_id", ""))
                if name_id:
                    created_ids.append(name_id)
            elif isinstance(value, str) and value.strip():
                import_result = term.import_terms(
                    dataset_id="PERSONAL_LIB",
                    terms=[
                        {
                            "term_name": mention_text,
                            "term_type_code": "USER_DEFINED",
                            "domain_ids": ["PERSONAL_DOMAIN"],
                            "knowledge_desc": value,
                            "user_id": user_id,
                        }
                    ],
                )
                new_ids = import_result.get("term_ids", [])
                if new_ids:
                    created_ids.extend(str(tid) for tid in new_ids)

        return created_ids

    # ── Binding & Resolution (new) ────────────────────

    def resolve_value_with_binding(
        self: _HasOntologyAndTermBackend,
        base_id: str,
        scope_code: str,
        field_term: str,
        value_term: str,
    ) -> list[dict[str, Any]]:
        """属性→术语类型绑定 → 按类型检索术语值。

        编排说明（两步，按领域拆分）：
        - Step 1（本体元数据）：OntologyBackend.get_object_property_term_bindings()
          查询 scope 下哪些属性绑定了什么术语类型（HAS_TERM 关系）。
        - Step 2（术语数据）：TermBackend.search_terms(term_type=..., keyword=...)
          在每个绑定的术语类型中检索匹配用户输入的术语值。

        DSL 对应关系：
        - field="处理人" → Step 1 找到绑定的术语类型 "list_handler"
        - value="黄总" → Step 2 在 "list_handler" 类型中检索匹配值
        """
        onto = self._ontology_for(base_id)
        term = self._term_for(base_id)

        # Step 1: 查属性→术语类型绑定（本体元数据，零 DB）
        bindings = onto.get_object_property_term_bindings([scope_code], base_id=base_id)

        # Step 2: 在每个绑定的术语类型中检索术语值
        results: list[dict[str, Any]] = []
        for binding in bindings:
            prop_code = str(binding.get("propertyCode", ""))
            prop_name = str(binding.get("propertyName", ""))
            if prop_code != field_term and prop_name != field_term:
                continue

            search_result = term.search_terms(
                keyword=value_term,
                term_type=prop_code,
                query_type="fulltext",
                top_k=10,
            )
            items: list[dict[str, Any]] = search_result.get("items", [])
            results.extend(items)

        return results

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
