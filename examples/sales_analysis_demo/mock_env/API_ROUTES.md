# datacloud-mock API 接口清单

## 启动方式

```bash
cd datacloud-mock
PYTHONPATH=src uvicorn datacloud_mock.main:app --host 0.0.0.0 --port 8000
```

或使用 VSCode launch 配置「启动 datacloud-mock」（需设置 `cwd` 和 `PYTHONPATH`）。

## 前置条件

1. **PostgreSQL**：PO、Todo、Expense 接口依赖数据库，需配置 `DATABASE_URL`（默认 `postgresql+asyncpg://localhost:5432/crm_demo`）
2. **Redis**（可选）：Todo 模块依赖 redis，未安装时 todo 相关接口不会挂载，但 **PO 接口可正常使用**

## 调试：查看已注册路由

```bash
curl http://127.0.0.1:8000/api/routes
```

## 已注册的 API 接口

### 人员组织 (PO) - ontology 使用路径

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/po/users/query` | 按用户ID或名称查询人员 |
| POST | `/api/v1/po/users/by-org` | 按组织ID查询人员 |
| POST | `/api/v1/po/organizations/query` | 按组织ID或名称查询组织 |
| POST | `/api/v1/po/organizations/children` | 查询下级组织 |

### 兼容路径（带 crm_demo 前缀）

| 方法 | 路径 |
|------|------|
| POST | `/api/v1/crm_demo/po/users/query` |
| POST | `/api/v1/crm_demo/po/users/by-org` |
| POST | `/api/v1/crm_demo/po/organizations/query` |
| POST | `/api/v1/crm_demo/po/organizations/children` |

### 示例请求

```bash
# 按组织ID查询人员（ontology 调用的路径）
curl -X POST 'http://127.0.0.1:8000/api/v1/po/users/by-org' \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer your-token' \
  -H 'X-Tenant-Id: tenant-001' \
  -d '{"orgId": "6979", "includeSubOrgs": false}'
```

### 其他接口

- `GET /` - 服务信息
- `GET /health` - 健康检查
- `GET /api/routes` - 列出所有 API 路由（调试）
- `GET /docs` - Swagger UI
