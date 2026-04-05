"""
依赖注入模块

提供全局依赖实例的获取接口，用于工具调用时获取必要的服务实例。
"""

from __future__ import annotations
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from datacloud_data_sdk.oql import OqlRouter

# 全局实例存储
_oql_router: Optional[OqlRouter] = None
_action_service = None
_term_resolver = None
_executor = None
_datasource_registry = None


def init_dependencies(
    oql_router: OqlRouter,
    action_service=None,
    term_resolver=None,
    executor=None,
    datasource_registry=None,
):
    """
    初始化全局依赖实例。

    应在应用启动时调用一次。

    Args:
        oql_router: OQL 路由器实例
        action_service: 动作服务实例
        term_resolver: 术语解析器实例
        executor: 执行器实例
        datasource_registry: 数据源注册表实例
    """
    global _oql_router, _action_service, _term_resolver, _executor, _datasource_registry
    _oql_router = oql_router
    _action_service = action_service
    _term_resolver = term_resolver
    _executor = executor
    _datasource_registry = datasource_registry


def get_oql_router() -> OqlRouter:
    """获取 OQL 路由器实例"""
    if _oql_router is None:
        raise RuntimeError("OqlRouter 未初始化，请先调用 init_dependencies()")
    return _oql_router


def get_action_service():
    """获取动作服务实例"""
    if _action_service is None:
        raise RuntimeError("ActionService 未初始化，请先调用 init_dependencies()")
    return _action_service


def get_term_resolver():
    """获取术语解析器实例"""
    return _term_resolver


def get_executor():
    """获取执行器实例"""
    return _executor


def get_datasource_registry():
    """获取数据源注册表实例"""
    return _datasource_registry
