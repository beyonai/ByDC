

#### 3.3.3 标准格式规范（JSON / YAML / OWL）

本体服务支持以 **JSON、YAML、OWL** 三种标准格式描述本体定义，仅提供**两种文件粒度**：**视图级**与**对象级**。**领域**不作为独立顶层节点，而是作为**视图**和**对象**的属性（`domain_ref`），用于标识其所属业务领域。

| 文件粒度 | 链路 | 包含节点 | 适用场景 |
|---------|------|---------|---------|
| **视图级（View-Level）** | View → Object → Action → Function(Tool) | `metadata` + `functions` + `objects` + `relations` + `views` | 完整业务场景交付，一个视图文件即可实例化出一套完整的 MCP 服务；视图中含 `domain_ref` 标识所属领域 |
| **对象级（Object-Level）** | Object → Action → Function(Tool) | `metadata` + `functions` + `objects` + `relations` | 单个或多个对象的定义交换，无视图包装，适用于对象粒度的复用和共享；对象中含 `domain_ref` 标识所属领域 |

> **核心原则**：无论哪种粒度，文件必须是**自包含的**——文件内 Action 引用的 Function（`function_ref` / `function_refs`）必须在同一文件的 `functions` 列表中声明；Action 可另含可选 `script`（脚本）；`relations` 引用的 source/target Object 必须在 `objects` 列表中存在。导入后，系统可基于该文件直接实例化出可用的 MCP Server。领域信息由各视图、对象的 **`domain_ref`** 提供，导入时据此创建或匹配 dc_domain。
>
> **函数参数设计原则**：API 类型函数使用 `api_schema`（标准 OpenAPI 3.0.x 文档）描述接口定义，无需 `params` 列表；PLUGIN/BOT/MCP 类型函数继续在 `carrier_config` 中内嵌参数描述。Action 的 `params` 代表面向 AI 模型/用户的抽象接口。

##### 3.3.3.0 文件粒度与结构对比

**领域作为视图与对象的属性**：标准格式中**不包含**顶层 `domains` 节点。领域知识通过 **`domain_ref`**（领域编码，如 `"crm"`、`"sales"`）作为**视图**和**对象**的属性表达；导入时根据各视图、对象的 `domain_ref` 创建或匹配 dc_domain。

**视图级文件结构（含 views 节点）：**

```json
{
  "$schema": "https://datacloud.io/schemas/ontology/v1.0",
  "version": "1.0",
  "scope": "VIEW",
  "metadata": { "name": "...", "tenant_id": "..." },
  "functions": [ /* 全局函数/工具定义 */ ],
  "objects": [ /* 对象（含 domain_ref）+ 属性 + 动作 */ ],
  "relations": [ /* 对象间关系 */ ],
  "views": [ /* 视图（含 domain_ref）+ 核心对象 + 关联对象 */ ]
}
```

**对象级文件结构（无 views 节点）：**

```json
{
  "$schema": "https://datacloud.io/schemas/ontology/v1.0",
  "version": "1.0",
  "scope": "OBJECT",
  "metadata": { "name": "...", "tenant_id": "..." },
  "functions": [ /* 全局函数/工具定义 */ ],
  "objects": [ /* 对象（含 domain_ref）+ 属性 + 动作 */ ],
  "relations": [ /* 对象间关系 */ ]
}
```

**对象级完整 JSON 示例（单对象 + 动作 + 工具 + 关系，含 api_schema）：**

以下示例展示**编码字段**用法：`function_code`（如 fn_query_mysql）、`object_code`（如 sales_person）、`action_code`（如 query_opportunity_by_emp）必填且文件内唯一。

