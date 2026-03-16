"""
待办系统路由配置
"""
from app.api.router import api_registry
from .todo import (
    create_todo,
    query_todo_list,
    get_todo_detail,
    update_todo,
    handle_todo,
    return_todo,
    receive_todo,
    approve_todo,
    follow_up_todo,
    delete_todo,
    query_todo_by_meeting_note,
    query_todo_by_handler,
    query_todo_by_promoter,
    query_todo_by_approver,
    CreateTodoRequestBody,
    UpdateTodoRequestBody,
    TodoListQueryBody,
    TodoDetailBody,
    HandleTodoRequestBody,
    ReturnTodoRequestBody,
    ReceiveTodoRequestBody,
    ApproveTodoRequestBody,
    FollowUpTodoRequestBody,
    DeleteTodoRequestBody,
    QueryTodoByMeetingNoteRequest,
    QueryTodoByHandlerRequest,
    QueryTodoByPromoterRequest,
    QueryTodoByApproverRequest,
    CreateTodoResponse,
    TodoListResponse,
    TodoDetailResponse,
    UpdateTodoResponse,
    HandleTodoResponse,
    ReturnTodoResponse,
    ReceiveTodoResponse,
    ApproveTodoResponse,
    FollowUpTodoResponse,
    DeleteTodoResponse
)


