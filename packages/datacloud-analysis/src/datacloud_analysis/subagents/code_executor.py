"""CodeExecutorSubAgent — 专用代码执行子代理。

负责 Python 代码编写与执行、数据分析、图表生成。
拥有独立文件系统上下文，支持多文件 Python 项目。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

CODE_EXECUTOR_SYSTEM_PROMPT = """\
你是一个专用的 Python 代码执行代理。

## 职责
- 接收数据文件路径（CSV/JSON）或内联数据
- 编写并执行 Python 代码完成数据分析、统计计算、图表生成
- 通过文件系统工具管理中间结果
- 调用 emit_result 输出最终结果

## 工作流程
1. 使用 read_file 读取数据文件
2. 使用 write_file 创建 Python 脚本（使用 pandas/numpy/matplotlib）
3. 使用 execute 运行脚本
4. 将结果文件路径或摘要通过 task 工具返回给主代理

## 约束
- 只处理数据分析类任务，不执行系统命令或网络请求
- 所有文件操作限定在工作区内
- 每步执行后验证输出，确保结果正确
"""

CODE_EXECUTOR_SUBAGENT: dict[str, Any] = {
    "name": "code-executor",
    "description": (
        "专用代码执行代理。负责编写和执行 Python 代码进行数据分析、统计计算、图表生成。"
        "当需要复杂计算、数据转换、可视化时，委托此代理。"
        "接收：数据文件路径或 JSON 数据；返回：分析结果文件路径或摘要。"
    ),
    "system_prompt": CODE_EXECUTOR_SYSTEM_PROMPT,
    "tools": [],  # 依赖 FilesystemMiddleware 内置的 execute / read_file / write_file
    "interrupt_on": {
        "execute": {"prompt": True},  # 执行代码前弹出确认（可配置关闭）
    },
}
