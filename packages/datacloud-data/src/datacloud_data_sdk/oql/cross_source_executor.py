"""
OQL 跨源执行器（策略 B）

职责：
1. 两阶段跨源执行
2. 同源/跨源 include_links 分类
3. 大 IN 自动分批
4. 内存合并
"""

from __future__ import annotations
import logging
from typing import Any

from datacloud_data_sdk.oql.adapter import (
    OqlAdapter, resolve_object, resolve_column, build_field_map,
    translate_conditions, preprocess_where_terms
)
from datacloud_data_sdk.oql.memory_merger import MemoryMerger
from datacloud_data_sdk.oql.models import OQLError, OQLErrorCode

logger = logging.getLogger(__name__)


def classify_include_links(include_links: list[dict], root_cls: Any, registry) -> tuple[list, list]:
    """
    分类 include_links 为同源和跨源。

    Args:
        include_links: include_links 列表
        root_cls: 根对象
        registry: 本体注册表

    Returns:
        (same_source_links, cross_source_links) 元组
    """
    same_source = []
    cross_source = []

    for link in include_links:
        path = link.get("path", "")
        path_segments = path.split(".")

        current_cls = root_cls
        is_same_source = True

        for segment in path_segments:
            # 查找关系
            rel = None
            if hasattr(current_cls, 'relations'):
                for r in current_cls.relations:
                    if r.relation_code == segment:
                        rel = r
                        break

            if rel is None:
                raise OQLError(
                    OQLErrorCode.OQL_ERR_UNKNOWN_RELATION,
                    f"关系 '{segment}' 不存在于对象 '{current_cls.object_code}'"
                )

            target_cls = registry.get_class(rel.target_class)
            if target_cls is None:
                raise OQLError(
                    OQLErrorCode.OQL_ERR_UNKNOWN_OBJECT,
                    f"目标对象 '{rel.target_class}' 不存在"
                )

            # 判断是否同源
            if target_cls.source_type != "DB" or target_cls.datasource_alias != root_cls.datasource_alias:
                is_same_source = False
                break

            current_cls = target_cls

        if is_same_source:
            same_source.append(link)
        else:
            cross_source.append(link)

    return same_source, cross_source


