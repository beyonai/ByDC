"""TermStore 协议 — 术语 CRUD 操作接口。

定义面向 HTTP API 的术语存储协议，包含 5 个核心方法：
- query_terms:     检索术语（映射 POST /core/term/queryStandardTerm）
- get_term_detail: 查询术语详情（映射 POST /core/term/queryTermDetail）
- list_terms:      分页列出术语（映射 POST /core/terms/pageList）
- import_terms:    批量新增术语（映射 POST /file/importMultipleTerm）
- update_term:     更新术语（映射 POST /core/terms/updateTerm）

零外部依赖，纯 typing.Protocol。
"""

from __future__ import annotations

from typing import Protocol

from .types import (
    ImportResult,
    LabelCondition,
    LabelFilter,
    QueryResult,
    QueryType,
    TermCreate,
    TermDetail,
    TermUpdate,
)


class TermStore(Protocol):
    """术语存储协议 — 面向 HTTP API 的术语 CRUD 操作接口。

    五个方法分别对应 HTTP API 的五个端点。实现方负责 HTTP 请求组装、
    响应解析和错误处理。编排逻辑（降级、多路召回融合）由调用方负责。
    """

    def query_terms(
        self,
        *,
        dataset_ids: list[str] | None = None,
        keyword: str | None = None,
        term_name: str | None = None,
        term_type: str | list[str] | None = None,
        query_type: QueryType = "fulltext",
        parent_term_code: str | None = None,
        label_filters: list[LabelFilter] | None = None,
        label_condition: LabelCondition = "and",
        term_ids: list[str] | None = None,
        top_k: int = 20,
        offset: int = 0,
    ) -> QueryResult:
        """检索术语。

        映射到 POST /core/term/queryStandardTerm。
        支持全文检索、精确匹配、语义检索和混合召回四种策略。

        Args:
            dataset_ids:      术语库 ID 列表。None/空 = 不限制。
            keyword:          检索关键词（模糊匹配 term_name/term_code）。
            term_name:        术语名称精确匹配。与 keyword 互斥。
            term_type:        术语类型编码。None = 不限制类型。
            query_type:       检索策略（fulltext/exact/embedding/mixed）。
            parent_term_code: 父术语编码过滤。None = 不限制。
            label_filters:    标签过滤条件列表。
            label_condition:  多标签组合方式（and/or）。
            term_ids:         按 ID 列表精确查询。传入时忽略 keyword/query_type。
            top_k:            返回条数（1..200）。
            offset:           分页偏移（>=0）。

        Returns:
            QueryResult，包含 total 和 items（TermItem 列表）。
        """
        ...

    def get_term_detail(
        self,
        *,
        dataset_id: str,
        term_id: str,
    ) -> TermDetail | None:
        """查询单条术语完整详情。

        映射到 POST /core/term/queryTermDetail。
        返回包含 parent_term_name、synonym_list、label_info 的完整详情。

        Args:
            dataset_id: 术语库 ID。
            term_id:    术语 ID。

        Returns:
            TermDetail，不存在返回 None。
        """
        ...

    def list_terms(
        self,
        *,
        dataset_id: str,
        term_type: str | None = None,
        term_type_no_eq: str | None = None,
        page_index: int = 1,
        page_size: int = 50,
    ) -> QueryResult:
        """分页列出术语（每条含完整详情：parentName、synonyms、labelInfo）。

        映射到 POST /core/terms/pageList。返回的 items 为 TermDetail 列表，
        包含 ``parent_term_name``、``synonym_list``、``label_info`` 等
        ``query_terms`` 不返回的完整字段。

        典型用途：
        - 加载某个类型下的全部术语（构建 name index / dimension cache）
        - 无需并发，一个请求替代 N 个 ``get_term_detail``

        Args:
            dataset_id:      术语库 ID。
            term_type:       术语类型编码。None = 不限。
            term_type_no_eq: 排除的术语类型编码。传 ``"-1"`` 表示排除术语类型本身，
                             只返回实例。None = 不过滤。
            page_index:      页码（从 1 开始）。
            page_size:       每页条数。

        Returns:
            QueryResult，其中 items 为 TermDetail 列表。
        """
        ...

    def import_terms(
        self,
        *,
        dataset_id: str,
        terms: list[TermCreate],
    ) -> ImportResult:
        """批量新增术语（含同义词、标签、扩展属性）。

        映射到 POST /file/importMultipleTerm。
        一次请求可导入多条术语，返回成功创建数和 term_id 列表。

        Args:
            dataset_id: 目标术语库 ID。
            terms:      待新增术语列表。

        Returns:
            ImportResult，含创建数和 term_id 列表。
        """
        ...

    def update_term(
        self,
        *,
        dataset_id: str,
        term_id: str,
        updates: TermUpdate,
    ) -> None:
        """更新术语。仅更新非 None 字段。

        映射到 POST /core/terms/updateTerm。
        外部 API 通过 termId 定位术语，updates 中非 None 字段被更新。

        Args:
            dataset_id: 术语库 ID。
            term_id:    术语 ID。
            updates:    更新字段（None = 不修改）。

        Raises:
            ValueError: 术语不存在。
        """
        ...


# ═══════════════════════════════════════════════════════════════════════════════
# 公开 API 导出
# ═══════════════════════════════════════════════════════════════════════════════

__all__ = ["TermStore"]
