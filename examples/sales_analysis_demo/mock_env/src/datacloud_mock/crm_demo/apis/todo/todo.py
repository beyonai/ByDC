"""
待办系统API实现
作者: AI Assistant
日期: 2024-12-05
功能: 提供待办事项的创建、查询、修改、处理、审批、催更等功能
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Any, Dict
from datetime import datetime
import threading
import time
from enum import Enum
from http.cookies import SimpleCookie
import uuid
import json
import redis
import psycopg2
import traceback
from fastapi import Request
from psycopg2.extras import RealDictCursor

from app.api.endpoints.datacloud_new.staff_api_proxy.utils import get_client, logger
from app.core.config import settings
import requests

user_code_dict = {}


# ============================================================================
# 枚举类型定义
# ============================================================================

class TodoPriority(str, Enum):
    """优先级枚举"""
    LOW = "Low"
    NORMAL = "Normal"
    HIGH = "High"
    URGENT = "Urgent"


class UrgencyLevel(str, Enum):
    """紧急程度枚举"""
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class TodoStatus(str, Enum):
    """待办状态枚举"""
    PENDING_RECEIVE = "PendingReceive"  # 待接收
    RETURNED = "Returned"                # 退回
    RECEIVED = "Received"                # 已接收
    PENDING_REVIEW = "PendingReview"     # 待审核
    NOT_PASSED = "NotPassed"             # 不通过
    CLOSED = "Closed"                    # 关闭

TODO_STATUS_LIST = {
    TodoStatus.PENDING_RECEIVE.value: "待接收",
    TodoStatus.RETURNED.value: "退回",
    TodoStatus.RECEIVED.value: "已接收",
    TodoStatus.PENDING_REVIEW.value: "待审核",
    TodoStatus.NOT_PASSED.value: "不通过",
    TodoStatus.CLOSED.value: "关闭",
}
URGENCY_LEVEL_LIST = {UrgencyLevel.LOW.value: "低", UrgencyLevel.MEDIUM.value: "中", UrgencyLevel.HIGH.value: "高", UrgencyLevel.CRITICAL.value: "紧急"}
TODO_PRIORITY_LIST = {TodoPriority.LOW.value: "低", TodoPriority.NORMAL.value: "中", TodoPriority.HIGH.value: "高", TodoPriority.URGENT.value: "紧急"}
# ============================================================================
# 数据模型定义
# ============================================================================

class AttachmentItem(BaseModel):
    """附件对象"""
    fileName: str = Field(..., description="文件名")
    storagePath: str = Field(..., description="文件存储路径或URL")


class CreateTodoRequestBody(BaseModel):
    """创建待办请求体"""
    title: str = Field(..., description="待办标题", max_length=512)
    fileIdList: Optional[list[str]] = Field(None, description="关联的会议纪要文件")
    content: str = Field(..., description="待办内容")
    deadlineAt: str = Field(..., description="截止时间，格式：YYYY-MM-DD HH:mm:ss")
    priority: Optional[TodoPriority] = Field(TodoPriority.NORMAL, description="优先级")
    urgencyLevel: Optional[UrgencyLevel] = Field(None, description="紧急程度")
    promoter: str = Field(..., description="发起人ID")
    handlerIds: List[str] = Field(..., description="处理人列表")
    attachments: Optional[List[AttachmentItem]] = Field(None, description="附件列表")
    remark: Optional[str] = Field(None, description='备注')
    meetingNoteId: Optional[str] = Field(None, description='关联的会议纪要ID')


class UpdateTodoRequestBody(BaseModel):
    """修改待办请求体（仅发起人可修改）"""
    todoId: str = Field(..., description="待办ID")
    content: Optional[str] = Field(None, description="待办内容")
    handlerIds: Optional[List[str]] = Field(None, description="处理人列表")
    priority: Optional[TodoPriority] = Field(None, description="优先级")
    urgencyLevel: Optional[UrgencyLevel] = Field(None, description="紧急程度")
    planFinishTime: Optional[str] = Field(None, description="计划完成时间，格式：YYYY-MM-DD HH:mm:ss")


class TodoListQueryBody(BaseModel):
    """待办列表查询请求体"""
    queryType: Optional[str] = Field(None, description="查询类型：my_todos(待我处理的) 或 my_created(我发起的) 或 all(全部)")
    status: Optional[TodoStatus] = Field(None, description="状态筛选（单个状态）")
    statusList: Optional[List[TodoStatus]] = Field(None, description="状态列表筛选（多个状态，优先级高于status）")
    priority: Optional[TodoPriority] = Field(None, description="优先级筛选")
    keyword: Optional[str] = Field(None, description="关键词搜索（标题、描述）")
    urgencyLevel: Optional[UrgencyLevel] = Field(None, description="紧急程度")
    deadlineStart: Optional[str] = Field(None, description="截止时间开始，格式：YYYY-MM-DD HH:mm:ss")
    deadlineEnd: Optional[str] = Field(None, description="截止时间结束，格式：YYYY-MM-DD HH:mm:ss")
    handledStart: Optional[str] = Field(None, description="处理完成时间开始，格式：YYYY-MM-DD HH:mm:ss")
    handledEnd: Optional[str] = Field(None, description="处理完成时间结束，格式：YYYY-MM-DD HH:mm:ss")
    rejectedStart: Optional[str] = Field(None, description="审批拒绝时间开始，格式：YYYY-MM-DD HH:mm:ss")
    rejectedEnd: Optional[str] = Field(None, description="审批拒绝时间结束，格式：YYYY-MM-DD HH:mm:ss")
    completedStart: Optional[str] = Field(None, description="完成时间开始，格式：YYYY-MM-DD HH:mm:ss")
    completedEnd: Optional[str] = Field(None, description="完成时间结束，格式：YYYY-MM-DD HH:mm:ss")
    promoter: Optional[str] = Field(None, description="发起人id")
    orgId: Optional[int] = Field(None, description="组织ID（同时查询发起人组织和处理人组织）")
    includeSubOrgs: bool = Field(False, description="是否包含下级组织，默认false只查询指定组织（适用于orgId、promoterOrgId、handlerOrgId）")
    promoterOrgId: Optional[int] = Field(None, description="发起人组织ID")
    handlerOrgId: Optional[int] = Field(None, description="处理人组织ID")
    handlerIds: Optional[list[str]] = Field(None, description="处理人id列表")
    meetingNoteIds: Optional[list[str]] = Field(None, description="会议纪要ID列表")
    page: Optional[int] = Field(1, description="页码，从1开始", ge=1)
    pageSize: Optional[int] = Field(20, description="每页数量", ge=1, le=100)
    sortBy: Optional[str] = Field("created_at", description="排序字段：created_at, deadline_at, updated_at")
    sortOrder: Optional[str] = Field("desc", description="排序方向：asc, desc")


class HandleTodoRequestBody(BaseModel):
    """处理待办请求体"""
    todoIds: List[str] = Field(..., description="待办ID")
    progress: int = Field(..., ge=0, le=100, description="进度0-100%，达到100%时状态改为待审核，否则保持已接收")
    handleComment: Optional[str] = Field(None, description="处理意见/备注")
    attachments: Optional[List[AttachmentItem]] = Field(None, description="附件列表")

class ApproveTodoRequestBody(BaseModel):
    """审核待办请求体"""
    todoIds: List[str]= Field(..., description="待办ID")
    approvalStatus: str = Field(..., description="审核结果：Approving(通过) 或 Rejected(拒绝)")
    approvalComment: Optional[str] = Field(None, description="审批意见")
    attachments: Optional[List[AttachmentItem]] = Field(None, description="附件列表")


class FollowUpTodoRequestBody(BaseModel):
    """催更待办请求体"""
    todoIds: List[str] = Field(..., description="待办ID")
    followUpContent: str = Field(..., description="催更内容", max_length=1000)


class ReturnTodoRequestBody(BaseModel):
    """退回待办请求体"""
    todoId: str = Field(..., description="待办ID")
    returnReason: str = Field(..., description="退回理由", min_length=1, max_length=2000)


class ReceiveTodoRequestBody(BaseModel):
    """接收待办请求体"""
    todoId: str = Field(..., description="待办ID")


class DeleteTodoRequestBody(BaseModel):
    """删除待办请求体"""
    todoIds: List[str] = Field(..., description="待办ID列表")


class TodoDetailBody(BaseModel):
    """待办详情请求体"""
    todo_id: str = Field(..., description="待办ID")


# ============================================================================
# 响应模型定义
# ============================================================================

class BaseTodoResponse(BaseModel):
    """通用待办响应"""
    success: bool = Field(..., description="请求是否成功")
    code: int = Field(..., description="业务码，200 表示成功")
    message: str = Field(..., description="提示信息，失败时包含错误原因")
    data: Optional[dict] = Field(None, description="返回数据体，不同接口结构不同")


class CreateTodoResponseData(BaseModel):
    """创建待办的返回数据"""
    todoId: str = Field(..., description="待办唯一标识")
    title: str = Field(..., description="待办标题")
    status: str = Field(..., description="待办状态")
    createdAt: str = Field(..., description="创建时间，格式：YYYY-MM-DD HH:mm:ss")


class CreateTodoResponse(BaseTodoResponse):
    data: Optional[CreateTodoResponseData] = None


class TodoListItem(BaseModel):
    """待办列表项"""
    todoId: Optional[str] = Field(None, description="待办唯一标识")
    title: Optional[str] = Field(None, description="待办标题")
    content: Optional[str] = Field(None, description="待办内容/描述")
    status: Optional[str] = Field(None, description="当前状态")
    priority: Optional[str] = Field(None, description="优先级")
    deadlineAt: Optional[str] = Field(None, description="截止时间")
    createdAt: Optional[str] = Field(None, description="创建时间")
    updatedAt: Optional[str] = Field(None, description="最近更新时间")
    promoter: Optional[str] = Field(None, description="发起人ID")
    handlering: Optional[str] = Field(None, description="正在处理者")
    handlers: Optional[List[str]] = Field(None, description="处理人ID列表")
    attachments: Optional[List[AttachmentItem]] = Field(None, description="附件列表")
    urgencyLevel: Optional[str] = Field(None, description="紧急程度")
    completedAt: Optional[str] = Field(None, description="完成时间")
    cancelledAt: Optional[str] = Field(None, description="取消时间")
    cancelledReason: Optional[str] = Field(None, description="取消原因")
    approvedAt: Optional[str] = Field(None, description="审批通过时间")
    rejectedAt: Optional[str] = Field(None, description="审批拒绝时间")
    approvalComment: Optional[str] = Field(None, description="审批意见")
    remark: Optional[str] = Field(None, description='备注')
    handleContent: Optional[str] = Field(None, description="处理内容")
    progress: Optional[int] = Field(None, description="进度0-100%")
    returnReason: Optional[str] = Field(None, description="退回原因，仅状态为退同时有值")
    meetingNoteId: Optional[str] = Field(None, description="关联的会议纪要ID")
    meetingNoteTitle: Optional[str] = Field(None, description="关联的会议纪要标题")


class PaginationInfo(BaseModel):
    """分页信息"""
    page: int = Field(..., description="当前页码，从 1 开始")
    pageSize: int = Field(..., description="每页数量")
    total: int = Field(..., description="总记录数")
    totalPages: int = Field(..., description="总页数")


class TodoListResponseData(BaseModel):
    """待办列表返回数据"""
    items: List[TodoListItem]
    pagination: PaginationInfo


class TodoListResponse(BaseTodoResponse):
    data: Optional[TodoListResponseData] = None


class TodoDetailResponseData(BaseModel):
    """待办详情返回数据"""
    todoId: Optional[str] = Field(None, description="待办唯一标识")
    title: Optional[str] = Field(None, description="待办标题")
    content: Optional[str] = Field(None, description="待办内容/描述")
    status: Optional[str] = Field(None, description="当前状态")
    priority: Optional[str] = Field(None, description="优先级")
    deadlineAt: Optional[str] = Field(None, description="截止时间")
    createdAt: Optional[str] = Field(None, description="创建时间")
    updatedAt: Optional[str] = Field(None, description="最近更新时间")
    promoter: Optional[str] = Field(None, description="发起人ID")
    handler: Optional[str] = Field(None, description="正在处理者")
    handlers: Optional[List[str]] = Field(None, description="处理人ID列表")
    attachments: Optional[List[AttachmentItem]] = Field(None, description="附件列表")
    urgencyLevel: Optional[str] = Field(None, description="紧急程度")
    completedAt: Optional[str] = Field(None, description="完成时间")
    cancelledAt: Optional[str] = Field(None, description="取消时间")
    cancelledReason: Optional[str] = Field(None, description="取消原因")
    approvedAt: Optional[str] = Field(None, description="审批通过时间")
    rejectedAt: Optional[str] = Field(None, description="审批拒绝时间")
    approvalComment: Optional[str] = Field(None, description="审批意见")


class TodoDetailResponse(BaseTodoResponse):
    data: Optional[TodoDetailResponseData] = None


class UpdateTodoResponseData(BaseModel):
    """修改待办返回数据"""
    todoId: Optional[str] = Field(None, description="被修改的待办ID")


class UpdateTodoResponse(BaseTodoResponse):
    data: Optional[UpdateTodoResponseData] = None


class HandleTodoResponseData(BaseModel):
    """处理待办返回数据"""
    todoId: Optional[str] = Field(None, description="被处理的待办ID")


class HandleTodoResponse(BaseTodoResponse):
    data: Optional[HandleTodoResponseData] = None


class ApproveTodoResponseData(BaseModel):
    """审批待办返回数据"""
    todoId: Optional[str] = Field(None, description="被审批的待办ID")
    approvalStatus: Optional[str] = Field(None, description="审批结果：Approving 或 Rejected")


class ApproveTodoResponse(BaseTodoResponse):
    data: Optional[ApproveTodoResponseData] = None


class FollowUpTodoResponseData(BaseModel):
    """催更待办返回数据"""
    todoId: Optional[str] = Field(None, description="被催更的待办ID")
    followUpAt: Optional[str] = Field(None, description="催更时间，格式：YYYY-MM-DD HH:mm:ss")


class FollowUpTodoResponse(BaseTodoResponse):
    data: Optional[FollowUpTodoResponseData] = None


class DeleteTodoResponseData(BaseModel):
    """删除待办返回数据"""
    deletedIds: List[str] = Field(..., description="成功删除的待办ID列表")
    skipped: List[Dict[str, Any]] = Field(default_factory=list, description="跳过的待办及原因")


class DeleteTodoResponse(BaseTodoResponse):
    data: Optional[DeleteTodoResponseData] = None


class ReturnTodoResponseData(BaseModel):
    """退回待办返回数据"""
    todoId: Optional[str] = Field(None, description="待办ID")
    status: Optional[str] = Field(None, description="当前状态")


class ReturnTodoResponse(BaseTodoResponse):
    data: Optional[ReturnTodoResponseData] = None


class ReceiveTodoResponseData(BaseModel):
    """接收待办返回数据"""
    todoId: Optional[str] = Field(None, description="待办ID")
    status: Optional[str] = Field(None, description="当前状态")


class ReceiveTodoResponse(BaseTodoResponse):
    data: Optional[ReceiveTodoResponseData] = None


# ============================================================================
# 四个专用查询接口的请求模型
# ============================================================================

class QueryTodoByMeetingNoteRequest(BaseModel):
    """按会议纪要查询待办请求"""
    meetingNoteId: str = Field(..., description="会议纪要ID")
    status: Optional[TodoStatus] = Field(None, description="状态筛选")
    priority: Optional[TodoPriority] = Field(None, description="优先级筛选")
    urgencyLevel: Optional[UrgencyLevel] = Field(None, description="紧急程度筛选")
    keyword: Optional[str] = Field(None, description="关键词搜索（标题、描述）")
    page: int = Field(1, description="页码，从1开始", ge=1)
    pageSize: int = Field(20, description="每页数量", ge=1, le=100)
    sortBy: Optional[str] = Field("created_at", description="排序字段：created_at, deadline_at, updated_at")
    sortOrder: Optional[str] = Field("desc", description="排序方向：asc, desc")


class QueryTodoByHandlerRequest(BaseModel):
    """按处理人查询待办请求"""
    handlerId: Optional[str] = Field(None, description="处理人工号，不提供则查询当前用户")
    priority: Optional[TodoPriority] = Field(None, description="优先级筛选")
    urgencyLevel: Optional[UrgencyLevel] = Field(None, description="紧急程度筛选")
    keyword: Optional[str] = Field(None, description="关键词搜索（标题、描述）")
    deadlineStart: Optional[str] = Field(None, description="截止时间开始，格式：YYYY-MM-DD HH:mm:ss")
    deadlineEnd: Optional[str] = Field(None, description="截止时间结束，格式：YYYY-MM-DD HH:mm:ss")
    page: int = Field(1, description="页码，从1开始", ge=1)
    pageSize: int = Field(20, description="每页数量", ge=1, le=100)
    sortBy: Optional[str] = Field("deadline_at", description="排序字段：created_at, deadline_at, updated_at")
    sortOrder: Optional[str] = Field("asc", description="排序方向：asc, desc")


class QueryTodoByPromoterRequest(BaseModel):
    """按发起人查询待办请求"""
    promoterId: Optional[str] = Field(None, description="发起人工号，不提供则查询当前用户")
    status: Optional[TodoStatus] = Field(None, description="状态筛选")
    priority: Optional[TodoPriority] = Field(None, description="优先级筛选")
    urgencyLevel: Optional[UrgencyLevel] = Field(None, description="紧急程度筛选")
    keyword: Optional[str] = Field(None, description="关键词搜索（标题、描述）")
    handlerIds: Optional[List[str]] = Field(None, description="处理人ID列表筛选")
    deadlineStart: Optional[str] = Field(None, description="截止时间开始，格式：YYYY-MM-DD HH:mm:ss")
    deadlineEnd: Optional[str] = Field(None, description="截止时间结束，格式：YYYY-MM-DD HH:mm:ss")
    page: int = Field(1, description="页码，从1开始", ge=1)
    pageSize: int = Field(20, description="每页数量", ge=1, le=100)
    sortBy: Optional[str] = Field("created_at", description="排序字段：created_at, deadline_at, updated_at")
    sortOrder: Optional[str] = Field("desc", description="排序方向：asc, desc")


class QueryTodoByApproverRequest(BaseModel):
    """按审批人查询待办请求"""
    priority: Optional[TodoPriority] = Field(None, description="优先级筛选")
    urgencyLevel: Optional[UrgencyLevel] = Field(None, description="紧急程度筛选")
    keyword: Optional[str] = Field(None, description="关键词搜索（标题、描述）")
    deadlineStart: Optional[str] = Field(None, description="截止时间开始，格式：YYYY-MM-DD HH:mm:ss")
    deadlineEnd: Optional[str] = Field(None, description="截止时间结束，格式：YYYY-MM-DD HH:mm:ss")
    page: int = Field(1, description="页码，从1开始", ge=1)
    pageSize: int = Field(20, description="每页数量", ge=1, le=100)
    sortBy: Optional[str] = Field("updated_at", description="排序字段：created_at, deadline_at, updated_at")
    sortOrder: Optional[str] = Field("desc", description="排序方向：asc, desc")


# ============================================================================
# 数据库与工具函数（PostgreSQL）
# ============================================================================


def _format_datetime(dt: Optional[datetime]) -> Optional[str]:
    """将 datetime 对象格式化为字符串 yyyy-MM-dd HH:mm:ss"""
    if dt is None:
        return None
    # 如果有时区信息，转换为本地时间（或保持UTC，根据需求）
    if dt.tzinfo is not None:
        # 转换为UTC时间（去掉时区信息）
        dt = dt.replace(tzinfo=None)
    return dt.strftime('%Y-%m-%d %H:%M:%S')


def _get_conn():
    """
    获取PG连接，使用 settings.database_url 或详细配置。
    该方法为同步实现，如项目已有统一封装，可直接替换调用。
    """
    db_schema = None

    # 优先使用 database_url，如果没有则使用详细配置构建连接
    if settings.database_url:
        # 处理 database_url 中可能包含的 schema 参数
        database_url = settings.database_url
        if 'schema=' in database_url:
            # 提取 schema 参数
            import urllib.parse
            parsed = urllib.parse.urlparse(database_url)
            query_params = urllib.parse.parse_qs(parsed.query)
            db_schema = query_params.get('schema', [None])[0]
            # 移除 schema 参数重新构建 URL
            if db_schema:
                query_params.pop('schema', None)
                new_query = urllib.parse.urlencode(query_params, doseq=True)
                database_url = database_url.replace(parsed.query, new_query).rstrip('?')

        conn = psycopg2.connect(database_url, cursor_factory=RealDictCursor)
    else:
        # 使用详细配置构建连接
        conn = psycopg2.connect(
            host=getattr(settings, "db_host", "localhost"),
            port=getattr(settings, "db_port", 5432),
            database=getattr(settings, "db_name", "postgres"),
            user=getattr(settings, "db_user", "postgres"),
            password=getattr(settings, "db_password", ""),
            cursor_factory=RealDictCursor
        )

    # 设置 schema（优先使用从 URL 中提取的 schema，否则使用配置的 schema）
    final_schema = db_schema or getattr(settings, "db_schema", None)
    if final_schema:
        with conn.cursor() as cur:
            cur.execute(f"SET search_path TO {final_schema}")
        conn.commit()

    return conn




# 雪花算法生成主键
_SNOWFLAKE_EPOCH = 1288834974657  # 自定义起始时间戳（ms）
_snowflake_lock = threading.Lock()
_snowflake_last_ts = 0
_snowflake_sequence = 0


def _next_snowflake_id() -> int:
    """
    生成雪花算法ID（64bit）
    时间戳41bit + datacenter 5bit + worker 5bit + sequence 12bit
    """
    global _snowflake_last_ts, _snowflake_sequence
    datacenter_id = getattr(settings, "snowflake_datacenter_id", 1) & 0x1F
    worker_id = getattr(settings, "snowflake_worker_id", 1) & 0x1F

    with _snowflake_lock:
        ts = int(time.time() * 1000)
        if ts < _snowflake_last_ts:
            raise ValueError("系统时钟回拨，无法生成雪花ID")
        if ts == _snowflake_last_ts:
            _snowflake_sequence = (_snowflake_sequence + 1) & 0xFFF
            if _snowflake_sequence == 0:
                while ts <= _snowflake_last_ts:
                    ts = int(time.time() * 1000)
        else:
            _snowflake_sequence = 0
        _snowflake_last_ts = ts

        return (
            ((ts - _SNOWFLAKE_EPOCH) << 22)
            | (datacenter_id << 17)
            | (worker_id << 12)
            | _snowflake_sequence
        )


def _get_redis_client():
    """构造Redis客户端，支持集群模式"""
    # 检查是否有集群配置
    cluster_nodes = getattr(settings, "redis_cluster_nodes", None)
    redis_password = getattr(settings, "redis_password", None)

    if cluster_nodes:
        # 解析集群节点配置
        try:
            from redis import RedisCluster
            from redis.cluster import ClusterNode
            # 解析节点列表，格式: host1:port1,host2:port2,...
            startup_nodes = []
            for node in cluster_nodes.split(','):
                host, port = node.strip().split(':')
                startup_nodes.append(ClusterNode(host, int(port)))

            # 创建 RedisCluster 客户端，使用更兼容的参数
            cluster_client = RedisCluster(
                startup_nodes=startup_nodes,
                password=redis_password,
                decode_responses=True,
                skip_full_coverage_check=True,  # 允许部分节点不可用
                max_connections=32,
                max_connections_per_node=8,
                retry_on_timeout=True
            )
            return cluster_client
        except Exception as e:
            # 如果集群连接失败，尝试回退到单机模式
            print(f"Redis cluster connection failed: {e}, falling back to standalone mode")
            return redis.Redis(
                host="localhost",  # 使用默认配置
                port=6379,
                db=0,
                password=None,
                decode_responses=True,
            )
    else:
        # 原有单机模式作为后备
        redis_url = getattr(settings, "redis_url", None)
        if redis_url:
            return redis.Redis.from_url(redis_url, decode_responses=True)
        return redis.Redis(
            host=getattr(settings, "redis_host", "localhost"),
            port=getattr(settings, "redis_port", 6379),
            db=getattr(settings, "redis_db", 0),
            password=redis_password,
            decode_responses=True,
        )


def _resolve_user_real_id(user_code: Optional[str]) -> Optional[str]:
    """
    将用户编码映射为真实用户ID
    Redis key: SHARE_BFM_USER_CODE_{user_code}
    """
    if not user_code:
        return None
    redis_client = _get_redis_client()
    real_id = redis_client.get(f"SHARE_BFM_USER_CODE_{user_code}")
    return real_id or user_code


def _extract_session_id(request: Request) -> str:
    """从请求中解析 sessionId，支持 cookies 与原始 header"""
    session_id = request.cookies.get("SESSION") or request.cookies.get("session")
    if not session_id:
        raw_cookie = request.headers.get("cookie")
        if raw_cookie:
            cookie = SimpleCookie()
            cookie.load(raw_cookie)
            for key in ("SESSION", "session"):
                if key in cookie:
                    session_id = cookie[key].value
                    break
    if not session_id:
        raise ValueError("未获取到登录会话，请重新登录")
    return session_id


def _get_current_user_from_session(request: Request) -> Dict[str, Optional[str]]:
    """基于 session 从 Redis 获取当前登录人信息"""
    session_id = _extract_session_id(request)
    redis_client = _get_redis_client()
    redis_key = f"common_system:sessions:{session_id}"

    try:
        session_data = redis_client.hgetall(redis_key)
        # 确保 session_data 是字典类型
        if not isinstance(session_data, dict):
            session_data = {}
    except Exception as e:
        print(f"Redis hgetall error: {e}")
        session_data = {}

    if not session_data:
        raise ValueError("登录会话已失效，请重新登录")

    user_id = session_data.get("sessionAttr:userId")
    user_code = session_data.get("sessionAttr:USER_CODE")
    if not user_id:
        raise ValueError("会话中缺少用户信息，请重新登录")

    # 确保返回值是字符串类型
    user_code = str(user_code).replace('"', '') if user_code else ""
    user_id = str(user_id).replace('"', '') if user_id else ""
    return {"user_id": user_id, "user_code": user_code}


def _send_notice(notice_details: List[Dict[str, Any]], request: Request):
    """调用外部通知接口，失败不阻断主流程"""
    if not notice_details:
        return
    try:
        # 发送前将 senderId/targetId 转换为真实用户ID
        resolved_details = []
        for item in notice_details:
            new_item = dict(item)
            if "senderId" in new_item:
                new_item["senderId"] = _resolve_user_real_id(new_item.get("senderId"))
            if "targetId" in new_item:
                new_item["targetId"] = _resolve_user_real_id(new_item.get("targetId"))
            resolved_details.append(new_item)

        # 提取 cookie 并透传到通知接口
        cookies = {}
        # 优先从 request.cookies 获取（FastAPI 已解析）
        if request.cookies:
            cookies = dict(request.cookies)
        # 如果 request.cookies 为空，尝试从 header 中获取 cookie
        elif request.headers.get("cookie"):
            cookie_header = request.headers.get("cookie")
            cookie_obj = SimpleCookie()
            cookie_obj.load(cookie_header)
            for key, morsel in cookie_obj.items():
                cookies[key] = morsel.value

        requests.post(
            settings.notice_url,
            json={"noticeDetails": resolved_details},
            cookies=cookies,
            timeout=5,
        )
    except Exception as e:
        # 生产可接入日志，这里静默失败
        print(e)
        pass


def _row_to_todo_item(row: Dict[str, Any]) -> dict:
    """将查询结果行映射为驼峰结构，日期时间字段格式化为字符串"""
    status = TODO_STATUS_LIST.get(row.get("todo_status"))
    priority = TODO_PRIORITY_LIST.get(row.get("todo_priority"))
    urgencyLevel = URGENCY_LEVEL_LIST.get(row.get("urgency_level"))
    promoter = f"{_get_user_name_by_user_code(row.get('promoter'))}({row.get('promoter')})"
    handler_id = row.get("handler_id")
    # 处理内容与进度一致：优先从子查询得到的主处理人 handle_comment
    handle_comment = row.get("handle_comment") or ""
    handlers = row.get("handlers", [])
    handler_name_list = [f"{_get_user_name_by_user_code(handler.get('handlerId'))}({handler.get('handlerId')})" for handler in handlers]
    if not handle_comment and handler_id and handlers:
        for handler in handlers:
            if handler.get("handlerId") == handler_id:
                handle_comment = handler.get("handleComment") or ""
                break
    if handler_id:
        handler_id = f"{_get_user_name_by_user_code(row.get('handler_id'))}({row.get('handler_id')})"

    # 处理会议纪要信息
    meeting_note_id = str(row.get("meeting_note_id")) if row.get("meeting_note_id") else None
    meeting_note_title = row.get("meeting_note_title") if row.get("meeting_note_title") else None

    return {
        "todoId": str(row.get("id")),
        "title": row.get("title"),
        "content": row.get("todo_content"),
        "status": status,
        "priority": priority,
        "deadlineAt": _format_datetime(row.get("deadline_at")),
        "createdAt": _format_datetime(row.get("created_at")),
        "updatedAt": _format_datetime(row.get("updated_at")),
        "promoter": promoter,
        "handlering": handler_id,
        "handlers": handler_name_list,
        "attachments": row.get("attachments") or [],
        "urgencyLevel": urgencyLevel,
        "completedAt": _format_datetime(row.get("completed_at")),
        "cancelledAt": _format_datetime(row.get("cancelled_at")),
        "cancelledReason": row.get("cancelled_reason"),
        "approvedAt": _format_datetime(row.get("approved_at")),
        "rejectedAt": _format_datetime(row.get("rejected_at")),
        "approvalComment": row.get("approval_comment"),
        "handleContent": handle_comment,
        "progress": row.get("progress_percentage"),
        "returnReason": row.get("return_reason") if row.get("todo_status") == TodoStatus.RETURNED.value else None,
        "remark": row.get("remark"),
        "meetingNoteId": meeting_note_id,
        "meetingNoteTitle": meeting_note_title
    }


async def _get_sub_org_ids(org_id: int) -> List[int]:
    """
    递归查询指定组织的所有下级组织ID（包含自身）
    
    Args:
        org_id: 组织ID
        
    Returns:
        List[int]: 组织ID列表（包含自身和所有下级组织）
    """
    client = get_client()
    org_ids = [org_id]  # 包含自身
    
    try:
        # 使用 query_org_by_up_org_id 接口查询直接下级组织
        path = "/zmp-pr/zmp-nhr/open/nhrapp/org/qryOrgByUpOrgId"
        params = {"orgId": org_id}
        
        result = await client.request(
            method="GET",
            path=path,
            params=params,
            need_auth=True
        )
        
        if result.get("success") and result.get("data"):
            sub_orgs = result.get("data")
            
            # 处理响应数据
            if isinstance(sub_orgs, dict) and sub_orgs.get("data"):
                sub_orgs = sub_orgs.get("data")
            
            if isinstance(sub_orgs, list):
                # 递归查询每个下级组织的子组织
                for sub_org in sub_orgs:
                    if isinstance(sub_org, dict):
                        # 支持 ORG_ID 和 orgId 两种字段名
                        sub_org_id = sub_org.get("ORG_ID") or sub_org.get("orgId")
                        if sub_org_id:
                            sub_org_id = int(sub_org_id)
                            if sub_org_id not in org_ids:
                                org_ids.append(sub_org_id)
                                # 递归查询该组织的下级组织
                                try:
                                    sub_sub_org_ids = await _get_sub_org_ids(sub_org_id)
                                    for sub_sub_id in sub_sub_org_ids:
                                        if sub_sub_id not in org_ids:
                                            org_ids.append(sub_sub_id)
                                except Exception as sub_e:
                                    logger.warning(f"递归查询组织 {sub_org_id} 的下级组织失败: {str(sub_e)}")
                                    continue
        
        logger.info(f"查询组织 {org_id} 的所有下级组织，共 {len(org_ids)} 个")
        return org_ids
        
    except Exception as e:
        logger.warning(f"查询组织 {org_id} 的下级组织失败: {str(e)}，仅返回当前组织")
        return [org_id]


def _get_handlers(conn, todo_id: int) -> List[str]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT handler_id FROM todo_item_handlers WHERE todo_item_id = %s",
            (todo_id,),
        )
        rows = cur.fetchall()
        return [r["handler_id"] for r in rows]


def _get_todo_basic(conn, todo_id: int) -> Optional[Dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, title, promoter, deadline_at, handler_id,
                   approved_at, rejected_at, completed_at, todo_status
            FROM todo_items WHERE id = %s
            """,
            (todo_id,),
        )
        row = cur.fetchone()
        return row

