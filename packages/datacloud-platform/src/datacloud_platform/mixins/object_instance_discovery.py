"""非结构化对象实例发现编排（ObjectInstanceDiscoveryMixin）。

流程：① 参数校验 → ② 输入实例定位并读取知识库文件（get_document_content_by_term_id）
→ ④ LLM 抽取（B 模式，T8）→ ③ AC 锚定（词典快路 + 反查兜底，T7）→ 冲突候选
待裁决（T10）→ ⑤ 新实例创建（write action / AUTO_DISCOVERED 直写）→ ⑥ term_id
强校验 → ⑦ 文件登记 → ⑧ 「提及」关系（源→目标，单向幂等）→ ⑨ 返回结果。

无降级：任何异常直接上抛，由 RPC 层统一映射为错误码。
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any, Protocol

from datacloud_platform.mixins.document import (
    _build_object_file_status,
    build_processing_labels,
)
from datacloud_platform.models.document import (
    DocumentContentResult,
    DocumentEnrichObjectScope,
    DocumentObjectItem,
    DocumentProcessingStatus,
)
from datacloud_platform.models.shared import (
    ObjectInstanceDiscoveryHit,
    ObjectInstanceDiscoveryResult,
    ObjectInstanceWriteMissingTermIdError,
)
from datacloud_platform.services.object_action import (
    invoke_object_write_action,
    unwrap_action_result,
)

logger = logging.getLogger(__name__)

_PENDING_LABELS: dict[str, Any] = {
    "dc_status": "待整理",
    "dc_failure_reason": None,
    "dc_failure_count": 0,
}

# ③ 锚定反查单次检索条数上限（词面相等/子串重叠判定所需的候选窗口）
_ANCHOR_SEARCH_TOP_K = 50


@dataclass(frozen=True)
class _AnchorResult:
    """③ 锚定结果分发（Spec §5.1）。

    Attributes:
        existing: 唯一词面相等命中 → 已有实例候选行（is_new=False，含 evidence）。
        ambiguity: 词面相等命中 ≥2 term → 同名多候选（T10 歧义裁决）。
        synonym: 与已有 term 子串重叠（非相等）→ 同义候选（T10 同义裁决）。
        unanchored: 未锚定 mention 原样返回（走 ⑤ 新实例创建）。
    """

    existing: list[dict[str, Any]]
    ambiguity: list[dict[str, Any]]
    synonym: list[dict[str, Any]]
    unanchored: list[dict[str, Any]]


# ── 词典缓存单例（R-5）────────────────────────────────────────────────────────
# 归属：编排侧（本模块）模块级单例，读取经 ``list_vocabulary`` 协议；
# 缓存只做「候选判定」，不做「最终锚定」——真命中必须经反查拿 term_id（T7）。
# 缓存旧（增删词未刷新）最多损失快路（多走一次 DB 查询），不产生错误锚定。
_cached_vocabulary: frozenset[str] | None = None


def invalidate_vocabulary_cache() -> None:
    """显式失效词典缓存：发现管道创建 term / 回填词后调用。

    置空缓存，下次 discover 重新经 ``list_vocabulary()`` 全量加载 → 飞轮实时。
    """
    global _cached_vocabulary
    _cached_vocabulary = None


class _ObjectInstanceDiscoveryPlatform(Protocol):
    """ObjectInstanceDiscoveryMixin 所依赖的 Platform 最小能力协议。"""

    async def get_document_content_by_term_id(
        self, base_id: str, *, term_id: str
    ) -> DocumentContentResult: ...
    def list_term_relations(self, base_id: str, **kwargs: Any) -> dict[str, Any]: ...
    def create_term_relation(
        self, base_id: str, *, relation: dict[str, Any]
    ) -> dict[str, Any]: ...
    async def save_or_update_object_files(
        self, base_id: str, *, object_files: list[dict[str, Any]]
    ) -> Any: ...
    def list_vocabulary(self, base_id: str) -> list[str]: ...
    def search_terms(self, base_id: str, **kwargs: Any) -> Any: ...
    def list_term_names(self, base_id: str, **kwargs: Any) -> list[dict[str, Any]]: ...


class ObjectInstanceDiscoveryMixin:
    """非结构化对象实例发现编排（与 DocumentMixin 平级，不继承）。

    通过 ``_ObjectInstanceDiscoveryPlatform`` 声明对平台的最小能力依赖。
    """

    async def discover_object_instances_unstructured(
        self: Any,
        base_id: str,
        *,
        instance_id: str,
        object_codes: list[str],
        session_id: str,
    ) -> ObjectInstanceDiscoveryResult:
        """从输入实例的知识库文件中发现对象实例。

        Args:
            base_id: 本体库/系统空间标识。
            instance_id: 输入实例的 term_id。
            object_codes: 非结构化对象类型编码列表（已有实例匹配范围 + 新实例候选类型）。
            session_id: 会话 ID，用于文件登记条目的 sessionId 字段。

        Returns:
            发现结果信封；已有实例在前、新实例在后，每项含 is_new 标记。

        Raises:
            ValueError: 入参非法（instance_id 为空 / object_codes 缺失）。
            KeyError: 输入实例不存在。
            NotImplementedError: ④ 发现逻辑 TODO 占位（T8 替换）。
        """
        # ① 参数校验
        if not instance_id.strip():
            raise ValueError("instance_id is required")
        if not object_codes:
            raise ValueError("object_codes must be a non-empty list")
        if not all(str(code).strip() for code in object_codes):
            raise ValueError("object_codes must not contain blank values")

        # ② 输入实例定位 + 读文件（异常原样上抛，无降级）
        document = await self.get_document_content_by_term_id(
            base_id, term_id=instance_id
        )

        # ④ LLM 抽取（B 模式，T8）→ mention 列表（实现编排 ④→③，对外顺序不变）
        mentions = self._discover_new_object_instances(
            base_id, content=document.content, object_codes=object_codes
        )

        # ③ AC 锚定（词典快路 + 反查兜底，T7）→ 结果分发
        anchor = self._discover_existing_object_instances(
            base_id, mentions=mentions, object_codes=object_codes
        )

        # ⑤⑥⑦⑧ 串联：已有在前、新在后；未锚定逐项 创建 → 强校验 → 登记 → 提及关系
        items: list[ObjectInstanceDiscoveryHit] = [
            _build_existing_hit(row) for row in anchor.existing
        ]
        for candidate in anchor.unanchored:
            items.append(
                await self._create_new_instance_flow(
                    base_id=base_id,
                    source_term_id=instance_id,
                    candidate=candidate,
                    session_id=session_id,
                )
            )
        # 歧义/同义冲突候选：T10 同步裁决接入前保守跳过（不建重复实例、不产已有 hit）
        pending_count = len(anchor.ambiguity) + len(anchor.synonym)
        if pending_count:
            logger.info(
                "discover: %d 个冲突候选待 T10 裁决（歧义=%d 同义=%d）",
                pending_count,
                len(anchor.ambiguity),
                len(anchor.synonym),
            )
        return ObjectInstanceDiscoveryResult(items=items)

    def _vocabulary_words(
        self: _ObjectInstanceDiscoveryPlatform, base_id: str
    ) -> frozenset[str]:
        """惰性加载词典缓存（单例，R-5）。

        全量 term_vocabulary → frozenset，O(1) 命中判定。只做候选判定，
        不做最终锚定（真命中必须经反查拿 term_id）。失效经
        :func:`invalidate_vocabulary_cache` 显式触发，下次访问重载。

        Args:
            base_id: 本体库/系统空间标识（透传 list_vocabulary 协议）。

        Returns:
            词典词集合（frozenset）。
        """
        global _cached_vocabulary
        if _cached_vocabulary is None:
            words = self.list_vocabulary(base_id)
            _cached_vocabulary = frozenset(words)
        return _cached_vocabulary

    async def _create_new_instance_flow(
        self: Any,
        *,
        base_id: str,
        source_term_id: str,
        candidate: dict[str, Any],
        session_id: str,
    ) -> ObjectInstanceDiscoveryHit:
        """⑤⑥⑦⑧ 新实例创建链路：创建 → 强校验 → 登记 → 提及关系。

        Args:
            base_id: 本体库/系统空间标识。
            source_term_id: 输入实例 term_id（提及关系源）。
            candidate: 新实例候选 ``{"term_name", "object_code", "evidence"}``。
            session_id: 会话 ID（透传文件登记）。

        Returns:
            新实例发现结果项（is_new=True，relation_name="提及"）。

        Raises:
            ValueError: 候选缺 object_code/term_name。
            ObjectInstanceWriteMissingTermIdError: write 响应缺 term_id。
        """
        object_code = str(candidate["object_code"]).strip()
        term_name = str(candidate["term_name"]).strip()
        if not object_code or not term_name:
            raise ValueError("discovered candidate must have object_code and term_name")
        evidence = candidate.get("evidence")
        evidence_text = str(evidence) if evidence is not None else None

        term_id = await self._create_discovered_instance(
            base_id=base_id,
            object_code=object_code,
            term_name=term_name,
            session_id=session_id,
        )
        await self._register_object_file(
            base_id=base_id,
            object_code=object_code,
            term_name=term_name,
            term_id=term_id,
            session_id=session_id,
            action_result={"records": [{"term_id": term_id}]},
        )
        self._establish_mention_relation(
            base_id=base_id,
            source_term_id=source_term_id,
            target_term_id=term_id,
        )
        return ObjectInstanceDiscoveryHit(
            instance_id=term_id,
            instance_code=term_name,
            instance_name=term_name,
            object_code=object_code,
            file_name=f"/{object_code}/{term_name}.md",
            kb_resource_id=None,
            kb_id=None,
            is_new=True,
            evidence=evidence_text,
        )

    async def _create_discovered_instance(
        self: Any,
        *,
        base_id: str,
        object_code: str,
        term_name: str,
        session_id: str,
    ) -> str:
        """⑤⑥ 新实例创建 + term_id 强校验。

        经 ``invoke_object_write_action``（services/object_action.py）写入知识库
        文件（write_<object_code> action），对响应做 term_id 强校验。

        Args:
            base_id: 本体库/系统空间标识。
            object_code: 新实例对象类型编码。
            term_name: 新实例名称。
            session_id: 会话 ID（本方法不使用，保留签名以透传后续登记）。

        Returns:
            强校验非空的 term_id。

        Raises:
            ObjectInstanceWriteMissingTermIdError: write 响应缺 term_id。
        """
        labels = build_processing_labels(
            initial_status=DocumentProcessingStatus.PENDING_ORGANIZATION,
            labels=_PENDING_LABELS,
        )
        term_name = term_name.strip()
        content = f"# {term_name}\n\n{term_name}对象实例文档。"
        source_path = f"/{object_code}/{term_name}.md"
        result = await invoke_object_write_action(
            platform=self,
            base_id=base_id,
            object_code=object_code,
            content=content,
            labels=labels,
            file_description=f"{term_name}对象实例文档",
            source_path=source_path,
        )
        return _extract_written_term_id(result)

    def _discover_existing_object_instances(
        self: Any,
        base_id: str,
        *,
        mentions: list[dict[str, Any]],
        object_codes: list[str],
    ) -> _AnchorResult:
        """③ 已有实例发现（AC 文本锚定，Spec §5.1）。

        对 ④ 产出的 mention 列表做 词典快路命中 → 反查兜底拿 term_id →
        结果分发：

        - 唯一词面相等命中 1 term → ``existing``（is_new=False，evidence=mention）
        - 词面相等命中 ≥2 term → ``ambiguity``（同名多候选，T10 歧义裁决）
        - 与已有 term 子串重叠（非相等）→ ``synonym``（同义候选，T10 裁决）
        - 无命中 / 缓存命中但反查落空 → ``unanchored``（走 ⑤ 新实例创建）

        ``object_codes`` 保留以维持签名稳定（v3 锚定不做类型过滤，命中即已有实例）。

        Args:
            base_id: 本体库/系统空间标识。
            mentions: ④ 产出的 mention 列表 ``[{term_name, object_code, evidence, raw_type}]``。
            object_codes: 非结构化对象类型编码列表（本版仅透传，不参与过滤）。

        Returns:
            锚定结果分发（_AnchorResult 四桶）。
        """
        vocabulary = self._vocabulary_words(base_id)
        existing: list[dict[str, Any]] = []
        ambiguity: list[dict[str, Any]] = []
        synonym: list[dict[str, Any]] = []
        unanchored: list[dict[str, Any]] = []

        for mention in mentions:
            name = str(mention.get("term_name") or "").strip()
            if not name:
                logger.debug("跳过空 mention: %s", mention)
                continue
            # 快路：词典缓存命中判定（O(1)）
            if name not in vocabulary:
                unanchored.append(mention)
                continue
            # 反查兜底：按 mention 拿 term_id 才算真命中
            rows, surface_exact = self._reverse_lookup_terms(base_id, name)
            if not rows:
                # 缓存旧（词已删/改名/孤儿词）→ 按未锚定处理，不报错、不建实例
                logger.info("词典命中但反查落空（缓存旧或孤儿词）: %s", name)
                unanchored.append(mention)
                continue
            # 分发（词面相等判定）
            if surface_exact:
                # 精确路径（term_name / term_code / TermName 别名）→ 全部词面相等命中
                surface = rows
            else:
                # BM25 / ilike 部分匹配路径 → 仅 term_name 词面相等者才算
                surface = [row for row in rows if _row_term_name(row) == name]
            if len(surface) == 1:
                hit_row = _term_row_to_hit_row(surface[0])
                hit_row["evidence"] = name
                existing.append(hit_row)
            elif len(surface) >= 2:
                ambiguity.append({"mention": name, "terms": surface})
            else:
                overlap = [
                    row for row in rows if _substring_overlap(name, _row_term_name(row))
                ]
                if overlap:
                    synonym.append(
                        {"mention": name, "term": _term_row_to_hit_row(overlap[0])}
                    )
                else:
                    unanchored.append(mention)
        return _AnchorResult(
            existing=existing,
            ambiguity=ambiguity,
            synonym=synonym,
            unanchored=unanchored,
        )

    def _reverse_lookup_terms(
        self: _ObjectInstanceDiscoveryPlatform, base_id: str, name: str
    ) -> tuple[list[dict[str, Any]], bool]:
        """按 mention 反查 term（拿 term_id 才算真命中）。

        三级兜底（R-1）：
        ① ``search_terms`` 精确匹配（term_name / term_code，别名经 TermName 自动参与）
        ② 无命中 → ``search_terms`` BM25 全文兜底（JOIN term_name）
        ③ 仍无命中 → ``list_term_names(name_text=mention)`` ilike 别名反查
           → term_ids 反查 term 详情

        Args:
            base_id: 本体库/系统空间标识。
            name: mention 文本。

        Returns:
            ``(rows, surface_exact)``：
            - rows: 匹配 term 行列表（空列表 = 未锚定）。
            - surface_exact: True=全部行按词面精确命中（term_name/term_code/别名
              完全相等，别名反查路径亦属词面命中）；False=仅模糊/部分匹配
              （BM25 / ilike），需调用方按 term_name 词面相等再判定。
        """
        exact = self.search_terms(
            base_id, term_name=name, query_type="exact", top_k=_ANCHOR_SEARCH_TOP_K
        )
        rows = _search_result_items(exact)
        if rows:
            return rows, True

        fuzzy = self.search_terms(
            base_id, keyword=name, query_type="fulltext", top_k=_ANCHOR_SEARCH_TOP_K
        )
        rows = _search_result_items(fuzzy)
        if rows:
            return rows, False

        name_rows = self.list_term_names(base_id, name_text=name)
        if not name_rows:
            return [], False
        term_ids = sorted({str(r["term_id"]) for r in name_rows if r.get("term_id")})
        if not term_ids:
            return [], False
        by_ids = self.search_terms(
            base_id, term_ids=term_ids, top_k=_ANCHOR_SEARCH_TOP_K
        )
        detail_rows = _search_result_items(by_ids)
        if not detail_rows:
            return [], False
        # ilike 路径：name_text 完全相等 = 词面命中（别名反查路径 R-1）；
        # 仅部分匹配（ilike %mention%）→ 模糊，需调用方做子串/相等判定。
        surface_exact = any(str(r.get("name_text") or "") == name for r in name_rows)
        return detail_rows, surface_exact

    def _discover_new_object_instances(
        self: _ObjectInstanceDiscoveryPlatform,
        base_id: str,
        *,
        content: str,
        object_codes: list[str],
    ) -> list[dict[str, Any]]:
        """④ 新实例发现（TODO 占位，后续迭代 T8 实现）。

        接入点（spec D-4.4 / §6 B 模式）：
            ``build_llm`` + prompt（类型枚举 = object_codes 的 TermType 中文名）
            + temp=0 + 16K 截断 + JSON 解析重试（≤3 次退避）
            → ``[{term_name, object_code|AUTO_DISCOVERED, evidence, raw_type}]``
            → D-2 回填 ``batch_create_vocabulary``（抽到就填，幂等）。

        Raises:
            NotImplementedError: 本版未实现。
        """
        raise NotImplementedError("new instance discovery is not implemented")

    async def _register_object_file(
        self: _ObjectInstanceDiscoveryPlatform,
        *,
        base_id: str,
        object_code: str,
        term_name: str,
        term_id: str,
        session_id: str,
        action_result: dict[str, Any],
    ) -> None:
        """⑦ 文件登记：复用 document.py 的 ``_build_object_file_status`` 模式。

        登记条目含 sessionId / objectName / objectCode / fileName / filePath /
        version / statusCd（待整理）/ extContent{kb_resource_id, kb_id,
        kb_directory, term_id=强校验值}。

        Args:
            base_id: 本体库/系统空间标识。
            object_code: 新实例对象类型编码。
            term_name: 新实例名称。
            term_id: 强校验后的 term_id（write action 响应）。
            session_id: 会话 ID（透传为登记条目 sessionId）。
            action_result: write action 归一化响应（提供 fileName/termId）。
        """
        term_name = term_name.strip()
        file_path = f"/{object_code}/{term_name}.md"
        document = DocumentObjectItem(
            termId=term_id,
            termName=term_name,
            termCode=term_name,
            termTypeCode=object_code,
            filePath=file_path,
            kbResourceId="",
        )
        object_scope = DocumentEnrichObjectScope(
            objectCode=object_code,
            objectName=term_name,
        )
        object_file = _build_object_file_status(
            session_id=session_id,
            document=document,
            object_scope=object_scope,
            status=DocumentProcessingStatus.PENDING_ORGANIZATION,
            labels=_PENDING_LABELS,
            action_result=action_result,
        )
        await self.save_or_update_object_files(base_id, object_files=[object_file])

    def _establish_mention_relation(
        self: _ObjectInstanceDiscoveryPlatform,
        *,
        base_id: str,
        source_term_id: str,
        target_term_id: str,
    ) -> bool:
        """⑧ 建立「提及」关系（源→目标，单向、幂等）。

        先按源实例 + 关键词「提及」查重；已存在同源同目标的提及关系则跳过，
        否则创建 camelCase 三字段关系。方向固定为 源=输入实例 → 目标=发现实例，
        不建反向。

        Args:
            base_id: 本体库/系统空间标识。
            source_term_id: 输入实例 term_id（关系源）。
            target_term_id: 发现实例 term_id（关系目标）。

        Returns:
            True=本次创建了关系；False=关系已存在（跳过）。

        Raises:
            list/create 失败时原样上抛（无降级）。
        """
        page = self.list_term_relations(
            base_id, source_term_id=source_term_id, keyword="提及"
        )
        for row in _relation_items(page):
            relation_name = str(
                row.get("relation_name") or row.get("relationName") or ""
            )
            target = str(row.get("target_term_id") or row.get("targetTermId") or "")
            if relation_name == "提及" and target == target_term_id:
                return False
        self.create_term_relation(
            base_id,
            relation={
                "sourceTermId": source_term_id,
                "targetTermId": target_term_id,
                "relationName": "提及",
            },
        )
        return True


def _extract_written_term_id(action_result: dict[str, Any]) -> str:
    """⑥ term_id 强校验：从 write action 响应中提取 records[0] 的 term_id。

    响应先经 ``unwrap_action_result`` 归一化为 ``{records, total, meta}``；
    取 ``records[0].term_id / termId``，缺失或为空则抛错（不延迟、不做 pending）。

    Args:
        action_result: write action 原始响应（可为未归一化信封）。

    Returns:
        强校验非空的 term_id（去除首尾空白）。

    Raises:
        ObjectInstanceWriteMissingTermIdError: records 缺失或 term_id 缺失/为空。
    """
    normalized = unwrap_action_result(action_result)
    records = normalized.get("records")
    first = (
        records[0]
        if isinstance(records, list) and records and isinstance(records[0], dict)
        else None
    )
    term_id = (
        str(first.get("term_id") or first.get("termId") or "").strip() if first else ""
    )
    if not term_id:
        raise ObjectInstanceWriteMissingTermIdError(
            "write action response is missing term_id"
        )
    return term_id


def _relation_items(page: dict[str, Any]) -> list[dict[str, Any]]:
    """从 list_term_relations 响应中提取关系记录行（兼容 data/items/records）。"""
    rows = page.get("data") or page.get("items") or page.get("records") or []
    return [row for row in rows if isinstance(row, dict)]


def _search_result_items(result: Any) -> list[dict[str, Any]]:
    """从 search_terms 响应提取术语行（兼容 QueryResult dataclass / dict 信封）。

    TermItem 为 frozen dataclass → asdict 归一化为 dict，供锚定判定使用。
    """
    if result is None:
        return []
    if isinstance(result, dict):
        raw = result.get("items") or result.get("data") or result.get("records") or []
    else:
        raw = getattr(result, "items", None)
        if raw is None:
            raw = getattr(result, "data", None) or []
    rows: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict):
            rows.append(item)
        elif hasattr(item, "__dataclass_fields__"):
            rows.append(asdict(item))
        else:
            rows.append(
                {
                    key: getattr(item, key)
                    for key in vars(item)
                    if not key.startswith("_")
                }
            )
    return rows


def _row_term_name(row: dict[str, Any]) -> str:
    """取术语行的标准名称（兼容 camelCase / snake_case）。"""
    return str(row.get("term_name") or row.get("termName") or "").strip()


def _substring_overlap(left: str, right: str) -> bool:
    """词面互为子串（非相等）——同义裁决候选触发条件。"""
    return left != right and (left in right or right in left)


def _term_row_to_hit_row(row: dict[str, Any]) -> dict[str, Any]:
    """把 search_terms 术语行归一化为已有实例候选行（_build_existing_hit 输入形态）。

    兼容 TermItem 的 ``term_type`` 字段与既有 ``term_type_code`` / ``termTypeCode``。
    """
    return {
        "term_id": str(row.get("term_id") or row.get("termId") or ""),
        "term_code": str(row.get("term_code") or row.get("termCode") or ""),
        "term_name": str(row.get("term_name") or row.get("termName") or ""),
        "term_type_code": str(
            row.get("term_type_code")
            or row.get("termTypeCode")
            or row.get("term_type")
            or ""
        ),
        "file_name": str(row.get("file_name") or row.get("fileName") or "") or None,
        "kb_resource_id": str(
            row.get("kb_resource_id") or row.get("kbResourceId") or ""
        )
        or None,
        "kb_id": str(row.get("kb_id") or row.get("kbId") or "") or None,
    }


def _build_existing_hit(row: dict[str, Any]) -> ObjectInstanceDiscoveryHit:
    """把已有实例候选行组装为发现结果项（is_new=False）。

    候选行字段与 ObjectInstanceHit 对齐：
    term_id / term_code / term_name / term_type_code（或 term_type）/
    file_name / kb_resource_id / kb_id / evidence
    （同时兼容 camelCase 变体）。
    """
    evidence = row.get("evidence")
    return ObjectInstanceDiscoveryHit(
        instance_id=str(row["term_id"]),
        instance_code=str(row.get("term_code") or row.get("termCode") or ""),
        instance_name=str(row.get("term_name") or row.get("termName") or ""),
        object_code=str(
            row.get("term_type_code")
            or row.get("termTypeCode")
            or row.get("term_type")
            or ""
        ),
        file_name=str(row.get("file_name") or row.get("fileName") or "") or None,
        kb_resource_id=str(row.get("kb_resource_id") or row.get("kbResourceId") or "")
        or None,
        kb_id=str(row.get("kb_id") or row.get("kbId") or "") or None,
        is_new=False,
        evidence=str(evidence) if evidence is not None else None,
    )
