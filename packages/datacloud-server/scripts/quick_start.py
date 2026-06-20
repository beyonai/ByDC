#!/usr/bin/env python3
"""快速开始：本体检索示例。

用法:
    cd ByDC/packages/datacloud-server
    uv run python scripts/quick_start.py

向量检索需要:
    - DATACLOUD_EMBEDDING_API_KEY   DashScope API key
    - DATACLOUD_DB_*                 OpenGauss 连接信息（默认 10.10.168.200:5432）
"""

from __future__ import annotations

import json
import logging
import os

from dotenv import load_dotenv

load_dotenv()

from datacloud_server.adapters.local_adapter import LocalOntologyAdapter
from datacloud_server.registry.registry import OntologyBaseEntry, OntologyBaseRegistry
from datacloud_server.services.adapter_router import AdapterRouter
from datacloud_server.services.ontology_base_service import OntologyBaseService
from datacloud_server.services.ontology_resource_service import OntologyResourceService
from datacloud_server.services.ontology_search_service import OntologySearchService
from datacloud_server.services.search_engine import (
    DirectStrategy,
    RRFStrategy,
    SearchEngine,
)
from datacloud_server.storage.json_writer import JSONWriter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-5s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("quick_start")

DATA_DIR = "/data/byai/byaiAllInOne/mino/byclaw"
BASE_ID = "resource"
HAS_EMBEDDING = bool(os.environ.get("DATACLOUD_EMBEDDING_API_KEY"))


def _banner(title: str) -> None:
    print(f"\n{'─' * 60}\n  {title}\n{'─' * 60}")


def _print_hits(result: dict | None, limit: int = 3) -> None:
    """打印向量检索命中结果，不吞异常。"""
    if result is None:
        print("    (调用失败，查看上方日志)")
        return
    metadata_hits = result.get("metadata", [])
    instance_hits = result.get("instances", [])
    if not metadata_hits and not instance_hits:
        print("    (无结果)")
        return
    for hit in metadata_hits[:limit]:
        rt = hit.get("resultType", "?")
        score = hit.get("score", 0)
        name = hit.get("objectName") or hit.get("propertyName") or hit.get("matchedValue", "?")
        code = hit.get("objectCode") or hit.get("propertyCode") or "?"
        print(f"    → [{rt}] {name}  ({code})  score={score:.4f}")


def _print_engine_hits(hits: list[dict], limit: int = 3) -> None:
    """打印 SearchEngine 命中结果。"""
    if not hits:
        print("    (无结果)")
        return
    for h in hits[:limit]:
        rt = h.get("resultType", "?")
        score = h.get("score", 0)
        name = h.get("objectName") or h.get("matchedValue", "?")
        code = h.get("objectCode") or h.get("propertyCode") or "?"
        print(f"    → [{rt}] {name}  ({code})  score={score:.4f}")