def _get_user_id_from_context(request: Request) -> str:
    """从会话中获取当前用户ID"""
    return _get_current_user_from_session(request)["user_id"]

def _get_user_code_from_context(request: Request) -> str:
    """从会话中获取当前用户ID"""
    return _get_current_user_from_session(request)["user_code"]


async def _get_org_id_by_user_code(user_code: str) -> int:
    """根据员工工号查询组织ID"""
    client = get_client()
    
    try:
        path = f"/zmp-pr/db-zmpapi/open/zmpapi/org/queryStaffOrg/{user_code}"
        result = await client.request(
            method="GET",
            path=path,
            need_auth=True  # 需要认证
        )

        # 从响应中提取 orgId
        if result.get("success") and result.get("data"):
            data = result.get("data")
            if isinstance(data, dict) and data.get("data") and isinstance(data.get("data"), list):
                staff_list = data.get("data")
                if staff_list and len(staff_list) > 0:
                    org_id = staff_list[0].get("orgId")
                    if org_id is not None:
                        return int(org_id)
                    else:
                        logger.warning(f"查询员工工号 {user_code} 组织失败: 响应中缺少 orgId 字段")
                        raise ValueError(f"查询员工工号 {user_code} 组织失败: 响应中缺少 orgId 字段")
                else:
                    logger.warning(f"查询员工工号 {user_code} 组织失败: 响应数据为空")
                    raise ValueError(f"查询员工工号 {user_code} 组织失败: 响应数据为空")
            else:
                logger.warning(f"查询员工工号 {user_code} 组织失败: 响应数据格式不正确")
                raise ValueError(f"查询员工工号 {user_code} 组织失败: 响应数据格式不正确")
        elif result.get("success") is False:
            # 如果查询失败，记录日志并抛出异常
            error_msg = result.get('message', '未知错误')
            logger.warning(f"查询员工工号 {user_code} 组织失败: {error_msg}")
            raise ValueError(f"查询员工工号 {user_code} 组织失败: {error_msg}")
        else:
            logger.warning(f"查询员工工号 {user_code} 组织失败: 响应格式不正确")
            raise ValueError(f"查询员工工号 {user_code} 组织失败: 响应格式不正确")
    except ValueError:
        # 重新抛出 ValueError
        raise
    except Exception as e:
        # 捕获其他异常，记录日志并抛出
        logger.error(f"查询员工工号 {user_code} 组织时发生异常: {str(e)}")
        raise ValueError(f"查询员工工号 {user_code} 组织时发生异常: {str(e)}")


