"""从 YAML 加载数据源配置，支持 ${ENV_VAR} 环境变量替换。"""

from __future__ import annotations

import os
import re
from pathlib import Path

from datacloud_data_sdk.sql_executor.models import DataSourceConfig


def _substitute_env(value: str) -> str:
    """将 ${VAR} 或 ${VAR:-default} 替换为环境变量值。"""
    if not isinstance(value, str):
        return value

    def repl(match: re.Match[str]) -> str:
        inner = match.group(1).strip()
        if ":-" in inner:
            var, default = inner.split(":-", 1)
            return os.environ.get(var.strip(), default.strip())
        return os.environ.get(inner, "")

    return re.sub(r"\$\{([^}]+)\}", repl, value)


def _substitute_dict(obj: dict) -> dict:
    """递归对 dict 中所有字符串值做环境变量替换。"""
    result: dict = {}
    for k, v in obj.items():
        if isinstance(v, str):
            result[k] = _substitute_env(v)
        elif isinstance(v, dict):
            result[k] = _substitute_dict(v)
        else:
            result[k] = v
    return result


def _dict_to_config(alias: str, d: dict) -> DataSourceConfig:
    """将 dict 转为 DataSourceConfig。"""
    return DataSourceConfig(
        alias=d.get("alias", alias),
        db_type=str(d.get("db_type", "SQLITE")),
        jdbc_url=str(d.get("jdbc_url", "")),
        user=str(d.get("user", "")),
        password=str(d.get("password", "")),
        pool_min=int(d.get("pool_min", 1)),
        pool_max=int(d.get("pool_max", 5)),
        pool_timeout=float(d.get("pool_timeout", 30.0)),
        open_gauss_compat=bool(d.get("open_gauss_compat", False)),
        connector_type=str(d.get("connector_type") or ""),
        service_name=str(d.get("service_name") or ""),
        datasource_id=d.get("datasource_id") if d.get("datasource_id") is not None else None,
        endpoint_url=str(d.get("endpoint_url") or ""),
    )


def load_datasources_from_yaml(path: str | Path) -> dict[str, DataSourceConfig]:
    """从 YAML 文件加载数据源配置，对 password、jdbc_url、user 等字段做 ${VAR} 替换。

    YAML 格式示例:
        datasources:
          crm_db:
            alias: crm_db
            db_type: MYSQL
            jdbc_url: jdbc:mysql://host:3306/db
            user: root
            password: ${DATACLOUD_DB_PASSWORD}
            pool_min: 1
            pool_max: 5
    """
    import yaml

    content = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not content or "datasources" not in content:
        return {}

    raw = _substitute_dict(content["datasources"])
    configs: dict[str, DataSourceConfig] = {}
    for alias, cfg in raw.items():
        if not isinstance(cfg, dict):
            continue
        configs[alias] = _dict_to_config(alias, cfg)
    return configs
