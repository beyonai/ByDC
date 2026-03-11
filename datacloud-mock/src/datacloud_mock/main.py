"""DataCloud Mock 服务总入口：创建 FastAPI 应用并挂载各子系统路由。"""

from fastapi import FastAPI

from datacloud_mock import __version__

app = FastAPI(
    title="datacloud-mock",
    description="DataCloud 2.0 数据仿真系统",
    version=__version__,
)


@app.get("/")
def root() -> dict:
    """健康与版本检查."""
    return {"service": "datacloud-mock", "version": __version__}


@app.get("/health")
def health() -> dict:
    """健康检查."""
    return {"status": "ok"}


def _mount_subsystems() -> None:
    """挂载各子系统路由（按需取消注释或新增）。"""
    try:
        from datacloud_mock.crm_demo.apis import router as crm_router

        app.include_router(crm_router, prefix="/api/v1/crm_demo", tags=["crm_demo"])
    except ImportError:
        pass  # 子系统未实现时忽略


_mount_subsystems()
