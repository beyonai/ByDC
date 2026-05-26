"""path_mapping 裁剪的单元测试：验证 _make_pm_key 及 order_by/group_by 键被正确保留。

TC-2-11b: _make_pm_key paradigm-id 感知
TC-2-11c: order_by 关键字保留时，"o1" 键不被裁剪
TC-2-11d: groupBy 关键字保留时，"g1" 键不被裁剪
TC-2-11e: select 关键字保留时，对应键不被裁剪
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

from datacloud_analysis.orchestration.clarification.user_clarify_node import (
    _make_pm_key,
    user_clarify_node,
)

# ── 公共常量 ─────────────────────────────────────────────────────────────

_TOOL_NAME = "query_p_product_management"
_QUERY = "查询产品"

_SELECT_PARADIGM_LIST: list[dict[str, Any]] = [
    {
        "paradigmId": "1",
        "paradigmName": "查询值",
        "paradigmResult": [
            {"keyword": "评率", "recall": ["折扣率"], "kid": 1, "ktype": "select"},
        ],
    },
    {"paradigmId": "2", "paradigmName": "分组条件", "paradigmResult": []},
    {"paradigmId": "3", "paradigmName": "过滤条件", "paradigmResult": []},
    {
        "paradigmId": "4",
        "paradigmName": "排序目标",
        "paradigmResult": [
            {"keyword": "好评率", "recall": ["产品状态"], "kid": 1, "ktype": "orderBy"},
        ],
    },
    {"paradigmId": "5", "paradigmName": "统计函数", "paradigmResult": []},
]

_GROUP_PARADIGM_LIST: list[dict[str, Any]] = [
    {"paradigmId": "1", "paradigmName": "查询值", "paradigmResult": []},
    {
        "paradigmId": "2",
        "paradigmName": "分组条件",
        "paradigmResult": [
            {"keyword": "区域", "recall": ["region"], "kid": 1, "ktype": "groupBy"},
        ],
    },
    {"paradigmId": "3", "paradigmName": "过滤条件", "paradigmResult": []},
    {"paradigmId": "4", "paradigmName": "排序目标", "paradigmResult": []},
    {"paradigmId": "5", "paradigmName": "统计函数", "paradigmResult": []},
]

_SELECT_ONLY_PARADIGM_LIST: list[dict[str, Any]] = [
    {
        "paradigmId": "1",
        "paradigmName": "查询值",
        "paradigmResult": [
            {"keyword": "名称", "recall": ["name"], "kid": 1, "ktype": "select"},
        ],
    },
    {"paradigmId": "2", "paradigmName": "分组条件", "paradigmResult": []},
    {"paradigmId": "3", "paradigmName": "过滤条件", "paradigmResult": []},
    {"paradigmId": "4", "paradigmName": "排序目标", "paradigmResult": []},
    {"paradigmId": "5", "paradigmName": "统计函数", "paradigmResult": []},
]

_INTERRUPT_PATCH = "datacloud_analysis.orchestration.clarification.user_clarify_node.interrupt"
_FINALIZE_PATCH = (
    "datacloud_analysis.orchestration.clarification.user_clarify_node.finalize_query_clarification"
)


def _make_state(paradigm_list: list[dict[str, Any]]) -> dict[str, Any]:
    """构造含指定 paradigm_list 和 clarify_knowledge 的 state。"""
    path_mapping: dict[str, str] = {}
    # 模拟 build_paradigm_list 生成的 path_mapping（包含所有 paradigm 键）
    for paradigm in paradigm_list:
        pid = str(paradigm.get("paradigmId", ""))
        for item in paradigm.get("paradigmResult") or []:
            kid = item.get("kid")
            ktype = str(item.get("ktype", ""))
            if kid is None:
                continue
            if pid == "1":
                key = str(kid)
            elif pid == "2":
                key = f"g{kid}"
            elif pid == "4":
                key = f"o{kid}"
            else:
                continue
            if ktype == "select":
                path_mapping[key] = f"select.{int(kid) - 1}"
            elif ktype == "groupBy":
                path_mapping[key] = f"dimensions.{int(kid) - 1}"
            elif ktype == "orderBy":
                path_mapping[key] = f"order_by.{int(kid) - 1}.field"

    clarify_knowledge = json.dumps(
        {
            "path_mapping": path_mapping,
            "confirmed_conditions": [],
            "mode": "query",
        },
        ensure_ascii=False,
    )

    return {
        "pending_clarification_context": {
            "tool_name": _TOOL_NAME,
            "query": _QUERY,
            "structured_input": {
                "select": ["名称"],
                "order_by": [{"field": "好评率", "direction": "desc"}],
                "dimensions": ["区域"],
                "complex_conditions": [],
            },
            "is_compute": False,
        },
        "clarification_analyze_result": {
            "paradigm_list": paradigm_list,
            "clarify_knowledge": clarify_knowledge,
        },
        "messages": [],
    }


def _make_resume_value(paradigm_list_from_resume: list[dict[str, Any]]) -> dict[str, Any]:
    """构造用户提交的 resume_value。"""
    return {
        "paradigmList": [
            {
                "paradigmList": paradigm_list_from_resume,
            }
        ],
        "metadata": {},
    }


# ── _make_pm_key 单元测试 ──────────────────────────────────────────────────


def test_make_pm_key_select() -> None:
    """paradigmId="1" → 纯数字 kid。"""
    assert _make_pm_key("1", 3) == "3"


def test_make_pm_key_group_by() -> None:
    """paradigmId="2" → "g{kid}"。"""
    assert _make_pm_key("2", 1) == "g1"
    assert _make_pm_key("2", 3) == "g3"


def test_make_pm_key_order_by() -> None:
    """paradigmId="4" → "o{kid}"。"""
    assert _make_pm_key("4", 1) == "o1"
    assert _make_pm_key("4", 5) == "o5"


def test_make_pm_key_unknown_fallback() -> None:
    """未知 paradigmId 回退到纯数字 kid。"""
    assert _make_pm_key("99", 7) == "7"


# ── TC-2-11c: order_by "o1" 键不被裁剪 ──────────────────────────────────────


async def test_path_mapping_preserves_order_by_key() -> None:
    """用户保留 order_by 的关键字时，path_mapping 中 "o1" 键不应被裁剪。"""
    state = _make_state(_SELECT_PARADIGM_LIST)
    # 用户提交的表单：同时保留了 select 和 order_by 的选项
    resume_value = _make_resume_value(
        [
            {
                "paradigmId": "1",
                "paradigmName": "查询值",
                "paradigmResult": [
                    {"keyword": "评率", "choiceKeyword": "产品名称"},
                ],
            },
            {
                "paradigmId": "4",
                "paradigmName": "排序目标",
                "paradigmResult": [
                    {"keyword": "好评率", "choiceKeyword": "产品价格"},
                ],
            },
        ]
    )

    finalized = MagicMock()
    finalized.structured_input = {
        "select": ["产品名称"],
        "order_by": [{"field": "产品价格", "direction": "desc"}],
    }
    finalized.persisted_synonyms = None

    with (
        patch(_INTERRUPT_PATCH, return_value=resume_value),
        patch(_FINALIZE_PATCH, return_value=finalized) as mock_finalize,
    ):
        await user_clarify_node(state, MagicMock())

    # 验证传给 finalize 的 metadata 中包含 "o1" 键
    call_kwargs = mock_finalize.call_args.kwargs
    metadata_raw = call_kwargs["metadata"]
    metadata = json.loads(metadata_raw) if isinstance(metadata_raw, str) else metadata_raw
    pm = metadata.get("path_mapping", {})

    assert "1" in pm, f"select key '1' should be preserved, got keys={sorted(pm.keys())}"
    assert "o1" in pm, f"order_by key 'o1' should be preserved, got keys={sorted(pm.keys())}"


# ── TC-2-11d: groupBy "g1" 键不被裁剪 ───────────────────────────────────────


async def test_path_mapping_preserves_group_by_key() -> None:
    """用户保留 groupBy 的关键字时，path_mapping 中 "g1" 键不应被裁剪。"""
    state = _make_state(_GROUP_PARADIGM_LIST)
    resume_value = _make_resume_value(
        [
            {
                "paradigmId": "2",
                "paradigmName": "分组条件",
                "paradigmResult": [
                    {"keyword": "区域", "choiceKeyword": "region"},
                ],
            },
        ]
    )

    finalized = MagicMock()
    finalized.structured_input = {"dimensions": ["region"]}
    finalized.persisted_synonyms = None

    with (
        patch(_INTERRUPT_PATCH, return_value=resume_value),
        patch(_FINALIZE_PATCH, return_value=finalized) as mock_finalize,
    ):
        await user_clarify_node(state, MagicMock())

    call_kwargs = mock_finalize.call_args.kwargs
    metadata_raw = call_kwargs["metadata"]
    metadata = json.loads(metadata_raw) if isinstance(metadata_raw, str) else metadata_raw
    pm = metadata.get("path_mapping", {})

    assert "g1" in pm, f"groupBy key 'g1' should be preserved, got keys={sorted(pm.keys())}"


# ── TC-2-11e: select 裁剪正常（不该保留的被删除）─────────────────────────────


async def test_path_mapping_prunes_unreferenced_select_keys() -> None:
    """只有用户保留的 keyword 对应的 select 键被保留。"""
    # 使用有两个 select items 的 paradigm_list
    paradigm_list: list[dict[str, Any]] = [
        {
            "paradigmId": "1",
            "paradigmName": "查询值",
            "paradigmResult": [
                {"keyword": "名称", "recall": ["name"], "kid": 1, "ktype": "select"},
                {"keyword": "价格", "recall": ["price"], "kid": 2, "ktype": "select"},
            ],
        },
        {"paradigmId": "2", "paradigmName": "分组条件", "paradigmResult": []},
        {"paradigmId": "3", "paradigmName": "过滤条件", "paradigmResult": []},
        {"paradigmId": "4", "paradigmName": "排序目标", "paradigmResult": []},
        {"paradigmId": "5", "paradigmName": "统计函数", "paradigmResult": []},
    ]
    state = _make_state(paradigm_list)
    # 用户只保留了"名称"，删除了"价格"
    resume_value = _make_resume_value(
        [
            {
                "paradigmId": "1",
                "paradigmName": "查询值",
                "paradigmResult": [
                    {"keyword": "名称", "choiceKeyword": "name"},
                ],
            },
        ]
    )

    finalized = MagicMock()
    finalized.structured_input = {"select": ["name"]}
    finalized.persisted_synonyms = None

    with (
        patch(_INTERRUPT_PATCH, return_value=resume_value),
        patch(_FINALIZE_PATCH, return_value=finalized) as mock_finalize,
    ):
        await user_clarify_node(state, MagicMock())

    call_kwargs = mock_finalize.call_args.kwargs
    metadata_raw = call_kwargs["metadata"]
    metadata = json.loads(metadata_raw) if isinstance(metadata_raw, str) else metadata_raw
    pm = metadata.get("path_mapping", {})

    assert "1" in pm, f"select key '1' (名称) should be preserved, got keys={sorted(pm.keys())}"
    assert "2" not in pm, f"select key '2' (价格) should be pruned, got keys={sorted(pm.keys())}"
