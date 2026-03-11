#!/usr/bin/env python3
"""
fix_camel_and_params.py
对 objects_registry.json 进行以下修复：
1. property_code → camelCase
2. relations source/target_property_ref → camelCase
3. 替换 po_users、po_organization、todo_items 的 actions（硬编码）
4. fn_po_users_query_by_ids response items.properties key → camelCase
5. 补全 fn_po_users_query_by_org response items properties
6. 补全 fn_po_org_query_sub_orgs response items properties
"""

import json
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REGISTRY_PATH = os.path.join(SCRIPT_DIR, "objects_registry.json")


def snake_to_camel(name: str) -> str:
    parts = name.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


# ── 硬编码 actions ────────────────────────────────────────────────────────────

PO_USERS_ACTIONS = [
    {
        "action_code": "query_users_by_name_or_ids",
        "action_name": "按名称或ID查询人员",
        "action_type": "BUSINESS",
        "function_refs": ["fn_po_users_query_by_ids"],
        "description": "按用户ID列表或姓名列表批量查询人员详情",
        "visible": True,
        "tags": ["查询"],
        "params": [
            {
                "param_code": "names",
                "param_name": "用户名称列表",
                "param_type": "ARRAY",
                "direction": "IN",
                "required": False,
                "mapping_path": "$.requestBody.names",
            },
            {
                "param_code": "userIds",
                "param_name": "用户ID列表",
                "param_type": "ARRAY",
                "direction": "IN",
                "required": False,
                "mapping_path": "$.requestBody.userIds",
            },
            {
                "param_code": "userId",
                "param_name": "用户ID",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.users[].userId",
            },
            {
                "param_code": "userName",
                "param_name": "用户名称",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.users[].userName",
            },
            {
                "param_code": "userNumber",
                "param_name": "工号",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.users[].userNumber",
            },
            {
                "param_code": "orgId",
                "param_name": "组织ID",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.users[].orgId",
            },
            {
                "param_code": "state",
                "param_name": "用户状态",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.users[].state",
            },
            {
                "param_code": "email",
                "param_name": "邮箱",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.users[].email",
            },
            {
                "param_code": "phone",
                "param_name": "电话",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.users[].phone",
            },
        ],
    },
    {
        "action_code": "query_users_by_org_id",
        "action_name": "按组织ID查询人员",
        "action_type": "BUSINESS",
        "function_refs": ["fn_po_users_query_by_org"],
        "description": "按组织ID查询该组织下的人员列表，可选是否包含下级组织",
        "visible": True,
        "tags": ["查询"],
        "params": [
            {
                "param_code": "orgId",
                "param_name": "组织ID",
                "param_type": "STRING",
                "direction": "IN",
                "required": True,
                "mapping_path": "$.parameters.orgId",
            },
            {
                "param_code": "includeSubOrgs",
                "param_name": "是否包含下级组织",
                "param_type": "BOOLEAN",
                "direction": "IN",
                "required": False,
                "mapping_path": "$.parameters.includeSubOrgs",
            },
            {
                "param_code": "userId",
                "param_name": "用户ID",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.users[].userId",
            },
            {
                "param_code": "userName",
                "param_name": "用户名称",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.users[].userName",
            },
            {
                "param_code": "userNumber",
                "param_name": "工号",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.users[].userNumber",
            },
            {
                "param_code": "orgId",
                "param_name": "所属组织ID",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.users[].orgId",
            },
            {
                "param_code": "state",
                "param_name": "用户状态",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.users[].state",
            },
            {
                "param_code": "email",
                "param_name": "邮箱",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.users[].email",
            },
            {
                "param_code": "phone",
                "param_name": "电话",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.users[].phone",
            },
        ],
    },
]