class CrossSourceExecutor:
    """跨源执行器"""

    BATCH_SIZE = 1000

    def execute(
        self,
        oql_params: dict,
        root_cls: Any,
        registry,
        term_resolver,
        executor,
        datasource_registry
    ) -> list[dict]:
        """
        两阶段跨源执行。

        Phase 1: 查主对象（同源 include_links 可下推 SQL JOIN）
        Phase 2: 逐跳查关联对象（内存合并）

        Args:
            oql_params: OQL 参数
            root_cls: 根对象
            registry: 本体注册表
            term_resolver: 术语解析器
            executor: 执行器
            datasource_registry: 数据源注册表

        Returns:
            合并后的结果列表
        """
        include_links = oql_params.get("include_links", [])
        same_source, cross_source = classify_include_links(include_links, root_cls, registry)

        # Phase 1: 查主对象（同源 include_links 下推）
        phase1_params = dict(oql_params)
        phase1_params["include_links"] = same_source

        adapter = OqlAdapter()
        db_type = self._get_db_type(root_cls, datasource_registry)
        task = adapter.translate(phase1_params, root_cls, db_type, registry, term_resolver)

        main_records = executor.run(task)
        if not isinstance(main_records, list):
            main_records = [main_records]

        # Phase 2: 逐跳查关联对象
        for link in cross_source:
            path = link.get("path", "")
            select_fields = link.get("select", [])

            main_records = self._execute_cross_link(
                main_records, path, select_fields, root_cls, registry,
                term_resolver, executor, datasource_registry
            )

        return main_records

    def _execute_cross_link(
        self,
        main_records: list[dict],
        path: str,
        select_fields: list[str],
        root_cls: Any,
        registry,
        term_resolver,
        executor,
        datasource_registry
    ) -> list[dict]:
        """
        执行单条跨源关联。

        Args:
            main_records: 主表记录
            path: 关系路径（如 "crew"）
            select_fields: 要选择的字段
            root_cls: 根对象
            registry: 本体注册表
            term_resolver: 术语解析器
            executor: 执行器
            datasource_registry: 数据源注册表

        Returns:
            合并后的记录
        """
        path_segments = path.split(".")

        # 逐跳执行
        current_cls = root_cls
        current_records = main_records
        current_main_key = None

        for i, segment in enumerate(path_segments):
            # 查找关系
            rel = None
            if hasattr(current_cls, 'relations'):
                for r in current_cls.relations:
                    if r.relation_code == segment:
                        rel = r
                        break

            if rel is None:
                raise OQLError(
                    OQLErrorCode.OQL_ERR_UNKNOWN_RELATION,
                    f"关系 '{segment}' 不存在"
                )

            target_cls = registry.get_class(rel.target_class)
            if target_cls is None:
                raise OQLError(
                    OQLErrorCode.OQL_ERR_UNKNOWN_OBJECT,
                    f"目标对象 '{rel.target_class}' 不存在"
                )

            # 获取关联键
            join_keys = rel.join_keys if hasattr(rel, 'join_keys') else {}
            source_key = list(join_keys.keys())[0] if join_keys else "id"
            target_key = list(join_keys.values())[0] if join_keys else "id"

            # 收集关联键值
            key_values = []
            for record in current_records:
                val = record.get(source_key)
                if val is not None:
                    key_values.append(val)

            if not key_values:
                # 无关联键，返回原记录
                return current_records

            # 查询关联对象（分批）
            sub_records = self._fetch_sub_records_batched(
                key_values, target_key, {"select": select_fields},
                target_cls, registry, term_resolver, executor, datasource_registry
            )

            # 内存合并
            col_prefix = path[:path.rfind(".")] if "." in path else segment
            current_records = MemoryMerger.left_join(
                current_records, sub_records, source_key, target_key, col_prefix
            )

            current_cls = target_cls

        return current_records

    def _fetch_sub_records_batched(
        self,
        key_values: list,
        tgt_field: str,
        clause: dict,
        target_cls: Any,
        registry,
        term_resolver,
        executor,
        datasource_registry
    ) -> list[dict]:
        """
        分批查询关联对象。

        Args:
            key_values: 关联键值列表
            tgt_field: 目标字段
            clause: include_links 子句
            target_cls: 目标对象
            registry: 本体注册表
            term_resolver: 术语解析器
            executor: 执行器
            datasource_registry: 数据源注册表

        Returns:
            查询结果列表
        """
        all_sub = []
        adapter = OqlAdapter()

        for i in range(0, len(key_values), self.BATCH_SIZE):
            batch = key_values[i : i + self.BATCH_SIZE]
            sub_oql = {
                "object": target_cls.object_code,
                "fields": clause.get("select", []),
                "where": [{"field": tgt_field, "op": "in", "value": batch}],
                "limit": min(len(batch) * 10, 10000),
            }

            db_type = self._get_db_type(target_cls, datasource_registry)
            task = adapter.translate(sub_oql, target_cls, db_type, registry, term_resolver)
            result = executor.run(task)

            if isinstance(result, list):
                all_sub.extend(result)
            else:
                all_sub.append(result)

        return all_sub

    def _get_db_type(self, cls: Any, datasource_registry) -> str:
        """获取数据库类型。"""
        if cls.source_type == "API":
            return "API"

        datasource_alias = cls.datasource_alias
        if not datasource_alias:
            return "MYSQL"

        try:
            ds = datasource_registry.get(datasource_alias)
            if ds and hasattr(ds, 'db_type'):
                return ds.db_type.upper()
        except Exception:
            pass

        return "MYSQL"
