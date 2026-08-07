"""非结构化对象实例发现编排（ObjectInstanceDiscoveryMixin）。

流程：① 参数校验 → ② 输入实例定位并读取知识库文件（get_document_content_by_term_id）
→ ③ 已有实例发现（TODO 占位）→ ④ 新实例发现（TODO 占位）→ ⑤ 新实例创建（write
action）→ ⑥ term_id 强校验 → ⑦ 文件登记 → ⑧ 「提及」关系（源→目标，单向幂等）
→ ⑨ 返回结果。

无降级：任何异常直接上抛，由 RPC 层统一映射为错误码。
"""

from __future__ import annotations

from typing import Any, Protocol

from datacloud_platform.models.document import DocumentContentResult
from datacloud_platform.models.shared import (
    ObjectInstanceDiscoveryHit,
    ObjectInstanceDiscoveryResult,
)


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
        """⑤⑥⑦⑧ 新实例创建链路：创建 → 强校验 → 登记 → 提及关系（T2/T3 实现）。"""
        raise NotImplementedError("new instance creation flow is not implemented")

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
