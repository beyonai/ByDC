"""待办 API handlers - 9 个接口，逻辑对齐 todo.py."""

from datetime import datetime, timezone
from typing import Any

from fastapi import Request
from pydantic import BaseModel
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from datacloud_mock.crm_demo.db import get_session
from datacloud_mock.crm_demo.db.models import PoOrganization, PoUsers, PoUsersOrganization, TodoItems, TodoItemHandlers
from datacloud_mock.crm_demo.notice import send_notice

# --- 状态常量（与 todo.py 一致）---
PENDING_RECEIVE = "PendingReceive"
RETURNED = "Returned"
RECEIVED = "Received"
PENDING_REVIEW = "PendingReview"
NOT_PASSED = "NotPassed"
CLOSED = "Closed"


# --- 工具函数 ---


def _format_datetime(dt: datetime | None) -> str | None:
    """格式化为 YYYY-MM-DD HH:mm:ss."""
    if dt is None:
        return None
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _get_current_user(request: Request | None) -> str:
    """从 Header X-User-Code 获取当前用户，缺省 system."""
    if request is None:
        return "system"
    return request.headers.get("X-User-Code", "system")


def _parse_datetime(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace(" ", "T"))


async def _get_org_id_by_user_code(session: AsyncSession, user_code: str) -> int:
    """根据 user_code 或 user_number 查 org_id，无则返回 0."""
    u = await session.execute(
        select(PoUsers.user_id).where(
            (PoUsers.user_code == user_code) | (PoUsers.user_number == user_code)
        ).limit(1)
    )
    uid = u.scalar_one_or_none()
    if not uid:
        return 0
    o = await session.execute(
        select(PoUsersOrganization.org_id)
        .where(PoUsersOrganization.user_id == uid)
        .limit(1)
    )
    org_row = o.scalar_one_or_none()
    return int(org_row) if org_row else 0


async def _get_sub_org_ids(session: AsyncSession, org_id: int) -> list[int]:
    """递归查询组织及所有下级组织 ID（含自身）."""
    result: list[int] = [org_id]
    to_process = [org_id]
    seen = {org_id}
    while to_process:
        children = await session.execute(
            select(PoOrganization.org_id).where(
                PoOrganization.parent_org_id.in_(to_process),
                ~PoOrganization.org_id.in_(seen),
            )
        )
        next_ids = list(children.scalars().all())
        to_process = []
        for oid in next_ids:
            if oid not in seen:
                result.append(oid)
                seen.add(oid)
                to_process.append(oid)
    return result


# --- Request schemas ---


class TodoCreateRequest(BaseModel):
    title: str
    deadlineAt: str | None = None
    handlerIds: list[str] | None = None
    priority: str | None = None
    urgencyLevel: str | None = None
    content: str | None = None
    meetingNoteId: str | None = None
    promoter: str | None = None
    remark: str | None = None


class TodoListRequest(BaseModel):
    queryType: str | None = None
    priority: str | None = None
    urgencyLevel: str | None = None
    orgId: str | None = None
    promoterOrgId: str | None = None
    handlerOrgId: str | None = None
    meetingNoteIds: list[str] | None = None
    statusList: list[str] | None = None
    page: int | None = 1
    keyword: str | None = None
    deadlineEnd: str | None = None
    status: str | None = None
    promoter: str | None = None
    deadlineStart: str | None = None
    pageSize: int | None = 20
    includeSubOrgs: bool | None = False
    handlerIds: list[str] | None = None
    sortBy: str | None = "created_at"
    sortOrder: str | None = "desc"


class TodoAcceptRequest(BaseModel):
    todoId: str


class TodoReturnRequest(BaseModel):
    todoId: str
    returnReason: str


class TodoProcessRequest(BaseModel):
    todoIds: list[str]
    handleComment: str | None = None
    progress: int | None = None


class TodoDeleteRequest(BaseModel):
    todoIds: list[str]


class TodoUrgeRequest(BaseModel):
    todoIds: list[str]
    followUpContent: str | None = None


class TodoUpdateRequest(BaseModel):
    todoId: str
    planFinishTime: str | None = None
    handlerIds: list[str] | None = None
    priority: str | None = None
    urgencyLevel: str | None = None
    content: str | None = None


class TodoApproveRequest(BaseModel):
    todoIds: list[str]
    approvalStatus: str
    approvalComment: str | None = None