```json
{
  "$schema": "https://datacloud.io/schemas/ontology/v1.0",
  "version": "1.0",
  "scope": "OBJECT",
  "metadata": {
    "name": "商机对象定义",
    "description": "商机对象及其关联对象、动作和工具定义",
    "author": "admin",
    "created_time": "2026-02-10T12:00:00Z",
    "tenant_id": "TENANT_001",
    "domain_ref": "crm"
  },

  "functions": [
    {
      "function_code": "fn_query_mysql",
      "function_name": "MySQL通用查询",
      "function_type": "API",
      "description": "数据服务提供的SQL查询工具",
      "api_schema": {
        "openapi": "3.0.3",
        "info": { "title": "数据服务查询", "version": "1.0.0" },
        "servers": [ { "url": "http://data-service:8082" } ],
        "paths": {
          "/api/v1/query": {
            "post": {
              "operationId": "fn_query_mysql",
              "x-timeout-ms": 30000,
              "parameters": [],
              "requestBody": {
                "required": true,
                "content": {
                  "application/json": {
                    "schema": {
                      "type": "object",
                      "required": ["sql", "datasource_id"],
                      "properties": {
                        "sql": { "type": "string", "description": "SQL语句" },
                        "datasource_id": { "type": "string", "description": "数据源ID" },
                        "sql_param_emp_no": { "type": "string", "description": "动态参数：员工工号" }
                      }
                    }
                  }
                }
              },
              "responses": {
                "200": {
                  "description": "查询成功",
                  "content": {
                    "application/json": {
                      "schema": {
                        "type": "object",
                        "properties": {
                          "result_set": { "type": "array", "items": { "type": "object" } }
                        }
                      }
                    }
                  }
                }
              }
            }
          }
        }
      }
    },
    {
      "function_code": "fn_crm_update_opportunity",
      "function_name": "CRM商机更新接口",
      "function_type": "API",
      "description": "调用CRM系统外部API更新商机状态",
      "api_schema": {
        "openapi": "3.0.3",
        "info": { "title": "CRM商机API", "version": "1.0.0" },
        "servers": [ { "url": "https://crm-api.example.com" } ],
        "paths": {
          "/v2/opportunities/{opportunity_id}": {
            "put": {
              "operationId": "fn_crm_update_opportunity",
              "x-timeout-ms": 10000,
              "parameters": [
                { "name": "opportunity_id", "in": "path", "required": true, "schema": { "type": "string" }, "description": "商机ID" },
                { "name": "X-Tenant-Id", "in": "header", "required": true, "schema": { "type": "string" }, "description": "租户标识" }
              ],
              "requestBody": {
                "required": true,
                "content": {
                  "application/json": {
                    "schema": {
                      "type": "object",
                      "required": ["status"],
                      "properties": {
                        "status": { "type": "string", "enum": ["OPEN", "WON", "LOST"] },
                        "tags": { "type": "array", "items": { "type": "string" } },
                        "contacts": {
                          "type": "array",
                          "items": {
                            "type": "object",
                            "properties": {
                              "name": { "type": "string" },
                              "role": { "type": "string" },
                              "phone": { "type": "string" }
                            }
                          }
                        }
                      }
                    }
                  }
                }
              },
              "responses": {
                "200": {
                  "description": "更新成功",
                  "content": {
                    "application/json": {
                      "schema": {
                        "type": "object",
                        "properties": {
                          "success": { "type": "boolean" },
                          "message": { "type": "string" }
                        }
                      }
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
  ],

  "objects": [
    {
      "object_code": "sales_person",
      "object_name": "员工对象",
      "object_type": "ANALYTICS_DB",
      "source_system": "crm_system",
      "domain_ref": "crm",
      "description": "销售员工",
      "tags": ["CRM", "员工", "高优"],
      "source_config": {
        "connector_type": "mysql",
        "datasource_id": "ds_sales",
        "table_name": "sales_person",
        "primary_key": "emp_no"
      },
      "properties": [
        { "property_code": "emp_no", "property_name": "员工工号", "property_type": "STRING", "required": true, "is_primary_key": true, "source_column": "emp_no" },
        { "property_code": "name", "property_name": "姓名", "property_type": "STRING", "required": true, "source_column": "name" }
      ],
      "actions": [
        {
          "action_code": "query_emp_info",
          "action_name": "查询员工信息",
          "action_type": "BUSINESS",
          "function_refs": ["fn_query_mysql"],
          "visible": true,
          "tags": ["查询", "高优"],
          "params": [
            { "param_code": "emp_no", "param_name": "员工工号", "param_type": "STRING", "direction": "IN", "required": true, "mapping_path": "$.requestBody.sql_param_emp_no", "tags": ["主键"] },
            { "param_code": "datasource_id", "param_name": "数据源", "param_type": "STRING", "direction": "IN", "required": false, "mapping_path": "$.requestBody.datasource_id", "default_value": "ds_sales" },
            { "param_code": "emp_info", "param_name": "员工信息", "param_type": "OBJECT", "direction": "OUT", "required": true, "mapping_path": "$.response.result_set" }
          ]
        }
      ]
    },
    {
      "object_code": "sales_business_opportunity",
      "object_name": "商机对象",
      "object_type": "ANALYTICS_DB",
      "source_system": "crm_system",
      "domain_ref": "crm",
      "description": "CRM商机",
      "tags": ["CRM", "商机", "高优"],
      "source_config": {
        "connector_type": "mysql",
        "datasource_id": "ds_sales",
        "table_name": "sales_business_opportunity",
        "primary_key": "id"
      },
      "properties": [
        { "property_code": "id", "property_name": "商机ID", "property_type": "STRING", "required": true, "is_primary_key": true, "source_column": "id" },
        { "property_code": "bo_name", "property_name": "商机名称", "property_type": "STRING", "required": true, "source_column": "bo_name" },
        { "property_code": "iwhale_cbm_emp_no", "property_name": "负责人工号", "property_type": "STRING", "required": true, "source_column": "iwhale_cbm_emp_no" },
        { "property_code": "business_opportunity_process", "property_name": "商机状态", "property_type": "STRING", "required": true, "source_column": "business_opportunity_process", "ext_attrs": { "term_type_id": "TT_OPP_STATUS", "term_type_code": "opportunity_status", "term_type_name": "商机状态" } },
        { "property_code": "contract_scale", "property_name": "合同额（万）", "property_type": "DECIMAL", "required": false, "source_column": "contract_scale" }
      ],
      "actions": [
        {
          "action_code": "query_opportunity_by_emp",
          "action_name": "按员工查商机",
          "action_type": "BUSINESS",
          "function_refs": ["fn_query_mysql"],
          "description": "根据员工工号查询其负责的商机列表",
          "visible": true,
          "tags": ["查询", "商机", "高优"],
          "params": [
            { "param_code": "emp_no", "param_name": "员工工号", "param_type": "STRING", "direction": "IN", "required": true, "mapping_path": "$.requestBody.sql_param_emp_no" },
            { "param_code": "datasource_id", "param_name": "数据源", "param_type": "STRING", "direction": "IN", "required": false, "mapping_path": "$.requestBody.datasource_id", "default_value": "ds_sales" },
            { "param_code": "opportunity_list", "param_name": "商机列表", "param_type": "LIST", "direction": "OUT", "required": true, "mapping_path": "$.response.result_set",
              "children": [
                { "param_code": "bo_name", "param_name": "商机名称", "param_type": "STRING", "direction": "OUT" },
                { "param_code": "customer_name", "param_name": "客户名称", "param_type": "STRING", "direction": "OUT" },
                { "param_code": "contract_scale", "param_name": "合同额", "param_type": "DECIMAL", "direction": "OUT" },
                { "param_code": "business_opportunity_process", "param_name": "商机状态", "param_type": "STRING", "direction": "OUT" }
              ]
            }
          ]
        },
        {
          "action_code": "update_opportunity_status",
          "action_name": "更新商机状态",
          "action_type": "BUSINESS",
          "function_refs": ["fn_crm_update_opportunity"],
          "script": { "type": "python", "content": "# 可选：前置或后置脚本\ndef before_call(ctx):\n  return ctx\n" },
          "description": "调用CRM外部API更新商机的业务状态",
          "visible": true,
          "params": [
            { "param_code": "opportunity_id", "param_name": "商机ID", "param_type": "STRING", "direction": "IN", "required": true, "mapping_path": "$.parameters.opportunity_id" },
            { "param_code": "new_status", "param_name": "新状态", "param_type": "STRING", "direction": "IN", "required": true, "mapping_path": "$.requestBody.status", "ext_attrs": { "term_type_id": "TT_OPP_STATUS", "term_type_code": "opportunity_status", "term_type_name": "商机状态" } },
            { "param_code": "tenant_id", "param_name": "租户标识", "param_type": "STRING", "direction": "IN", "required": false, "mapping_path": "$.parameters.X-Tenant-Id", "default_value": "TENANT_001" },
            { "param_code": "update_result", "param_name": "更新结果", "param_type": "OBJECT", "direction": "OUT", "required": true, "mapping_path": "$.response.data",
              "children": [
                { "param_code": "success", "param_name": "是否成功", "param_type": "BOOLEAN", "direction": "OUT" },
                { "param_code": "message", "param_name": "消息", "param_type": "STRING", "direction": "OUT" }
              ]
            }
          ]
        }
      ]
    }
  ],

  "relations": [
    {
      "relation_name": "员工负责商机",
      "source_object_ref": "sales_person",
      "target_object_ref": "sales_business_opportunity",
      "relation_type": "ASSOCIATES",
      "cardinality": "ONE_TO_MANY",
      "source_property_ref": "emp_no",
      "target_property_ref": "iwhale_cbm_emp_no",
      "action_ref": "query_opportunity_by_emp"
    }
  ]
}
```

> 上述对象级文件导入后，系统可直接据此实例化 MCP Server：`sales_person` 和 `sales_business_opportunity` 成为 MCP Resource，`query_opportunity_by_emp` 和 `update_opportunity_status` 成为 MCP Tool。
> 
> **参数层级说明**：JSON 中 `params` 内的 `children` 数组对应数据库中 `parent_param_id` 的父子关系，导入时系统自动将嵌套结构展平为 dc_param 行记录。`mapping_path` 使用 `$` 前缀引用 api_schema 中的参数位置。

##### 3.3.3.1 dataCloud 本体 JSON 格式规范（dc-ontology.json）— 视图级完整示例

JSON 格式是 dataCloud 的**主格式**，所有其他格式转换以 JSON 为中间表示。

**视图级顶层结构：**

```json
{
  "$schema": "https://datacloud.io/schemas/ontology/v1.0",
  "version": "1.0",
  "scope": "VIEW",
  "metadata": {
    "name": "销售分析本体",
    "description": "销售分析助手的本体定义，包含员工视图和组织视图",
    "author": "admin",
    "created_time": "2026-02-10T10:00:00Z",
    "tenant_id": "TENANT_001",
    "domain_ref": "sales"
  },
  "functions": [ ... ],
  "objects": [ ... ],
  "relations": [ ... ],
  "views": [ ... ]
}
```

**完整示例（以销售分析助手为例）：**

以下示例包含**编码字段**完整用例：`function_code`、`object_code`、`action_code`、`view_code` 在各自层级必填且文件内唯一（如 view_code: employee_view、object_code: sales_person、action_code: query_emp_by_no）。

