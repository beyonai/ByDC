"""领域 & 本体库 OWL 渲染 — 基于 GraphBuilder API。

根据实施计划 v2.2，domain.owl / library.owl 已取消独立文件，
领域和术语库信息由术语的 domain_code / library_code 字段承载。
此处渲染函数供 GraphBuilder 内部使用，用于在 OWL 图中注册 Domain/Library 实体。

迁移模式（供其他 renderer 参考）：
1. 将 Config/Model 数据转为 KPS frozen dataclass（DomainDef/LibraryDef/...）
2. 调用 GraphBuilder.add_*() 方法将实体注册到 rdflib.Graph
3. 最终由 generator.py 统一调用 builder.build().serialize() 产出 OWL XML
"""

from __future__ import annotations

from datacloud_knowledge.contracts.kps import DomainDef, LibraryDef
from datacloud_knowledge.ingestion.owl_generate.graph_builder import GraphBuilder
from datacloud_knowledge.ingestion.owl_generate.models import OwlGenConfig


def render_domains(config: OwlGenConfig, builder: GraphBuilder) -> None:
    """将领域定义加入 GraphBuilder 图中。

    业务逻辑：从生成配置中提取领域信息，构造 KPS DomainDef，
    通过 GraphBuilder 的 RDFLib Graph API 注册为 OWL NamedIndividual。
    领域不作为独立 .owl 文件产出，信息由各术语的 domain_code 字段承载。
    """
    domain = DomainDef(
        domain_code=config.domain_code,
        domain_name=config.domain_name,
        domain_desc=config.domain_desc,
    )
    builder.add_domain(domain)


def render_library(config: OwlGenConfig, builder: GraphBuilder) -> None:
    """将术语库定义加入 GraphBuilder 图中。

    业务逻辑：从生成配置中提取术语库信息，构造 KPS LibraryDef，
    通过 GraphBuilder 的 RDFLib Graph API 注册为 OWL NamedIndividual。
    术语库不作为独立 .owl 文件产出，信息由各术语的 library_code 字段承载。
    """
    library = LibraryDef(
        library_code=config.library_code,
        library_name=config.library_name,
        library_desc=config.library_desc,
    )
    builder.add_library(library)