def _todo_to_list_item(
    row: TodoItems,
    progress: int | None = None,
    handle_comment: str | None = None,
    handlers_data: list[dict] | None = None,
) -> dict[str, Any]:
    """将 DB 行转为列表项格式."""
    return {
        "todoId": str(row.id),
        "deadlineAt": _format_datetime(row.deadline_at),
        "approvalComment": row.approval_comment,
        "priority": row.todo_priority,
        "urgencyLevel": row.urgency_level,
        "content": row.todo_content,
        "progress": progress or 0,
        "status": row.todo_status,
        "completedAt": _format_datetime(row.completed_at),
        "meetingNoteId": str(row.meeting_note_id) if row.meeting_note_id else None,
        "title": row.title,
        "approvedAt": _format_datetime(row.approved_at),
        "createdAt": _format_datetime(row.created_at),
        "handleContent": handle_comment,
        "handlers": handlers_data or [],
        "returnReason": row.return_reason if row.todo_status == RETURNED else None,
        "promoter": row.promoter,
    }


# --- Handler implementations (called by router) ---


def _next_id() -> int:
    """生成唯一 ID（mock 用，替代 snowflake）."""
    import time
    return int(time.time() * 1_000_000)


async def create_todo(
    body: TodoCreateRequest,
    session: AsyncSession,
    request: Request | None = None,
) -> dict:
    """创建待办，逻辑对齐 todo.py create_todo."""
    promoter = body.promoter or _get_current_user(request)
    now = datetime.now(timezone.utc)

    # 校验 deadlineAt
    if body.deadlineAt:
        try:
            deadline_ts = datetime.strptime(body.deadlineAt, "%Y-%m-%d %H:%M:%S")
            if deadline_ts.tzinfo is None:
                deadline_ts = deadline_ts.replace(tzinfo=timezone.utc)
            if deadline_ts < now:
                return {
                    "todoId": "",
                    "errorMsg": "截止时间不能小于当前时间",
                    "status": "",
                    "title": body.title,
                    "createdAt": _format_datetime(now),
                }
        except ValueError:
            return {
                "todoId": "",
                "errorMsg": "截止时间格式错误，请使用 YYYY-MM-DD HH:mm:ss 格式",
                "status": "",
                "title": body.title,
                "createdAt": _format_datetime(now),
            }

    org_id = await _get_org_id_by_user_code(session, promoter)
    priority_val = body.priority or "Normal"
    urgency_val = body.urgencyLevel or "Low"
    meeting_note_id = int(body.meetingNoteId) if body.meetingNoteId else None
    content = f"{body.title}\n\n{body.content}" if body.content else body.title

    todo = TodoItems(
        title=body.title,
        todo_content=content,
        deadline_at=_parse_datetime(body.deadlineAt),
        todo_priority=priority_val,
        todo_status=PENDING_RECEIVE,
        created_by=promoter,
        promoter=promoter,
        org_id=org_id,
        handler_id=body.handlerIds[0] if body.handlerIds else None,
        urgency_level=urgency_val,
        remark=body.remark,
        meeting_note_id=meeting_note_id,
    )
    session.add(todo)
    await session.flush()

    # 写入 todo_item_handlers
    handler_ids = body.handlerIds or []
    for h_id in handler_ids:
        try:
            h_org_id = await _get_org_id_by_user_code(session, h_id)
        except Exception:
            h_org_id = org_id
        th = TodoItemHandlers(
            id=_next_id(),
            todo_item_id=todo.id,
            org_id=h_org_id,
            handler_id=h_id,
        )
        session.add(th)

    # 通知处理人（跳过发起人自己）
    notices = []
    for hid in handler_ids:
        if hid != promoter:
            notices.append({
                "content": f"待办创建：{body.title}",
                "priority": 2,
                "senderId": promoter,
                "targetId": hid,
                "title": "新的待办任务",
            })
    if notices:
        await send_notice(notices, request)

    return {
        "todoId": str(todo.id),
        "errorMsg": None,
        "status": PENDING_RECEIVE,
        "title": todo.title,
        "createdAt": _format_datetime(todo.created_at or now),
    }