```json
{
  "$schema": "https://datacloud.io/schemas/ontology/v1.0",
  "version": "1.0",
  "scope": "VIEW",
  "metadata": {
    "name": "销售分析本体",
    "description": "销售分析助手场景的完整本体定义",
    "author": "admin",
    "created_time": "2026-02-10T10:00:00Z",
    "tenant_id": "TENANT_001",
    "domain_ref": "sales"
  },

  "functions": [
    {
      "function_code": "fn_query_mysql",
      "function_name": "MySQL通用查询函数",
      "function_type": "API",
      "description": "通过SQL查询MySQL数据源并返回结果集",
      "api_schema": {
        "openapi": "3.0.3",
        "info": { "title": "数据服务查询", "version": "1.0.0" },
        "servers": [ { "url": "http://data-service:8082" } ],
        "paths": {
          "/api/v1/query": {
            "post": {
              "operationId": "fn_query_mysql",
              "x-timeout-ms": 30000,
              "parameters": [],
              "requestBody": {
                "required": true,
                "content": {
                  "application/json": {
                    "schema": {
                      "type": "object",
                      "required": ["sql", "datasource_id"],
                      "properties": {
                        "sql": { "type": "string", "description": "SQL语句" },
                        "datasource_id": { "type": "string", "description": "数据源ID" },
                        "sql_param_emp_no": { "type": "string", "description": "动态参数：员工工号" },
                        "sql_param_date_from": { "type": "string", "format": "date", "description": "动态参数：开始日期" },
                        "sql_param_date_to": { "type": "string", "format": "date", "description": "动态参数：结束日期" }
                      }
                    }
                  }
                }
              },
              "responses": {
                "200": {
                  "description": "查询成功",
                  "content": {
                    "application/json": {
                      "schema": {
                        "type": "object",
                        "properties": {
                          "result_set": { "type": "array", "items": { "type": "object" } }
                        }
                      }
                    }
                  }
                }
              }
            }
          }
        }
      }
    },
    {
      "function_code": "fn_aggregate_calc",
      "function_name": "聚合计算函数",
      "function_type": "PLUGIN",
      "description": "对数据集进行聚合计算（SUM/AVG/COUNT等）",
      "carrier_config": {
        "plugin_id": "plugin_aggregate",
        "method": "calculate",
        "params": {
          "input": [
            { "name": "dataset", "type": "LIST", "required": true },
            { "name": "agg_config", "type": "OBJECT", "required": true, "description": "包含字段名、聚合函数类型等" }
          ],
          "output": [
            { "name": "agg_result", "type": "OBJECT", "required": true }
          ]
        }
      }
    }
  ],

  "objects": [
    {
      "object_code": "sales_person",
      "object_name": "员工对象",
      "object_type": "ANALYTICS_DB",
      "source_system": "crm_system",
      "domain_ref": "sales",
      "description": "描述员工实体，对应 sales_person 表",
      "tags": ["CRM", "员工", "高优"],
      "source_config": {
        "connector_type": "mysql",
        "datasource_id": "ds_sales",
        "table_name": "sales_person",
        "primary_key": "emp_no",
        "display_column": "name"
      },
      "properties": [
        {
          "property_code": "emp_no",
          "property_name": "员工工号",
          "property_type": "STRING",
          "required": true,
          "is_primary_key": true,
          "source_column": "emp_no"
        },
        {
          "property_code": "name",
          "property_name": "姓名",
          "property_type": "STRING",
          "required": true,
          "source_column": "name"
        },
        {
          "property_code": "org_id",
          "property_name": "组织ID",
          "property_type": "STRING",
          "required": true,
          "source_column": "org_id"
        },
        {
          "property_code": "emp_level",
          "property_name": "职级",
          "property_type": "STRING",
          "required": false,
          "source_column": "emp_level"
        },
        {
          "property_code": "status",
          "property_name": "状态",
          "property_type": "STRING",
          "required": true,
          "source_column": "status",
          "ext_attrs": { "term_type_id": "TT_EMP_STATUS", "term_type_code": "emp_status", "term_type_name": "员工状态" }
        },
        {
          "property_code": "role",
          "property_name": "角色",
          "property_type": "STRING",
          "required": true,
          "source_column": "role"
        }
      ],
      "actions": [
        {
          "action_code": "query_emp_by_no",
          "action_name": "按工号查询员工",
          "action_type": "BUSINESS",
          "function_refs": ["fn_query_mysql"],
          "description": "根据员工工号查询员工基本信息",
          "visible": true,
          "tags": ["查询", "高优"],
          "params": [
            { "param_code": "emp_no", "param_name": "员工工号", "param_type": "STRING", "direction": "IN", "required": true, "mapping_path": "$.requestBody.sql_param_emp_no", "tags": ["主键"], "ext_attrs": { "term_type_id": "TT_EMP_NO", "term_type_code": "emp_no", "term_type_name": "员工工号" } },
            { "param_code": "datasource_id", "param_name": "数据源", "param_type": "STRING", "direction": "IN", "required": false, "mapping_path": "$.requestBody.datasource_id", "default_value": "ds_sales" },
            { "param_code": "emp_info", "param_name": "员工信息", "param_type": "OBJECT", "direction": "OUT", "required": true, "mapping_path": "$.response.result_set" }
          ]
        }
      ]
    },
    {
      "object_code": "sales_business_opportunity",
      "object_name": "商机对象",
      "object_type": "API",
      "source_system": "crm_system",
      "domain_ref": "crm",
      "description": "描述商机实体，通过 CRM 接口获取数据",
      "tags": ["CRM", "商机", "高优"],
      "source_config": {
        "connector_type": "http",
        "base_url": "https://crm-api.example.com/v2/opportunities",
        "auth": {
          "type": "bearer",
          "token_endpoint": "https://crm-api.example.com/oauth/token"
        },
        "timeout_ms": 30000,
        "primary_key": "id",
        "display_column": "bo_name"
      },
      "properties": [
        {
          "property_code": "bo_name",
          "property_name": "商机名称",
          "property_type": "STRING",
          "required": true,
          "source_column": "bo_name"
        },
        {
          "property_code": "customer_name",
          "property_name": "客户名称",
          "property_type": "STRING",
          "required": true,
          "source_column": "customer_name"
        },
        {
          "property_code": "iwhale_cbm_emp_no",
          "property_name": "负责人工号",
          "property_type": "STRING",
          "required": true,
          "source_column": "iwhale_cbm_emp_no"
        },
        {
          "property_code": "business_opportunity_process",
          "property_name": "商机状态",
          "property_type": "STRING",
          "required": true,
          "source_column": "business_opportunity_process",
          "ext_attrs": { "term_type_id": "TT_OPP_STATUS", "term_type_code": "opportunity_status", "term_type_name": "商机状态" }
        },
        {
          "property_code": "contract_scale",
          "property_name": "合同额（万）",
          "property_type": "DECIMAL",
          "required": false,
          "source_column": "contract_scale"
        },
        {
          "property_code": "win_bid",
          "property_name": "是否中标",
          "property_type": "BOOLEAN",
          "required": true,
          "source_column": "win_bid"
        }
      ],
      "actions": [
        {
          "action_code": "query_opportunity_by_emp",
          "action_name": "按员工查询商机",
          "action_type": "BUSINESS",
          "function_refs": ["fn_query_mysql"],
          "description": "根据员工工号和时间范围查询商机列表",
          "visible": true,
          "params": [
            { "param_code": "emp_no", "param_name": "员工工号", "param_type": "STRING", "direction": "IN", "required": true, "mapping_path": "$.requestBody.sql_param_emp_no", "ext_attrs": { "term_type_id": "TT_EMP_NO", "term_type_code": "emp_no", "term_type_name": "员工工号" } },
            { "param_code": "date_from", "param_name": "开始日期", "param_type": "DATE", "direction": "IN", "required": false, "mapping_path": "$.requestBody.sql_param_date_from" },
            { "param_code": "date_to", "param_name": "结束日期", "param_type": "DATE", "direction": "IN", "required": false, "mapping_path": "$.requestBody.sql_param_date_to" },
            { "param_code": "datasource_id", "param_name": "数据源", "param_type": "STRING", "direction": "IN", "required": false, "mapping_path": "$.requestBody.datasource_id", "default_value": "ds_sales" },
            { "param_code": "opportunity_list", "param_name": "商机列表", "param_type": "LIST", "direction": "OUT", "required": true, "mapping_path": "$.response.result_set",
              "children": [
                { "param_code": "bo_name", "param_name": "商机名称", "param_type": "STRING", "direction": "OUT" },
                { "param_code": "customer_name", "param_name": "客户名称", "param_type": "STRING", "direction": "OUT" },
                { "param_code": "contract_scale", "param_name": "合同额", "param_type": "DECIMAL", "direction": "OUT" },
                { "param_code": "business_opportunity_process", "param_name": "商机状态", "param_type": "STRING", "direction": "OUT" },
                { "param_code": "win_bid", "param_name": "是否中标", "param_type": "BOOLEAN", "direction": "OUT" }
              ]
            }
          ]
        }
      ]
    }
  ],

  "relations": [
    {
      "relation_name": "员工归属组织",
      "source_object_ref": "sales_person",
      "target_object_ref": "organization_department",
      "relation_type": "BELONGS_TO",
      "cardinality": "MANY_TO_ONE",
      "source_property_ref": "org_id",
      "target_property_ref": "org_id"
    },
    {
      "relation_name": "员工负责商机",
      "source_object_ref": "sales_person",
      "target_object_ref": "sales_business_opportunity",
      "relation_type": "ASSOCIATES",
      "cardinality": "ONE_TO_MANY",
      "source_property_ref": "emp_no",
      "target_property_ref": "iwhale_cbm_emp_no",
      "action_ref": "query_opportunity_by_emp"
    }
  ],

  "views": [
    {
      "view_code": "employee_view",
      "view_name": "员工视图",
      "source_system": "crm_system",
      "domain_ref": "sales",
      "description": "以员工为中心聚合商机、合同、KPI、日报、考勤等对象",
      "tags": ["销售概览", "高优"],
      "core_object_ref": "sales_person",
      "related_objects": [
        {
          "object_ref": "sales_business_opportunity",
          "relation_path": "sales_person.emp_no -> sales_business_opportunity.iwhale_cbm_emp_no"
        },
        {
          "object_ref": "sales_person_kpi_detail",
          "relation_path": "sales_person.emp_no -> sales_person_kpi_detail.emp_no"
        },
        {
          "object_ref": "sales_person_kpi_summary",
          "relation_path": "sales_person.emp_no -> sales_person_kpi_summary.emp_no"
        },
        {
          "object_ref": "sales_daily_report",
          "relation_path": "sales_person.emp_no -> sales_daily_report.belong_emp_no"
        },
        {
          "object_ref": "sales_emp_attendance",
          "relation_path": "sales_person.emp_no -> sales_emp_attendance.emp_no"
        }
      ]
    }
  ]
}
```

