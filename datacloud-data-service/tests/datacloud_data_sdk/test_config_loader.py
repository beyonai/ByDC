"""测试 config_loader 的 YAML 加载与环境变量替换。"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from datacloud_data_sdk.sql_executor.config_loader import load_datasources_from_yaml


def test_load_datasources_from_yaml_empty(tmp_path: Path) -> None:
    """空文件或无效结构返回空 dict。"""
    empty = tmp_path / "empty.yaml"
    empty.write_text("")
    assert load_datasources_from_yaml(empty) == {}

    no_ds = tmp_path / "no_ds.yaml"
    no_ds.write_text("other: value")
    assert load_datasources_from_yaml(no_ds) == {}


def test_load_datasources_from_yaml_basic(tmp_path: Path) -> None:
    """基本 YAML 加载。"""
    yaml_path = tmp_path / "datasources.yaml"
    yaml_path.write_text(
        """
datasources:
  crm_db:
    alias: crm_db
    db_type: MYSQL
    jdbc_url: jdbc:mysql://localhost:3306/crm
    user: root
    password: secret
    pool_min: 1
    pool_max: 5
"""
    )
    configs = load_datasources_from_yaml(yaml_path)
    assert len(configs) == 1
    cfg = configs["crm_db"]
    assert cfg.alias == "crm_db"
    assert cfg.db_type == "MYSQL"
    assert cfg.jdbc_url == "jdbc:mysql://localhost:3306/crm"
    assert cfg.user == "root"
    assert cfg.password == "secret"
    assert cfg.pool_min == 1
    assert cfg.pool_max == 5


def test_load_datasources_from_yaml_open_gauss_compat(tmp_path: Path) -> None:
    """open_gauss_compat 字段解析。"""
    yaml_path = tmp_path / "datasources.yaml"
    yaml_path.write_text(
        """
datasources:
  ds_crm:
    alias: ds_crm
    db_type: POSTGRESQL
    jdbc_url: jdbc:postgresql://host:5432/db
    open_gauss_compat: true
"""
    )
    configs = load_datasources_from_yaml(yaml_path)
    assert configs["ds_crm"].open_gauss_compat is True


def test_load_datasources_from_yaml_env_substitution(tmp_path: Path) -> None:
    """${VAR} 环境变量替换。"""
    os.environ["TEST_DB_PASS"] = "env_secret"
    try:
        yaml_path = tmp_path / "datasources.yaml"
        yaml_path.write_text(
            """
datasources:
  crm_db:
    alias: crm_db
    db_type: MYSQL
    jdbc_url: jdbc:mysql://localhost:3306/crm
    user: root
    password: ${TEST_DB_PASS}
    pool_min: 1
    pool_max: 5
"""
        )
        configs = load_datasources_from_yaml(yaml_path)
        assert configs["crm_db"].password == "env_secret"
    finally:
        os.environ.pop("TEST_DB_PASS", None)
