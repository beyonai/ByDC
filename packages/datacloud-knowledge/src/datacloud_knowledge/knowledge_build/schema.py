"""知识构建模块公共请求/响应模型。"""

from __future__ import annotations

from pydantic import BaseModel


class TermCreateResponse(BaseModel):
    """术语创建响应。"""

    term_id: str
    term_name: str
    term_type_code: str


class TermUpdateResponse(BaseModel):
    """术语更新响应。"""

    term_id: str
    term_name: str
    updated_time: str


class ImportResult(BaseModel):
    """文件导入结果响应。"""

    total: int
    success: int
    failed: int
    errors: list[str] = []


# ── 知识包导入 ────────────────────────────────────────────────────────────────

class CallbackConfig(BaseModel):
    """回调通知配置：导入完成（成功或失败）后通知源系统。"""

    url: str
    method: str = "POST"                    # GET | POST
    headers: dict[str, str] = {}            # 自定义请求头，如 Authorization


class ImportPackageRequest(BaseModel):
    """纯预检请求：只校验，不入库，不回调。"""

    folder_path: str


class ImportPackageRunRequest(BaseModel):
    """知识包执行请求：预检 → 入库 → 回调通知（不论成功/失败）。"""

    folder_path: str
    callback: CallbackConfig | None = None  # 不传则仅同步返回结果


class PrecheckError(BaseModel):
    """单条预检错误。"""

    file: str
    line: int | None = None
    error: str


class FileCheckResult(BaseModel):
    """单个文件的预检摘要。"""

    file: str
    rows: int
    errors: list[PrecheckError] = []


class PrecheckResult(BaseModel):
    """预检结果。

    status='ok' 时 errors 为空；status='failed' 时包含所有错误详情。
    """

    status: str           # "ok" | "failed"
    total_rows: int = 0
    files: list[FileCheckResult] = []
    errors: list[PrecheckError] = []


class EntityStats(BaseModel):
    """单类实体的入库统计。"""

    inserted: int = 0
    updated: int = 0
    deleted: int = 0


class RunResult(BaseModel):
    """执行结果（预检 + 入库全流程）。

    status 取值：
      precheck_failed — 预检未通过，未入库
      success         — 预检通过且入库成功
      import_failed   — 预检通过但入库失败（已回滚）
    callback_notified — 是否成功触发了回调通知
    """

    status: str
    folder_path: str
    precheck_errors: list[PrecheckError] = []
    stats: dict[str, EntityStats] = {}
    error: str | None = None
    callback_notified: bool = False