PO_ORG_ACTIONS = [
    {
        "action_code": "query_org_by_name_or_id",
        "action_name": "按名称或ID查询组织",
        "action_type": "BUSINESS",
        "function_refs": ["fn_po_org_query_by_ids"],
        "description": "按组织ID列表或名称列表批量查询组织详情",
        "visible": True,
        "tags": ["查询"],
        "params": [
            {
                "param_code": "orgIds",
                "param_name": "组织ID列表",
                "param_type": "ARRAY",
                "direction": "IN",
                "required": False,
                "mapping_path": "$.requestBody.orgIds",
            },
            {
                "param_code": "orgNames",
                "param_name": "组织名称列表",
                "param_type": "ARRAY",
                "direction": "IN",
                "required": False,
                "mapping_path": "$.requestBody.orgNames",
            },
            {
                "param_code": "orgId",
                "param_name": "组织ID",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.organizations[].orgId",
            },
            {
                "param_code": "orgName",
                "param_name": "组织名称",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.organizations[].orgName",
            },
            {
                "param_code": "orgCode",
                "param_name": "组织编码",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.organizations[].orgCode",
            },
            {
                "param_code": "parentOrgId",
                "param_name": "父组织ID",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.organizations[].parentOrgId",
            },
            {
                "param_code": "orgLevel",
                "param_name": "组织层级",
                "param_type": "INTEGER",
                "direction": "OUT",
                "mapping_path": "$.response.organizations[].orgLevel",
            },
            {
                "param_code": "orgType",
                "param_name": "组织类型",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.organizations[].orgType",
            },
            {
                "param_code": "orgDesc",
                "param_name": "组织描述",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.organizations[].orgDesc",
            },
        ],
    },
    {
        "action_code": "query_sub_orgs_by_org_id",
        "action_name": "查询下级组织",
        "action_type": "BUSINESS",
        "function_refs": ["fn_po_org_query_sub_orgs"],
        "description": "按组织ID查询其所有直接下级或全部下级组织",
        "visible": True,
        "tags": ["查询"],
        "params": [
            {
                "param_code": "orgId",
                "param_name": "组织ID",
                "param_type": "STRING",
                "direction": "IN",
                "required": True,
                "mapping_path": "$.parameters.orgId",
            },
            {
                "param_code": "recursive",
                "param_name": "是否递归",
                "param_type": "BOOLEAN",
                "direction": "IN",
                "required": False,
                "mapping_path": "$.parameters.recursive",
            },
            {
                "param_code": "orgId",
                "param_name": "组织ID",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.organizations[].orgId",
            },
            {
                "param_code": "orgName",
                "param_name": "组织名称",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.organizations[].orgName",
            },
            {
                "param_code": "orgCode",
                "param_name": "组织编码",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.organizations[].orgCode",
            },
            {
                "param_code": "parentOrgId",
                "param_name": "父组织ID",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.organizations[].parentOrgId",
            },
            {
                "param_code": "orgLevel",
                "param_name": "组织层级",
                "param_type": "INTEGER",
                "direction": "OUT",
                "mapping_path": "$.response.organizations[].orgLevel",
            },
            {
                "param_code": "orgType",
                "param_name": "组织类型",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.organizations[].orgType",
            },
        ],
    },
]