async def query_todo_list(
    body: TodoListRequest,
    session: AsyncSession,
    request: Request | None = None,
) -> list:
    """查询待办列表，逻辑对齐 todo.py query_todo_list."""
    page = body.page or 1
    page_size = body.pageSize or 20
    sort_by = body.sortBy if body.sortBy in ("created_at", "deadline_at", "updated_at") else "created_at"
    sort_desc = (body.sortOrder or "desc").lower() == "desc"

    q = select(TodoItems)
    conditions = []

    # orgId + includeSubOrgs
    if body.orgId:
        try:
            org_id = int(body.orgId)
            org_ids = await _get_sub_org_ids(session, org_id) if body.includeSubOrgs else [org_id]
            if org_ids:
                # ti.org_id 或 todo_item_handlers.org_id
                sub_handlers = select(TodoItemHandlers.todo_item_id).where(
                    TodoItemHandlers.org_id.in_(org_ids)
                )
                conditions.append(
                    (TodoItems.org_id.in_(org_ids)
                     | TodoItems.id.in_(sub_handlers))
                )
        except ValueError:
            pass

    if body.promoterOrgId:
        try:
            oid = int(body.promoterOrgId)
            org_ids = await _get_sub_org_ids(session, oid) if body.includeSubOrgs else [oid]
            if org_ids:
                conditions.append(TodoItems.org_id.in_(org_ids))
        except ValueError:
            pass

    if body.handlerOrgId:
        try:
            h_oid = int(body.handlerOrgId)
            h_org_ids = await _get_sub_org_ids(session, h_oid) if body.includeSubOrgs else [h_oid]
            sub = select(TodoItemHandlers.todo_item_id).where(
                TodoItemHandlers.org_id.in_(h_org_ids)
            )
            conditions.append(TodoItems.id.in_(sub))
        except ValueError:
            pass

    if body.handlerIds:
        hids = [h for h in (body.handlerIds or []) if h]
        if hids:
            sub = select(TodoItemHandlers.todo_item_id).where(
                TodoItemHandlers.handler_id.in_(hids)
            )
            conditions.append(
                (TodoItems.handler_id.in_(hids) | TodoItems.id.in_(sub))
            )

    if body.promoter:
        conditions.append(TodoItems.promoter == body.promoter)

    if body.meetingNoteIds:
        mnids = [int(x) for x in body.meetingNoteIds if x]
        if mnids:
            conditions.append(TodoItems.meeting_note_id.in_(mnids))

    if body.statusList:
        conditions.append(TodoItems.todo_status.in_(body.statusList))
    elif body.status:
        conditions.append(TodoItems.todo_status == body.status)

    if body.priority:
        conditions.append(TodoItems.todo_priority == body.priority)
    if body.urgencyLevel:
        conditions.append(TodoItems.urgency_level == body.urgencyLevel)
    if body.keyword:
        kw = f"%{body.keyword}%"
        conditions.append(
            or_(
                TodoItems.title.ilike(kw),
                func.coalesce(TodoItems.todo_content, "").ilike(kw),
            )
        )
    if body.deadlineStart:
        conditions.append(TodoItems.deadline_at >= _parse_datetime(body.deadlineStart))
    if body.deadlineEnd:
        conditions.append(TodoItems.deadline_at <= _parse_datetime(body.deadlineEnd))

    for c in conditions:
        q = q.where(c)

    # count（在 order/limit 之前）
    from sqlalchemy import func as fn
    count_q = select(fn.count(TodoItems.id)).select_from(TodoItems)
    for c in conditions:
        count_q = count_q.where(c)
    total = (await session.execute(count_q)).scalar() or 0

    # order
    order_col = getattr(TodoItems, sort_by, TodoItems.created_at)
    q = q.order_by(order_col.desc() if sort_desc else order_col.asc())
    q = q.offset((page - 1) * page_size).limit(page_size)
    result = await session.execute(q)
    rows = result.scalars().all()

    # 获取 handlers 和 progress
    todo_ids = [r.id for r in rows]
    handlers_q = select(TodoItemHandlers).where(
        TodoItemHandlers.todo_item_id.in_(todo_ids)
    )
    handlers_result = await session.execute(handlers_q)
    handlers_rows = handlers_result.scalars().all()
    handlers_by_todo: dict[int, list] = {}
    for h in handlers_rows:
        handlers_by_todo.setdefault(h.todo_item_id, []).append(h)

    items = []
    for r in rows:
        handlers_list = handlers_by_todo.get(r.id, [])
        progress = None
        handle_comment = None
        for h in handlers_list:
            if h.handler_id == r.handler_id:
                progress = h.progress_percentage
                handle_comment = h.handle_comment
                break
        handlers_data = [
            {"handlerId": h.handler_id, "handleComment": h.handle_comment}
            for h in handlers_list
        ]
        items.append(_todo_to_list_item(r, progress, handle_comment, handlers_data))

    # ontology 返回数组
    return items


