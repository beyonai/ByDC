"""待办路由汇总."""

from fastapi import APIRouter, Body, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from sales_analysis_demo.apis.todo.handlers import (
    TodoAcceptRequest,
    TodoApproveRequest,
    TodoCreateRequest,
    TodoDeleteRequest,
    TodoListRequest,
    TodoProcessRequest,
    TodoReturnRequest,
    TodoUpdateRequest,
    TodoUrgeRequest,
    accept_todo,
    approve_todos,
    create_todo,
    delete_todos,
    process_todos,
    query_todo_list,
    return_todo,
    update_todo,
    urge_todos,
)
from sales_analysis_demo.db import get_session

router = APIRouter(prefix="/todos")


@router.post("")
async def todo_create(
    request: Request,
    body: TodoCreateRequest,
    session: AsyncSession = Depends(get_session),
):
    """创建待办."""
    return await create_todo(body, session, request)


@router.post("/list")
async def todo_list(
    request: Request,
    body: TodoListRequest = Body(default_factory=TodoListRequest),
    session: AsyncSession = Depends(get_session),
):
    """查询待办列表."""
    items = await query_todo_list(body, session, request)
    return {
        "message": "",
        "code": "",
        "data": items,
    }


@router.post("/accept")
async def todo_accept(
    request: Request,
    body: TodoAcceptRequest,
    session: AsyncSession = Depends(get_session),
):
    """接收待办."""
    return await accept_todo(body, session, request)


@router.post("/return")
async def todo_return(
    request: Request,
    body: TodoReturnRequest,
    session: AsyncSession = Depends(get_session),
):
    """退回待办."""
    return await return_todo(body, session, request)


@router.post("/batch/process")
async def todo_process(
    request: Request,
    body: TodoProcessRequest,
    session: AsyncSession = Depends(get_session),
):
    """批量处理待办."""
    return await process_todos(body, session, request)


@router.post("/batch")
async def todo_delete(
    request: Request,
    body: TodoDeleteRequest,
    session: AsyncSession = Depends(get_session),
):
    """批量删除待办."""
    return await delete_todos(body, session, request)


@router.post("/batch/urge")
async def todo_urge(
    request: Request,
    body: TodoUrgeRequest,
    session: AsyncSession = Depends(get_session),
):
    """批量催更待办."""
    return await urge_todos(body, session, request)


@router.post("/update")
async def todo_update(
    request: Request,
    body: TodoUpdateRequest,
    session: AsyncSession = Depends(get_session),
):
    """修改待办."""
    return await update_todo(body, session, request)


@router.post("/batch/approve")
async def todo_approve(
    request: Request,
    body: TodoApproveRequest,
    session: AsyncSession = Depends(get_session),
):
    """批量审批待办."""
    return await approve_todos(body, session, request)