def _get_org_id_by_user_id(user_id: str) -> int:
    """
    根据用户ID（可能是用户编码或真实用户ID）获取组织ID
    优先解析 JSON，若有多个组织取第一个 orgId
    """
    if not user_id:
        raise ValueError("用户ID不能为空")

    # 先尝试将 user_id 作为用户编码转换为真实用户ID
    real_user_id = _resolve_user_real_id(user_id) or user_id

    redis_client = _get_redis_client()
    redis_key = f"SHARE_USER_ORG_POST_{real_user_id}"

    org_id = None
    raw_value = redis_client.get(redis_key)
    if raw_value:
        try:
            parsed = json.loads(raw_value)
            if isinstance(parsed, list) and parsed:
                first = parsed[0]
                if isinstance(first, dict):
                    org_id = first.get("orgId") or first.get("org_id")
            elif isinstance(parsed, dict):
                org_id = parsed.get("orgId") or parsed.get("org_id")
        except Exception:
            # 非 JSON 时忽略解析错误
            pass

    if not org_id:
        hash_value = redis_client.hgetall(redis_key)
        if hash_value:
            org_id = hash_value.get("orgId") or hash_value.get("org_id")

    if not org_id:
        raise ValueError(f"未获取到用户 {user_id} 的组织信息，请检查组织配置")

    return int(org_id)

def _get_user_name_by_user_code(user_code: str) -> str:
    if not user_code:
        raise ValueError("用户编码不能为空")

    user_name = user_code_dict.get(user_code)
    if user_name:
        return user_name

    # 先尝试将 user_id 作为用户编码转换为真实用户ID
    real_user_id = _resolve_user_real_id(user_code) or user_code
    redis_client = _get_redis_client()
    redis_key = f"SHARE_BFM_USER_{real_user_id}"

    raw_value = redis_client.get(redis_key)
    if raw_value:
        try:
            parsed = json.loads(raw_value)
            if isinstance(parsed, list) and parsed:
                first = parsed[0]
                if isinstance(first, dict):
                    user_name = first.get("userName")
            elif isinstance(parsed, dict):
                user_name = parsed.get("userName")
        except Exception:
            # 非 JSON 时忽略解析错误
            pass

    if user_name:
        user_code_dict[user_code] = user_name

    return user_name if user_name else user_code


def _check_todo_permission(todo_id: str, user_id: str, permission_type: str) -> bool:
    """
    检查待办权限
    
    Args:
        todo_id: 待办ID
        user_id: 用户ID
        permission_type: 权限类型：'view'(查看), 'edit'(编辑), 'handle'(处理), 'approve'(审批)
    
    Returns:
        bool: 是否有权限
    """
    # TODO: 实现数据库查询，检查用户是否有权限
    # permission_type == 'view': 检查是否是创建人或处理人
    # permission_type == 'edit': 创建人、发起人、处理人都可以修改
    # permission_type == 'handle': 检查是否是处理人
    # permission_type == 'approve': 检查是否是审批人（如果有审批流程）
    return True


