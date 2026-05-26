"""Action OWL 文件渲染器 — 独立通道，不作为术语。

根据 OwlGenConfig 中的 Action 配置（ActionConfig），
生成 actions/{action_code}.owl 文件。

Action 定义包含：
- ActionDefinition：action 基本元信息（编码、名称、类型、URL、方法）
- RequestParameter：请求参数定义
- ResponseParameter：响应参数定义
- HeaderParameter：请求头参数定义

Phase 1 中 Action 不落库，仅做文件级引用完整性校验。
"""

from __future__ import annotations

import logging

from rdflib import Graph

from datacloud_knowledge.contracts.kps import ActionDef, ActionParamDef
from datacloud_knowledge.ingestion.owl_generate.graph_builder import GraphBuilder
from datacloud_knowledge.ingestion.owl_generate.models import (
    ActionConfig,
    ActionParamConfig,
    OwlGenConfig,
)

logger = logging.getLogger(__name__)

# ── CRUD Action 默认配置模板 ──────────────────────────────────────────────────

# 按表自动生成的标准 CRUD Action 名称模板
_CRUD_TEMPLATES = [
    ("get", "获取", "QUERY", "GET"),
    ("list", "列表", "QUERY", "GET"),
    ("create", "创建", "MUTATION", "POST"),
    ("update", "更新", "MUTATION", "PUT"),
    ("delete", "删除", "MUTATION", "DELETE"),
]


def _build_crud_actions(table_code: str, table_name: str, base_url: str) -> list[ActionConfig]:
    """为指定表自动生成标准 CRUD Action 配置。

    业务逻辑：
    - 每个业务对象表默认生成 5 个 CRUD Action：get/list/create/update/delete
    - action_code 格式：{verb}_{table_code}，如 get_by_customer
    - action_name 格式：{动词}{表名}，如 "获取客户"
    - Action 不依赖特定对象，仅为数据操作 API 的语义描述
    """
    actions: list[ActionConfig] = []
    for verb_prefix, verb_name, action_type, http_method in _CRUD_TEMPLATES:
        actions.append(
            ActionConfig(
                action_code=f"{verb_prefix}_{table_code}",
                action_name=f"{verb_name}{table_name}",
                action_type=action_type,
                request_url=f"{base_url}/{table_code}/{verb_prefix}",
                request_method=http_method,
                request_params=[
                    ActionParamConfig(
                        param_code="id" if verb_prefix == "get" else "page",
                        param_type="integer",
                        description="主键ID" if verb_prefix == "get" else "页码",
                        is_required=True,
                    )
                ],
            )
        )
    return actions


def _build_action_def(config: ActionConfig) -> ActionDef:
    """从 ActionConfig 构建 KPS ActionDef。

    将配置层的 ActionParamConfig 转换为 KPS 层的 ActionParamDef（frozen dataclass）。
    """
    return ActionDef(
        action_code=config.action_code,
        action_name=config.action_name,
        action_type=config.action_type,
        request_url=config.request_url,
        request_method=config.request_method,
        request_params=tuple(
            ActionParamDef(
                param_code=p.param_code,
                param_type=p.param_type,
                description=p.description,
                is_required=p.is_required,
            )
            for p in config.request_params
        ),
        response_params=tuple(
            ActionParamDef(
                param_code=p.param_code,
                param_type=p.param_type,
                description=p.description,
                is_required=p.is_required,
            )
            for p in config.response_params
        ),
    )


def render_actions(
    config: OwlGenConfig,
    table_code: str,
    table_name: str,
) -> list[Graph]:
    """为指定表渲染 Action OWL 文件。

    渲染流程：
    1. 从配置中读取 Action 列表（含 CRUD 自动生成 + 用户自定义）
    2. 每个 Action 构建为 ActionDef（KPS 类型）
    3. 使用 GraphBuilder 将 ActionDef 序列化为 rdflib Graph
    4. 每个 Action 一个独立的 Graph（对应一个 .owl 文件）

    返回 Graph 列表，调用方负责 serialize 到文件。

    Args:
        config: OWL 生成配置（含 actions 列表）。
        table_code: 表编码（用于自动 CRUD 生成）。
        table_name: 表中文名（用于 Action 中文命名）。

    Returns:
        list[rdflib.Graph]，每个元素对应一个 Action 的 OWL 内容。
    """
    # 收集该表的所有 Action 配置（CRUD 自动 + 用户自定义）
    action_configs: list[ActionConfig] = []

    # 自动生成默认 CRUD Action
    base_url = config.db_params.get("api_base_url", "")
    if config.actions:
        # 有自定义配置时，不自动生成 CRUD（避免冲突）
        action_configs.extend(config.actions)
    else:
        # 无自定义配置时，自动生成标准 CRUD
        action_configs.extend(_build_crud_actions(table_code, table_name, base_url))

    if not action_configs:
        return []

    graphs: list[Graph] = []
    for action_config in action_configs:
        # 构建 KPS ActionDef
        action_def = _build_action_def(action_config)

        # 使用 GraphBuilder 构建 rdflib Graph
        builder = GraphBuilder()
        builder.add_actions([action_def])
        graphs.append(builder.build())

        logger.debug("Action 已渲染: %s (%s)", action_config.action_code, action_config.action_name)

    return graphs


def write_action_files(
    config: OwlGenConfig,
    table_code: str,
    table_name: str,
) -> int:
    """渲染并写入 Action OWL 文件到 output_dir/actions/ 子目录。

    文件命名：{action_code}.owl

    返回写入的文件数量。
    """
    graphs = render_actions(config, table_code, table_name)
    if not graphs:
        return 0

    actions_dir = config.output_dir / "actions"
    actions_dir.mkdir(parents=True, exist_ok=True)

    file_count = 0
    for graph in graphs:
        # 从图中提取 action_code 用于文件命名
        action_code = _extract_action_code_from_graph(graph)
        if not action_code:
            continue

        file_path = actions_dir / f"{action_code}.owl"
        graph.serialize(str(file_path), format="xml", encoding="utf-8")
        file_count += 1
        logger.info("  → actions/%s.owl", action_code)

    return file_count


def _extract_action_code_from_graph(graph: Graph) -> str:
    """从 rdflib Graph 中提取 Action 编码（action_code 属性值）。

    用于确定写入文件的命名。
    """
    from rdflib import RDF, URIRef
    from rdflib.namespace import OWL

    ns = graph.namespace_manager.store.namespace("")
    action_class = URIRef(f"{ns}ActionDefinition") if ns else None

    for subject in graph.subjects(
        RDF.type, OWL.NamedIndividual if action_class is None else action_class
    ):
        if action_class and (subject, RDF.type, action_class) not in graph:
            continue
        # 读取 :actionCode 属性
        action_code_uri = URIRef(f"{ns}actionCode") if ns else URIRef("#actionCode")
        for _, _, value in graph.triples((subject, action_code_uri, None)):
            return str(value)
    return ""


__all__ = [
    "render_actions",
    "write_action_files",
]
