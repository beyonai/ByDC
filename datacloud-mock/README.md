# datacloud-mock

DataCloud Mock 是 dataCloud 2.0 的辅助服务，用于提供 API Mock 响应和数据示例存放。

## 核心定位

**Mock 服务**：为开发和测试环境提供模拟数据和 API 响应。

## 核心功能

### 1. API Mock

- **Mock 数据管理**：提供预定义的 API 响应数据
- **动态 Mock**：支持基于请求参数的动态响应
- **场景模拟**：模拟各种业务场景和边界情况

### 2. 数据示例

- **CSV 数据示例**：存放各类业务数据的 CSV 示例文件
- **数据模板**：提供标准数据格式模板
- **测试数据**：为单元测试和集成测试提供数据支持

### 3. 数据管理

- **数据分类**：按业务领域组织数据文件
- **版本控制**：数据文件与代码同步版本管理
- **数据导入**：支持将 CSV 数据导入到测试数据库

## 项目结构

```
datacloud-mock/
├── README.md              # 本文件
├── pyproject.toml         # 项目配置
├── src/
│   └── datacloud_mock/    # 核心代码
│       ├── __init__.py
│       ├── api/           # API Mock 路由
│       ├── data/          # 数据管理模块
│       └── cli.py         # 命令行入口
├── data/                  # 数据文件目录
│   ├── api/               # API Mock 响应数据
│   └── examples/          # 数据示例 CSV 文件
└── tests/                 # 测试文件
```

## 数据文件规范

### CSV 文件格式

- 使用 UTF-8 编码
- 第一行为表头
- 使用逗号作为分隔符
- 文本字段使用双引号包裹（包含逗号或换行时）

### 文件命名规范

- 使用小写字母
- 使用下划线分隔单词
- 格式：`{domain}_{entity}_{type}.csv`
- 示例：`sales_order_sample.csv`, `user_profile_template.csv`

## 快速开始

```bash
# 安装依赖（在根目录执行，会自动安装所有 workspace 成员）
uv sync

# 启动 Mock 服务
uv run --package datacloud-mock python -m datacloud_mock.main

# 或者使用命令行
uv run --package datacloud-mock datacloud-mock
```

## 许可证

MIT License
