"""子Agent配置模块 - 基于POC 5 v3验证结果

关键发现：
- 子Agent通过task工具被调用
- 子Agent可以配置自己的tools
- 调用链路：父Agent → task → 子Agent → 子Agent工具
"""

from typing import Any
from dataclasses import dataclass


@dataclass
class SubAgentConfig:
    """子Agent配置"""

    name: str
    description: str
    system_prompt: str
    tools: list[Any] | None = None
    model: Any | None = None  # 可选，默认继承父Agent


def get_default_subagents() -> list[dict[str, Any]]:
    """
    获取默认子Agent配置

    基于POC 5 v3验证的子Agent调用模式
    """
    return [
        {
            "name": "researcher",
            "description": "研究专家，擅长信息检索和知识查询",
            "system_prompt": """你是一个研究专家。当需要查询知识时，你必须使用 know 工具。

可用的工具：
- know: 用于检索业务知识和本体知识

重要：对于每个研究请求，请主动调用 know 工具获取信息。
""",
        },
        {
            "name": "data_analyst",
            "description": "数据分析师，擅长数据查询和分析",
            "system_prompt": """你是一个数据分析师。当需要查询数据时，你必须使用 query 工具。

可用的工具：
- query: 用于执行数据查询（NL2Data）
- compute: 用于执行数学计算

重要：对于每个数据分析请求，请主动调用相应工具获取数据。
""",
        },
        {
            "name": "visualizer",
            "description": "可视化专家，擅长生成图表和报告",
            "system_prompt": """你是一个可视化专家。当需要生成可视化输出时，你必须使用 render 工具。

可用的工具：
- render: 用于生成可视化输出

重要：对于每个可视化请求，请主动调用 render 工具。
""",
        },
    ]


def convert_to_deepagents_format(
    subagents: list[SubAgentConfig] | list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    转换为deepagents格式

    Args:
        subagents: 子Agent配置列表

    Returns:
        deepagents兼容的配置列表
    """
    result: list[dict[str, Any]] = []
    for sa in subagents:
        if isinstance(sa, SubAgentConfig):
            config: dict[str, Any] = {
                "name": sa.name,
                "description": sa.description,
                "system_prompt": sa.system_prompt,
            }
            if sa.tools is not None:
                config["tools"] = sa.tools
            if sa.model:
                config["model"] = sa.model
            result.append(config)
        else:
            result.append(sa)
    return result