async def create_todo(body: CreateTodoRequestBody, request: Request):
    """
    创建待办事项
    
    Args:
        title: 待办标题
        handler_id: 处理人ID（主处理人）
        description: 待办描述
        deadline_at: 截止时间
        priority: 优先级
        handler_ids: 其他处理人ID列表
        attachments: 附件列表
    
    Returns:
        dict: 创建结果
    """
    # 记录入参日志
    try:
        logger.info(f"[create_todo] 入参: {body.model_dump() if hasattr(body, 'model_dump') else body.dict()}")
    except Exception:
        logger.info(f"[create_todo] 入参: {str(body)}")
    
    try:
        # 获取当前用户ID
        current_user = _get_current_user_from_session(request)
        current_user_id = current_user.get("user_id")
        current_user_code = current_user.get("user_code")
        body.promoter = current_user_code

        
        # 验证会议纪要存在性（如果提供了）
        meeting_note_id = None
        if body.meetingNoteId:
            try:
                meeting_note_id = int(body.meetingNoteId)
                # 验证会议纪要存在且未删除
                conn_temp = _get_conn()
                with conn_temp:
                    with conn_temp.cursor() as cur_temp:
                        cur_temp.execute(
                            """
                            SELECT id, deleted_at FROM meeting_notes WHERE id = %s
                            """,
                            (meeting_note_id,)
                        )
                        meeting_row = cur_temp.fetchone()
                        if not meeting_row:
                            return {
                                "success": False,
                                "code": 400,
                                "message": "会议纪要不存在",
                                "data": None
                            }
                        if meeting_row.get('deleted_at'):
                            return {
                                "success": False,
                                "code": 400,
                                "message": "会议纪要已删除，无法关联",
                                "data": None
                            }
            except ValueError:
                return {
                    "success": False,
                    "code": 400,
                    "message": "会议纪要ID格式错误",
                    "data": None
                }
        
        # 根据发起人获取组织ID
        promoter_org_id = await _get_org_id_by_user_code(body.promoter)
        
        # 解析截止时间
        deadline_timestamp = None
        if body.deadlineAt:
            try:
                deadline_timestamp = datetime.strptime(body.deadlineAt, '%Y-%m-%d %H:%M:%S')
                # 检查截止时间是否小于当前时间
                if deadline_timestamp < datetime.now():
                    return {
                        "success": False,
                        "code": 400,
                        "message": "截止时间不能小于当前时间",
                        "data": {"errorMsg": "[create_todo] 参数错误:截止时间不能小于当前时间"}
                    }
            except ValueError:
                return {
                    "success": False,
                    "code": 400,
                    "message": "截止时间格式错误，请使用 YYYY-MM-DD HH:mm:%S 格式",
                    "data": {"errorMsg": "[create_todo] 参数错误:截止时间格式错误，请使用 YYYY-MM-DD HH:mm:%S 格式"}
                }
        conn = _get_conn()
        with conn:
            with conn.cursor() as cur:
                todo_id = _next_snowflake_id()
                # 确保枚举值正确获取
                priority_value = body.priority.value if body.priority is not None else TodoPriority.NORMAL.value
                urgency_value = body.urgencyLevel.value if body.urgencyLevel is not None else UrgencyLevel.LOW.value

                cur.execute(
                    """
                    INSERT INTO todo_items (
                        id, title, todo_content, deadline_at, todo_priority, todo_status,
                        created_by, promoter, org_id, urgency_level, created_at, remark, meeting_note_id
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING created_at
                    """,
                    (
                        todo_id,
                        body.title,
                        f"{body.title}\n\n{body.content}",
                        deadline_timestamp,
                        priority_value,
                        TodoStatus.PENDING_RECEIVE.value,
                        current_user_code,
                        body.promoter,
                        promoter_org_id,
                        urgency_value,
                        datetime.now(),
                        body.remark,
                        meeting_note_id
                    ),
                )
                row = cur.fetchone()
                created_at = row["created_at"]

                # 处理人列表（含主处理人），每个处理人使用自己的组织ID
                handler_ids = body.handlerIds or []
                todo_handler_id = _next_snowflake_id()
                if handler_ids:
                    handler_org_pairs = []
                    for handler_id in handler_ids:
                        try:
                            handler_org_id = await _get_org_id_by_user_code(handler_id)
                            handler_org_pairs.append((todo_handler_id, todo_id, handler_org_id, handler_id))
                        except Exception as e:
                            # 如果获取处理人组织ID失败，使用发起人的组织ID作为兜底
                            handler_org_pairs.append((todo_handler_id, todo_id, promoter_org_id, handler_id))
                    
                    # 使用 WHERE NOT EXISTS 替代 ON CONFLICT，提高兼容性
                    for todo_handler_id, todo_item_id, org_id, handler_id in handler_org_pairs:
                        cur.execute(
                            """
                            INSERT INTO todo_item_handlers (id, todo_item_id, org_id, handler_id)
                            SELECT %s, %s, %s, %s
                            WHERE NOT EXISTS (
                                SELECT 1 FROM todo_item_handlers 
                                WHERE todo_item_id = %s AND handler_id = %s
                            )
                            """,
                            (todo_handler_id, todo_item_id, org_id, handler_id, todo_item_id, handler_id),
                        )

                # 附件
                if body.attachments:
                    attachment_id = _next_snowflake_id()
                    cur.executemany(
                        """
                        INSERT INTO todo_item_attachments (id, todo_item_id, file_name, storage_path, uploaded_by)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        [
                            (attachment_id, todo_id, att.fileName, att.storagePath, current_user_code)
                            for att in body.attachments
                        ],
                    )

        # 通知处理人（如果操作人是发起人，则不需要发消息通知）
        notices = []
        # 判断当前用户是否是发起人，如果是发起人则不需要发消息通知
        for hid in body.handlerIds or []:
                # 跳过通知发起人自己
                if hid != body.promoter:
                    notices.append({
                        "content": f"待办创建：{body.title}",
                        "priority": 2,
                        "senderId": body.promoter,
                        "targetId": hid,
                        "title": "新的待办任务",
                    })
        if notices:
            _send_notice(notices, request)

        return {
            "success": True,
            "code": 200,
            "message": "创建成功",
            "data": {
                "todoId": str(todo_id),
                "title": body.title,
                "status": TodoStatus.PENDING_RECEIVE.value,
                "createdAt": _format_datetime(created_at),
                "urgencyLevel": body.urgencyLevel.value if body.urgencyLevel else None,
                "errorMsg": ""
            },
        }
        
    except ValueError as e:
        logger.error(f"[create_todo] 参数错误: {str(e)}\n{traceback.format_exc()}")
        return {
            "success": False,
            "code": 401,
            "message": str(e),
            "data": {"errorMsg": f"[create_todo] 参数错误: {str(e)}\n{traceback.format_exc()}"}
        }
    except Exception as e:
        logger.error(f"[create_todo] 创建失败: {str(e)}\n{traceback.format_exc()}")
        return {
            "success": False,
            "code": 500,
            "message": f"创建失败: {str(e)}",
            "data": {"errorMsg": f"[create_todo] 创建失败: {str(e)}\n{traceback.format_exc()}"}
        }


async def query_todo_list(body: TodoListQueryBody, request: Request):
    """
    查询待办列表
    
    支持两种查询类型：
    1. my_todos: 待我处理的待办（handler_id = 当前用户）
    2. my_created: 我发起的待办（created_by = 当前用户）
    3. all: 全部待办（需指定处理人列表或组织ID）
    
    Args:
        query_type: 查询类型
        status: 状态筛选
        priority: 优先级筛选
        keyword: 关键词搜索
        urgency_level: 紧急程度筛选
        deadline_start/deadline_end: 截止时间范围
        handler_ids: 处理人ID列表
        meeting_note_ids: 会议纪要ID列表
        org_id: 组织ID
        include_sub_orgs: 是否包含下级组织
        page: 页码
        page_size: 每页数量
        sort_by: 排序字段
        sort_order: 排序方向
    
    Returns:
        dict: 查询结果
    """
    # 记录入参日志
    try:
        logger.info(f"[query_todo_list] 入参: {body.model_dump() if hasattr(body, 'model_dump') else body.dict()}")
    except Exception:
        logger.info(f"[query_todo_list] 入参: {str(body)}")
    
    try:
        body.keyword = None
        # 获取当前用户ID
        current_user_code = _get_user_code_from_context(request)
        if body.queryType is None:
            body.queryType = 'all'
        
        # 验证查询类型
        if body.queryType not in ['my_todos', 'my_created', 'all']:
            return {
                "success": False,
                "code": 400,
                "message": "查询类型错误，必须是 my_todos 或 my_created 或 all",
                "data": None
            }
        if body.queryType == "all" and body.handlerIds is None and body.orgId is None and body.promoterOrgId is None and body.handlerOrgId is None and body.meetingNoteIds is None and body.promoter is None:
            return {
                "success": False,
                "code": 400,
                "message": "请提供需要查询的处理人列表、组织ID、发起人ID或会议纪要id",
                "data": None
            }
        
        conn = _get_conn()
        with conn:
            with conn.cursor() as cur:
                conditions = []
                params = []

                # if body.queryType == 'my_todos':
                #     conditions.append("(ti.handler_id = %s OR EXISTS (SELECT 1 FROM todo_item_handlers th WHERE th.todo_item_id = ti.id AND th.handler_id = %s))")
                #     params.extend([current_user_code, current_user_code])
                #     if body.status is None:
                #         conditions.append("(ti.todo_status in (%s, %s, %s))")
                #         params.extend([TodoStatus.PENDING_RECEIVE.value, TodoStatus.PENDING_REVIEW.value, TodoStatus.NOT_PASSED.value])
                # elif body.queryType == 'my_created':
                #     conditions.append("ti.promoter = %s")
                #     params.append(current_user_code)

                # 组织筛选（同时查询发起人组织和处理人组织）
                if body.orgId:
                    org_ids = [int(body.orgId)]
                    
                    # 如果需要包含下级组织，递归查询所有下级组织ID
                    if body.includeSubOrgs:
                        try:
                            org_ids = await _get_sub_org_ids(int(body.orgId))
                            logger.info(f"组织 {body.orgId} 包含下级组织查询，共 {len(org_ids)} 个组织")
                        except Exception as e:
                            logger.warning(f"查询下级组织失败: {str(e)}，仅使用当前组织")
                            org_ids = [int(body.orgId)]
                    
                    # 构建SQL查询条件（同时匹配发起人组织和处理人组织）
                    if org_ids:
                        placeholders = ','.join(['%s'] * len(org_ids))
                        # 发起人组织（ti.org_id）或处理人组织（todo_item_handlers.org_id）
                        conditions.append(f"(ti.org_id IN ({placeholders}) OR EXISTS (SELECT 1 FROM todo_item_handlers th WHERE th.todo_item_id = ti.id AND th.org_id IN ({placeholders})))")
                        params.extend(org_ids)
                        params.extend(org_ids)

                # 发起人组织筛选
                if body.promoterOrgId:
                    promoter_org_ids = [int(body.promoterOrgId)]
                    
                    # 如果需要包含下级组织，递归查询所有下级组织ID
                    if body.includeSubOrgs:
                        try:
                            promoter_org_ids = await _get_sub_org_ids(int(body.promoterOrgId))
                            logger.info(f"发起人组织 {body.promoterOrgId} 包含下级组织查询，共 {len(promoter_org_ids)} 个组织")
                        except Exception as e:
                            logger.warning(f"查询发起人下级组织失败: {str(e)}，仅使用当前组织")
                            promoter_org_ids = [int(body.promoterOrgId)]
                    
                    # 构建SQL查询条件（ti.org_id 存储的是发起人的组织ID）
                    if promoter_org_ids:
                        placeholders = ','.join(['%s'] * len(promoter_org_ids))
                        conditions.append(f"ti.org_id IN ({placeholders})")
                        params.extend(promoter_org_ids)

                # 处理人组织筛选
                if body.handlerOrgId:
                    handler_org_ids = [int(body.handlerOrgId)]
                    
                    # 如果需要包含下级组织，递归查询所有下级组织ID
                    if body.includeSubOrgs:
                        try:
                            handler_org_ids = await _get_sub_org_ids(int(body.handlerOrgId))
                            logger.info(f"处理人组织 {body.handlerOrgId} 包含下级组织查询，共 {len(handler_org_ids)} 个组织")
                        except Exception as e:
                            logger.warning(f"查询处理人下级组织失败: {str(e)}，仅使用当前组织")
                            handler_org_ids = [int(body.handlerOrgId)]
                    
                    # 构建SQL查询条件（需要关联 todo_item_handlers 表查询处理人组织）
                    if handler_org_ids:
                        placeholders = ','.join(['%s'] * len(handler_org_ids))
                        conditions.append(f"EXISTS (SELECT 1 FROM todo_item_handlers th WHERE th.todo_item_id = ti.id AND th.org_id IN ({placeholders}))")
                        params.extend(handler_org_ids)

                if body.handlerIds:
                    # 过滤处理人ID列表，同时检查主表的handler_id和处理人表的handler_id
                    handler_ids = [handler_id for handler_id in body.handlerIds if handler_id]
                    if handler_ids:
                        placeholders = ','.join(['%s'] * len(handler_ids))
                        conditions.append(f"(ti.handler_id IN ({placeholders}) OR EXISTS (SELECT 1 FROM todo_item_handlers th WHERE th.todo_item_id = ti.id AND th.handler_id IN ({placeholders})))")
                        params.extend(handler_ids)
                        params.extend(handler_ids)

                # 发起人筛选
                if body.promoter:
                    conditions.append("ti.promoter = %s")
                    params.append(body.promoter)

                # 会议纪要ID筛选
                if body.meetingNoteIds:
                    # 过滤会议纪要ID列表
                    meeting_note_ids = [note_id for note_id in body.meetingNoteIds if note_id]
                    if meeting_note_ids:
                        placeholders = ','.join(['%s'] * len(meeting_note_ids))
                        conditions.append(f"ti.meeting_note_id IN ({placeholders})")
                        params.extend(meeting_note_ids)

                # 状态筛选：优先使用statusList，如果未提供则使用status
                if body.statusList and len(body.statusList) > 0:
                    # 使用状态列表查询
                    status_values = [s.value for s in body.statusList]
                    placeholders = ','.join(['%s'] * len(status_values))
                    conditions.append(f"ti.todo_status IN ({placeholders})")
                    params.extend(status_values)
                elif body.status:
                    # 使用单个状态查询
                    conditions.append("ti.todo_status = %s")
                    params.append(body.status.value)
                
                if body.priority:
                    conditions.append("ti.todo_priority = %s")
                    params.append(body.priority.value)
                if body.urgencyLevel:
                    conditions.append("ti.urgency_level = %s")
                    params.append(body.urgencyLevel.value)
                if body.keyword:
                    conditions.append("(ti.title ILIKE %s OR ti.todo_content ILIKE %s)")
                    kw = f"%{body.keyword}%"
                    params.extend([kw, kw])

                if body.deadlineStart:
                    conditions.append("ti.deadline_at >= %s")
                    params.append(body.deadlineStart)
                if body.deadlineEnd:
                    conditions.append("ti.deadline_at <= %s")
                    params.append(body.deadlineEnd)
                if body.handledStart:
                    conditions.append("EXISTS (SELECT 1 FROM todo_item_handlers th WHERE th.todo_item_id = ti.id AND th.handled_at >= %s)")
                    params.append(body.handledStart)
                if body.handledEnd:
                    conditions.append("EXISTS (SELECT 1 FROM todo_item_handlers th WHERE th.todo_item_id = ti.id AND th.handled_at <= %s)")
                    params.append(body.handledEnd)
                if body.rejectedStart:
                    conditions.append("ti.rejected_at >= %s")
                    params.append(body.rejectedStart)
                if body.rejectedEnd:
                    conditions.append("ti.rejected_at <= %s")
                    params.append(body.rejectedEnd)
                if body.completedStart:
                    conditions.append("ti.completed_at >= %s")
                    params.append(body.completedStart)
                if body.completedEnd:
                    conditions.append("ti.completed_at <= %s")
                    params.append(body.completedEnd)

                where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

                sort_by = body.sortBy if body.sortBy in ["created_at", "deadline_at", "updated_at"] else "created_at"
                sort_order = "ASC" if (body.sortOrder or "").lower() == "asc" else "DESC"

                count_sql = f"""
                    SELECT COUNT(*) AS cnt
                    FROM todo_items ti
                    {where_clause}
                """
                cur.execute(count_sql, params)
                total = cur.fetchone()["cnt"]

                offset = (body.page - 1) * body.pageSize
                list_sql = f"""
                    SELECT
                        ti.*,
                        (SELECT h1.progress_percentage FROM todo_item_handlers h1 WHERE h1.todo_item_id = ti.id AND h1.handler_id = ti.handler_id LIMIT 1) AS progress_percentage,
                        (SELECT h1.handle_comment FROM todo_item_handlers h1 WHERE h1.todo_item_id = ti.id AND h1.handler_id = ti.handler_id LIMIT 1) AS handle_comment,
                        COALESCE(
                            (
                                SELECT json_agg(
                                    json_build_object(
                                        'handlerId', th.handler_id,
                                        'handleComment', th.handle_comment
                                    )
                                )
                                FROM todo_item_handlers th
                                WHERE th.todo_item_id = ti.id
                            )::json,
                            '[]'::json
                        ) AS handlers,
                        COALESCE(
                            (
                                SELECT json_agg(
                                    json_build_object(
                                        'fileName', ta.file_name,
                                        'storagePath', ta.storage_path
                                    )
                                )
                                FROM todo_item_attachments ta
                                WHERE ta.todo_item_id = ti.id
                            )::json,
                            '[]'::json
                        ) AS attachments
                    FROM todo_items ti
                    {where_clause}
                    ORDER BY ti.{sort_by} {sort_order}
                    LIMIT %s OFFSET %s
                """
                cur.execute(list_sql, params + [body.pageSize, offset])
                rows = cur.fetchall()

                items = [_row_to_todo_item(r) for r in rows]
                return {
                    "success": True,
                    "code": 200,
                    "message": "查询成功",
                    "data": {
                        "items": items,
                        "pagination": {
                            "page": body.page,
                            "pageSize": body.pageSize,
                            "total": total,
                            "totalPages": (total + body.pageSize - 1) // body.pageSize if body.pageSize else 0
                        }
                    }
                }
        
    except ValueError as e:
        logger.error(f"[query_todo_list] 参数错误: {str(e)}\n{traceback.format_exc()}")
        return {
            "success": False,
            "code": 401,
            "message": str(e),
            "data": None
        }
    except Exception as e:
        logger.error(f"[query_todo_list] 查询失败: {str(e)}\n{traceback.format_exc()}")
        return {
            "success": False,
            "code": 500,
            "message": f"查询失败: {str(e)}",
            "data": None
        }


def get_todo_detail(body: TodoDetailBody, request: Request):
    """
    查询待办详情
    
    Args:
        todo_id: 待办ID
    
    Returns:
        dict: 待办详情
    """
    # 记录入参日志
    try:
        logger.info(f"[get_todo_detail] 入参: {body.model_dump() if hasattr(body, 'model_dump') else body.dict()}")
    except Exception:
        logger.info(f"[get_todo_detail] 入参: {str(body)}")
    
    try:
        # 获取当前用户ID
        current_user_code = _get_user_id_from_context(request)
        
        # 检查权限
        if not _check_todo_permission(body.todo_id, current_user_code, 'view'):
            return {
                "success": False,
                "code": 403,
                "message": "无权限查看该待办",
                "data": None
            }
        
        # TODO: 执行数据库查询
        # SELECT ti.*, 
        #        (SELECT json_agg(json_build_object('id', u.id, 'name', u.name))
        #         FROM todo_item_handlers th
        #         INNER JOIN users u ON th.handler_id = u.id
        #         WHERE th.todo_item_id = ti.id) as handlers,
        #        (SELECT json_agg(json_build_object('id', ta.id, 'file_name', ta.file_name, 'storage_path', ta.storage_path))
        #         FROM todo_item_attachments ta
        #         WHERE ta.todo_item_id = ti.id) as attachments
        # FROM todo_items ti
        # WHERE ti.id = :todo_id
        
        return {
            "success": True,
            "code": 200,
            "message": "查询成功",
            "data": None
        }
        
    except ValueError as e:
        logger.error(f"[get_todo_detail] 参数错误: {str(e)}\n{traceback.format_exc()}")
        return {
            "success": False,
            "code": 401,
            "message": str(e),
            "data": None
        }
    except Exception as e:
        logger.error(f"[get_todo_detail] 查询失败: {str(e)}\n{traceback.format_exc()}")
        return {
            "success": False,
            "code": 500,
            "message": f"查询失败: {str(e)}",
            "data": None
        }


def update_todo(body: UpdateTodoRequestBody, request: Request):
    """
    修改待办事项，仅发起人可修改。
    仅待接收、退回状态的待办可修改；修改后状态统一为待接收。
    可修改：内容(content)、处理人(handlerIds)、优先级、紧急程度、计划完成时间。
    """
    try:
        logger.info(f"[update_todo] 入参: {body.model_dump() if hasattr(body, 'model_dump') else body.dict()}")
    except Exception:
        logger.info(f"[update_todo] 入参: {str(body)}")
    
    try:
        todo_id = body.todoId
        current_user_code = _get_user_code_from_context(request)
        conn = _get_conn()
        plan_finish_dt = None
        base_row = None
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, created_by, promoter, handler_id, deadline_at, todo_status, title, todo_content, org_id
                    FROM todo_items WHERE id = %s
                    """,
                    (todo_id,),
                )
                base_row = cur.fetchone()
                if not base_row:
                    return {"success": False, "code": 404, "message": "待办不存在", "data": None}

                # 仅发起人可修改
                if current_user_code != base_row.get("promoter"):
                    return {
                        "success": False,
                        "code": 403,
                        "message": "仅发起人可修改该待办",
                        "data": None,
                    }

                # 仅待接收、退回状态可修改
                if base_row.get("todo_status") not in [TodoStatus.PENDING_RECEIVE.value, TodoStatus.RETURNED.value]:
                    return {
                        "success": False,
                        "code": 400,
                        "message": "仅待接收、退回状态的待办可修改",
                        "data": None,
                    }

                update_fields = []
                params = []

                # 内容：更新 todo_content，保留原 title 作为第一行
                if body.content is not None:
                    title = base_row.get("title") or ""
                    new_todo_content = f"{title}\n\n{body.content}".strip()
                    update_fields.append("todo_content = %s")
                    params.append(new_todo_content)

                if body.priority is not None:
                    update_fields.append("todo_priority = %s")
                    params.append(body.priority.value)

                if body.urgencyLevel is not None:
                    update_fields.append("urgency_level = %s")
                    params.append(body.urgencyLevel.value)

                if body.planFinishTime is not None:
                    try:
                        plan_finish_dt = datetime.strptime(body.planFinishTime, "%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        return {
                            "success": False,
                            "code": 400,
                            "message": "计划完成时间格式错误，请使用 YYYY-MM-DD HH:mm:ss",
                            "data": None,
                        }
                    update_fields.append("completed_at = %s")
                    params.append(plan_finish_dt)

                # 处理人：先删后插，并更新主表 handler_id（使用发起人组织作为兜底，同步上下文不调用 async）
                if body.handlerIds is not None:
                    promoter_org_id = base_row.get("org_id") or 0
                    cur.execute("DELETE FROM todo_item_handlers WHERE todo_item_id = %s", (todo_id,))
                    new_handler_id = None
                    if body.handlerIds:
                        new_handler_id = body.handlerIds[0]
                        for hid in body.handlerIds:
                            th_id = _next_snowflake_id()
                            cur.execute(
                                """
                                INSERT INTO todo_item_handlers (id, todo_item_id, org_id, handler_id)
                                SELECT %s, %s, %s, %s
                                WHERE NOT EXISTS (
                                    SELECT 1 FROM todo_item_handlers
                                    WHERE todo_item_id = %s AND handler_id = %s
                                )
                                """,
                                (th_id, todo_id, promoter_org_id, hid, todo_id, hid),
                            )
                        update_fields.append("handler_id = %s")
                        params.append(new_handler_id)
                    else:
                        update_fields.append("handler_id = %s")
                        params.append(None)

                if not update_fields:
                    return {
                        "success": True,
                        "code": 200,
                        "message": "无可更新字段",
                        "data": {"todoId": todo_id},
                    }

                # 修改后状态统一为待接收
                update_fields.append("todo_status = %s")
                params.append(TodoStatus.PENDING_RECEIVE.value)
                update_fields.append("updated_at = %s")
                now_ts = datetime.now()
                params.append(now_ts)
                params.append(todo_id)

                cur.execute(
                    f"UPDATE todo_items SET {', '.join(update_fields)} WHERE id = %s",
                    params,
                )

            # 超期提醒（统一为无时区再比较，避免 aware/naive 冲突）
            deadline_dt = base_row.get("deadline_at")
            if isinstance(deadline_dt, datetime) and deadline_dt.tzinfo is not None:
                deadline_dt = deadline_dt.replace(tzinfo=None)
            if plan_finish_dt and deadline_dt and plan_finish_dt > deadline_dt and current_user_code != base_row.get("promoter"):
                notices = [{
                    "content": f"待办 {base_row.get('title')} 计划完成时间晚于截止时间",
                    "priority": 1,
                    "senderId": current_user_code,
                    "targetId": base_row.get("promoter"),
                    "title": "待办超期提醒",
                }]
                _send_notice(notices, request)

        return {
            "success": True,
            "code": 200,
            "message": "修改成功",
            "data": {
                "todoId": todo_id
            }
        }
        
    except ValueError as e:
        logger.error(f"[update_todo] 参数错误: {str(e)}\n{traceback.format_exc()}")
        return {
            "success": False,
            "code": 401,
            "message": str(e),
            "data": None
        }
    except Exception as e:
        logger.error(f"[update_todo] 修改失败: {str(e)}\n{traceback.format_exc()}")
        return {
            "success": False,
            "code": 500,
            "message": f"修改失败: {str(e)}",
            "data": None
        }