**编码字段约定：**

视图、对象、动作、函数均具有**编码（code）**字段，用于唯一标识与引用，在 JSON/YAML 中必填、文件内不可重复；与数据库、OWL 对应关系如下。

| 实体 | 编码字段（DB） | JSON/YAML 键 | OWL 属性 | 示例值 |
|------|----------------|-------------|----------|--------|
| 函数 | dc_function.function_code | `function_code` | `dc:functionCode` | fn_query_mysql |
| 对象 | dc_object.object_code | `object_code` | `dc:objectCode` | sales_person |
| 动作 | dc_action.action_code | `action_code` | `dc:actionCode` | query_opportunity_by_emp |
| 视图 | dc_object_view.view_code | `view_code` | `dc:viewCode` | employee_view |

引用关系：动作可填 `function_ref`（单函数，兼容）或 `function_refs`（数组，多个函数，按顺序调用），值为 function_code；可选 `script`（脚本内容）与 `script_type`（如 python）；`core_object_ref`/`object_ref` 填对象编码；relations 的 `source_object_ref`/`target_object_ref` 亦为对象编码；relations 可选 `action_ref` 填动作编码（action_code）。下方 JSON/YAML/OWL 示例中均包含上述编码字段用例。

**JSON 字段映射规则说明：**

| JSON 路径 | 对应数据库表/字段 | 说明 |
|-----------|-----------------|------|
| `metadata.domain_ref` | （可选）文件级默认领域，用于未显式写 domain_ref 的视图/对象 | 可选；领域以视图、对象的 `domain_ref` 为主 |
| `functions[*]` | dc_function | 全局函数定义 |
| **`functions[*].function_code`** | **dc_function.function_code** | **函数编码，必填，文件内唯一；如 fn_query_mysql** |
| `functions[*].api_schema` | dc_function.api_schema | API 类型函数的标准 OpenAPI 3.0.x 文档（单路径单方法） |
| `functions[*].carrier_config` | dc_function.carrier_config | PLUGIN/BOT/MCP 类型函数的载体配置 |
| `objects[*]` | dc_object | 对象定义 |
| **`objects[*].object_code`** | **dc_object.object_code** | **对象编码，必填，文件内唯一；如 sales_person** |
| `objects[*].object_type` | dc_object.object_type | 对象类型：API / KNOWLEDGE_BASE / ANALYTICS_DB |
| `objects[*].source_system` | dc_object.source_system | 来源系统标识 |
| `objects[*].domain_ref` | dc_object.domain_id → dc_domain | 对象所属领域（领域作为对象属性，必填或由 metadata.domain_ref 兜底） |
| `objects[*].source_config` | dc_object.source_config | 数据源配置（含 connector_type 及连接详情） |
| `objects[*].tags` | dc_object.tags | 对象标签打标（JSON 数组） |
| `objects[*].properties[*]` | dc_property | 对象属性 |
| `objects[*].actions[*]` | dc_action | 对象动作 |
| **`objects[*].actions[*].action_code`** | **dc_action.action_code** | **动作编码，必填，同一对象下唯一；如 query_opportunity_by_emp** |
| `objects[*].actions[*].script` | dc_action.script_type + script_content | 可选；可为字符串（脚本内容）或对象 `{ "type": "python", "content": "..." }`，type 写 script_type，content 写 script_content |
| `objects[*].actions[*].function_ref` | dc_action.function_id（兼容） | 可选，单个函数编码；与 function_refs 二选一或并存，视为 function_refs 首元素 |
| `objects[*].actions[*].function_refs` | dc_action_function | 函数编码数组，顺序对应 sort_order；至少一个函数或与 script 并存 |
| `objects[*].actions[*].tags` | dc_action.tags | 动作标签打标（JSON 数组） |
| `objects[*].actions[*].params[*]` | dc_param (action_id, parent_param_id=NULL) | 顶层动作参数 |
| `objects[*].actions[*].params[*].tags` | dc_param.tags | 参数标签打标（JSON 数组） |
| `objects[*].actions[*].params[*].children[*]` | dc_param (parent_param_id→父参数) | OBJECT/LIST 的子参数（层级递归） |
| `objects[*].actions[*].params[*].mapping_path` | dc_param.mapping_path | 参数级映射路径（指向函数 api_schema 的 JSON Path） |
| `objects[*].actions[*].params[*].ext_attrs` | dc_param.ext_attrs | 参数扩展属性（枚举值、校验规则、绑定的术语类型等） |
| `objects[*].actions[*].function_ref` | dc_action.function_id → dc_function（兼容） | 可选，单个函数编码 |
| `objects[*].actions[*].function_refs` | dc_action_function | 函数编码数组，对应多函数绑定 |
| `objects[*].properties[*].ext_attrs` | dc_property.ext_attrs | 属性扩展属性（枚举值、格式约束、绑定的术语类型等） |
| `relations[*]` | dc_object_relation | 对象间关系 |
| `relations[*].action_ref` | dc_object_relation.action_id → dc_action | 绑定的动作（非必填），值为 action_code；该动作须属于 source_object_ref 或 target_object_ref 所指对象之一 |
| `views[*]` | dc_object_view + dc_object_view_mapping | 视图定义 |
| **`views[*].view_code`** | **dc_object_view.view_code** | **视图编码，必填，文件内唯一；如 employee_view** |
| `views[*].tags` | dc_object_view.tags | 视图标签打标（JSON 数组） |
| `views[*].source_system` | dc_object_view.source_system | 视图来源系统标识 |
| `views[*].domain_ref` | dc_object_view.domain_id → dc_domain | 视图所属领域（领域作为视图属性，必填或由 metadata.domain_ref 兜底） |