def register_routes():
    """注册待办系统相关路由"""
    
    # 1. 创建待办
    api_registry.register_post(
        path="/datacloud/todo/create",
        handler=create_todo,
        tags=["待办系统", "新待办"],
        summary="创建待办事项",
        description="创建新的待办事项，支持指定处理人、优先级、截止时间等",
        response_model=CreateTodoResponse
    )
    
    # 2. 查询待办列表
    api_registry.register_post(
        path="/datacloud/todo/list",
        handler=query_todo_list,
        tags=["待办系统", "新待办"],
        summary="查询待办列表",
        description=(
            "查询待办列表\n\n"
            "**查询类型**:\n"
            "- my_todos: 待我处理的待办\n"
            "- my_created: 我发起的待办\n"
            "- all: 全部（需指定组织ID、处理人列表或发起人ID）\n\n"
            "**筛选条件**:\n"
            "- status: 状态筛选（单个状态）\n"
            "- statusList: 状态列表筛选（多个状态，优先级高于status）\n"
            "- priority: 优先级筛选\n"
            "- urgencyLevel: 紧急程度\n"
            "- keyword: 关键词搜索（标题、描述）\n"
            "- promoter: 发起人ID（支持在all类型中使用）\n"
            "- orgId: 组织ID（同时查询发起人组织和处理人组织）\n"
            "- includeSubOrgs: 是否包含下级组织（默认false，仅查询指定组织；true则递归查询所有下级组织，适用于orgId、promoterOrgId、handlerOrgId）\n"
            "- promoterOrgId: 发起人组织ID\n"
            "- handlerOrgId: 处理人组织ID\n"
            "- handlerIds: 处理人ID列表\n"
            "- 各种时间范围筛选\n\n"
            "**分页和排序**:\n"
            "- page: 页码（默认1）\n"
            "- pageSize: 每页数量（默认20）\n"
            "- sortBy: 排序字段\n"
            "- sortOrder: 排序方向"
        ),
        response_model=TodoListResponse
    )
    
    # 3. 查询待办详情
    api_registry.register_post(
        path="/datacloud/todo/detail",
        handler=get_todo_detail,
        tags=["待办系统", "新待办"],
        summary="查询待办详情",
        description="根据待办ID查询待办详情，包括处理人、附件等信息",
        response_model=TodoDetailResponse
    )
    
    # 4. 修改待办
    api_registry.register_post(
        path="/datacloud/todo/update",
        handler=update_todo,
        tags=["待办系统", "新待办"],
        summary="修改待办事项",
        description="修改待办事项信息，仅发起人可修改。仅待接收、退回状态可修改，修改后状态变为待接收。可修改：内容、处理人、优先级、紧急程度、计划完成时间。",
        response_model=UpdateTodoResponse
    )
    
    # 5. 处理待办
    api_registry.register_post(
        path="/datacloud/todo/handle",
        handler=handle_todo,
        tags=["待办系统", "新待办"],
        summary="处理待办事项",
        description="处理待办事项，必填进度0-100%。进度达到100%时状态改为待审核（发起人本人则直接关闭），否则保持已接收。仅处理人可操作，可处理状态：待接收、不通过、已接收。",
        response_model=HandleTodoResponse
    )
    
    # 6. 退回待办
    api_registry.register_post(
        path="/datacloud/todo/return",
        handler=return_todo,
        tags=["待办系统", "新待办"],
        summary="退回待办",
        description="仅当状态为待接收、且当前用户为该待办的处理人时可退回，需填写退回理由。退回后状态为「退回」。",
        response_model=ReturnTodoResponse
    )

    # 7. 接收待办
    api_registry.register_post(
        path="/datacloud/todo/receive",
        handler=receive_todo,
        tags=["待办系统", "新待办"],
        summary="接收待办",
        description="仅当状态为待接收、且当前用户为该待办的处理人时可接收。接收后状态为「已接收」。",
        response_model=ReceiveTodoResponse
    )

    # 8. 审核待办
    api_registry.register_post(
        path="/datacloud/todo/approve",
        handler=approve_todo,
        tags=["待办系统", "新待办"],
        summary="审核待办事项",
        description="审核待办事项，支持通过或拒绝（通过后状态为关闭，拒绝后状态为不通过）",
        response_model=ApproveTodoResponse
    )
    
    # 9. 催更待办
    api_registry.register_post(
        path="/datacloud/todo/follow-up",
        handler=follow_up_todo,
        tags=["待办系统", "新待办"],
        summary="催更待办事项",
        description="催更待办事项，只有创建人可以催更，会调用外部通知API通知处理人",
        response_model=FollowUpTodoResponse
    )
    
    # 10. 删除待办
    api_registry.register_post(
        path="/datacloud/todo/delete",
        handler=delete_todo,
        tags=["待办系统", "新待办"],
        summary="删除待办事项",
        description="删除待办事项，只有发起人可以删除，支持批量删除",
        response_model=DeleteTodoResponse
    )
    
    # ============================================================================
    # 四个专用查询接口
    # ============================================================================
    
    # 11. 按会议纪要查询待办
    api_registry.register_post(
        path="/datacloud/todo/list-by-meeting-note",
        handler=query_todo_by_meeting_note,
        tags=["待办系统", "专用查询"],
        summary="按会议纪要查询待办",
        description="查询指定会议纪要关联的所有待办，支持状态、优先级筛选",
        response_model=TodoListResponse
    )
    
    # 12. 按处理人查询待办
    api_registry.register_post(
        path="/datacloud/todo/list-by-handler",
        handler=query_todo_by_handler,
        tags=["待办系统", "专用查询"],
        summary="按处理人查询待办",
        description="查询指定处理人的待办，仅返回待接收和不通过状态，默认查询当前用户",
        response_model=TodoListResponse
    )
    
    # 13. 按发起人查询待办
    api_registry.register_post(
        path="/datacloud/todo/list-by-promoter",
        handler=query_todo_by_promoter,
        tags=["待办系统", "专用查询"],
        summary="按发起人查询待办",
        description="查询指定发起人创建的所有待办，返回所有状态，默认查询当前用户",
        response_model=TodoListResponse
    )
    
    # 14. 按审批人查询待办
    api_registry.register_post(
        path="/datacloud/todo/list-by-approver",
        handler=query_todo_by_approver,
        tags=["待办系统", "专用查询"],
        summary="按审批人查询待办",
        description="查询需要当前用户审核的待办，仅返回待审核状态",
        response_model=TodoListResponse
    )
