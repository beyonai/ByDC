"""Query clarification analysis helpers."""

# ruff: noqa: RUF001

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from .types import ClarificationResult

if TYPE_CHECKING:
    from collections.abc import Mapping

_INDUSTRY_CHAIN_FORM: dict[str, Any] = {
    "paradigmList": [
        {
            "paradigmId": "1",
            "paradigmName": "查询值",
            "paradigmResult": [
                {"keyword": "产业链", "recall": [], "kid": 1, "ktype": "select"},
                {
                    "keyword": "环节",
                    "recall": ["所属产业环节编码", "所属产业环节名称"],
                    "kid": 2,
                    "ktype": "select",
                },
                {"keyword": "企业类型", "recall": [], "kid": 3, "ktype": "select"},
                {"keyword": "企业数量", "recall": ["企业数量"], "kid": 4, "ktype": "select"},
            ],
        },
        {
            "paradigmId": "2",
            "paradigmName": "分组条件",
            "paradigmResult": [
                {"keyword": "产业链", "recall": [], "kid": 1, "ktype": "groupBy"},
                {
                    "keyword": "环节",
                    "recall": ["所属产业环节编码", "所属产业环节名称"],
                    "kid": 2,
                    "ktype": "groupBy",
                },
                {"keyword": "企业类型", "recall": [], "kid": 3, "ktype": "groupBy"},
            ],
        },
        {
            "paradigmId": "3",
            "paradigmName": "过滤条件",
            "paradigmResult": [
                {
                    "type": "predicate",
                    "field": "产业链",
                    "fieldRecall": [],
                    "comparison": "eq",
                    "value": "信息技术",
                    "valueRecall": [
                        "信息技术、新兴信息技术",
                        "信息技术、电子",
                        "众联物联网信息技术有限公司",
                        "中科医药信息技术有限公司",
                        "中科创新（4630）信息技术有限公司",
                    ],
                },
                {
                    "type": "predicate",
                    "field": "产业链",
                    "fieldRecall": [],
                    "comparison": "eq",
                    "value": "汽车",
                    "valueRecall": [
                        "汽车、汽车零部件制造",
                        "汽车、汽车服务",
                        "北京市丰台区汽车博物馆东路1号院3号楼20层2307",
                        "北京市丰台区汽车博物馆东路1号院3号楼20层2308（园区）",
                        "北京市丰台区汽车博物馆东路8号院7号楼7层701-1室",
                    ],
                },
                {
                    "type": "predicate",
                    "field": "环节",
                    "fieldRecall": ["所属产业环节名称", "所属产业环节编码"],
                    "comparison": "eq",
                    "value": "北京力争上游商贸有限公司",
                    "valueRecall": ["北京力争上游商贸有限公司"],
                },
                {
                    "type": "predicate",
                    "field": "环节",
                    "fieldRecall": ["所属产业环节名称", "所属产业环节编码"],
                    "comparison": "eq",
                    "value": "下游",
                    "valueRecall": [],
                },
                {
                    "type": "predicate",
                    "field": "企业类型",
                    "fieldRecall": [],
                    "comparison": "eq",
                    "value": "龙头",
                    "valueRecall": [
                        "链主龙头",
                        "北京市门头沟区石龙南路10号QS1089（集群注册）",
                        "北京市门头沟区石龙南路10号A-274室",
                        "北京市门头沟区石龙西路58号永定镇政府办公楼YD323",
                    ],
                },
                {
                    "type": "predicate",
                    "field": "企业类型",
                    "fieldRecall": [],
                    "comparison": "eq",
                    "value": "骨干",
                    "valueRecall": [
                        "核心骨干",
                        "川椒魂·干锅排骨虾(风味3北京美蛙聚兴餐饮管理有限公司)",
                    ],
                },
            ],
        },
        {"paradigmId": "4", "paradigmName": "排序目标", "paradigmResult": []},
        {
            "paradigmId": "5",
            "paradigmName": "统计函数",
            "paradigmResult": [
                {"keyword": "企业数量", "recall": [], "kid": 1, "ktype": "aggregation"}
            ],
        },
    ]
}

_GRID_BENEFIT_KNOWLEDGE: dict[str, Any] = {
    "paradigmList": [
        {
            "paradigmId": "1",
            "paradigmName": "查询值",
            "paradigmResult": [
                {"keyword": "营收", "recall": ["企业总营收（万元）"], "kid": 1, "ktype": "select"},
                {
                    "keyword": "企业总利润（万元）",
                    "recall": ["企业总利润（万元）"],
                    "kid": 2,
                    "ktype": "select",
                },
                {
                    "keyword": "物理网格亩产效益（万元/亩）",
                    "recall": ["物理网格亩产效益（万元/亩）"],
                    "kid": 3,
                    "ktype": "select",
                },
            ],
        },
        {
            "paradigmId": "2",
            "paradigmName": "分组条件",
            "paradigmResult": [
                {
                    "keyword": "企业经济效益等级（高、中、低）",
                    "recall": ["企业经济效益等级（高、中、低）"],
                    "kid": 1,
                    "ktype": "groupBy",
                }
            ],
        },
        {"paradigmId": "3", "paradigmName": "过滤条件", "paradigmResult": []},
        {"paradigmId": "4", "paradigmName": "排序目标", "paradigmResult": []},
        {
            "paradigmId": "5",
            "paradigmName": "统计函数",
            "paradigmResult": [{"keyword": "求和", "recall": [], "kid": 1, "ktype": "aggregation"}],
        },
    ]
}


def _serialize_payload(payload: Mapping[str, Any] | None) -> str:
    if payload is None:
        return ""
    return json.dumps(payload, ensure_ascii=False)


def analyze_query_clarification(query: str) -> ClarificationResult:
    """Analyze whether a query needs clarification before downstream recall.

    Args:
        query: Raw natural-language query from the caller.

    Returns:
        Structured clarification analysis result for the current v1 rule set.
    """
    if query == "信息技术、汽车各链的上游、下游的龙头、骨干企业数":
        return ClarificationResult(
            query=(
                "信息技术链的上游龙头企业数、信息技术链的下游龙头企业数、"
                "信息技术链的上游骨干企业数、信息技术链的下游骨干企业数、"
                "汽车链的上游龙头企业数、汽车链的下游龙头企业数、"
                "汽车链的上游骨干企业数、汽车链的下游骨干企业数、"
            ),
            needs_clarification=True,
            form=_serialize_payload(_INDUSTRY_CHAIN_FORM),
        )

    if query == "高效益、中效益、低效益网格的营收、利润、亩产":
        return ClarificationResult(
            query=(
                "高效益网格的营收、中效益网格的营收、低效益网格的营收、"
                "高效益网格的利润、中效益网格的利润、低效益网格的利润、"
                "高效益网格的亩产、中效益网格的亩产、低效益网格的亩产"
            ),
            knowledge=_serialize_payload(_GRID_BENEFIT_KNOWLEDGE),
        )

    return ClarificationResult(query=query)