async def accept_todo(
    body: TodoAcceptRequest,
    session: AsyncSession,
    request: Request | None = None,
) -> dict:
    """接收待办，逻辑对齐 todo.py receive_todo."""
    current_user = _get_current_user(request)
    try:
        tid = int(body.todoId)
    except ValueError:
        return {"todoId": body.todoId, "status": "error"}
    row = (await session.execute(select(TodoItems).where(TodoItems.id == tid))).scalar_one_or_none()
    if not row:
        return {"todoId": body.todoId, "status": "error", "errorMsg": "待办不存在"}
    if row.todo_status != PENDING_RECEIVE:
        return {"todoId": body.todoId, "status": "error", "errorMsg": "仅待接收状态的待办可接收"}
    # 权限：主处理人或协同处理人
    is_handler = row.handler_id == current_user
    if not is_handler:
        h = await session.execute(
            select(1).where(
                TodoItemHandlers.todo_item_id == tid,
                TodoItemHandlers.handler_id == current_user,
            )
        )
        is_handler = h.scalar_one_or_none() is not None
    if not is_handler:
        return {"todoId": body.todoId, "status": "error", "errorMsg": "仅处理人可接收该待办"}
    now = datetime.now(timezone.utc)
    await session.execute(
        update(TodoItems)
        .where(TodoItems.id == tid)
        .values(todo_status=RECEIVED, handler_id=current_user, updated_at=now)
    )
    return {"todoId": body.todoId, "status": RECEIVED}


async def return_todo(
    body: TodoReturnRequest,
    session: AsyncSession,
    request: Request | None = None,
) -> dict:
    """退回待办，逻辑对齐 todo.py return_todo."""
    current_user = _get_current_user(request)
    try:
        tid = int(body.todoId)
    except ValueError:
        return {"todoId": body.todoId, "status": "error"}
    row = (await session.execute(select(TodoItems).where(TodoItems.id == tid))).scalar_one_or_none()
    if not row:
        return {"todoId": body.todoId, "status": "error", "errorMsg": "待办不存在"}
    if row.todo_status != PENDING_RECEIVE:
        return {"todoId": body.todoId, "status": "error", "errorMsg": "仅待接收状态的待办可退回"}
    is_handler = row.handler_id == current_user
    if not is_handler:
        h = await session.execute(
            select(1).where(
                TodoItemHandlers.todo_item_id == tid,
                TodoItemHandlers.handler_id == current_user,
            )
        )
        is_handler = h.scalar_one_or_none() is not None
    if not is_handler:
        return {"todoId": body.todoId, "status": "error", "errorMsg": "仅处理人可退回该待办"}
    now = datetime.now(timezone.utc)
    await session.execute(
        update(TodoItems)
        .where(TodoItems.id == tid)
        .values(
            todo_status=RETURNED,
            return_reason=body.returnReason.strip(),
            returned_at=now,
            updated_at=now,
        )
    )
    return {"todoId": body.todoId, "status": RETURNED}


async def process_todos(
    body: TodoProcessRequest,
    session: AsyncSession,
    request: Request | None = None,
) -> dict:
    """批量处理待办，逻辑对齐 todo.py handle_todo."""
    if not body.todoIds:
        return {"todoIds": [], "handledIds": [], "skipped": []}
    current_user = _get_current_user(request)
    progress_val = min(100, body.progress or 0)
    now = datetime.now(timezone.utc)
    handled_ids = []
    skipped = []
    notices = []
    for tid_str in body.todoIds:
        try:
            tid = int(tid_str)
        except ValueError:
            skipped.append({"todoId": tid_str, "reason": "ID格式错误"})
            continue
        row = (await session.execute(select(TodoItems).where(TodoItems.id == tid))).scalar_one_or_none()
        if not row:
            skipped.append({"todoId": tid_str, "reason": "待办不存在"})
            continue
        is_handler = row.handler_id == current_user
        if not is_handler:
            h = await session.execute(
                select(1).where(
                    TodoItemHandlers.todo_item_id == tid,
                    TodoItemHandlers.handler_id == current_user,
                )
            )
            is_handler = h.scalar_one_or_none() is not None
        if not is_handler:
            skipped.append({"todoId": tid_str, "reason": "无权限处理"})
            continue
        if row.todo_status not in (PENDING_RECEIVE, NOT_PASSED, RECEIVED):
            skipped.append({"todoId": tid_str, "reason": "状态不可处理"})
            continue
        await session.execute(
            update(TodoItemHandlers)
            .where(
                TodoItemHandlers.todo_item_id == tid,
                TodoItemHandlers.handler_id == current_user,
            )
            .values(
                progress_percentage=progress_val,
                handle_comment=body.handleComment,
                handled_at=now,
            )
        )
        new_status = (
            CLOSED if current_user == row.promoter
            else PENDING_REVIEW
        ) if progress_val >= 100 else row.todo_status
        await session.execute(
            update(TodoItems)
            .where(TodoItems.id == tid)
            .values(todo_status=new_status, handler_id=current_user, updated_at=now)
        )
        # 进度达到 100% 且操作人不是发起人时，通知发起人
        if progress_val >= 100 and current_user != row.promoter:
            notices.append({
                "content": f"待办处理：{row.title} 进度已100%，已提交审核",
                "priority": 2,
                "senderId": current_user,
                "targetId": row.promoter,
                "title": "待办处理进度",
            })
        handled_ids.append(tid_str)
    if notices:
        await send_notice(notices, request)
    return {"todoIds": handled_ids, "handledIds": handled_ids, "skipped": skipped}


