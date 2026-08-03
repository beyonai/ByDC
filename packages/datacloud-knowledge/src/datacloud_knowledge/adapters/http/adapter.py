"""HTTP 适配器 — 同时实现 TermReader 和 TermWriter 协议。

一个类实现两个协议，共享 httpx client，避免重复的 HTTP 配置管理。
协议分离（Reader vs Writer）由类型系统保证 CQRS，
运行时同一个 HTTP 服务自然应共享同一个连接。

通过标签（label）系统将所有协议方法映射到 5 个外部 HTTP API：
- queryStandardTerm:  术语检索
- pageList:           分页列表
- queryTermDetail:    术语详情
- importMultipleTerm: 批量导入
- updateTerm:         术语更新

外部 API 特点（适配器层处理，不暴露到协议）：
- 全部 POST 请求，统一鉴权 Header ``pid``
- ``label`` / ``extAttribution`` 在响应中是 JSON 字符串，请求中是 JSON 对象
- ``synonyms`` 在响应中是 "|" 分隔字符串，请求中是 ``synonymList`` 数组
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from typing import Any

import httpx

from datacloud_knowledge.contracts.term_provider_types import (
    ImportResult,
    LabelCondition,
    LabelFilter,
    QueryResult,
    QueryType,
    TermCreate,
    TermDetail,
    TermUpdate,
)
from datacloud_knowledge.contracts.term_provider_types import (
    TermItem as NewTermItem,
)
from datacloud_knowledge.contracts.types import (
    AmbiguousCandidate,
    DimensionValueItem,
    FieldResolutionResult,
    NameItem,
    PropItem,
    SearchTermsResult,
    ShortestPathNode,
    TagFilter,
    TermNameCreate,
    UserScopedNameItem,
    ValueResolutionResult,
    ValueWithAliases,
)
from datacloud_knowledge.contracts.types import (
    TermItem as OldTermItem,
)

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# queryType / labelFilter 映射辅助
# ═══════════════════════════════════════════════════════════════════════════════

_QUERY_TYPE_MAP: dict[str, str] = {
    "fulltext": "fullTextRecall",
    "exact": "exactMatch",
    "embedding": "embedding",
    "mixed": "mixedRecall",
}


def _map_query_type(qt: QueryType) -> str:
    """将内部 queryType 映射为外部 API queryType。"""
    return _QUERY_TYPE_MAP.get(qt, qt)


def _map_label_filter(f: LabelFilter) -> dict[str, object]:
    """将 LabelFilter 映射为外部 API labelFilter 格式。"""
    result: dict[str, object] = {"fieldCode": f.field_code}
    if f.filter_value is not None:
        result["filterValue"] = f.filter_value
    if f.min_filter_value is not None:
        result["minFilterValue"] = f.min_filter_value
    if f.max_filter_value is not None:
        result["maxFilterValue"] = f.max_filter_value
    return result


def _parse_json_str(raw: object) -> dict[str, str]:
    """解析外部 API 返回的 JSON 字符串字段（label / extAttribution）。

    外部 API 在这些字段上响应是 JSON 字符串，适配器层解析为 dict。
    """
    if raw is None or raw == "":
        return {}
    try:
        parsed = json.loads(str(raw))
        if isinstance(parsed, dict):
            return {str(k): str(v) for k, v in parsed.items()}
    except (json.JSONDecodeError, TypeError):
        pass
    return {}


# ═══════════════════════════════════════════════════════════════════════════════
# 类型转换辅助（新 frozen dataclass TermItem ↔ 旧 Pydantic TermItem）
# ═══════════════════════════════════════════════════════════════════════════════


def _new_to_old_term_item(new_item: NewTermItem) -> OldTermItem:
    """将新类型 TermItem（frozen dataclass）转换为旧类型 TermItem（Pydantic）。"""
    return OldTermItem(
        term_id=new_item.term_id,
        term_code=new_item.term_code,
        term_name=new_item.term_name,
        term_type_code=new_item.term_type,
        desc_summary=new_item.desc or None,
        term_tags=dict(new_item.labels),
        created_time=None,
        updated_time=None,
        score=new_item.score,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 响应解析辅助
# ═══════════════════════════════════════════════════════════════════════════════


def _parse_term_item(raw: dict[str, object]) -> NewTermItem:
    """将外部 API 响应字段映射为 TermItem。

    label / ext_attrs 是 JSON 字符串，需解析为 dict。
    score 恒为 None（外部 API 无此字段）。
    """
    return NewTermItem(
        term_id=str(raw.get("termId", "")),
        term_code=str(raw.get("termCode", "")),
        term_name=str(raw.get("termName", "")),
        term_type=str(raw.get("termType", "")),
        dataset_id=str(raw.get("datasetId", "")),
        parent_term_code=str(raw.get("parentTermCode", "")),
        desc=str(raw.get("termDesc", "")),
        labels=_parse_json_str(raw.get("label", "{}")),
        synonyms=str(raw.get("synonyms", "")),
        ext_attrs=_parse_json_str(raw.get("extAttribution", "{}")),
        created_time=int(str(raw.get("createdTime", 0))),
        updated_time=int(str(raw.get("updatedTime", 0))),
        score=None,
        dataset_data_id=str(raw.get("datasetDataId", "")),
        dataset_file_id=str(raw.get("datasetFileId", "")),
        external_id=str(raw.get("externalId", "")),
        unique_code=str(raw.get("uniqueCode", "")),
    )


def _parse_term_detail(raw: dict[str, object]) -> TermDetail:
    """将外部 API 响应字段映射为 TermDetail（含 parentName/synonyms/labelInfo）。"""
    item = _parse_term_item(raw)

    # 解析 labelInfo 翻译标签列表
    raw_label_info: list[dict[str, str]] = []
    if raw.get("labelInfo") and isinstance(raw["labelInfo"], list):
        raw_label_info = [
            {str(k): str(v) for k, v in li.items()}
            for li in raw["labelInfo"]
            if isinstance(li, dict)
        ]

    # 解析 synonymList 同义词列表
    raw_synonym_list: list[str] = []
    if raw.get("synonymList") and isinstance(raw["synonymList"], list):
        raw_synonym_list = [str(s) for s in raw["synonymList"]]

    return TermDetail(
        term_id=item.term_id,
        term_code=item.term_code,
        term_name=item.term_name,
        term_type=item.term_type,
        dataset_id=item.dataset_id,
        parent_term_code=item.parent_term_code,
        desc=item.desc,
        labels=item.labels,
        synonyms=item.synonyms,
        ext_attrs=item.ext_attrs,
        created_time=item.created_time,
        updated_time=item.updated_time,
        score=item.score,
        dataset_data_id=item.dataset_data_id,
        dataset_file_id=item.dataset_file_id,
        external_id=item.external_id,
        unique_code=item.unique_code,
        parent_term_name=str(raw.get("parentTermName", "")),
        label_info=raw_label_info,
        synonym_list=raw_synonym_list,
        term_type_name=str(raw.get("termTypeName", "")),
    )


def _term_create_to_payload(tc: TermCreate) -> dict[str, object]:
    """将 TermCreate 映射为外部 API 请求 payload。

    desc 字段合并到 extAttribution 中（外部 API 无独立 desc 字段）。
    """
    payload: dict[str, object] = {
        "termName": tc.term_name,
        "termCode": tc.term_code,
        "termType": tc.term_type,
        "parentTermCode": tc.parent_term_code,
        "label": tc.labels,
        "synonymList": tc.synonyms,
    }
    ext: dict[str, str] = dict(tc.ext_attrs)
    if tc.desc:
        ext["desc"] = tc.desc
    payload["extAttribution"] = ext
    return payload


def _split_synonyms(syn_str: str) -> list[str]:
    """将 '|' 分隔的同义词字符串拆分为列表，过滤空字符串。"""
    if not syn_str:
        return []
    return [s for s in syn_str.split("|") if s]


# ═══════════════════════════════════════════════════════════════════════════════
# HttpTermAdapter — 同时实现 TermReader 和 TermWriter
# ═══════════════════════════════════════════════════════════════════════════════


class HttpTermAdapter:
    """HTTP 适配器，同时实现 TermReader 和 TermWriter 协议。

    通过标签（label）系统将全部协议方法映射到 5 个 HTTP API。
    共享 httpx client，协议分离由类型系统保证 CQRS。
    """

    _DEFAULT_DATASET_ID = ""  # 默认术语库 ID，子类可覆盖

    def __init__(
        self,
        base_url: str,
        pid: str,
        *,
        timeout: float = 30.0,
        default_dataset_id: str = "",
    ) -> None:
        """初始化 HTTP 适配器。

        Args:
            base_url: 外部 API 基地址（如 http://api.example.com）。
            pid: 鉴权 Header ``pid`` 值。
            timeout: HTTP 请求超时秒数。
            default_dataset_id: 默认术语库 ID（所有 API 调用无 dataset_id 时使用）。
        """
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=base_url,
            timeout=httpx.Timeout(timeout),
            headers={
                "Content-Type": "application/json",
                "pid": pid,
            },
        )
        self._default_dataset_id = default_dataset_id
        logger.info(
            "HttpTermAdapter 已初始化: base_url=%s timeout=%.1fs",
            self._base_url,
            timeout,
        )

    # ═════════════════════════════════════════════════════════════════════
    # TermReader — 新增协议方法（TermProvider）
    # ═════════════════════════════════════════════════════════════════════

    def query_terms(
        self,
        *,
        dataset_ids: list[str] | None = None,
        keyword: str | None = None,
        term_name: str | None = None,
        term_type: str | None = None,
        query_type: QueryType = "fulltext",
        parent_term_code: str | None = None,
        label_filters: list[LabelFilter] | None = None,
        label_condition: LabelCondition = "and",
        term_ids: list[str] | None = None,
        top_k: int = 20,
        offset: int = 0,
    ) -> QueryResult:
        """检索术语。映射到 POST /core/term/queryStandardTerm。"""
        effective_datasets = dataset_ids or (
            [self._default_dataset_id] if self._default_dataset_id else []
        )
        payload: dict[str, object] = {
            "datasetIds": effective_datasets,
            "keyword": keyword or "",
            "queryType": _map_query_type(query_type),
            "labelCondition": label_condition,
            "parentTermCode": parent_term_code or "",
            "topK": top_k + offset,
        }
        if term_name:
            payload["termName"] = term_name
        if term_type:
            payload["termType"] = term_type
        if term_ids:
            payload["termIdList"] = term_ids
        if label_filters:
            payload["labelFilter"] = [_map_label_filter(f) for f in label_filters]

        resp = self._client.post("/core/term/queryStandardTerm", json=payload)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        items_raw: list[dict[str, object]] = data["resultObject"]["termInfoList"]
        items: list[NewTermItem] = [_parse_term_item(raw) for raw in items_raw]
        total = len(items_raw)
        paged = items[offset : offset + top_k]
        return QueryResult(total=total, items=list(paged))

    def get_term_detail(self, *, dataset_id: str, term_id: str) -> TermDetail | None:
        """查询单条术语完整详情。映射到 POST /core/term/queryTermDetail。"""
        resp = self._client.post(
            "/core/term/queryTermDetail",
            json={
                "datasetId": int(dataset_id),
                "termId": int(term_id),
            },
        )
        data: dict[str, Any] = resp.json()
        if resp.status_code == 404 or data.get("resultCode") != "0":
            return None
        resp.raise_for_status()
        return _parse_term_detail(data["resultObject"])

    def list_terms(
        self,
        *,
        dataset_id: str,
        term_type: str | None = None,
        term_type_no_eq: str | None = None,
        page_index: int = 1,
        page_size: int = 50,
    ) -> QueryResult:
        """分页列出术语。映射到 POST /core/terms/pageList。"""
        ds_id = dataset_id or self._default_dataset_id
        payload: dict[str, object] = {
            "datasetId": ds_id,
            "pageIndex": page_index,
            "pageSize": page_size,
        }
        if term_type is not None:
            payload["termType"] = term_type
        if term_type_no_eq is not None:
            payload["termTypeNoEq"] = term_type_no_eq

        resp = self._client.post("/core/terms/pageList", json=payload)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        result = data["resultObject"]
        rows: list[dict[str, object]] = result["rows"]
        page_info: dict[str, int] = result["pageInfo"]
        items: list[NewTermItem] = [_parse_term_detail(raw) for raw in rows]
        return QueryResult(total=page_info["total"], items=list(items))

    # ═════════════════════════════════════════════════════════════════════
    # TermReader — 已有协议方法（通过标签系统映射）
    # ═════════════════════════════════════════════════════════════════════

    def search_terms_exact(
        self,
        *,
        term_type_code: str,
        keyword: str | None = None,
        tags: Sequence[TagFilter] | None = None,
        limit: int = 20,
        offset: int = 0,
        order_by: str = "relevance",
    ) -> SearchTermsResult:
        """精确检索术语。映射为 query_terms(query_type="exact", term_name=keyword)。"""
        _ = (order_by,)  # HTTP API 不支持排序，默认按 updated_time desc
        # TagFilter → LabelFilter 转换
        label_filters: list[LabelFilter] | None = None
        if tags:
            label_filters = [
                LabelFilter(field_code=t.key, filter_value=str(t.value))
                if isinstance(t.value, str)
                else LabelFilter(field_code=t.key)
                for t in tags
            ]
        result = self.query_terms(
            term_type=term_type_code,
            term_name=keyword,
            query_type="exact",
            top_k=limit,
            offset=offset,
            label_filters=label_filters,
        )
        items = [_new_to_old_term_item(item) for item in result.items]
        return SearchTermsResult(total=result.total, items=items)

    def search_terms(
        self,
        *,
        term_type_code: str,
        keyword: str | None = None,
        tags: Sequence[TagFilter] | None = None,
        limit: int = 20,
        offset: int = 0,
        order_by: str = "relevance",
    ) -> SearchTermsResult:
        """检索术语（含 BM25 兜底）。映射为 query_terms(query_type="fulltext")。"""
        _ = (order_by,)
        label_filters: list[LabelFilter] | None = None
        if tags:
            label_filters = [
                LabelFilter(field_code=t.key, filter_value=str(t.value))
                if isinstance(t.value, str)
                else LabelFilter(field_code=t.key)
                for t in tags
            ]
        # 先精确匹配
        result = self.query_terms(
            term_type=term_type_code,
            term_name=keyword,
            query_type="exact",
            top_k=limit,
            offset=offset,
            label_filters=label_filters,
        )
        # 无结果时降级到全文检索
        if result.total == 0 and keyword:
            result = self.query_terms(
                term_type=term_type_code,
                keyword=keyword,
                query_type="fulltext",
                top_k=limit,
                offset=offset,
                label_filters=label_filters,
            )
        items = [_new_to_old_term_item(item) for item in result.items]
        return SearchTermsResult(total=result.total, items=items)

    def resolve_field_aliases(
        self,
        *,
        terms: Sequence[str],
        scope_code: str,
        library_id: str | None = None,
        resolve_values: bool = False,
        value_terms: Sequence[str] | None = None,
    ) -> FieldResolutionResult:
        """字段别名消歧。

        通过标签系统实现：
        1. query_terms(term_type="prop", label_filters=propOf=scope_code) 获取 scope 下所有 prop
        2. client-side 精确匹配 term_name + synonyms
        3. resolve_values=True 时，对每个 prop 查询子术语做值消歧
        """
        _ = library_id
        unique_field_terms = list(dict.fromkeys(terms)) if terms else []
        unique_value_terms = (
            list(dict.fromkeys(value_terms)) if (resolve_values and value_terms) else []
        )
        if not scope_code or (not unique_field_terms and not unique_value_terms):
            all_unresolved = unique_field_terms + unique_value_terms
            return FieldResolutionResult(unresolved=all_unresolved)

        # Step 1: 获取 scope 下所有 prop
        ds_id = library_id or self._default_dataset_id
        props_result = self.query_terms(
            dataset_ids=[ds_id] if ds_id else None,
            term_type="prop",
            label_filters=[LabelFilter(field_code="propOf", filter_value=scope_code)],
            top_k=500,
        )

        # 按 field_term 匹配
        field_hits: dict[str, dict[str, tuple[str, dict[str, str]]]] = {}
        for item in props_result.items:
            aliases: list[str] = _split_synonyms(item.synonyms)
            all_names = [item.term_name, *aliases]
            for ft in unique_field_terms:
                if ft in all_names:
                    scope = {"scope": scope_code}
                    if ft not in field_hits:
                        field_hits[ft] = {}
                    if item.term_code not in field_hits[ft]:
                        field_hits[ft][item.term_code] = (item.term_name, scope)

        resolved: dict[str, str] = {}
        ambiguous: dict[str, list[AmbiguousCandidate]] = {}
        unresolved: list[str] = []

        for ft in unique_field_terms:
            candidates = field_hits.get(ft)
            if candidates is None:
                unresolved.append(ft)
            elif len(candidates) == 1:
                resolved[ft] = next(iter(candidates))
            else:
                ambiguous[ft] = [
                    AmbiguousCandidate(
                        term_code=code,
                        term_name=name,
                        matched_alias=ft,
                        scope=scope_dict,
                    )
                    for code, (name, scope_dict) in candidates.items()
                ]

        # Step 3: 值消歧（resolve_values=True）
        value_matched: set[str] = set()
        if resolve_values and unique_value_terms:
            # 对每个已解析的 prop，查子术语做值匹配
            for prop_code in resolved.values():
                children = self.query_terms(
                    dataset_ids=[ds_id] if ds_id else None,
                    parent_term_code=prop_code,
                    top_k=500,
                )
                for child in children.items:
                    aliases = _split_synonyms(child.synonyms)
                    all_child_names = [child.term_name, *aliases]
                    for vt in unique_value_terms:
                        if vt in all_child_names:
                            value_matched.add(vt)
            unresolved.extend(t for t in unique_value_terms if t not in value_matched)
        elif unique_value_terms:
            unresolved.extend(unique_value_terms)

        return FieldResolutionResult(
            resolved=resolved,
            ambiguous=ambiguous,
            unresolved=unresolved,
        )

    def resolve_value_aliases(
        self, *, terms: Sequence[str], scope_code: str
    ) -> ValueResolutionResult:
        """属性值精确消歧。

        通过 query_terms 查找 scope 下所有 prop 的子术语，
        匹配 term_name 和 synonyms。
        """
        terms_list = list(terms)
        if not terms_list or not scope_code:
            return ValueResolutionResult(unmatched=terms_list)
        unique_terms = list(dict.fromkeys(terms_list))

        # 获取 scope 下所有 prop
        props_result = self.query_terms(
            term_type="prop",
            label_filters=[LabelFilter(field_code="propOf", filter_value=scope_code)],
            top_k=500,
        )
        matched: set[str] = set()
        for prop_item in props_result.items:
            children = self.query_terms(
                parent_term_code=prop_item.term_code,
                top_k=500,
            )
            for child in children.items:
                aliases = _split_synonyms(child.synonyms)
                all_names = [child.term_name, *aliases]
                for ut in unique_terms:
                    if ut in all_names:
                        matched.add(ut)
        unmatched = [t for t in unique_terms if t not in matched]
        return ValueResolutionResult(matched=matched, unmatched=unmatched)

    def get_object_props_by_code(self, *, scope_code: str) -> list[PropItem]:
        """根据对象 code 查询其所有属性。

        通过标签系统：query_terms(term_type="prop", label_filters=propOf=scope_code)。
        """
        if not scope_code:
            return []
        props_result = self.query_terms(
            term_type="prop",
            label_filters=[LabelFilter(field_code="propOf", filter_value=scope_code)],
            top_k=500,
        )
        return [
            PropItem(
                term_id=item.term_id,
                term_code=item.term_code,
                term_name=item.term_name,
            )
            for item in props_result.items
        ]

    def get_prop_enum_values(
        self, *, scope_code: str, field_codes: Sequence[str]
    ) -> dict[str, list[str]]:
        """查询指定 prop 的枚举值。

        对每个 field_code 查询 parent_term_code=field_code 的子术语，
        收集 term_name 和 synonyms。
        """
        field_codes_list = list(field_codes)
        if not scope_code or not field_codes_list:
            return {}
        unique_codes = list(dict.fromkeys(field_codes_list))
        result: dict[str, list[str]] = {code: [] for code in unique_codes}
        for fc in unique_codes:
            children = self.query_terms(
                parent_term_code=fc,
                top_k=500,
            )
            seen: set[str] = set()
            for child in children.items:
                if child.term_name and child.term_name not in seen:
                    seen.add(child.term_name)
                    result[fc].append(child.term_name)
                for syn in _split_synonyms(child.synonyms):
                    if syn and syn not in seen:
                        seen.add(syn)
                        result[fc].append(syn)
        return result

    def get_term_by_ids(
        self, *, keys: Sequence[tuple[str, str, str]]
    ) -> dict[tuple[str, str, str], str]:
        """批量根据三元组查询 term_id。通过 query_terms 按 term_code 查询。"""
        if not keys:
            return {}
        mapping: dict[tuple[str, str, str], str] = {}
        for library_id, term_type_code, term_code in keys:
            result = self.query_terms(
                term_type=term_type_code,
                term_name=term_code,  # 精确匹配 term_code
                query_type="exact",
                top_k=1,
            )
            if result.items:
                key = (library_id, term_type_code, term_code)
                mapping[key] = result.items[0].term_id
        return mapping

    def get_term_names(
        self,
        *,
        term_ids: Sequence[str],
        scope_filter: dict[str, object] | None = None,
    ) -> dict[str, list[NameItem]]:
        """批量查询术语的所有名称。

        通过并发 get_term_detail 获取同义词列表。
        """
        _ = scope_filter  # HTTP API 不支持 scope 过滤
        term_ids_list = list(term_ids)
        if not term_ids_list:
            return {}
        # 并发查询需要 httpx.AsyncClient，此处用同步顺序查询
        result: dict[str, list[NameItem]] = {}
        for tid in term_ids_list:
            detail = self.get_term_detail(
                dataset_id=self._default_dataset_id,
                term_id=tid,
            )
            if detail is None:
                result[tid] = []
                continue
            names: list[NameItem] = []
            # 标准名称
            if detail.term_name:
                names.append(NameItem(name_text=detail.term_name, is_primary=True))
            # 同义词
            for syn in detail.synonym_list:
                if syn and syn != detail.term_name:
                    names.append(NameItem(name_text=syn, is_primary=False))
            result[tid] = names
        return result

    def get_object_props(self, *, source_term_ids: Sequence[str]) -> dict[str, list[PropItem]]:
        """批量查询对象/视图下的属性。

        对每个 source_term_id，通过 get_term_detail 获取 term_code 后查子 prop。
        """
        source_term_ids_list = list(source_term_ids)
        if not source_term_ids_list:
            return {}
        result: dict[str, list[PropItem]] = {}
        for sid in source_term_ids_list:
            detail = self.get_term_detail(
                dataset_id=self._default_dataset_id,
                term_id=sid,
            )
            if detail is None:
                result[sid] = []
                continue
            props = self.get_object_props_by_code(scope_code=detail.term_code)
            result[sid] = props
        return result

    def get_prop_values_with_aliases(
        self, *, source_term_ids: Sequence[str]
    ) -> dict[str, list[ValueWithAliases]]:
        """HTTP API 不支持此操作。"""
        raise NotImplementedError(
            "HTTP 后端不支持 get_prop_values_with_aliases，请使用 get_prop_enum_values 替代"
        )

    def get_bfs_distance(
        self,
        *,
        source_term_id: str,
        target_term_id: str,
        max_depth: int = 4,
    ) -> int | None:
        """HTTP API 不支持知识图谱遍历。"""
        raise NotImplementedError("HTTP 后端不支持知识图谱 BFS 遍历，仅支持术语 CRUD")

    def get_shortest_path_tree(
        self,
        *,
        target_term_id: str,
        source_term_type_codes: Sequence[str],
        max_depth: int = 6,
    ) -> Sequence[ShortestPathNode]:
        """HTTP API 不支持知识图谱遍历。"""
        raise NotImplementedError("HTTP 后端不支持最短路径树查询，仅支持术语 CRUD")

    def get_dimension_values(self) -> Sequence[DimensionValueItem]:
        """HTTP API 不支持维度值直接查询。"""
        raise NotImplementedError("HTTP 后端不支持维度值查询，请使用 list_terms 替代")

    def get_user_scoped_names(self, *, user_id: str) -> Sequence[UserScopedNameItem]:
        """通过标签系统查询用户作用域下的术语别名。"""
        result = self.query_terms(
            label_filters=[LabelFilter(field_code="userId", filter_value=user_id)],
            top_k=500,
        )
        return [
            UserScopedNameItem(
                name_text=item.term_name,
                term_id=item.term_id,
                term_type_code=item.term_type,
                search_scope={},
            )
            for item in result.items
        ]

    def get_type_codes_by_category(self, *, categories: set[int]) -> set[str]:
        """通过标签系统查询术语类型编码集合。"""
        result: set[str] = set()
        for cat in categories:
            cat_result = self.query_terms(
                term_type="-1",
                label_filters=[LabelFilter(field_code="typeCategory", filter_value=str(cat))],
                top_k=500,
            )
            result.update(item.term_code for item in cat_result.items)
        return result

    def get_matching_objects(
        self,
        *,
        ontology_code: str,
        field_codes: Sequence[str],
        limit: int = 2,
    ) -> Sequence[tuple[str, int]]:
        """HTTP API 不支持复杂对象匹配。"""
        raise NotImplementedError("HTTP 后端不支持对象匹配查询，仅支持术语 CRUD")

    def get_global_name_index(
        self,
    ) -> dict[str, list[tuple[str, str, str]]]:
        """HTTP API 不支持全局名称索引构建（全量遍历太慢）。"""
        raise NotImplementedError("HTTP 后端不支持全局名称索引，请使用 OpenGauss 后端")

    def get_name_ids_by_word(
        self,
        *,
        word: str,
        term_ids: Sequence[str],
        user_id: str | None = None,
    ) -> dict[str, str]:
        """HTTP API 不支持按单词+术语ID查询 name_id。"""
        raise NotImplementedError("HTTP 后端不支持 name_id 查询，仅支持术语 CRUD")

    # ═════════════════════════════════════════════════════════════════════
    # TermReader — 新增领域通用方法（NotImplementedError 占位）
    # ═════════════════════════════════════════════════════════════════════

    def list_domains(self, *, parent_id: str | None = None) -> list[dict[str, Any]]:
        """HTTP API 不支持领域列表查询。"""
        raise NotImplementedError("list_domains not implemented in HTTP adapter")

    def get_domain(self, *, domain_id: str) -> dict[str, Any] | None:
        """HTTP API 不支持领域详情查询。"""
        raise NotImplementedError("get_domain not implemented in HTTP adapter")

    def list_domain_term_types(self, *, domain_id: str) -> list[dict[str, Any]]:
        """HTTP API 不支持领域术语类型查询。"""
        raise NotImplementedError("list_domain_term_types not implemented in HTTP adapter")

    def list_term_libraries(
        self,
        *,
        library_code: str | None = None,
        library_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """HTTP API 不支持术语库列表查询。"""
        raise NotImplementedError("list_term_libraries not implemented in HTTP adapter")

    def get_term_library(self, *, library_id: str) -> dict[str, Any] | None:
        """HTTP API 不支持术语库详情查询。"""
        raise NotImplementedError("get_term_library not implemented in HTTP adapter")

    def list_term_types(self, *, type_category: int | None = None) -> list[dict[str, Any]]:
        """HTTP API 不支持术语类型列表查询。"""
        raise NotImplementedError("list_term_types not implemented in HTTP adapter")

    def get_term_type(self, *, type_code: str) -> dict[str, Any] | None:
        """HTTP API 不支持术语类型详情查询。"""
        raise NotImplementedError("get_term_type not implemented in HTTP adapter")

    def list_term_relations(
        self,
        *,
        source_term_id: str | None = None,
        target_term_id: str | None = None,
        relation_category: str | None = None,
        relation_code: str | None = None,
        keyword: str | None = None,
        page_index: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """HTTP API 不支持术语关系列表查询。"""
        raise NotImplementedError("list_term_relations not implemented in HTTP adapter")

    def get_term_relation(self, *, relation_id: str) -> dict[str, Any] | None:
        """HTTP API 不支持术语关系详情查询。"""
        raise NotImplementedError("get_term_relation not implemented in HTTP adapter")

    def list_term_names(
        self,
        *,
        term_id: str | None = None,
        name_text: str | None = None,
    ) -> list[dict[str, Any]]:
        """HTTP API 不支持术语名称列表查询。"""
        raise NotImplementedError("list_term_names not implemented in HTTP adapter")

    def get_term_name(self, *, name_id: str) -> dict[str, Any] | None:
        """HTTP API 不支持术语名称详情查询。"""
        raise NotImplementedError("get_term_name not implemented in HTTP adapter")

    def list_term_knowledges(
        self,
        *,
        term_id: str | None = None,
        ext_system: str | None = None,
    ) -> list[dict[str, Any]]:
        """HTTP API 不支持术语知识列表查询。"""
        raise NotImplementedError("list_term_knowledges not implemented in HTTP adapter")

    def get_term_knowledge(self, *, knowledge_id: str) -> dict[str, Any] | None:
        """HTTP API 不支持术语知识详情查询。"""
        raise NotImplementedError("get_term_knowledge not implemented in HTTP adapter")

    def query_term_relations(
        self,
        *,
        term_id: str,
        relation_category: str | None = None,
        direction: str = "both",
        depth: int = 1,
    ) -> dict[str, Any]:
        """HTTP API 不支持术语关系图谱查询。"""
        raise NotImplementedError("query_term_relations not implemented in HTTP adapter")

    # ═════════════════════════════════════════════════════════════════════
    # TermWriter — 新增协议方法（TermProvider）
    # ═════════════════════════════════════════════════════════════════════

    def import_terms(
        self,
        *,
        dataset_id: str,
        terms: list[TermCreate],
        backfill: bool = False,
    ) -> ImportResult:
        """批量新增术语。映射到 POST /file/importMultipleTerm。"""
        ds_id = dataset_id or self._default_dataset_id
        payload: dict[str, object] = {
            "datasetId": ds_id,
            "termList": [_term_create_to_payload(t) for t in terms],
        }
        logger.info("import_terms: dataset_id=%s count=%d", ds_id, len(terms))
        resp = self._client.post("/file/importMultipleTerm", json=payload)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        result: dict[str, Any] = data.get("resultObject", data)
        return ImportResult(
            created=result.get("created", len(terms)),
            updated=result.get("updated", 0),
            skipped=result.get("skipped", 0),
            term_ids=result.get("termIds", []),
            errors=result.get("errors", []),
        )

    def update_term(
        self,
        *,
        dataset_id: str,
        term_id: str,
        updates: TermUpdate,
    ) -> None:
        """更新术语。映射到 POST /core/terms/updateTerm。"""
        ds_id = dataset_id or self._default_dataset_id
        payload: dict[str, object] = {
            "datasetId": ds_id,
            "termId": term_id,
        }
        if updates.term_code is not None:
            payload["termCode"] = updates.term_code
        if updates.term_name is not None:
            payload["termName"] = updates.term_name
        if updates.term_type is not None:
            payload["termType"] = updates.term_type
        if updates.parent_term_code is not None:
            payload["parentTermCode"] = updates.parent_term_code
        if updates.desc is not None:
            payload["extAttribution"] = json.dumps({"desc": updates.desc})
        if updates.labels is not None:
            payload["label"] = updates.labels
        if updates.ext_attrs is not None:
            payload["extAttribution"] = updates.ext_attrs
        if updates.synonyms is not None:
            payload["synonymList"] = updates.synonyms

        logger.info("update_term: dataset_id=%s term_id=%s", ds_id, term_id)
        resp = self._client.post("/core/terms/updateTerm", json=payload)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        if data.get("resultCode") != "0":
            msg = f"更新失败: {data.get('resultMsg', 'unknown error')}"
            logger.error("update_term 失败: %s", msg)
            raise ValueError(msg)

    # ═════════════════════════════════════════════════════════════════════
    # TermWriter — 已有协议方法（通过标签系统映射）
    # ═════════════════════════════════════════════════════════════════════

    def insert_term(
        self,
        *,
        term_name: str,
        term_type_code: str,
        library_id: str | None = None,
        domain_ids: list[str],
        parent_term_id: str | None = None,
        term_tags: dict[str, object] | None = None,
        user_id: str | None = None,
    ) -> str:
        """原子插入术语记录。通过 importMultipleTerm 实现。"""
        _ = (domain_ids, user_id)
        ds_id = library_id or self._default_dataset_id
        # 将 term_tags 转换为 labels
        labels: dict[str, str] = {}
        if term_tags:
            labels = {str(k): str(v) for k, v in term_tags.items()}
        result = self.import_terms(
            dataset_id=ds_id,
            terms=[
                TermCreate(
                    term_name=term_name,
                    term_code=f"{term_type_code}_{term_name}",
                    term_type=term_type_code,
                    parent_term_code=parent_term_id or "",
                    labels=labels,
                )
            ],
        )
        if result.errors:
            raise RuntimeError(f"插入术语失败: {result.errors}")
        return result.term_ids[0] if result.term_ids else ""

    def insert_term_knowledge(
        self,
        *,
        term_id: str,
        desc_summary: str,
        desc: str,
    ) -> str:
        """HTTP API 不支持单独创建术语知识记录。"""
        raise NotImplementedError(
            "HTTP 后端不支持 insert_term_knowledge，请使用 create_term_with_knowledge 附带知识描述"
        )

    def create_term_name(
        self,
        *,
        term_id: str,
        name_text: str,
        search_scope: dict[str, object] | None = None,
        user_id: str | None = None,
    ) -> str:
        """创建术语别名。通过 updateTerm 追加 synonymList 实现。

        注：HTTP API 无独立术语别名 CRUD，别名作为同义词追加到术语上。
        scope/score/use_count 等字段在 HTTP API 中无对应概念，传入后会被忽略。
        """
        _ = (search_scope, user_id)
        # 先获取当前同义词列表
        detail = self.get_term_detail(
            dataset_id=self._default_dataset_id,
            term_id=term_id,
        )
        current_synonyms: list[str] = list(detail.synonym_list) if detail else []
        if name_text in current_synonyms:
            return f"syn-{term_id}-{name_text}"  # 幂等：返回伪 name_id
        self.update_term(
            dataset_id=self._default_dataset_id,
            term_id=term_id,
            updates=TermUpdate(synonyms=[*current_synonyms, name_text]),
        )
        return f"syn-{term_id}-{name_text}"

    def batch_create_term_names(
        self,
        *,
        items: Sequence[TermNameCreate],
    ) -> list[str]:
        """批量创建术语别名。逐个调用 create_term_name。"""
        return [
            self.create_term_name(
                term_id=item.term_id,
                name_text=item.name_text,
                search_scope=item.search_scope,
                user_id=item.user_id,
            )
            for item in items
        ]

    def create_term_with_knowledge(
        self,
        *,
        term_name: str,
        term_type_code: str,
        library_id: str | None = None,
        domain_ids: list[str],
        knowledge_desc: str | None = None,
        parent_term_id: str | None = None,
        term_tags: dict[str, object] | None = None,
        user_id: str | None = None,
    ) -> str:
        """创建新术语及其关联知识。通过 importMultipleTerm 实现。"""
        _ = (domain_ids, user_id)
        ds_id = library_id or self._default_dataset_id
        labels: dict[str, str] = {}
        if term_tags:
            labels = {str(k): str(v) for k, v in term_tags.items()}
        result = self.import_terms(
            dataset_id=ds_id,
            terms=[
                TermCreate(
                    term_name=term_name,
                    term_code=f"{term_type_code}_{term_name}",
                    term_type=term_type_code,
                    parent_term_code=parent_term_id or "",
                    desc=knowledge_desc or "",
                    labels=labels,
                    synonyms=[term_name],
                )
            ],
        )
        if result.errors:
            raise RuntimeError(f"创建术语失败: {result.errors}")
        return result.term_ids[0] if result.term_ids else ""

    def batch_create_vocabulary(self, *, words: Sequence[str]) -> None:
        """HTTP API 不支持分词词典写入。"""
        raise NotImplementedError(
            "HTTP 后端不支持 batch_create_vocabulary，分词词典仅 OpenGauss 支持"
        )

    def get_name_search_scope(self, *, name_id: str) -> dict[str, object] | None:
        """HTTP API 不支持 name_id 级 search_scope 查询。"""
        raise NotImplementedError("HTTP 后端不支持 get_name_search_scope，请使用 OpenGauss 后端")

    def update_name_search_scope(
        self,
        *,
        name_id: str,
        search_scope: dict[str, object],
        updated_time: object,
    ) -> None:
        """HTTP API 不支持 name_id 级 search_scope 更新。"""
        raise NotImplementedError("HTTP 后端不支持 update_name_search_scope，请使用 OpenGauss 后端")

    # ═════════════════════════════════════════════════════════════════════
    # TermWriter — 新增领域通用方法（NotImplementedError 占位）
    # ═════════════════════════════════════════════════════════════════════

    def create_domain(self, *, domain: dict[str, Any]) -> dict[str, Any]:
        """HTTP API 不支持领域创建。"""
        raise NotImplementedError("create_domain not implemented in HTTP adapter")

    def update_domain(self, *, domain_id: str, updates: dict[str, Any]) -> None:
        """HTTP API 不支持领域更新。"""
        raise NotImplementedError("update_domain not implemented in HTTP adapter")

    def delete_domain(self, *, domain_id: str) -> None:
        """HTTP API 不支持领域删除。"""
        raise NotImplementedError("delete_domain not implemented in HTTP adapter")

    def create_term_library(self, *, library: dict[str, Any]) -> dict[str, Any]:
        """HTTP API 不支持术语库创建。"""
        raise NotImplementedError("create_term_library not implemented in HTTP adapter")

    def update_term_library(self, *, library_id: str, updates: dict[str, Any]) -> None:
        """HTTP API 不支持术语库更新。"""
        raise NotImplementedError("update_term_library not implemented in HTTP adapter")

    def delete_term_library(self, *, library_id: str) -> None:
        """HTTP API 不支持术语库删除。"""
        raise NotImplementedError("delete_term_library not implemented in HTTP adapter")

    def create_term_type(self, *, term_type: dict[str, Any]) -> dict[str, Any]:
        """HTTP API 不支持术语类型创建。"""
        raise NotImplementedError("create_term_type not implemented in HTTP adapter")

    def update_term_type(self, *, type_code: str, updates: dict[str, Any]) -> None:
        """HTTP API 不支持术语类型更新。"""
        raise NotImplementedError("update_term_type not implemented in HTTP adapter")

    def delete_term_type(self, *, type_code: str) -> None:
        """HTTP API 不支持术语类型删除。"""
        raise NotImplementedError("delete_term_type not implemented in HTTP adapter")

    def create_term_relation(self, *, relation: dict[str, Any]) -> dict[str, Any]:
        """HTTP API 不支持术语关系创建。"""
        raise NotImplementedError("create_term_relation not implemented in HTTP adapter")

    def update_term_relation(self, *, relation_id: str, updates: dict[str, Any]) -> None:
        """HTTP API 不支持术语关系更新。"""
        raise NotImplementedError("update_term_relation not implemented in HTTP adapter")

    def delete_term_relation(self, *, relation_id: str) -> None:
        """HTTP API 不支持术语关系删除。"""
        raise NotImplementedError("delete_term_relation not implemented in HTTP adapter")

    def create_term_name_wrapper(self, *, name: dict[str, Any]) -> dict[str, Any]:
        """HTTP API 不支持 wrapper 式术语名称创建。"""
        raise NotImplementedError("create_term_name_wrapper not implemented in HTTP adapter")

    def update_term_name(self, *, name_id: str, updates: dict[str, Any]) -> None:
        """HTTP API 不支持术语名称更新。"""
        raise NotImplementedError("update_term_name not implemented in HTTP adapter")

    def delete_term_name(self, *, name_id: str) -> None:
        """HTTP API 不支持术语名称删除。"""
        raise NotImplementedError("delete_term_name not implemented in HTTP adapter")

    def create_term_knowledge(self, *, knowledge: dict[str, Any]) -> dict[str, Any]:
        """HTTP API 不支持术语知识创建。"""
        raise NotImplementedError("create_term_knowledge not implemented in HTTP adapter")

    def update_term_knowledge(self, *, knowledge_id: str, updates: dict[str, Any]) -> None:
        """HTTP API 不支持术语知识更新。"""
        raise NotImplementedError("update_term_knowledge not implemented in HTTP adapter")

    def delete_term_knowledge(self, *, knowledge_id: str) -> None:
        """HTTP API 不支持术语知识删除。"""
        raise NotImplementedError("delete_term_knowledge not implemented in HTTP adapter")

    def delete_term(self, *, term_id: str) -> None:
        """HTTP API 不支持术语删除。"""
        raise NotImplementedError("delete_term not implemented in HTTP adapter")

    # ═════════════════════════════════════════════════════════════════════
    # 上下文管理器（TermWriter 协议要求）
    # ═════════════════════════════════════════════════════════════════════

    def __enter__(self) -> HttpTermAdapter:
        """进入上下文管理器。HTTP adapter 无事务，直接返回 self。"""
        return self

    def __exit__(
        self,
        exc_type: object,
        exc_val: object,
        exc_tb: object,
    ) -> None:
        """退出上下文管理器。HTTP adapter 无事务，不做提交/回滚。"""

    # ═════════════════════════════════════════════════════════════════════
    # 资源管理
    # ═════════════════════════════════════════════════════════════════════

    def close(self) -> None:
        """关闭 HTTP 客户端连接。"""
        self._client.close()
        logger.info("HttpTermAdapter 已关闭")