TODO_ITEMS_ACTIONS = [
    {
        "action_code": "create_todo",
        "action_name": "创建待办",
        "action_type": "BUSINESS",
        "function_refs": ["fn_todo_create"],
        "description": "创建待办事项并指定处理人",
        "visible": True,
        "tags": ["写入"],
        "params": [
            {
                "param_code": "title",
                "param_name": "待办标题",
                "param_type": "STRING",
                "direction": "IN",
                "required": True,
                "mapping_path": "$.requestBody.title",
            },
            {
                "param_code": "deadlineAt",
                "param_name": "截止时间",
                "param_type": "STRING",
                "direction": "IN",
                "required": False,
                "mapping_path": "$.requestBody.deadlineAt",
            },
            {
                "param_code": "handlerIds",
                "param_name": "处理人ID列表",
                "param_type": "ARRAY",
                "direction": "IN",
                "required": False,
                "mapping_path": "$.requestBody.handlerIds",
            },
            {
                "param_code": "priority",
                "param_name": "优先级",
                "param_type": "STRING",
                "direction": "IN",
                "required": False,
                "mapping_path": "$.requestBody.priority",
            },
            {
                "param_code": "urgencyLevel",
                "param_name": "紧急程度",
                "param_type": "STRING",
                "direction": "IN",
                "required": False,
                "mapping_path": "$.requestBody.urgencyLevel",
            },
            {
                "param_code": "content",
                "param_name": "待办内容",
                "param_type": "STRING",
                "direction": "IN",
                "required": False,
                "mapping_path": "$.requestBody.content",
            },
            {
                "param_code": "meetingNoteId",
                "param_name": "会议纪要ID",
                "param_type": "STRING",
                "direction": "IN",
                "required": False,
                "mapping_path": "$.requestBody.meetingNoteId",
            },
            {
                "param_code": "promoter",
                "param_name": "发起人工号",
                "param_type": "STRING",
                "direction": "IN",
                "required": False,
                "mapping_path": "$.requestBody.promoter",
            },
            {
                "param_code": "remark",
                "param_name": "备注",
                "param_type": "STRING",
                "direction": "IN",
                "required": False,
                "mapping_path": "$.requestBody.remark",
            },
            {
                "param_code": "todoId",
                "param_name": "待办ID",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.todoId",
            },
            {
                "param_code": "errorMsg",
                "param_name": "错误信息",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.errorMsg",
            },
            {
                "param_code": "status",
                "param_name": "待办状态",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.status",
            },
            {
                "param_code": "title",
                "param_name": "待办标题",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.title",
            },
            {
                "param_code": "createdAt",
                "param_name": "创建时间",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.createdAt",
            },
        ],
    },
    {
        "action_code": "query_todo_list",
        "action_name": "查询待办列表",
        "action_type": "BUSINESS",
        "function_refs": ["fn_todo_query_list"],
        "description": "查询待办事项列表，支持多种过滤条件",
        "visible": True,
        "tags": ["查询"],
        "params": [
            {
                "param_code": "priority",
                "param_name": "优先级",
                "param_type": "STRING",
                "direction": "IN",
                "required": False,
                "mapping_path": "$.requestBody.priority",
            },
            {
                "param_code": "urgencyLevel",
                "param_name": "紧急程度",
                "param_type": "STRING",
                "direction": "IN",
                "required": False,
                "mapping_path": "$.requestBody.urgencyLevel",
            },
            {
                "param_code": "orgId",
                "param_name": "组织ID",
                "param_type": "STRING",
                "direction": "IN",
                "required": False,
                "mapping_path": "$.requestBody.orgId",
            },
            {
                "param_code": "meetingNoteIds",
                "param_name": "会议纪要ID列表",
                "param_type": "ARRAY",
                "direction": "IN",
                "required": False,
                "mapping_path": "$.requestBody.meetingNoteIds",
            },
            {
                "param_code": "statusList",
                "param_name": "状态列表",
                "param_type": "ARRAY",
                "direction": "IN",
                "required": False,
                "mapping_path": "$.requestBody.statusList",
            },
            {
                "param_code": "page",
                "param_name": "页码",
                "param_type": "STRING",
                "direction": "IN",
                "required": False,
                "mapping_path": "$.requestBody.page",
            },
            {
                "param_code": "keyword",
                "param_name": "关键词",
                "param_type": "STRING",
                "direction": "IN",
                "required": False,
                "mapping_path": "$.requestBody.keyword",
            },
            {
                "param_code": "deadlineEnd",
                "param_name": "截止时间结束",
                "param_type": "STRING",
                "direction": "IN",
                "required": False,
                "mapping_path": "$.requestBody.deadlineEnd",
            },
            {
                "param_code": "status",
                "param_name": "待办状态",
                "param_type": "STRING",
                "direction": "IN",
                "required": False,
                "mapping_path": "$.requestBody.status",
            },
            {
                "param_code": "promoter",
                "param_name": "发起人工号",
                "param_type": "STRING",
                "direction": "IN",
                "required": False,
                "mapping_path": "$.requestBody.promoter",
            },
            {
                "param_code": "deadlineStart",
                "param_name": "截止时间开始",
                "param_type": "STRING",
                "direction": "IN",
                "required": False,
                "mapping_path": "$.requestBody.deadlineStart",
            },
            {
                "param_code": "pageSize",
                "param_name": "页大小",
                "param_type": "STRING",
                "direction": "IN",
                "required": False,
                "mapping_path": "$.requestBody.pageSize",
            },
            {
                "param_code": "includeSubOrgs",
                "param_name": "是否查询下级",
                "param_type": "STRING",
                "direction": "IN",
                "required": False,
                "mapping_path": "$.requestBody.includeSubOrgs",
            },
            {
                "param_code": "todoId",
                "param_name": "待办ID",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.todos[].todoId",
            },
            {
                "param_code": "title",
                "param_name": "待办标题",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.todos[].title",
            },
            {
                "param_code": "status",
                "param_name": "待办状态",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.todos[].status",
            },
            {
                "param_code": "priority",
                "param_name": "优先级",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.todos[].priority",
            },
            {
                "param_code": "urgencyLevel",
                "param_name": "紧急程度",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.todos[].urgencyLevel",
            },
            {
                "param_code": "deadlineAt",
                "param_name": "截止时间",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.todos[].deadlineAt",
            },
            {
                "param_code": "content",
                "param_name": "待办内容",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.todos[].content",
            },
            {
                "param_code": "progress",
                "param_name": "处理进度",
                "param_type": "INTEGER",
                "direction": "OUT",
                "mapping_path": "$.response.todos[].progress",
            },
            {
                "param_code": "createdAt",
                "param_name": "创建时间",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.todos[].createdAt",
            },
            {
                "param_code": "promoter",
                "param_name": "发起人",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.todos[].promoter",
            },
            {
                "param_code": "approvalComment",
                "param_name": "审批意见",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.todos[].approvalComment",
            },
            {
                "param_code": "approvedAt",
                "param_name": "审批通过时间",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.todos[].approvedAt",
            },
            {
                "param_code": "completedAt",
                "param_name": "完成时间",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.todos[].completedAt",
            },
            {
                "param_code": "meetingNoteId",
                "param_name": "关联会议纪要ID",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.todos[].meetingNoteId",
            },
            {
                "param_code": "returnReason",
                "param_name": "退回原因",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.todos[].returnReason",
            },
        ],
    },
    {
        "action_code": "accept_todo",
        "action_name": "接收待办",
        "action_type": "BUSINESS",
        "function_refs": ["fn_todo_accept"],
        "description": "接收/认领指定待办事项",
        "visible": True,
        "tags": ["操作"],
        "params": [
            {
                "param_code": "todoId",
                "param_name": "待办ID",
                "param_type": "STRING",
                "direction": "IN",
                "required": True,
                "mapping_path": "$.parameters.todoId",
            },
            {
                "param_code": "todoId",
                "param_name": "待办ID",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.todoId",
            },
            {
                "param_code": "status",
                "param_name": "待办状态",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.status",
            },
        ],
    },
    {
        "action_code": "return_todo",
        "action_name": "退回待办",
        "action_type": "BUSINESS",
        "function_refs": ["fn_todo_return"],
        "description": "退回指定待办事项并说明原因",
        "visible": True,
        "tags": ["操作"],
        "params": [
            {
                "param_code": "todoId",
                "param_name": "待办ID",
                "param_type": "STRING",
                "direction": "IN",
                "required": True,
                "mapping_path": "$.parameters.todoId",
            },
            {
                "param_code": "returnReason",
                "param_name": "退回原因",
                "param_type": "STRING",
                "direction": "IN",
                "required": True,
                "mapping_path": "$.requestBody.returnReason",
            },
            {
                "param_code": "todoId",
                "param_name": "待办ID",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.todoId",
            },
            {
                "param_code": "status",
                "param_name": "待办状态",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.status",
            },
        ],
    },
    {
        "action_code": "process_todo",
        "action_name": "处理待办",
        "action_type": "BUSINESS",
        "function_refs": ["fn_todo_process"],
        "description": "批量处理待办事项，更新处理意见和进度",
        "visible": True,
        "tags": ["操作"],
        "params": [
            {
                "param_code": "todoIds",
                "param_name": "待办ID列表",
                "param_type": "ARRAY",
                "direction": "IN",
                "required": True,
                "mapping_path": "$.requestBody.todoIds",
            },
            {
                "param_code": "handleComment",
                "param_name": "处理意见",
                "param_type": "STRING",
                "direction": "IN",
                "required": False,
                "mapping_path": "$.requestBody.handleComment",
            },
            {
                "param_code": "progress",
                "param_name": "处理进度0-100",
                "param_type": "INTEGER",
                "direction": "IN",
                "required": False,
                "mapping_path": "$.requestBody.progress",
            },
            {
                "param_code": "todoId",
                "param_name": "被处理的待办ID",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.todoId",
            },
        ],
    },
    {
        "action_code": "delete_todo",
        "action_name": "删除待办",
        "action_type": "BUSINESS",
        "function_refs": ["fn_todo_delete"],
        "description": "批量删除待办事项",
        "visible": True,
        "tags": ["操作"],
        "params": [
            {
                "param_code": "todoIds",
                "param_name": "待办ID列表",
                "param_type": "ARRAY",
                "direction": "IN",
                "required": True,
                "mapping_path": "$.requestBody.todoIds",
            },
            {
                "param_code": "deletedIds",
                "param_name": "删除成功的ID串",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.deletedIds",
            },
        ],
    },
    {
        "action_code": "urge_todo",
        "action_name": "催更待办",
        "action_type": "BUSINESS",
        "function_refs": ["fn_todo_urge"],
        "description": "批量催更待办事项进度",
        "visible": True,
        "tags": ["操作"],
        "params": [
            {
                "param_code": "todoIds",
                "param_name": "待办ID列表",
                "param_type": "ARRAY",
                "direction": "IN",
                "required": True,
                "mapping_path": "$.requestBody.todoIds",
            },
            {
                "param_code": "followUpContent",
                "param_name": "催更内容",
                "param_type": "STRING",
                "direction": "IN",
                "required": False,
                "mapping_path": "$.requestBody.followUpContent",
            },
            {
                "param_code": "todoId",
                "param_name": "被催更的待办ID",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.todoId",
            },
            {
                "param_code": "followUpAt",
                "param_name": "催更时间",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.followUpAt",
            },
        ],
    },
    {
        "action_code": "update_todo",
        "action_name": "修改待办",
        "action_type": "BUSINESS",
        "function_refs": ["fn_todo_update"],
        "description": "修改待办事项的基本信息",
        "visible": True,
        "tags": ["写入"],
        "params": [
            {
                "param_code": "todoId",
                "param_name": "待办ID",
                "param_type": "STRING",
                "direction": "IN",
                "required": True,
                "mapping_path": "$.parameters.todoId",
            },
            {
                "param_code": "planFinishTime",
                "param_name": "计划完成时间",
                "param_type": "STRING",
                "direction": "IN",
                "required": False,
                "mapping_path": "$.requestBody.planFinishTime",
            },
            {
                "param_code": "handlerIds",
                "param_name": "处理人列表",
                "param_type": "ARRAY",
                "direction": "IN",
                "required": False,
                "mapping_path": "$.requestBody.handlerIds",
            },
            {
                "param_code": "priority",
                "param_name": "优先级",
                "param_type": "STRING",
                "direction": "IN",
                "required": False,
                "mapping_path": "$.requestBody.priority",
            },
            {
                "param_code": "urgencyLevel",
                "param_name": "紧急程度",
                "param_type": "STRING",
                "direction": "IN",
                "required": False,
                "mapping_path": "$.requestBody.urgencyLevel",
            },
            {
                "param_code": "content",
                "param_name": "待办内容",
                "param_type": "STRING",
                "direction": "IN",
                "required": False,
                "mapping_path": "$.requestBody.content",
            },
            {
                "param_code": "todoId",
                "param_name": "被修改的待办ID",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.todoId",
            },
        ],
    },
    {
        "action_code": "approve_todo",
        "action_name": "审批待办",
        "action_type": "BUSINESS",
        "function_refs": ["fn_todo_approve"],
        "description": "批量审批待办事项（通过或拒绝）",
        "visible": True,
        "tags": ["操作"],
        "params": [
            {
                "param_code": "approvalComment",
                "param_name": "审批意见",
                "param_type": "STRING",
                "direction": "IN",
                "required": False,
                "mapping_path": "$.requestBody.approvalComment",
            },
            {
                "param_code": "approvalStatus",
                "param_name": "审批状态",
                "param_type": "STRING",
                "direction": "IN",
                "required": True,
                "mapping_path": "$.requestBody.approvalStatus",
            },
            {
                "param_code": "todoIds",
                "param_name": "待办ID列表",
                "param_type": "ARRAY",
                "direction": "IN",
                "required": True,
                "mapping_path": "$.requestBody.todoIds",
            },
            {
                "param_code": "todoId",
                "param_name": "待办ID",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.todoId",
            },
            {
                "param_code": "approvalStatus",
                "param_name": "审批状态",
                "param_type": "STRING",
                "direction": "OUT",
                "mapping_path": "$.response.approvalStatus",
            },
        ],
    },
]