async def delete_todos(
    body: TodoDeleteRequest,
    session: AsyncSession,
    request: Request | None = None,
) -> dict:
    """批量删除待办，逻辑对齐 todo.py delete_todo."""
    if not body.todoIds:
        return {"deletedIds": [], "skipped": []}
    current_user = _get_current_user(request)
    deleted_ids = []
    skipped = []
    for tid_str in body.todoIds:
        try:
            tid = int(tid_str)
        except ValueError:
            skipped.append({"todoId": tid_str, "reason": "ID格式错误"})
            continue
        row = (await session.execute(select(TodoItems).where(TodoItems.id == tid))).scalar_one_or_none()
        if not row:
            skipped.append({"todoId": tid_str, "reason": "待办不存在"})
            continue
        if row.promoter != current_user:
            skipped.append({"todoId": tid_str, "reason": "只有发起人可以删除"})
            continue
        await session.execute(delete(TodoItemHandlers).where(TodoItemHandlers.todo_item_id == tid))
        await session.execute(delete(TodoItems).where(TodoItems.id == tid))
        deleted_ids.append(tid_str)
    return {"deletedIds": deleted_ids, "skipped": skipped}


async def urge_todos(
    body: TodoUrgeRequest,
    session: AsyncSession,
    request: Request | None = None,
) -> dict:
    """批量催更待办，逻辑对齐 todo.py follow_up_todo."""
    if not body.todoIds:
        return {"todoId": "", "followUpAt": _format_datetime(datetime.now(timezone.utc)), "handledIds": [], "skipped": []}
    current_user = _get_current_user(request)
    now = datetime.now(timezone.utc)
    handled_ids = []
    skipped = []
    notices = []
    for tid_str in body.todoIds:
        try:
            tid = int(tid_str)
        except ValueError:
            skipped.append({"todoId": tid_str, "reason": "ID格式错误"})
            continue
        row = (await session.execute(select(TodoItems).where(TodoItems.id == tid))).scalar_one_or_none()
        if not row:
            skipped.append({"todoId": tid_str, "reason": "待办不存在"})
            continue
        if row.promoter != current_user:
            skipped.append({"todoId": tid_str, "reason": "只有发起人可以催更"})
            continue
        if row.todo_status not in (PENDING_RECEIVE, NOT_PASSED):
            skipped.append({"todoId": tid_str, "reason": "仅待接收或不通过可催更"})
            continue
        # 查询处理人列表，用于通知
        handlers_result = await session.execute(
            select(TodoItemHandlers.handler_id).where(TodoItemHandlers.todo_item_id == tid)
        )
        handler_ids = list({r[0] for r in handlers_result.all() if r[0]})
        if row.handler_id and row.handler_id not in handler_ids:
            handler_ids.append(row.handler_id)
        for hid in handler_ids:
            if hid != row.promoter:
                notices.append({
                    "content": f"催办提醒：{row.title}，内容：{body.followUpContent or ''}",
                    "priority": 2,
                    "senderId": current_user,
                    "targetId": hid,
                    "title": "待办催办",
                })
        handled_ids.append(tid_str)
    if notices:
        await send_notice(notices, request)
    return {
        "todoId": handled_ids[0] if handled_ids else "",
        "followUpAt": _format_datetime(now),
        "handledIds": handled_ids,
        "skipped": skipped,
    }