def handle_todo(body: HandleTodoRequestBody, request: Request):
    """
    处理待办事项：更新进度(0-100%)。进度100%时状态改为待审核（发起人本人则直接关闭），否则保持已接收。
    仅处理人可处理；支持批量。可处理状态：待接收、不通过、已接收。
    """
    # 记录入参日志
    try:
        logger.info(f"[handle_todo] 入参: {body.model_dump() if hasattr(body, 'model_dump') else body.dict()}")
    except Exception:
        logger.info(f"[handle_todo] 入参: {str(body)}")
    
    try:
        if not body.todoIds:
            return {"success": False, "code": 400, "message": "缺少待办ID", "data": None}
        current_user_code = _get_user_code_from_context(request)
        now_ts = datetime.now()

        conn = _get_conn()
        handled_ids = []
        skipped = []
        notices = []
        with conn:
            with conn.cursor() as cur:
                for todo_id in body.todoIds:
                    # 基础信息
                    cur.execute(
                        """
                        SELECT id, todo_status, promoter, title, deadline_at, handler_id
                        FROM todo_items WHERE id = %s
                        """,
                        (todo_id,),
                    )
                    base_row = cur.fetchone()
                    if not base_row:
                        skipped.append({"todoId": todo_id, "reason": "待办不存在"})
                        continue

                    # 权限校验：主处理人或协同处理人
                    cur.execute(
                        "SELECT 1 FROM todo_item_handlers WHERE todo_item_id = %s AND handler_id = %s",
                        (todo_id, current_user_code),
                    )
                    is_sub_handler = cur.fetchone() is not None

                    if not is_sub_handler and base_row.get("handler_id") != current_user_code:
                        skipped.append({"todoId": todo_id, "reason": "无权限处理"})
                        continue

                    # 状态校验：待接收、不通过、已接收 可处理（已接收时可继续更新进度）
                    if base_row.get("todo_status") not in [
                        TodoStatus.NOT_PASSED.value,
                        TodoStatus.RECEIVED.value,
                    ]:
                        skipped.append({"todoId": todo_id, "reason": "状态不可处理"})
                        continue

                    # 更新处理人关联表：进度、处理备注、处理时间（进度存在处理人表）
                    cur.execute(
                        """
                        UPDATE todo_item_handlers
                        SET progress_percentage = %s,
                            handle_comment = %s,
                            handled_at = %s
                        WHERE todo_item_id = %s AND handler_id = %s
                        """,
                        (min(100, body.progress), body.handleComment, now_ts, todo_id, current_user_code),
                    )

                    # 按进度决定状态：进度100% -> 待审核（发起人本人则直接关闭）；非100% -> 保留原状态
                    current_status = base_row.get("todo_status")
                    if body.progress >= 100:
                        todo_status = (
                            TodoStatus.CLOSED.value
                            if current_user_code == base_row.get("promoter")
                            else TodoStatus.PENDING_REVIEW.value
                        )
                    else:
                        todo_status = current_status

                    # 更新主表：状态、主处理人（进度存处理人表，不写主表）
                    cur.execute(
                        """
                        UPDATE todo_items
                        SET todo_status = %s,
                            handler_id = %s,
                            updated_at = %s
                        WHERE id = %s
                        """,
                        (todo_status, current_user_code, now_ts, todo_id),
                    )

                    # 附件（处理上传）
                    if body.attachments:
                        attachment_rows = []
                        for att in body.attachments:
                            attachment_rows.append(
                                (_next_snowflake_id(), todo_id, att.fileName, att.storagePath, current_user_code)
                            )
                        cur.executemany(
                            """
                            INSERT INTO todo_item_attachments (id, todo_item_id, file_name, storage_path, uploaded_by)
                            VALUES (%s, %s, %s, %s, %s)
                            """,
                            attachment_rows,
                        )

                    handled_ids.append(todo_id)

                    # 进度达到100%且操作人不是发起人时，通知发起人
                    promoter = base_row.get("promoter")
                    if body.progress >= 100 and current_user_code != promoter:
                        notices.append({
                            "content": f"待办处理：{base_row.get('title')} 进度已100%，已提交审核",
                            "priority": 2,
                            "senderId": current_user_code,
                            "targetId": promoter,
                            "title": "待办处理进度",
                        })

        if notices:
            _send_notice(notices, request)

        return {
            "success": True,
            "code": 200,
            "message": f"处理成功 {len(handled_ids)} 条，跳过 {len(skipped)} 条",
            "data": {
                "handledIds": handled_ids,
                "skipped": skipped,
            }
        }
        
    except ValueError as e:
        logger.error(f"[handle_todo] 参数错误: {str(e)}\n{traceback.format_exc()}")
        return {
            "success": False,
            "code": 401,
            "message": str(e),
            "data": None
        }
    except Exception as e:
        logger.error(f"[handle_todo] 处理失败: {str(e)}\n{traceback.format_exc()}")
        return {
            "success": False,
            "code": 500,
            "message": f"处理失败: {str(e)}",
            "data": None
        }