HARDCODED_ACTIONS = {
    "po_users": PO_USERS_ACTIONS,
    "po_organization": PO_ORG_ACTIONS,
    "todo_items": TODO_ITEMS_ACTIONS,
}

# ── 补全 fn_po_users_query_by_org response items ──────────────────────────────

USERS_ORG_ITEMS_PROPERTIES = {
    "userId": {"type": "string", "description": "用户ID"},
    "userName": {"type": "string", "description": "用户名称"},
    "userNumber": {"type": "string", "description": "工号"},
    "orgId": {"type": "string", "description": "组织ID"},
    "state": {"type": "string", "description": "用户状态"},
    "email": {"type": "string", "description": "用户邮箱"},
    "phone": {"type": "string", "description": "用户电话"},
}

SUB_ORGS_ITEMS_PROPERTIES = {
    "orgId": {"type": "string", "description": "组织ID"},
    "orgName": {"type": "string", "description": "组织名称"},
    "orgCode": {"type": "string", "description": "组织编码"},
    "parentOrgId": {"type": "string", "description": "父组织ID"},
    "orgLevel": {"type": "integer", "description": "组织层级"},
    "orgType": {"type": "string", "description": "组织类型"},
}


# ── 工具函数：找到 api_schema 的 response 200 schema ──────────────────────────