def main() -> None:
    # --- 依赖装配 ---
    registry = OntologyBaseRegistry()
    registry.register(
        OntologyBaseEntry(
            base_id=BASE_ID,
            display_name="OWL 示例本体库",
            description="从 owl_example 目录加载的本体数据",
            owner_type="personal",
            source_type="LOCAL",
            ontology_path=f"{DATA_DIR}/{BASE_ID}",
        )
    )
    adapter = LocalOntologyAdapter(DATA_DIR, JSONWriter())
    router = AdapterRouter(
        registry=registry,
        adapters={"LOCAL": adapter},  # type: ignore[arg-type]
    )
    base_svc = OntologyBaseService(router)
    resource_svc = OntologyResourceService(router)
    search_svc = OntologySearchService(router)

    # --- 摘要 ---
    print("=" * 60)
    print("  本体检索 · 快速开始")
    print(f"  数据目录: {DATA_DIR}/{BASE_ID}")
    print(
        f"  向量检索: {'✅ 可用' if HAS_EMBEDDING else '⚠️ 不可用 (设置 DATACLOUD_EMBEDDING_API_KEY 启用)'}"
    )
    print("=" * 60)

    # =================================================================
    # 1. 浏览本体库
    # =================================================================
    _banner("1. 本体库列表")
    bases = base_svc.list_bases()
    for b in bases:
        print(f"  {b['baseId']}: {b['displayName']}  ({b['sourceType']}, {b['ownerType']})")

    # =================================================================
    # 2. 对象类型浏览
    # =================================================================
    _banner("2. 对象类型列表 (scene=object)")
    objects = resource_svc.get_objects(BASE_ID, "object")
    for o in objects:
        code = o.get("objectCode", "?")
        name = o.get("objectName", "?")
        source = o.get("objectSource", "")
        props = len(o.get("properties", []))
        actions = len(o.get("actions", []))
        print(f"  {code:30s} {name:16s}  source={source:12s}  props={props}  actions={actions}")

    # =================================================================
    # 3. 对象详情
    # =================================================================
    _banner("3. 对象详情 (by_customer)")
    detail = resource_svc.get_object_detail(BASE_ID, "object", "by_customer")
    if detail is None:
        print("  (未找到对象 'by_customer')")
    else:
        print(f"  名称: {detail.get('objectName')}")
        print(f"  来源: {detail.get('objectSource')}")
        print("  属性:")
        for p in detail.get("properties", [])[:5]:
            print(
                f"    - {p.get('propertyCode', '?')}: "
                f"{p.get('propertyName', '?')}  ({p.get('dataType', '?')})"
            )
        print("  动作:")
        for a in detail.get("actions", []):
            print(
                f"    - {a.get('actionCode', '?')}: "
                f"{a.get('actionName', '?')}  [{a.get('actionType', '?')}]"
            )

    # =================================================================
    # 4. 向量检索 (需要 DashScope API key + OpenGauss pgvector)
    # =================================================================
    _banner("4. 向量检索 · search_ontology(keyword='客户')")
    try:
        search_result = search_svc.search_ontology(
            BASE_ID,
            "object",
            keyword="客户",
            search_scope="metadata",
            result_per_type=5,
        )
    except Exception:
        logger.exception("向量检索失败")
        search_result = None
    _print_hits(search_result)
    if search_result:
        print(f"\n  完整响应结构：\n{json.dumps(search_result, ensure_ascii=False, indent=2)}")

    # =================================================================
    # 5. SearchEngine 多场景检索
    # =================================================================
    _banner("5. SearchEngine · DirectStrategy(keyword='project')")
    engine = SearchEngine(
        router=router,
        scopes=[(BASE_ID, "object")],
        strategy=DirectStrategy(),
    )
    try:
        direct_hits = engine.search(keyword="project", search_scope="metadata")
    except Exception:
        logger.exception("DirectStrategy 检索失败")
        direct_hits = []
    _print_engine_hits(direct_hits)

    _banner("5b. SearchEngine · RRFStrategy(「客户订单」)")
    engine_rrf = SearchEngine(
        router=router,
        scopes=[(BASE_ID, "object")],
        strategy=RRFStrategy(),
    )
    print("   分词: jieba.cut('客户订单') → ['客户','订单']")
    print("   策略: 每词独立检索 → RRF(k=60) 融合排名")
    try:
        rrf_hits = engine_rrf.search(keyword="客户订单", search_scope="metadata")
    except Exception:
        logger.exception("RRFStrategy 检索失败")
        rrf_hits = []
    _print_engine_hits(rrf_hits)

    # =================================================================
    # 6. Agent 挂载场景模拟
    # =================================================================
    _banner("6. Agent 挂载场景模拟")
    mount_config: list[dict[str, str]] = [
        {"type": "scene", "baseId": BASE_ID, "sceneId": "object"},
    ]
    scopes = [(m["baseId"], m["sceneId"]) for m in mount_config]
    agent_engine = SearchEngine(router=router, scopes=scopes, strategy=RRFStrategy())

    for query in ["帮我查客户相关的本体", "项目任务"]:
        print(f"\n  用户: 「{query}」")
        try:
            agent_hits = agent_engine.search(keyword=query, search_scope="metadata")
        except Exception:
            logger.exception("Agent 搜索失败: %s", query)
            agent_hits = []
        _print_engine_hits(agent_hits)

    print("\n" + "=" * 60)
    print("  完成。")
    print("  pip install jieba  可启用 RRF 分词检索")
    print("  设置 DATACLOUD_EMBEDDING_API_KEY 可启用向量嵌入")
    print("=" * 60)


if __name__ == "__main__":
    main()