def return_todo(body: ReturnTodoRequestBody, request: Request):
    """
    退回待办：仅当状态为待接收、且当前用户为该待办的处理人时可操作，需填写退回理由。
    """
    try:
        logger.info(f"[return_todo] 入参: {body.model_dump() if hasattr(body, 'model_dump') else body.dict()}")
    except Exception:
        logger.info(f"[return_todo] 入参: {str(body)}")
    try:
        current_user_code = _get_user_code_from_context(request)
        todo_id = body.todoId
        conn = _get_conn()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, todo_status, promoter, handler_id, title
                    FROM todo_items WHERE id = %s
                    """,
                    (todo_id,),
                )
                row = cur.fetchone()
                if not row:
                    return {
                        "success": False,
                        "code": 404,
                        "message": "待办不存在",
                        "data": None,
                    }
                if row.get("todo_status") != TodoStatus.PENDING_RECEIVE.value:
                    return {
                        "success": False,
                        "code": 400,
                        "message": "仅待接收状态的待办可退回",
                        "data": None,
                    }
                # 处理人校验：主处理人或协同处理人
                cur.execute(
                    "SELECT 1 FROM todo_item_handlers WHERE todo_item_id = %s AND handler_id = %s",
                    (todo_id, current_user_code),
                )
                is_sub_handler = cur.fetchone() is not None
                if not is_sub_handler and row.get("handler_id") != current_user_code:
                    return {
                        "success": False,
                        "code": 403,
                        "message": "仅处理人可退回该待办",
                        "data": None,
                    }
                now_ts = datetime.now()
                cur.execute(
                    """
                    UPDATE todo_items
                    SET todo_status = %s,
                        return_reason = %s,
                        returned_at = %s,
                        updated_at = %s
                    WHERE id = %s
                    """,
                    (TodoStatus.RETURNED.value, body.returnReason.strip(), now_ts, now_ts, todo_id),
                )
                promoter = row.get("promoter")
                notices = []
                if promoter and promoter != current_user_code:
                    notices.append({
                        "content": f"待办被退回：{row.get('title')}，理由：{body.returnReason[:100]}",
                        "priority": 2,
                        "senderId": current_user_code,
                        "targetId": promoter,
                        "title": "待办被退回",
                    })
        if notices:
            _send_notice(notices, request)
        return {
            "success": True,
            "code": 200,
            "message": "退回成功",
            "data": {"todoId": todo_id, "status": TodoStatus.RETURNED.value},
        }
    except Exception as e:
        logger.error(f"[return_todo] 退回失败: {str(e)}\n{traceback.format_exc()}")
        return {
            "success": False,
            "code": 500,
            "message": f"退回失败: {str(e)}",
            "data": None,
        }


def receive_todo(body: ReceiveTodoRequestBody, request: Request):
    """
    接收待办：仅当状态为待接收、且当前用户为该待办的处理人时可操作。
    """
    try:
        logger.info(f"[receive_todo] 入参: {body.model_dump() if hasattr(body, 'model_dump') else body.dict()}")
    except Exception:
        logger.info(f"[receive_todo] 入参: {str(body)}")
    try:
        current_user_code = _get_user_code_from_context(request)
        todo_id = body.todoId
        conn = _get_conn()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, todo_status, promoter, handler_id, title
                    FROM todo_items WHERE id = %s
                    """,
                    (todo_id,),
                )
                row = cur.fetchone()
                if not row:
                    return {
                        "success": False,
                        "code": 404,
                        "message": "待办不存在",
                        "data": None,
                    }
                if row.get("todo_status") != TodoStatus.PENDING_RECEIVE.value:
                    return {
                        "success": False,
                        "code": 400,
                        "message": "仅待接收状态的待办可接收",
                        "data": None,
                    }
                # 处理人校验：主处理人或协同处理人
                cur.execute(
                    "SELECT 1 FROM todo_item_handlers WHERE todo_item_id = %s AND handler_id = %s",
                    (todo_id, current_user_code),
                )
                is_sub_handler = cur.fetchone() is not None
                if not is_sub_handler and row.get("handler_id") != current_user_code:
                    return {
                        "success": False,
                        "code": 403,
                        "message": "仅处理人可接收该待办",
                        "data": None,
                    }
                now_ts = datetime.now()
                cur.execute(
                    """
                    UPDATE todo_items
                    SET todo_status = %s,
                        handler_id = %s,
                        updated_at = %s
                    WHERE id = %s
                    """,
                    (TodoStatus.RECEIVED.value, current_user_code, now_ts, todo_id),
                )
        return {
            "success": True,
            "code": 200,
            "message": "接收成功",
            "data": {"todoId": todo_id, "status": TodoStatus.RECEIVED.value},
        }
    except Exception as e:
        logger.error(f"[receive_todo] 接收失败: {str(e)}\n{traceback.format_exc()}")
        return {
            "success": False,
            "code": 500,
            "message": f"接收失败: {str(e)}",
            "data": None,
        }


def approve_todo(body: ApproveTodoRequestBody, request: Request):
    """
    审批待办事项
    
    Args:
        todo_id: 待办ID
        approval_status: 审批结果（Approved 或 Rejected）
        approval_comment: 审批意见
    
    Returns:
        dict: 审批结果
    """
    # 记录入参日志
    try:
        logger.info(f"[approve_todo] 入参: {body.model_dump() if hasattr(body, 'model_dump') else body.dict()}")
    except Exception:
        logger.info(f"[approve_todo] 入参: {str(body)}")
    
    try:
        current_user_code = _get_user_code_from_context(request)

        if body.approvalStatus not in ['Approving', 'Rejected']:
            return {
                "success": False,
                "code": 400,
                "message": "审核状态错误，必须是 Approving 或 Rejected",
                "data": None
            }

        if not body.todoIds:
            return {"success": False, "code": 400, "message": "缺少待办ID", "data": None}

        now_ts = datetime.now()
        conn = _get_conn()
        handled_ids = []
        skipped = []
        notices = []

        with conn:
            with conn.cursor() as cur:
                for todo_id in body.todoIds:
                    cur.execute(
                        """
                        SELECT id, promoter, todo_status, title
                        FROM todo_items WHERE id = %s
                        """,
                        (todo_id,),
                    )
                    base_row = cur.fetchone()
                    if not base_row:
                        skipped.append({"todoId": todo_id, "reason": "待办不存在"})
                        continue

                    if base_row.get("promoter") != current_user_code:
                        skipped.append({"todoId": todo_id, "reason": "非发起人，无权限审批"})
                        continue

                    if base_row.get("todo_status") != TodoStatus.PENDING_REVIEW.value:
                        skipped.append({"todoId": todo_id, "reason": "状态非待审核"})
                        continue

                    if body.approvalStatus == 'Approving':
                        cur.execute(
                            """
                            UPDATE todo_items
                            SET todo_status = %s,
                                approved_at = %s,
                                approval_comment = %s,
                                updated_at = %s
                            WHERE id = %s
                            """,
                            (TodoStatus.CLOSED.value, now_ts, body.approvalComment, now_ts, todo_id),
                        )
                        result_status = TodoStatus.CLOSED.value
                    else:
                        cur.execute(
                            """
                            UPDATE todo_items
                            SET todo_status = %s,
                                rejected_at = %s,
                                approval_comment = %s,
                                updated_at = %s
                            WHERE id = %s
                            """,
                            (TodoStatus.NOT_PASSED.value, now_ts, body.approvalComment, now_ts, todo_id),
                        )
                        result_status = TodoStatus.NOT_PASSED.value

                    # 查询处理人列表，用于通知
                    cur.execute(
                        """
                        SELECT DISTINCT handler_id FROM todo_item_handlers WHERE todo_item_id = %s
                        UNION
                        SELECT handler_id FROM todo_items WHERE id = %s AND handler_id IS NOT NULL
                        """,
                        (todo_id, todo_id),
                    )
                    handler_rows = cur.fetchall()
                    handler_ids = [r["handler_id"] for r in handler_rows if r.get("handler_id")]
                    if handler_ids:
                        msg = "审核通过" if result_status == TodoStatus.CLOSED.value else "审核不通过"
                        for hid in handler_ids:
                            # 跳过通知发起人自己
                            if hid != base_row.get("promoter"):
                                notices.append({
                                    "content": f"待办审批结果：{base_row.get('title')}，{msg}",
                                    "priority": 2,
                                    "senderId": current_user_code,
                                    "targetId": hid,
                                    "title": "待办审批结果",
                                })

                    handled_ids.append(todo_id)

        if notices:
            _send_notice(notices, request)

        return {
            "success": True,
            "code": 200,
            "message": f"审批成功 {len(handled_ids)} 条，跳过 {len(skipped)} 条",
            "data": {
                "handledIds": handled_ids,
                "skipped": skipped,
                "approvalStatus": body.approvalStatus
            }
        }
        
    except ValueError as e:
        logger.error(f"[approve_todo] 参数错误: {str(e)}\n{traceback.format_exc()}")
        return {
            "success": False,
            "code": 401,
            "message": str(e),
            "data": None
        }
    except Exception as e:
        logger.error(f"[approve_todo] 审批失败: {str(e)}\n{traceback.format_exc()}")
        return {
            "success": False,
            "code": 500,
            "message": f"审批失败: {str(e)}",
            "data": None
        }


