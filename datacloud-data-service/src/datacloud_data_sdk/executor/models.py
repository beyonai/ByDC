"""执行层任务模型。"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ApiExecTask:
    object_code: str
    action_code: str
    params: dict[str, Any] = field(default_factory=dict)
    output_ref: str = ""
    bind_from_step: str = ""
    bind_key: str = ""


@dataclass
class SqlExecTask:
    datasource_alias: str
    sql_template: str
    output_ref: str = ""
    bind_from_step: str = ""
    bind_key: str = ""


@dataclass
class ScriptExecTask:
    action_code: str
    script: str
    params: dict[str, Any] = field(default_factory=dict)
    output_ref: str = ""


@dataclass
class KbExecTask:
    datasource_alias: str
    query: str
    tags: dict[str, Any] = field(default_factory=dict)
    output_ref: str = ""
