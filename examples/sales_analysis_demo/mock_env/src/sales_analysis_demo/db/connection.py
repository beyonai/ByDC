"""PostgreSQL/OpenGauss 异步连接池。"""

import os
from collections.abc import AsyncGenerator
from urllib.parse import quote_plus

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# OpenGauss 版本兼容补丁在 main.py 中于应用启动时执行


def _build_database_url() -> str:
    """优先使用分项配置构建连接串，避免密码含特殊字符时 URL 解析错误."""
    host = os.getenv("DB_HOST")
    if host is not None:
        port = os.getenv("DB_PORT", "5432")
        user = os.getenv("DB_USER", "postgres")
        password = os.getenv("DB_PASSWORD", "")
        database = os.getenv("DB_NAME", "postgres")
        # 密码单独编码，避免 @# 等特殊字符导致解析错误
        safe_password = quote_plus(password) if password else ""
        auth = f"{user}:{safe_password}" if safe_password else user
        return f"postgresql+asyncpg://{auth}@{host}:{port}/{database}"
    url = os.getenv("DATABASE_URL", "postgresql+asyncpg://localhost:5432/postgres")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


DATABASE_URL = _build_database_url()

engine = create_async_engine(
    DATABASE_URL,
    echo=os.getenv("SQL_ECHO", "false").lower() == "true",
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """获取异步数据库 session，用于 FastAPI Depends，使用后自动关闭."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