def follow_up_todo(body: FollowUpTodoRequestBody, request: Request):
    """
    催更待办事项
    
    仅发起人可催更，支持批量
    
    Args:
        todo_id: 待办ID
        follow_up_content: 催更内容
    
    Returns:
        dict: 催更结果
    """
    # 记录入参日志
    try:
        logger.info(f"[follow_up_todo] 入参: {body.model_dump() if hasattr(body, 'model_dump') else body.dict()}")
    except Exception:
        logger.info(f"[follow_up_todo] 入参: {str(body)}")
    
    try:
        if not body.todoIds:
            return {"success": False, "code": 400, "message": "缺少待办ID", "data": None}
        current_user_code = _get_user_code_from_context(request)

        conn = _get_conn()
        handled_ids = []
        skipped = []
        notices = []
        with conn:
            with conn.cursor() as cur:
                for todo_id in body.todoIds:
                    cur.execute(
                        """
                        SELECT promoter, title, todo_status
                        FROM todo_items WHERE id = %s
                        """,
                        (todo_id,),
                    )
                    base_row = cur.fetchone()
                    if not base_row:
                        skipped.append({"todoId": todo_id, "reason": "待办不存在"})
                        continue

                    if base_row.get("promoter") != current_user_code:
                        skipped.append({"todoId": todo_id, "reason": "只有发起人可以催更"})
                        continue

                    if base_row.get("todo_status") not in [TodoStatus.PENDING_RECEIVE.value, TodoStatus.NOT_PASSED.value]:
                        skipped.append({"todoId": todo_id, "reason": "仅待接收或不通过可催更"})
                        continue

                    cur.execute(
                        """
                        SELECT DISTINCT handler_id FROM todo_item_handlers WHERE todo_item_id = %s
                        UNION
                        SELECT handler_id FROM todo_items WHERE id = %s AND handler_id IS NOT NULL
                        """,
                        (todo_id, todo_id),
                    )
                    handler_rows = cur.fetchall()
                    handler_ids = [r["handler_id"] for r in handler_rows if r.get("handler_id")]

                    # 如果操作人是发起人则不需要发消息通知
                    # 注意：催办操作必须是发起人，所以这里实际上不会发送通知
                    # 但为了代码的完整性和未来可能的扩展，保留逻辑判断
                    promoter = base_row.get("promoter")
                    for hid in handler_ids:
                            # 跳过通知发起人自己
                            if hid != promoter:
                                notices.append({
                                    "content": f"催办提醒：{base_row.get('title')}，内容：{body.followUpContent}",
                                    "priority": 2,
                                    "senderId": current_user_code,
                                    "targetId": hid,
                                    "title": "待办催办",
                                })

                    handled_ids.append(todo_id)

        if notices:
            _send_notice(notices, request)

        return {
            "success": True,
            "code": 200,
            "message": f"催更成功 {len(handled_ids)} 条，跳过 {len(skipped)} 条",
            "data": {
                "handledIds": handled_ids,
                "skipped": skipped,
                "followUpAt": _format_datetime(datetime.now())
            }
        }
        
    except ValueError as e:
        logger.error(f"[follow_up_todo] 参数错误: {str(e)}\n{traceback.format_exc()}")
        return {
            "success": False,
            "code": 401,
            "message": str(e),
            "data": None
        }
    except Exception as e:
        logger.error(f"[follow_up_todo] 催更失败: {str(e)}\n{traceback.format_exc()}")
        return {
            "success": False,
            "code": 500,
            "message": f"催更失败: {str(e)}",
            "data": None
        }


def delete_todo(body: DeleteTodoRequestBody, request: Request):
    """
    删除待办事项
    
    仅发起人可删除，支持批量删除
    
    Args:
        body: 删除请求体，包含待办ID列表
        request: FastAPI请求对象
    
    Returns:
        dict: 删除结果，包含成功删除的ID列表和跳过的待办及原因
    """
    # 记录入参日志
    try:
        logger.info(f"[delete_todo] 入参: {body.model_dump() if hasattr(body, 'model_dump') else body.dict()}")
    except Exception:
        logger.info(f"[delete_todo] 入参: {str(body)}")
    
    try:
        if not body.todoIds:
            return {"success": False, "code": 400, "message": "缺少待办ID", "data": None}
        
        current_user_code = _get_user_code_from_context(request)
        
        conn = _get_conn()
        deleted_ids = []
        skipped = []
        
        with conn:
            with conn.cursor() as cur:
                for todo_id in body.todoIds:
                    # 查询待办信息，验证存在性和权限
                    cur.execute(
                        """
                        SELECT id, promoter, title, todo_status
                        FROM todo_items WHERE id = %s
                        """,
                        (todo_id,),
                    )
                    base_row = cur.fetchone()
                    
                    if not base_row:
                        skipped.append({"todoId": todo_id, "reason": "待办不存在"})
                        continue
                    
                    # 验证权限：只有发起人可以删除
                    if base_row.get("promoter") != current_user_code:
                        skipped.append({"todoId": todo_id, "reason": "只有发起人可以删除"})
                        continue
                    
                    # 先删除关联的处理人记录
                    cur.execute(
                        """
                        DELETE FROM todo_item_handlers WHERE todo_item_id = %s
                        """,
                        (todo_id,),
                    )
                    
                    # 删除关联的附件记录
                    cur.execute(
                        """
                        DELETE FROM todo_item_attachments WHERE todo_item_id = %s
                        """,
                        (todo_id,),
                    )
                    
                    # 最后删除待办主记录
                    cur.execute(
                        """
                        DELETE FROM todo_items WHERE id = %s
                        """,
                        (todo_id,),
                    )
                    
                    # 检查是否成功删除
                    if cur.rowcount > 0:
                        deleted_ids.append(todo_id)
                    else:
                        skipped.append({"todoId": todo_id, "reason": "删除失败"})
                
                # 提交事务
                conn.commit()
        
        return {
            "success": True,
            "code": 200,
            "message": f"删除成功 {len(deleted_ids)} 条，跳过 {len(skipped)} 条",
            "data": {
                "deletedIds": deleted_ids,
                "skipped": skipped
            }
        }
        
    except ValueError as e:
        logger.error(f"[delete_todo] 参数错误: {str(e)}\n{traceback.format_exc()}")
        return {
            "success": False,
            "code": 401,
            "message": str(e),
            "data": None
        }
    except Exception as e:
        logger.error(f"[delete_todo] 删除失败: {str(e)}\n{traceback.format_exc()}")
        return {
            "success": False,
            "code": 500,
            "message": f"删除失败: {str(e)}",
            "data": None
        }


# ============================================================================
# 四个专用查询接口实现
# ============================================================================

def query_todo_by_meeting_note(body: QueryTodoByMeetingNoteRequest, request: Request):
    """
    按会议纪要查询待办列表
    
    Args:
        body: 查询请求体
        request: FastAPI请求对象
    
    Returns:
        dict: 查询结果
    """
    # 记录入参日志
    try:
        logger.info(f"[query_todo_by_meeting_note] 入参: {body.model_dump() if hasattr(body, 'model_dump') else body.dict()}")
    except Exception:
        logger.info(f"[query_todo_by_meeting_note] 入参: {str(body)}")
    
    try:
        # 获取当前用户
        current_user_code = _get_user_code_from_context(request)
        
        conn = _get_conn()
        with conn:
            with conn.cursor() as cur:
                # 验证会议纪要存在
                cur.execute(
                    """
                    SELECT id, deleted_at, title FROM meeting_notes WHERE id = %s
                    """,
                    (body.meetingNoteId,)
                )
                meeting_row = cur.fetchone()
                if not meeting_row:
                    return {
                        "success": False,
                        "code": 404,
                        "message": "会议纪要不存在",
                        "data": None
                    }
                
                # 构建查询条件
                conditions = ["ti.meeting_note_id = %s"]
                params = [body.meetingNoteId]
                
                # 状态筛选
                if body.status:
                    conditions.append("ti.todo_status = %s")
                    params.append(body.status.value)
                
                # 优先级筛选
                if body.priority:
                    conditions.append("ti.todo_priority = %s")
                    params.append(body.priority.value)
                
                # 紧急程度筛选
                if body.urgencyLevel:
                    conditions.append("ti.urgency_level = %s")
                    params.append(body.urgencyLevel.value)
                
                # 关键词搜索
                if body.keyword:
                    conditions.append("(ti.title ILIKE %s OR ti.todo_content ILIKE %s)")
                    kw = f"%{body.keyword}%"
                    params.extend([kw, kw])
                
                where_clause = "WHERE " + " AND ".join(conditions)
                
                # 排序
                sort_by = body.sortBy if body.sortBy in ["created_at", "deadline_at", "updated_at"] else "created_at"
                sort_order = "ASC" if (body.sortOrder or "").lower() == "asc" else "DESC"
                
                # 查询总数
                count_sql = f"""
                    SELECT COUNT(*) AS cnt
                    FROM todo_items ti
                    {where_clause}
                """
                cur.execute(count_sql, params)
                total = cur.fetchone()["cnt"]
                
                # 查询列表（包含会议纪要标题）
                offset = (body.page - 1) * body.pageSize
                list_sql = f"""
                    SELECT
                        ti.*,
                        (SELECT h1.progress_percentage FROM todo_item_handlers h1 WHERE h1.todo_item_id = ti.id AND h1.handler_id = ti.handler_id LIMIT 1) AS progress_percentage,
                        (SELECT h1.handle_comment FROM todo_item_handlers h1 WHERE h1.todo_item_id = ti.id AND h1.handler_id = ti.handler_id LIMIT 1) AS handle_comment,
                        mn.title AS meeting_note_title,
                        COALESCE(
                            (
                                SELECT json_agg(
                                    json_build_object(
                                        'handlerId', th.handler_id,
                                        'handleComment', th.handle_comment
                                    )
                                )
                                FROM todo_item_handlers th
                                WHERE th.todo_item_id = ti.id
                            )::json,
                            '[]'::json
                        ) AS handlers,
                        COALESCE(
                            (
                                SELECT json_agg(
                                    json_build_object(
                                        'fileName', ta.file_name,
                                        'storagePath', ta.storage_path
                                    )
                                )
                                FROM todo_item_attachments ta
                                WHERE ta.todo_item_id = ti.id
                            )::json,
                            '[]'::json
                        ) AS attachments
                    FROM todo_items ti
                    LEFT JOIN meeting_notes mn ON ti.meeting_note_id = mn.id
                    {where_clause}
                    ORDER BY ti.{sort_by} {sort_order}
                    LIMIT %s OFFSET %s
                """
                cur.execute(list_sql, params + [body.pageSize, offset])
                rows = cur.fetchall()
                
                items = [_row_to_todo_item(r) for r in rows]
                
                return {
                    "success": True,
                    "code": 200,
                    "message": "查询成功",
                    "data": {
                        "items": items,
                        "pagination": {
                            "page": body.page,
                            "pageSize": body.pageSize,
                            "total": total,
                            "totalPages": (total + body.pageSize - 1) // body.pageSize if body.pageSize else 0
                        }
                    }
                }
        
    except ValueError as e:
        logger.error(f"[query_todo_by_meeting_note] 参数错误: {str(e)}\n{traceback.format_exc()}")
        return {
            "success": False,
            "code": 401,
            "message": str(e),
            "data": None
        }
    except Exception as e:
        logger.error(f"[query_todo_by_meeting_note] 查询失败: {str(e)}\n{traceback.format_exc()}")
        return {
            "success": False,
            "code": 500,
            "message": f"查询失败: {str(e)}",
            "data": None
        }