def get_response_200_schema(api_schema: dict):
    """返回 response 200 content application/json schema（可能为 None）"""
    for path_obj in api_schema.get("paths", {}).values():
        for method_obj in path_obj.values():
            resp = method_obj.get("responses", {}).get("200", {})
            schema = resp.get("content", {}).get("application/json", {}).get("schema")
            if schema:
                return schema
    return None


def camel_rename_items_properties(schema: dict):
    """将 schema.properties 中每个 key 为数组的 items.properties 的 key 转为 camelCase"""
    for prop_key, prop_val in list(schema.get("properties", {}).items()):
        if prop_val.get("type") == "array":
            items = prop_val.get("items", {})
            old_props = items.get("properties")
            if old_props:
                new_props = {snake_to_camel(k): v for k, v in old_props.items()}
                items["properties"] = new_props


# ── 主逻辑 ────────────────────────────────────────────────────────────────────


def main():
    print(f"Loading {REGISTRY_PATH} ...")
    with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    # ── 修复 1：property_code → camelCase ────────────────────────────────────
    prop_fixed = 0
    for obj in data.get("objects", []):
        for prop in obj.get("properties", []):
            old = prop["property_code"]
            new = snake_to_camel(old)
            if old != new:
                prop["property_code"] = new
                prop_fixed += 1
    print(f"  property_code 转换: {prop_fixed} 个")

    # ── 修复 2：relations source/target_property_ref → camelCase ─────────────
    rel_fixed = 0
    for rel in data.get("relations", []):
        for key in ("source_property_ref", "target_property_ref"):
            if key in rel:
                old = rel[key]
                new = snake_to_camel(old)
                if old != new:
                    rel[key] = new
                    rel_fixed += 1
    print(f"  relations property_ref 转换: {rel_fixed} 个")

    # ── 修复 3：替换硬编码 actions ────────────────────────────────────────────
    for obj in data.get("objects", []):
        code = obj.get("object_code")
        if code in HARDCODED_ACTIONS:
            obj["actions"] = HARDCODED_ACTIONS[code]
            print(f"  {code} actions 已替换（{len(HARDCODED_ACTIONS[code])} 个）")

    # ── 修复 4：fn_po_users_query_by_ids response items properties → camelCase
    # ── 修复 5/6：补全 fn_po_users_query_by_org / fn_po_org_query_sub_orgs items
    for fn in data.get("functions", []):
        fc = fn.get("function_code")
        schema = get_response_200_schema(fn.get("api_schema", {}))
        if schema is None:
            continue

        if fc == "fn_po_users_query_by_ids":
            camel_rename_items_properties(schema)
            print(f"  {fc}: response items.properties keys → camelCase")

        elif fc == "fn_po_users_query_by_org":
            users_prop = schema.get("properties", {}).get("users", {})
            if users_prop.get("type") == "array":
                users_prop["items"] = {
                    "type": "object",
                    "properties": USERS_ORG_ITEMS_PROPERTIES,
                }
            print(f"  {fc}: response items.properties 已补全")

        elif fc == "fn_po_org_query_sub_orgs":
            orgs_prop = schema.get("properties", {}).get("organizations", {})
            if orgs_prop.get("type") == "array":
                orgs_prop["items"] = {
                    "type": "object",
                    "properties": SUB_ORGS_ITEMS_PROPERTIES,
                }
            print(f"  {fc}: response items.properties 已补全")

    # ── 写回 ──────────────────────────────────────────────────────────────────
    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n✓ 已写回 {REGISTRY_PATH}")


if __name__ == "__main__":
    main()
