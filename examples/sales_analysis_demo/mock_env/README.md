# sales-analysis-demo

DataCloud Mock 是 dataCloud 2.0 的**数据仿真系统**，用于提供 API Mock 响应、数据示例与本体等，支撑开发与联调。

## 核心定位

- **仿真服务**：为开发/测试环境提供模拟 API 与可启动的聚合服务。
- **多子系统**：按业务子系统（如 `crm_demo`）组织文档、本体、服务代码与测试。

---

## 目录结构约定

按「文档 / 本体 / 服务代码 / 测试」分离，子系统在各自顶层目录下再分子目录。

```text
sales-analysis-demo/
├── README.md                 # 本说明
├── pyproject.toml            # 项目与依赖
│
├── resource/                 # 仿真资源统一入口（结构化数据、知识、非结构化数据）
│   ├── data/                 # 结构化业务数据（表数据、CSV/SQL）
│   │   └── crm_demo/
│   │       └── ...
│   ├── knowledge/            # 知识资源（本体 + 术语）
│   │   └── crm_demo/
│   │       ├── ontology/
│   │       └── terminology/
│   └── files/                # 非结构化数据（文档、附件、原始文件）
│       └── ...
│
├── docs/                     # 文档（按子系统分子文件夹）
│   └── crm_demo/             # 示例：CRM 演示子系统文档
│       └── *.md
│
├── data_tools/               # 资源加工脚本（数据修正、生成、本体处理）
│   └── *.py
│
├── scripts/                  # 运行脚本（启动、初始化、测试）
│   └── *.sh
│
├── src/
│   └── sales_analysis_demo/  # 仿真服务代码（包名：下划线）
│       ├── __init__.py
│       ├── main.py           # 服务总入口（FastAPI app）
│       ├── apis/             # API 路由
│       │   └── __init__.py
│       ├── db/               # 数据库访问层
│       │   └── __init__.py
│       └── notice.py         # 业务通知逻辑
│
└── tests/                    # 测试用例（按子系统分子目录）
    └── crm_demo/
        └── test_*.py
```

### Python 工程上的建议

- **包与目录名**：Python 包名用**下划线**（如 `sales_analysis_demo`），不要用连字符（`sales-analysis-demo` 不能作为包导入）。
- **服务入口**：统一从 `src/sales_analysis_demo/main.py` 的 FastAPI `app` 启动；各子系统的路由在 `main.py` 中挂载（mount 或 include_router）。

---

## resource（仿真资源）

仿真资源统一放在 **`resource/`** 下，按用途分为三个子目录：

| 目录 | 用途 |
| ------ | ------ |
| **resource/data** | 放结构化数据（业务表数据、CSV、导入 SQL 等，可按子系统如 `crm_demo` 再分子目录） |
| **resource/knowledge** | 放知识（本体 ontology + 术语 terminology，按子系统分子目录） |
| **resource/files** | 放非结构化数据文件（文档、附件、原始文件等） |

服务与脚本统一从 `resource` 下读取，避免多入口路径。

---

## 1. 文档（docs）

- **用途**：设计说明、接口说明、场景说明等，与代码分离存放。
- **规则**：
  - 根目录：`docs/`
  - 按子系统分子文件夹：`docs/<子系统名>/`，如 `docs/crm_demo/`
  - 其下直接放各类 `.md` 或子目录（如按模块再分子文件夹）。

**创建示例**（按需执行）：

```bash
mkdir -p docs/crm_demo
# 然后在 docs/crm_demo/ 下添加 销售场景概述.md 等
```

---

## 2. 本体（ontology）

- **用途**：存放各子系统的 OWL 等本体文件。
- **规则**：
  - 根目录：`ontology/`
  - 按子系统：`ontology/<子系统名>/`
  - 每个子系统下建议两子目录：
    - `common/`：公共本体
    - `modules/`：按模块划分的本体（目录名为 **modules**，不要写成 moduels）
  - 最底层放具体 `*.owl` 文件。