def query_todo_by_handler(body: QueryTodoByHandlerRequest, request: Request):
    """
    按处理人查询待办列表（仅返回Pending和Rejected状态）
    
    Args:
        body: 查询请求体
        request: FastAPI请求对象
    
    Returns:
        dict: 查询结果
    """
    # 记录入参日志
    try:
        logger.info(f"[query_todo_by_handler] 入参: {body.model_dump() if hasattr(body, 'model_dump') else body.dict()}")
    except Exception:
        logger.info(f"[query_todo_by_handler] 入参: {str(body)}")
    
    try:
        # 获取当前用户
        current_user_code = _get_user_code_from_context(request)
        
        # 确定查询的处理人（默认当前用户）
        handler_id = body.handlerId if body.handlerId else current_user_code
        
        # 如果查询他人，需要验证权限（这里简化实现，实际可能需要检查是否是管理员）
        # TODO: 实现管理员权限检查
        
        conn = _get_conn()
        with conn:
            with conn.cursor() as cur:
                # 构建查询条件
                conditions = [
                    "(ti.handler_id = %s OR EXISTS (SELECT 1 FROM todo_item_handlers th WHERE th.todo_item_id = ti.id AND th.handler_id = %s))",
                    "ti.todo_status IN (%s, %s)"  # 仅待接收和不通过
                ]
                params = [handler_id, handler_id, TodoStatus.PENDING_RECEIVE.value, TodoStatus.NOT_PASSED.value]
                
                # 优先级筛选
                if body.priority:
                    conditions.append("ti.todo_priority = %s")
                    params.append(body.priority.value)
                
                # 紧急程度筛选
                if body.urgencyLevel:
                    conditions.append("ti.urgency_level = %s")
                    params.append(body.urgencyLevel.value)
                
                # 关键词搜索
                if body.keyword:
                    conditions.append("(ti.title ILIKE %s OR ti.todo_content ILIKE %s)")
                    kw = f"%{body.keyword}%"
                    params.extend([kw, kw])
                
                # 截止时间范围
                if body.deadlineStart:
                    conditions.append("ti.deadline_at >= %s")
                    params.append(body.deadlineStart)
                if body.deadlineEnd:
                    conditions.append("ti.deadline_at <= %s")
                    params.append(body.deadlineEnd)
                
                where_clause = "WHERE " + " AND ".join(conditions)
                
                # 排序
                sort_by = body.sortBy if body.sortBy in ["created_at", "deadline_at", "updated_at"] else "deadline_at"
                sort_order = "ASC" if (body.sortOrder or "").lower() == "asc" else "DESC"
                
                # 查询总数
                count_sql = f"""
                    SELECT COUNT(*) AS cnt
                    FROM todo_items ti
                    {where_clause}
                """
                cur.execute(count_sql, params)
                total = cur.fetchone()["cnt"]
                
                # 查询列表
                offset = (body.page - 1) * body.pageSize
                list_sql = f"""
                    SELECT
                        ti.*,
                        (SELECT h1.progress_percentage FROM todo_item_handlers h1 WHERE h1.todo_item_id = ti.id AND h1.handler_id = ti.handler_id LIMIT 1) AS progress_percentage,
                        (SELECT h1.handle_comment FROM todo_item_handlers h1 WHERE h1.todo_item_id = ti.id AND h1.handler_id = ti.handler_id LIMIT 1) AS handle_comment,
                        mn.title AS meeting_note_title,
                        COALESCE(
                            (
                                SELECT json_agg(
                                    json_build_object(
                                        'handlerId', th.handler_id,
                                        'handleComment', th.handle_comment
                                    )
                                )
                                FROM todo_item_handlers th
                                WHERE th.todo_item_id = ti.id
                            )::json,
                            '[]'::json
                        ) AS handlers,
                        COALESCE(
                            (
                                SELECT json_agg(
                                    json_build_object(
                                        'fileName', ta.file_name,
                                        'storagePath', ta.storage_path
                                    )
                                )
                                FROM todo_item_attachments ta
                                WHERE ta.todo_item_id = ti.id
                            )::json,
                            '[]'::json
                        ) AS attachments
                    FROM todo_items ti
                    LEFT JOIN meeting_notes mn ON ti.meeting_note_id = mn.id
                    {where_clause}
                    ORDER BY ti.{sort_by} {sort_order}
                    LIMIT %s OFFSET %s
                """
                cur.execute(list_sql, params + [body.pageSize, offset])
                rows = cur.fetchall()
                
                items = [_row_to_todo_item(r) for r in rows]
                
                return {
                    "success": True,
                    "code": 200,
                    "message": "查询成功",
                    "data": {
                        "items": items,
                        "pagination": {
                            "page": body.page,
                            "pageSize": body.pageSize,
                            "total": total,
                            "totalPages": (total + body.pageSize - 1) // body.pageSize if body.pageSize else 0
                        }
                    }
                }
        
    except ValueError as e:
        logger.error(f"[query_todo_by_handler] 参数错误: {str(e)}\n{traceback.format_exc()}")
        return {
            "success": False,
            "code": 401,
            "message": str(e),
            "data": None
        }
    except Exception as e:
        logger.error(f"[query_todo_by_handler] 查询失败: {str(e)}\n{traceback.format_exc()}")
        return {
            "success": False,
            "code": 500,
            "message": f"查询失败: {str(e)}",
            "data": None
        }


def query_todo_by_promoter(body: QueryTodoByPromoterRequest, request: Request):
    """
    按发起人查询待办列表（返回所有状态）
    
    Args:
        body: 查询请求体
        request: FastAPI请求对象
    
    Returns:
        dict: 查询结果
    """
    # 记录入参日志
    try:
        logger.info(f"[query_todo_by_promoter] 入参: {body.model_dump() if hasattr(body, 'model_dump') else body.dict()}")
    except Exception:
        logger.info(f"[query_todo_by_promoter] 入参: {str(body)}")
    
    try:
        # 获取当前用户
        current_user_code = _get_user_code_from_context(request)
        
        # 确定查询的发起人（默认当前用户）
        promoter_id = body.promoterId if body.promoterId else current_user_code
        
        # 如果查询他人，需要验证权限（这里简化实现）
        # TODO: 实现管理员权限检查
        
        conn = _get_conn()
        with conn:
            with conn.cursor() as cur:
                # 构建查询条件
                conditions = ["ti.promoter = %s"]
                params = [promoter_id]
                
                # 状态筛选
                if body.status:
                    conditions.append("ti.todo_status = %s")
                    params.append(body.status.value)
                
                # 优先级筛选
                if body.priority:
                    conditions.append("ti.todo_priority = %s")
                    params.append(body.priority.value)
                
                # 紧急程度筛选
                if body.urgencyLevel:
                    conditions.append("ti.urgency_level = %s")
                    params.append(body.urgencyLevel.value)
                
                # 关键词搜索
                if body.keyword:
                    conditions.append("(ti.title ILIKE %s OR ti.todo_content ILIKE %s)")
                    kw = f"%{body.keyword}%"
                    params.extend([kw, kw])
                
                # 处理人筛选
                if body.handlerIds:
                    handler_ids = [hid for hid in body.handlerIds if hid]
                    if handler_ids:
                        placeholders = ','.join(['%s'] * len(handler_ids))
                        conditions.append(f"(ti.handler_id IN ({placeholders}) OR EXISTS (SELECT 1 FROM todo_item_handlers th WHERE th.todo_item_id = ti.id AND th.handler_id IN ({placeholders})))")
                        params.extend(handler_ids)
                        params.extend(handler_ids)
                
                # 截止时间范围
                if body.deadlineStart:
                    conditions.append("ti.deadline_at >= %s")
                    params.append(body.deadlineStart)
                if body.deadlineEnd:
                    conditions.append("ti.deadline_at <= %s")
                    params.append(body.deadlineEnd)
                
                where_clause = "WHERE " + " AND ".join(conditions)
                
                # 排序
                sort_by = body.sortBy if body.sortBy in ["created_at", "deadline_at", "updated_at"] else "created_at"
                sort_order = "ASC" if (body.sortOrder or "").lower() == "asc" else "DESC"
                
                # 查询总数
                count_sql = f"""
                    SELECT COUNT(*) AS cnt
                    FROM todo_items ti
                    {where_clause}
                """
                cur.execute(count_sql, params)
                total = cur.fetchone()["cnt"]
                
                # 查询列表
                offset = (body.page - 1) * body.pageSize
                list_sql = f"""
                    SELECT
                        ti.*,
                        (SELECT h1.progress_percentage FROM todo_item_handlers h1 WHERE h1.todo_item_id = ti.id AND h1.handler_id = ti.handler_id LIMIT 1) AS progress_percentage,
                        (SELECT h1.handle_comment FROM todo_item_handlers h1 WHERE h1.todo_item_id = ti.id AND h1.handler_id = ti.handler_id LIMIT 1) AS handle_comment,
                        mn.title AS meeting_note_title,
                        COALESCE(
                            (
                                SELECT json_agg(
                                    json_build_object(
                                        'handlerId', th.handler_id,
                                        'handleComment', th.handle_comment
                                    )
                                )
                                FROM todo_item_handlers th
                                WHERE th.todo_item_id = ti.id
                            )::json,
                            '[]'::json
                        ) AS handlers,
                        COALESCE(
                            (
                                SELECT json_agg(
                                    json_build_object(
                                        'fileName', ta.file_name,
                                        'storagePath', ta.storage_path
                                    )
                                )
                                FROM todo_item_attachments ta
                                WHERE ta.todo_item_id = ti.id
                            )::json,
                            '[]'::json
                        ) AS attachments
                    FROM todo_items ti
                    LEFT JOIN meeting_notes mn ON ti.meeting_note_id = mn.id
                    {where_clause}
                    ORDER BY ti.{sort_by} {sort_order}
                    LIMIT %s OFFSET %s
                """
                cur.execute(list_sql, params + [body.pageSize, offset])
                rows = cur.fetchall()
                
                items = [_row_to_todo_item(r) for r in rows]
                
                return {
                    "success": True,
                    "code": 200,
                    "message": "查询成功",
                    "data": {
                        "items": items,
                        "pagination": {
                            "page": body.page,
                            "pageSize": body.pageSize,
                            "total": total,
                            "totalPages": (total + body.pageSize - 1) // body.pageSize if body.pageSize else 0
                        }
                    }
                }
        
    except ValueError as e:
        logger.error(f"[query_todo_by_promoter] 参数错误: {str(e)}\n{traceback.format_exc()}")
        return {
            "success": False,
            "code": 401,
            "message": str(e),
            "data": None
        }
    except Exception as e:
        logger.error(f"[query_todo_by_promoter] 查询失败: {str(e)}\n{traceback.format_exc()}")
        return {
            "success": False,
            "code": 500,
            "message": f"查询失败: {str(e)}",
            "data": None
        }


def query_todo_by_approver(body: QueryTodoByApproverRequest, request: Request):
    """
    按审批人查询待办列表（仅返回Approving状态）
    
    Args:
        body: 查询请求体
        request: FastAPI请求对象
    
    Returns:
        dict: 查询结果
    """
    # 记录入参日志
    try:
        logger.info(f"[query_todo_by_approver] 入参: {body.model_dump() if hasattr(body, 'model_dump') else body.dict()}")
    except Exception:
        logger.info(f"[query_todo_by_approver] 入参: {str(body)}")
    
    try:
        # 获取当前用户（审批人即发起人）
        current_user_code = _get_user_code_from_context(request)
        
        conn = _get_conn()
        with conn:
            with conn.cursor() as cur:
                # 构建查询条件
                conditions = [
                    "ti.promoter = %s",           # 发起人是当前用户
                    "ti.todo_status = %s"         # 仅待审核状态
                ]
                params = [current_user_code, TodoStatus.PENDING_REVIEW.value]
                
                # 优先级筛选
                if body.priority:
                    conditions.append("ti.todo_priority = %s")
                    params.append(body.priority.value)
                
                # 紧急程度筛选
                if body.urgencyLevel:
                    conditions.append("ti.urgency_level = %s")
                    params.append(body.urgencyLevel.value)
                
                # 关键词搜索
                if body.keyword:
                    conditions.append("(ti.title ILIKE %s OR ti.todo_content ILIKE %s)")
                    kw = f"%{body.keyword}%"
                    params.extend([kw, kw])
                
                # 截止时间范围
                if body.deadlineStart:
                    conditions.append("ti.deadline_at >= %s")
                    params.append(body.deadlineStart)
                if body.deadlineEnd:
                    conditions.append("ti.deadline_at <= %s")
                    params.append(body.deadlineEnd)
                
                where_clause = "WHERE " + " AND ".join(conditions)
                
                # 排序（默认按更新时间倒序，最新提交的在前）
                sort_by = body.sortBy if body.sortBy in ["created_at", "deadline_at", "updated_at"] else "updated_at"
                sort_order = "ASC" if (body.sortOrder or "").lower() == "asc" else "DESC"
                
                # 查询总数
                count_sql = f"""
                    SELECT COUNT(*) AS cnt
                    FROM todo_items ti
                    {where_clause}
                """
                cur.execute(count_sql, params)
                total = cur.fetchone()["cnt"]
                
                # 查询列表
                offset = (body.page - 1) * body.pageSize
                list_sql = f"""
                    SELECT
                        ti.*,
                        (SELECT h1.progress_percentage FROM todo_item_handlers h1 WHERE h1.todo_item_id = ti.id AND h1.handler_id = ti.handler_id LIMIT 1) AS progress_percentage,
                        (SELECT h1.handle_comment FROM todo_item_handlers h1 WHERE h1.todo_item_id = ti.id AND h1.handler_id = ti.handler_id LIMIT 1) AS handle_comment,
                        mn.title AS meeting_note_title,
                        COALESCE(
                            (
                                SELECT json_agg(
                                    json_build_object(
                                        'handlerId', th.handler_id,
                                        'handleComment', th.handle_comment
                                    )
                                )
                                FROM todo_item_handlers th
                                WHERE th.todo_item_id = ti.id
                            )::json,
                            '[]'::json
                        ) AS handlers,
                        COALESCE(
                            (
                                SELECT json_agg(
                                    json_build_object(
                                        'fileName', ta.file_name,
                                        'storagePath', ta.storage_path
                                    )
                                )
                                FROM todo_item_attachments ta
                                WHERE ta.todo_item_id = ti.id
                            )::json,
                            '[]'::json
                        ) AS attachments
                    FROM todo_items ti
                    LEFT JOIN meeting_notes mn ON ti.meeting_note_id = mn.id
                    {where_clause}
                    ORDER BY ti.{sort_by} {sort_order}
                    LIMIT %s OFFSET %s
                """
                cur.execute(list_sql, params + [body.pageSize, offset])
                rows = cur.fetchall()
                
                items = [_row_to_todo_item(r) for r in rows]
                
                return {
                    "success": True,
                    "code": 200,
                    "message": "查询成功",
                    "data": {
                        "items": items,
                        "pagination": {
                            "page": body.page,
                            "pageSize": body.pageSize,
                            "total": total,
                            "totalPages": (total + body.pageSize - 1) // body.pageSize if body.pageSize else 0
                        }
                    }
                }
        
    except ValueError as e:
        logger.error(f"[query_todo_by_approver] 参数错误: {str(e)}\n{traceback.format_exc()}")
        return {
            "success": False,
            "code": 401,
            "message": str(e),
            "data": None
        }
    except Exception as e:
        logger.error(f"[query_todo_by_approver] 查询失败: {str(e)}\n{traceback.format_exc()}")
        return {
            "success": False,
            "code": 500,
            "message": f"查询失败: {str(e)}",
            "data": None
        }