##### 3.3.3.2 dataCloud 本体 YAML 格式规范（dc-ontology.yaml）

YAML 格式与 JSON 结构完全等价，更适合人工编辑和阅读。**编码字段**与 JSON 一致：`function_code`（函数）、`object_code`（对象）、`action_code`（动作）、`view_code`（视图）必填且文件内唯一；下方 YAML 示例中均包含上述编码用例。

```yaml
# dataCloud 本体定义文件（视图级；领域由 view/object 的 domain_ref 属性表达）
$schema: https://datacloud.io/schemas/ontology/v1.0
version: "1.0"
scope: VIEW

metadata:
  name: 销售分析本体
  description: 销售分析助手场景的完整本体定义
  author: admin
  created_time: "2026-02-10T10:00:00Z"
  tenant_id: TENANT_001
  domain_ref: sales  # 可选：文件级默认领域，未写 domain_ref 的 view/object 可继承

# ========== 全局函数（工具）定义 ==========
functions:
  # API 类型：使用 api_schema（标准 OpenAPI 3.0.x 文档）
  - function_code: fn_query_mysql
    function_name: MySQL通用查询函数
    function_type: API
    description: 通过SQL查询MySQL数据源并返回结果集
    api_schema:
      openapi: "3.0.3"
      info: { title: 数据服务查询, version: "1.0.0" }
      servers: [ { url: http://data-service:8082 } ]
      paths:
        /api/v1/query:
          post:
            operationId: fn_query_mysql
            x-timeout-ms: 30000
            parameters: []
            requestBody:
              required: true
              content:
                application/json:
                  schema:
                    type: object
                    required: [sql, datasource_id]
                    properties:
                      sql: { type: string, description: SQL语句 }
                      datasource_id: { type: string, description: 数据源ID }
                      sql_param_emp_no: { type: string, description: 动态参数员工工号 }
            responses:
              "200":
                description: 查询成功
                content:
                  application/json:
                    schema:
                      type: object
                      properties:
                        result_set: { type: array, items: { type: object } }

  # PLUGIN 类型：使用 carrier_config 内嵌参数
  - function_code: fn_aggregate_calc
    function_name: 聚合计算函数
    function_type: PLUGIN
    description: 对数据集进行聚合计算
    carrier_config:
      plugin_id: plugin_aggregate
      method: calculate
      params:
        input:
          - { name: dataset, type: LIST, required: true }
          - { name: agg_config, type: OBJECT, required: true }
        output:
          - { name: agg_result, type: OBJECT, required: true }

# ========== 对象定义 ==========
objects:
  - object_code: sales_person
    object_name: 员工对象
    object_type: ANALYTICS_DB
    source_system: crm_system  # 来源系统
    domain_ref: sales  # 所属领域
    description: 描述员工实体，对应 sales_person 表
    tags: [CRM, 员工, 高优]
    source_config:
      connector_type: mysql
      datasource_id: ds_sales
      table_name: sales_person
      primary_key: emp_no
      display_column: name
    properties:
      - property_code: emp_no
        property_name: 员工工号
        property_type: STRING
        required: true
        is_primary_key: true
        source_column: emp_no
      - property_code: name
        property_name: 姓名
        property_type: STRING
        required: true
        source_column: name
      - property_code: org_id
        property_name: 组织ID
        property_type: STRING
        required: true
        source_column: org_id
      - property_code: status
        property_name: 状态
        property_type: STRING
        required: true
        source_column: status
        ext_attrs: { term_type_id: TT_EMP_STATUS, term_type_code: emp_status, term_type_name: 员工状态 }
    actions:
      - action_code: query_emp_by_no
        action_name: 按工号查询员工
        action_type: BUSINESS
        function_refs: [fn_query_mysql]
        description: 根据员工工号查询员工基本信息
        visible: true
        tags: [查询, 高优]
        params:
          - { param_code: emp_no, param_name: 员工工号, param_type: STRING, direction: IN, required: true, mapping_path: "$.requestBody.sql_param_emp_no", tags: [主键], ext_attrs: { term_type_id: TT_EMP_NO, term_type_code: emp_no, term_type_name: 员工工号 } }
          - { param_code: datasource_id, param_name: 数据源, param_type: STRING, direction: IN, required: false, mapping_path: "$.requestBody.datasource_id", default_value: ds_sales }
          - { param_code: emp_info, param_name: 员工信息, param_type: OBJECT, direction: OUT, required: true, mapping_path: "$.response.result_set" }

  - object_code: sales_business_opportunity
    object_name: 商机对象
    object_type: API
    source_system: crm_system  # 来源系统
    domain_ref: crm  # 不同领域
    description: 描述商机实体，通过 CRM 接口获取数据
    tags: [CRM, 商机, 高优]
    source_config:
      connector_type: http
      base_url: https://crm-api.example.com/v2/opportunities
      auth:
        type: bearer
        token_endpoint: https://crm-api.example.com/oauth/token
      timeout_ms: 30000
      primary_key: id
      display_column: bo_name
    properties:
      - property_code: bo_name
        property_name: 商机名称
        property_type: STRING
        required: true
        source_column: bo_name
      - property_code: business_opportunity_process
        property_name: 商机状态
        property_type: STRING
        required: true
        source_column: business_opportunity_process
        ext_attrs: { term_type_id: TT_OPP_STATUS, term_type_code: opportunity_status, term_type_name: 商机状态 }
    actions:
      - action_code: query_opportunity_by_emp
        action_name: 按员工查询商机
        action_type: BUSINESS
        function_refs: [fn_query_mysql]
        script: { type: python, content: "# 可选脚本\n# def before_call(ctx): return ctx\n" }
        visible: true
        params:
          - { param_code: emp_no, param_name: 员工工号, param_type: STRING, direction: IN, required: true, mapping_path: "$.requestBody.sql_param_emp_no", ext_attrs: { term_type_id: TT_EMP_NO, term_type_code: emp_no, term_type_name: 员工工号 } }
          - { param_code: datasource_id, param_name: 数据源, param_type: STRING, direction: IN, required: false, mapping_path: "$.requestBody.datasource_id", default_value: ds_sales }
          - param_code: opportunity_list
            param_name: 商机列表
            param_type: LIST
            direction: OUT
            required: true
            mapping_path: "$.response.result_set"
            children:  # 子参数描述 LIST 元素结构
              - { param_code: bo_name, param_name: 商机名称, param_type: STRING, direction: OUT }
              - { param_code: customer_name, param_name: 客户名称, param_type: STRING, direction: OUT }
              - { param_code: contract_scale, param_name: 合同额, param_type: DECIMAL, direction: OUT }

# ========== 对象关系 ==========
relations:
  - relation_name: 员工负责商机
    source_object_ref: sales_person
    target_object_ref: sales_business_opportunity
    relation_type: ASSOCIATES
    cardinality: ONE_TO_MANY
    source_property_ref: emp_no
    target_property_ref: iwhale_cbm_emp_no
    action_ref: query_opportunity_by_emp   # 可选：绑定到某动作（action_code）

# ========== 视图定义 ==========
views:
  - view_code: employee_view
    view_name: 员工视图
    source_system: crm_system  # 来源系统
    domain_ref: sales  # 视图所属领域
    description: 以员工为中心聚合商机、合同、KPI、日报、考勤等对象
    tags: [销售概览, 高优]
    core_object_ref: sales_person
    related_objects:
      - object_ref: sales_business_opportunity
        relation_path: "sales_person.emp_no -> sales_business_opportunity.iwhale_cbm_emp_no"
      - object_ref: sales_person_kpi_detail
        relation_path: "sales_person.emp_no -> sales_person_kpi_detail.emp_no"
```