**创建示例**：

```bash
mkdir -p ontology/crm_demo/common
mkdir -p ontology/crm_demo/modules
# 在 common/ 或 modules/ 下添加 xxx.owl
```

---

## 3. 服务代码（src/sales_analysis_demo）

- **用途**：仿真的 API 服务逻辑，可被 `main.py` 统一启动。
- **规则**：
  - 包根目录：`src/sales_analysis_demo/`
  - **总入口**：`main.py`，其中创建 FastAPI `app`，并挂载各子系统的路由。
  - 推荐直接在 `sales_analysis_demo/` 下分层：
    - `apis/`：接口（Blueprint/Router），在 `main.py` 中挂载。
    - `db/`：数据库连接与模型。
    - 初始化逻辑统一放在 `scripts/` 与 `tests/`，避免耦合到服务运行时包。

**创建示例**：

```bash
mkdir -p src/sales_analysis_demo/apis
mkdir -p src/sales_analysis_demo/db
touch src/sales_analysis_demo/apis/__init__.py
touch src/sales_analysis_demo/db/__init__.py
```

在 `main.py` 中挂载子系统路由示例：

```python
# 在 main.py 中
from fastapi import FastAPI
from sales_analysis_demo.apis import router as crm_router

app = FastAPI(title="sales-analysis-demo")
app.include_router(crm_router, prefix="/crm_demo", tags=["crm_demo"])
```

---

## 4. 测试（tests）

- **用途**：单测、接口测试等。
- **规则**：
  - 根目录：`tests/`
  - 按测试类型或模块分组：如 `tests/type1_db_schema/`、`tests/type3_api_service/`
  - 测试文件命名：`test_*.py`，便于 pytest 自动发现。

**创建示例**：

```bash
mkdir -p tests/type1_db_schema
# 添加 test_xxx.py
```

---

## 5. 结构化数据（resource/data）

- **用途**：结构化业务数据（CSV、导入 SQL 等），与代码分离。
- **规则**：按子系统建 `resource/data/<子系统名>/`，其下再按业务或模块分子目录。
- **推荐**：数据、本体、术语统一放 `resource` 下管理（参见 [resource（仿真资源）](#resource仿真资源)）。

## 6. 非结构化数据（resource/files）

- **用途**：文档、附件、原始文件等非结构化数据。
- **规则**：按场景或主题分子目录组织，避免与结构化表数据混放。

---

## 服务启动

### 方式一：通过 uvicorn 运行 main（推荐）

```bash
# 在仓库根目录（含 pyproject.toml 的目录）
uv sync
uv run uvicorn sales_analysis_demo.main:app --reload --host 0.0.0.0 --port 8000
```

- 默认地址：<http://127.0.0.1:8000>
- 文档：<http://127.0.0.1:8000/docs>

### 方式二：以模块方式运行（需 main.py 内启动 uvicorn）

若在 `main.py` 中写了 `if __name__ == "__main__": uvicorn.run(app, ...)`，则：

```bash
uv run python -m sales_analysis_demo.main
```

### 方式三：命令行入口（若已配置 pyproject scripts）

```bash
uv run sales-analysis-demo
```

（当前 `pyproject.toml` 中配置为 `sales_analysis_demo.cli:main`，若未实现 `cli.py` 则此命令可能不可用，以方式一为准。）

### 方式四：使用 scripts 目录脚本

```bash
# 初始化/刷新资源
bash scripts/bootstrap_resources.sh

# 启动 mock API
bash scripts/start_mock_api.sh

# 执行 mock_env 测试
bash scripts/run_mock_tests.sh
```

---

## 快速自检

```bash
# 安装依赖
uv sync

# 启动服务（任选一种）
uv run uvicorn sales_analysis_demo.main:app --reload --port 8000

# 运行测试
uv run pytest tests/ -v
```

---

## 许可证

MIT License
