"""
SQL 执行器相关模型

本模块定义了 SQL 执行器使用的数据模型，包括数据源配置和执行结果。

核心模型：
- DataSourceConfig: 数据源连接配置
- SqlExecResult: SQL 执行结果
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DataSourceConfig:
    """
    数据源配置

    定义数据库连接的所有参数，支持多种数据库类型。

    Attributes:
        alias: 数据源别名，用于在查询中引用
        db_type: 数据库类型，支持 SQLITE/MYSQL/POSTGRESQL/OPENGAUSS/CLICKHOUSE/HTTP_SQL
        jdbc_url: JDBC 连接 URL（可选，用于解析连接参数）
        user: 数据库用户名
        password: 数据库密码
        pool_min: 连接池最小连接数
        pool_max: 连接池最大连接数
        pool_timeout: 连接池超时时间（秒）
        open_gauss_compat: 是否启用 openGauss 兼容模式
        datasource_id: 数据源ID（不为空时使用 HTTP SQL 服务执行）
        endpoint_url: HTTP_SQL 后端服务地址（仅 HTTP_SQL 使用）。
            由 ``DataSourceManager`` 在选择 HTTP connector 时根据
            ``OntologyAgentConfig.sql_execute_url`` 注入；其他 connector 忽略。

    Example:
        config = DataSourceConfig(
            alias="main_db",
            db_type="MYSQL",
            jdbc_url="jdbc:mysql://localhost:3306/mydb",
            user="root",
            password="secret"
        )
    """

    alias: str
    db_type: str
    jdbc_url: str = ""
    user: str = ""
    password: str = ""
    pool_min: int = 1
    pool_max: int = 5
    pool_timeout: float = 30.0
    open_gauss_compat: bool = False
    datasource_id: int | None = None
    endpoint_url: str = ""


@dataclass
class SqlExecResult:
    """
    SQL 执行结果

    存储 SQL 查询执行的结果信息。

    Attributes:
        csv_path: 结果 CSV 文件路径
        row_count: 返回的记录行数
    """

    csv_path: str
    row_count: int = 0