##### 3.3.3.3 dataCloud 本体 OWL 格式规范（dc-ontology.owl）

OWL（Web Ontology Language）格式基于 W3C 标准，使用 RDF/XML 序列化。dataCloud 自定义命名空间 `dc:` 扩展了标准 OWL 以表达动作（Action）、逻辑（Logic）、函数（Function）等概念。

**命名空间约定：**

| 前缀 | URI | 说明 |
|------|-----|------|
| `owl:` | `http://www.w3.org/2002/07/owl#` | OWL 标准 |
| `rdfs:` | `http://www.w3.org/2000/01/rdf-schema#` | RDFS 标准 |
| `xsd:` | `http://www.w3.org/2001/XMLSchema#` | XML Schema 数据类型 |
| `dc:` | `https://datacloud.io/ontology/` | dataCloud 本体命名空间 |
| `dcfn:` | `https://datacloud.io/ontology/function/` | dataCloud 函数命名空间 |
| `dcact:` | `https://datacloud.io/ontology/action/` | dataCloud 动作命名空间 |
| `dcview:` | `https://datacloud.io/ontology/view/` | dataCloud 视图命名空间 |

**概念映射：**

| dataCloud 概念 | OWL 映射 | 说明 |
|---------------|----------|------|
| Object（对象） | `owl:Class` | 业务对象定义为 OWL 类 |
| Property（属性） | `owl:DatatypeProperty` | 对象属性映射为数据属性 |
| Relation（关系） | `owl:ObjectProperty` | 对象间关系映射为对象属性；可选 `dc:actionRef`（xsd:string，值为 action_code）表示关系绑定的动作 |
| Action（动作） | `dc:Action`（自定义类） | OWL 无内置动作概念，通过 dc 命名空间扩展；可选 `dc:script`（xsd:string）、`dc:scriptType`（xsd:string）；多函数通过多个 `dc:invokesFunction` 三元组表达，顺序由文档顺序或 dc:sortOrder 等约定 |
| Function（函数） | `dc:Function`（自定义类） | 通过 dc 命名空间扩展 |
| View（视图） | `dc:ObjectView`（自定义类） | 通过 dc 命名空间扩展 |
| Param（参数） | `dc:Parameter`（自定义类） | 通过 dc 命名空间扩展 |
| **编码（函数/对象/动作/视图）** | **`dc:functionCode` / `dc:objectCode` / `dc:actionCode` / `dc:viewCode`** | **必填，与 JSON 中 function_code、object_code、action_code、view_code 一一对应；示例见下方 OWL 示例** |
| **领域（domain_ref）** | **`dc:domainRef`** | 视图、对象的所属领域编码，与 JSON 的 domain_ref 对应；领域作为视图/对象属性 |
| **API 函数接口定义** | **`dc:apiSchema`**（xsd:string，值为标准 OpenAPI 3.0.x 文档 JSON 字符串） | 仅 function_type=API 时使用；与 JSON 的 api_schema 对应；PLUGIN/BOT/MCP 用 dc:carrierConfig |
| tags（标签） | `dc:tags`（xsd:string，值为 JSON 数组字符串） | 视图、对象、动作、参数均可打标，如 `["CRM","高优"]` |
| ext_attrs（扩展属性，含绑定的术语类型） | `dc:extAttrs`（xsd:string，值为 JSON 对象字符串） | 属性、参数的扩展信息，如 `{"term_type_id":"TT_OPP_STATUS","term_type_code":"opportunity_status","term_type_name":"商机状态"}` |

> **注意**：动作层**无** inputMapping/outputMapping；参数映射由 dc_param.mapping_path 承载，OWL 中 Action 的 dc:hasParameter 仅描述抽象参数，映射细节在参数的 mapping_path（可存于 dc:mappingPath 等）或转换时从 JSON 获取。

**OWL 文件示例（RDF/XML 格式）：**

本示例与**3.3.5.2 节的 YAML 用例**表达同一套内容，便于对照：同一视图级范围（员工视图 + 员工对象 + 商机对象 + 两个函数 + 关系 + 动作与参数）。编码字段在 OWL 中为 `dc:functionCode`、`dc:objectCode`、`dc:actionCode`、`dc:viewCode`；领域为 `dc:domainRef`；API 函数用 `dc:apiSchema`，PLUGIN 函数用 `dc:carrierConfig`；视图的关联对象与关系路径用 `dc:includesObject`、`dc:relationPaths` 表达。