async def update_todo(
    body: TodoUpdateRequest,
    session: AsyncSession,
    request: Request | None = None,
) -> dict:
    """修改待办，逻辑对齐 todo.py update_todo."""
    current_user = _get_current_user(request)
    try:
        tid = int(body.todoId)
    except ValueError:
        return {"todoId": body.todoId}
    row = (await session.execute(select(TodoItems).where(TodoItems.id == tid))).scalar_one_or_none()
    if not row:
        return {"todoId": body.todoId, "errorMsg": "待办不存在"}
    if row.promoter != current_user:
        return {"todoId": body.todoId, "errorMsg": "仅发起人可修改"}
    if row.todo_status not in (PENDING_RECEIVE, RETURNED):
        return {"todoId": body.todoId, "errorMsg": "仅待接收、退回状态可修改"}
    vals = {"todo_status": PENDING_RECEIVE}
    if body.content is not None:
        vals["todo_content"] = body.content
    if body.priority is not None:
        vals["todo_priority"] = body.priority
    if body.urgencyLevel is not None:
        vals["urgency_level"] = body.urgencyLevel
    if body.planFinishTime is not None:
        vals["deadline_at"] = _parse_datetime(body.planFinishTime)
    if body.handlerIds:
        vals["handler_id"] = body.handlerIds[0]
        # 同步 todo_item_handlers：先删后插
        await session.execute(
            delete(TodoItemHandlers).where(TodoItemHandlers.todo_item_id == tid)
        )
        org_id = row.org_id
        for h_id in body.handlerIds:
            th = TodoItemHandlers(
                id=_next_id(),
                todo_item_id=tid,
                org_id=org_id,
                handler_id=h_id,
            )
            session.add(th)
    vals["updated_at"] = datetime.now(timezone.utc)
    await session.execute(update(TodoItems).where(TodoItems.id == tid).values(**vals))
    return {"todoId": body.todoId}


async def approve_todos(
    body: TodoApproveRequest,
    session: AsyncSession,
    request: Request | None = None,
) -> dict:
    """批量审批待办，逻辑对齐 todo.py approve_todo."""
    if body.approvalStatus not in ("Approving", "Rejected"):
        return {"todoIds": [], "handledIds": [], "skipped": [{"reason": "审核状态错误"}]}
    if not body.todoIds:
        return {"todoIds": [], "handledIds": [], "skipped": []}
    current_user = _get_current_user(request)
    now = datetime.now(timezone.utc)
    handled_ids = []
    skipped = []
    notices = []
    for tid_str in body.todoIds:
        try:
            tid = int(tid_str)
        except ValueError:
            skipped.append({"todoId": tid_str, "reason": "ID格式错误"})
            continue
        row = (await session.execute(select(TodoItems).where(TodoItems.id == tid))).scalar_one_or_none()
        if not row:
            skipped.append({"todoId": tid_str, "reason": "待办不存在"})
            continue
        if row.promoter != current_user:
            skipped.append({"todoId": tid_str, "reason": "非发起人，无权限审批"})
            continue
        if row.todo_status != PENDING_REVIEW:
            skipped.append({"todoId": tid_str, "reason": "状态非待审核"})
            continue
        if body.approvalStatus == "Approving":
            await session.execute(
                update(TodoItems)
                .where(TodoItems.id == tid)
                .values(
                    todo_status=CLOSED,
                    approved_at=now,
                    approval_comment=body.approvalComment,
                    updated_at=now,
                )
            )
        else:
            await session.execute(
                update(TodoItems)
                .where(TodoItems.id == tid)
                .values(
                    todo_status=NOT_PASSED,
                    rejected_at=now,
                    approval_comment=body.approvalComment,
                    updated_at=now,
                )
            )
        # 查询处理人列表，用于通知
        handlers_result = await session.execute(
            select(TodoItemHandlers.handler_id).where(TodoItemHandlers.todo_item_id == tid)
        )
        handler_ids = list({r[0] for r in handlers_result.all() if r[0]})
        if row.handler_id and row.handler_id not in handler_ids:
            handler_ids.append(row.handler_id)
        msg = "审核通过" if body.approvalStatus == "Approving" else "审核不通过"
        for hid in handler_ids:
            if hid != row.promoter:
                notices.append({
                    "content": f"待办审批结果：{row.title}，{msg}",
                    "priority": 2,
                    "senderId": current_user,
                    "targetId": hid,
                    "title": "待办审批结果",
                })
        handled_ids.append(tid_str)
    if notices:
        await send_notice(notices, request)
    return {"todoIds": handled_ids, "handledIds": handled_ids, "skipped": skipped}
