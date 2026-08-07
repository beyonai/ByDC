"""非结构化对象实例发现编排（ObjectInstanceDiscoveryMixin）。

流程：① 参数校验 → ② 输入实例定位并读取知识库文件（get_document_content_by_term_id）
→ ③ 已有实例发现（TODO 占位）→ ④ 新实例发现（TODO 占位）→ ⑤ 新实例创建（write
action）→ ⑥ term_id 强校验 → ⑦ 文件登记 → ⑧ 「提及」关系（源→目标，单向幂等）
→ ⑨ 返回结果。

无降级：任何异常直接上抛，由 RPC 层统一映射为错误码。
"""

from __future__ import annotations

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

_PENDING_LABELS: dict[str, Any] = {
    "dc_status": "待整理",
    "dc_failure_reason": None,
    "dc_failure_count": 0,
}


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
            NotImplementedError: ③④ 发现逻辑 TODO 占位。
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

        # ③ 已有实例发现（TODO 占位 → NotImplementedError）
        self._discover_existing_object_instances(
            base_id, content=document.content, object_codes=object_codes
        )

        # ④ 新实例发现（TODO 占位 → NotImplementedError，③ 短路后不可达）
        self._discover_new_object_instances(
            base_id, content=document.content, object_codes=object_codes
        )

        # ⑤⑥⑦⑧ 串联（T2/T3/T4 实现）：新实例创建 → term_id 强校验 → 文件登记 → 提及关系
        return ObjectInstanceDiscoveryResult(items=[])

    async def _create_new_instance_flow(
        self: _ObjectInstanceDiscoveryPlatform,
        *,
        base_id: str,
        source_term_id: str,
        candidate: dict[str, Any],
        session_id: str,
    ) -> ObjectInstanceDiscoveryHit:
        """⑤⑥⑦⑧ 新实例创建链路：创建 → 强校验 → 登记 → 提及关系（T4 串联实现）。"""
        raise NotImplementedError("new instance creation flow is not implemented")

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
        self: _ObjectInstanceDiscoveryPlatform,
        base_id: str,
        *,
        content: str,
        object_codes: list[str],
    ) -> list[dict[str, Any]]:
        """③ 已有实例发现（TODO 占位，后续迭代 T6 实现）。

        接入点（spec D-4.3）：
            ``search_terms_by_labels(
                label_filters=[{field_code: "kb_file_path", ...}],
                label_condition="or",
                term_type_codes=object_codes,
            )``
            + ``_match_chunks_to_terms_by_filepath``
            （``adapters/data_adapter/_ontology_metadata.py`` 既有匹配管道）
        → ``is_new=False`` 候选列表。

        Raises:
            NotImplementedError: 本版未实现。
        """
        raise NotImplementedError("existing instance discovery is not implemented")

    def _discover_new_object_instances(
        self: _ObjectInstanceDiscoveryPlatform,
        base_id: str,
        *,
        content: str,
        object_codes: list[str],
    ) -> list[dict[str, Any]]:
        """④ 新实例发现（TODO 占位，后续迭代 T7 实现）。

        接入点（spec D-4.4）：
            ``build_llm`` + prompt + JSON 解析重试
            （参考 ``services/object_instance_build``、``mixins/document_enrich.py``
            的 LLM 抽取模式）
        → ``[{term_name, object_code, evidence}]`` → 去重（排除已有实例）。

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