```xml
<?xml version="1.0" encoding="UTF-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
         xmlns:owl="http://www.w3.org/2002/07/owl#"
         xmlns:xsd="http://www.w3.org/2001/XMLSchema#"
         xmlns:dc="https://datacloud.io/ontology/"
         xmlns:dcfn="https://datacloud.io/ontology/function/"
         xmlns:dcact="https://datacloud.io/ontology/action/"
         xmlns:dcview="https://datacloud.io/ontology/view/">

  <!-- 本体声明 -->
  <owl:Ontology rdf:about="https://datacloud.io/ontology/sales">
    <rdfs:label>销售分析本体</rdfs:label>
    <rdfs:comment>销售分析助手场景的完整本体定义</rdfs:comment>
    <owl:versionInfo>1.0</owl:versionInfo>
    <dc:author>admin</dc:author>
    <dc:tenantId>TENANT_001</dc:tenantId>
  </owl:Ontology>

  <!-- ==================== dataCloud 元类定义 ==================== -->
  <owl:Class rdf:about="https://datacloud.io/ontology/Action">
    <rdfs:label>动作</rdfs:label>
    <rdfs:comment>对象上可执行的业务动作</rdfs:comment>
  </owl:Class>

  <owl:Class rdf:about="https://datacloud.io/ontology/Function">
    <rdfs:label>函数</rdfs:label>
    <rdfs:comment>可复用的计算逻辑</rdfs:comment>
  </owl:Class>

  <owl:Class rdf:about="https://datacloud.io/ontology/ObjectView">
    <rdfs:label>视图</rdfs:label>
    <rdfs:comment>以核心对象为中心的对象聚合视图</rdfs:comment>
  </owl:Class>

  <owl:Class rdf:about="https://datacloud.io/ontology/Parameter">
    <rdfs:label>参数</rdfs:label>
  </owl:Class>

  <!-- ==================== 函数（工具）定义 ==================== -->
  <!-- API 类型：使用 dc:apiSchema 存标准 OpenAPI 3.0.x 文档（JSON 字符串）；参数由 api_schema 内 requestBody/responses 描述，不在此处重复 hasParameter -->
  <dc:Function rdf:about="https://datacloud.io/ontology/function/fn_query_mysql">
    <rdfs:label>MySQL通用查询函数</rdfs:label>
    <dc:functionCode>fn_query_mysql</dc:functionCode>
    <dc:functionType>API</dc:functionType>
    <dc:apiSchema rdf:datatype="xsd:string">
      {"openapi":"3.0.3","info":{"title":"数据服务查询","version":"1.0.0"},"servers":[{"url":"http://data-service:8082"}],"paths":{"/api/v1/query":{"post":{"operationId":"fn_query_mysql","x-timeout-ms":30000,"parameters":[],"requestBody":{"required":true,"content":{"application/json":{"schema":{"type":"object","required":["sql","datasource_id"],"properties":{"sql":{"type":"string"},"datasource_id":{"type":"string"},"sql_param_emp_no":{"type":"string"}}}}}},"responses":{"200":{"description":"查询成功","content":{"application/json":{"schema":{"type":"object","properties":{"result_set":{"type":"array","items":{"type":"object"}}}}}}}}}}}}
    </dc:apiSchema>
  </dc:Function>

  <!-- PLUGIN 类型：使用 dc:carrierConfig 存载体配置（与 YAML 中 fn_aggregate_calc 对应） -->
  <dc:Function rdf:about="https://datacloud.io/ontology/function/fn_aggregate_calc">
    <rdfs:label>聚合计算函数</rdfs:label>
    <dc:functionCode>fn_aggregate_calc</dc:functionCode>
    <dc:functionType>PLUGIN</dc:functionType>
    <dc:carrierConfig rdf:datatype="xsd:string">
      {"plugin_id":"plugin_aggregate","method":"calculate","params":{"input":[{"name":"dataset","type":"LIST","required":true},{"name":"agg_config","type":"OBJECT","required":true}],"output":[{"name":"agg_result","type":"OBJECT","required":true}]}}
    </dc:carrierConfig>
  </dc:Function>

  <!-- ==================== 对象定义（OWL Class） ==================== -->
  <owl:Class rdf:about="https://datacloud.io/ontology/sales_person">
    <rdfs:label>员工对象</rdfs:label>
    <rdfs:comment>描述员工实体，对应 sales_person 表</rdfs:comment>
    <dc:objectCode>sales_person</dc:objectCode>
    <dc:domainRef>sales</dc:domainRef>
    <dc:objectType>ANALYTICS_DB</dc:objectType>
    <dc:sourceSystem>crm_system</dc:sourceSystem>
    <dc:tags rdf:datatype="xsd:string">["CRM","员工","高优"]</dc:tags>
    <dc:sourceConfig rdf:datatype="xsd:string">
      {"connector_type":"mysql","datasource_id":"ds_sales","table_name":"sales_person","primary_key":"emp_no"}
    </dc:sourceConfig>
  </owl:Class>

  <!-- 对象属性（DatatypeProperty） -->
  <owl:DatatypeProperty rdf:about="https://datacloud.io/ontology/sales_person/emp_no">
    <rdfs:label>员工工号</rdfs:label>
    <rdfs:domain rdf:resource="https://datacloud.io/ontology/sales_person"/>
    <rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/>
    <dc:propertyCode>emp_no</dc:propertyCode>
    <dc:sourceColumn>emp_no</dc:sourceColumn>
    <dc:isPrimaryKey rdf:datatype="xsd:boolean">true</dc:isPrimaryKey>
    <dc:isRequired rdf:datatype="xsd:boolean">true</dc:isRequired>
  </owl:DatatypeProperty>

  <owl:DatatypeProperty rdf:about="https://datacloud.io/ontology/sales_person/name">
    <rdfs:label>姓名</rdfs:label>
    <rdfs:domain rdf:resource="https://datacloud.io/ontology/sales_person"/>
    <rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/>
    <dc:propertyCode>name</dc:propertyCode>
    <dc:sourceColumn>name</dc:sourceColumn>
    <dc:isRequired rdf:datatype="xsd:boolean">true</dc:isRequired>
  </owl:DatatypeProperty>

  <owl:DatatypeProperty rdf:about="https://datacloud.io/ontology/sales_person/org_id">
    <rdfs:label>组织ID</rdfs:label>
    <rdfs:domain rdf:resource="https://datacloud.io/ontology/sales_person"/>
    <rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/>
    <dc:propertyCode>org_id</dc:propertyCode>
    <dc:sourceColumn>org_id</dc:sourceColumn>
    <dc:isRequired rdf:datatype="xsd:boolean">true</dc:isRequired>
  </owl:DatatypeProperty>

  <owl:DatatypeProperty rdf:about="https://datacloud.io/ontology/sales_person/status">
    <rdfs:label>状态</rdfs:label>
    <rdfs:domain rdf:resource="https://datacloud.io/ontology/sales_person"/>
    <rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/>
    <dc:propertyCode>status</dc:propertyCode>
    <dc:sourceColumn>status</dc:sourceColumn>
    <dc:isRequired rdf:datatype="xsd:boolean">true</dc:isRequired>
    <dc:extAttrs rdf:datatype="xsd:string">{"term_type_id":"TT_EMP_STATUS","term_type_code":"emp_status","term_type_name":"员工状态"}</dc:extAttrs>
  </owl:DatatypeProperty>

  <!-- 属性扩展：绑定的术语类型（ext_attrs 存 JSON） -->
  <owl:DatatypeProperty rdf:about="https://datacloud.io/ontology/sales_business_opportunity/business_opportunity_process">
    <rdfs:label>商机状态</rdfs:label>
    <rdfs:domain rdf:resource="https://datacloud.io/ontology/sales_business_opportunity"/>
    <rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/>
    <dc:propertyCode>business_opportunity_process</dc:propertyCode>
    <dc:sourceColumn>business_opportunity_process</dc:sourceColumn>
    <dc:isRequired rdf:datatype="xsd:boolean">true</dc:isRequired>
    <dc:extAttrs rdf:datatype="xsd:string">{"term_type_id":"TT_OPP_STATUS","term_type_code":"opportunity_status","term_type_name":"商机状态"}</dc:extAttrs>
  </owl:DatatypeProperty>

  <!-- 商机对象属性 bo_name（与 YAML 中 properties 一致） -->
  <owl:DatatypeProperty rdf:about="https://datacloud.io/ontology/sales_business_opportunity/bo_name">
    <rdfs:label>商机名称</rdfs:label>
    <rdfs:domain rdf:resource="https://datacloud.io/ontology/sales_business_opportunity"/>
    <rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/>
    <dc:propertyCode>bo_name</dc:propertyCode>
    <dc:sourceColumn>bo_name</dc:sourceColumn>
    <dc:isRequired rdf:datatype="xsd:boolean">true</dc:isRequired>
  </owl:DatatypeProperty>

  <!-- 商机对象 -->
  <owl:Class rdf:about="https://datacloud.io/ontology/sales_business_opportunity">
    <rdfs:label>商机对象</rdfs:label>
    <dc:objectCode>sales_business_opportunity</dc:objectCode>
    <dc:domainRef>crm</dc:domainRef>
    <dc:objectType>API</dc:objectType>
    <dc:sourceSystem>crm_system</dc:sourceSystem>
    <dc:tags rdf:datatype="xsd:string">["CRM","商机","高优"]</dc:tags>
    <dc:sourceConfig rdf:datatype="xsd:string">
      {"connector_type":"http","base_url":"https://crm-api.example.com/v2/opportunities","timeout_ms":30000}
    </dc:sourceConfig>
  </owl:Class>

  <!-- 对象：员工KPI明细（与 YAML 视图 related_objects 第二项对应，仅占位以便视图引用） -->
  <owl:Class rdf:about="https://datacloud.io/ontology/sales_person_kpi_detail">
    <rdfs:label>员工KPI明细</rdfs:label>
    <dc:objectCode>sales_person_kpi_detail</dc:objectCode>
    <dc:domainRef>sales</dc:domainRef>
  </owl:Class>

  <!-- ==================== 对象关系（ObjectProperty） ==================== -->
  <owl:ObjectProperty rdf:about="https://datacloud.io/ontology/relation/emp_has_opportunity">
    <rdfs:label>员工负责商机</rdfs:label>
    <rdfs:domain rdf:resource="https://datacloud.io/ontology/sales_person"/>
    <rdfs:range rdf:resource="https://datacloud.io/ontology/sales_business_opportunity"/>
    <dc:relationType>ASSOCIATES</dc:relationType>
    <dc:cardinality>ONE_TO_MANY</dc:cardinality>
    <dc:sourcePropertyRef>emp_no</dc:sourcePropertyRef>
    <dc:targetPropertyRef>iwhale_cbm_emp_no</dc:targetPropertyRef>
    <dc:actionRef>query_opportunity_by_emp</dc:actionRef>
  </owl:ObjectProperty>

  <!-- ==================== 动作定义 ==================== -->
  <!-- 员工对象动作（与 YAML 中 sales_person.actions.query_emp_by_no 对应）；多函数可重复 dc:invokesFunction -->
  <dc:Action rdf:about="https://datacloud.io/ontology/action/query_emp_by_no">
    <rdfs:label>按工号查询员工</rdfs:label>
    <dc:actionCode>query_emp_by_no</dc:actionCode>
    <dc:actionType>BUSINESS</dc:actionType>
    <dc:tags rdf:datatype="xsd:string">["查询","高优"]</dc:tags>
    <dc:belongsToObject rdf:resource="https://datacloud.io/ontology/sales_person"/>
    <dc:isVisible rdf:datatype="xsd:boolean">true</dc:isVisible>
    <dc:invokesFunction rdf:resource="https://datacloud.io/ontology/function/fn_query_mysql"/>
    <dc:hasParameter>
      <dc:Parameter><dc:paramCode>emp_no</dc:paramCode><dc:paramName>员工工号</dc:paramName><dc:paramType>STRING</dc:paramType><dc:direction>IN</dc:direction><dc:required rdf:datatype="xsd:boolean">true</dc:required><dc:tags rdf:datatype="xsd:string">["主键"]</dc:tags><dc:extAttrs rdf:datatype="xsd:string">{"term_type_id":"TT_EMP_NO","term_type_code":"emp_no","term_type_name":"员工工号"}</dc:extAttrs></dc:Parameter>
    </dc:hasParameter>
    <dc:hasParameter>
      <dc:Parameter><dc:paramCode>datasource_id</dc:paramCode><dc:paramName>数据源</dc:paramName><dc:paramType>STRING</dc:paramType><dc:direction>IN</dc:direction><dc:required rdf:datatype="xsd:boolean">false</dc:required><dc:defaultValue>ds_sales</dc:defaultValue></dc:Parameter>
    </dc:hasParameter>
    <dc:hasParameter>
      <dc:Parameter><dc:paramCode>emp_info</dc:paramCode><dc:paramName>员工信息</dc:paramName><dc:paramType>OBJECT</dc:paramType><dc:direction>OUT</dc:direction><dc:required rdf:datatype="xsd:boolean">true</dc:required></dc:Parameter>
    </dc:hasParameter>
  </dc:Action>

  <!-- 商机对象动作（与 YAML 中 sales_business_opportunity.actions.query_opportunity_by_emp 对应）；可选脚本 + 多函数（多个 dc:invokesFunction） -->
  <dc:Action rdf:about="https://datacloud.io/ontology/action/query_opportunity_by_emp">
    <rdfs:label>按员工查询商机</rdfs:label>
    <dc:actionCode>query_opportunity_by_emp</dc:actionCode>
    <dc:actionType>BUSINESS</dc:actionType>
    <dc:tags rdf:datatype="xsd:string">["查询","商机","高优"]</dc:tags>
    <dc:belongsToObject rdf:resource="https://datacloud.io/ontology/sales_business_opportunity"/>
    <dc:isVisible rdf:datatype="xsd:boolean">true</dc:isVisible>
    <dc:scriptType rdf:datatype="xsd:string">python</dc:scriptType>
    <dc:script rdf:datatype="xsd:string"><![CDATA[# 可选脚本
# def before_call(ctx): return ctx
]]></dc:script>
    <dc:invokesFunction rdf:resource="https://datacloud.io/ontology/function/fn_query_mysql"/>
    <dc:invokesFunction rdf:resource="https://datacloud.io/ontology/function/fn_aggregate_calc"/>
    <!-- 动作参数（与 dc_param 对应；映射关系在参数的 mapping_path，此处仅描述抽象参数） -->
    <dc:hasParameter>
      <dc:Parameter>
        <dc:paramCode>emp_no</dc:paramCode>
        <dc:paramName>员工工号</dc:paramName>
        <dc:paramType>STRING</dc:paramType>
        <dc:direction>IN</dc:direction>
        <dc:required rdf:datatype="xsd:boolean">true</dc:required>
        <dc:tags rdf:datatype="xsd:string">["主键"]</dc:tags>
        <dc:extAttrs rdf:datatype="xsd:string">{"term_type_id":"TT_EMP_NO","term_type_code":"emp_no","term_type_name":"员工工号"}</dc:extAttrs>
      </dc:Parameter>
    </dc:hasParameter>
    <dc:hasParameter>
      <dc:Parameter>
        <dc:paramCode>datasource_id</dc:paramCode>
        <dc:paramName>数据源</dc:paramName>
        <dc:paramType>STRING</dc:paramType>
        <dc:direction>IN</dc:direction>
        <dc:required rdf:datatype="xsd:boolean">false</dc:required>
        <dc:defaultValue>ds_sales</dc:defaultValue>
      </dc:Parameter>
    </dc:hasParameter>
    <dc:hasParameter>
      <dc:Parameter>
        <dc:paramCode>opportunity_list</dc:paramCode>
        <dc:paramName>商机列表</dc:paramName>
        <dc:paramType>LIST</dc:paramType>
        <dc:direction>OUT</dc:direction>
        <dc:required rdf:datatype="xsd:boolean">true</dc:required>
        <!-- LIST 子参数（children）与 YAML 中 bo_name、customer_name、contract_scale 对应，可由 mapping_path 或 extAttrs 表达 -->
      </dc:Parameter>
    </dc:hasParameter>
  </dc:Action>

  <!-- ==================== 视图定义 ==================== -->
  <!-- 与 YAML 中 views.employee_view 一致：core_object_ref + related_objects（含 relation_path） -->
  <dc:ObjectView rdf:about="https://datacloud.io/ontology/view/employee_view">
    <rdfs:label>员工视图</rdfs:label>
    <rdfs:comment>以员工为中心聚合商机、合同、KPI、日报、考勤等对象</rdfs:comment>
    <dc:viewCode>employee_view</dc:viewCode>
    <dc:domainRef>sales</dc:domainRef>
    <dc:sourceSystem>crm_system</dc:sourceSystem>
    <dc:tags rdf:datatype="xsd:string">["销售概览","高优"]</dc:tags>
    <dc:coreObject rdf:resource="https://datacloud.io/ontology/sales_person"/>
    <dc:includesObject rdf:resource="https://datacloud.io/ontology/sales_business_opportunity"/>
    <dc:includesObject rdf:resource="https://datacloud.io/ontology/sales_person_kpi_detail"/>
    <dc:relationPaths rdf:datatype="xsd:string">["sales_person.emp_no -&gt; sales_business_opportunity.iwhale_cbm_emp_no","sales_person.emp_no -&gt; sales_person_kpi_detail.emp_no"]</dc:relationPaths>
  </dc:ObjectView>

</rdf:RDF>
```