# datacloud-mock

DataCloud Mock 是 dataCloud 2.0 的**数据仿真系统**，用于提供 API Mock 响应、数据示例与本体等，支撑开发与联调。

## 核心定位

- **仿真服务**：为开发/测试环境提供模拟 API 与可启动的聚合服务。
- **多子系统**：按业务子系统（如 `crm_demo`）组织文档、本体、服务代码与测试。

---

## 目录结构约定

按「文档 / 本体 / 服务代码 / 测试」分离，子系统在各自顶层目录下再分子目录。

```
datacloud-mock/
├── README.md                 # 本说明
├── pyproject.toml            # 项目与依赖
│
├── docs/                     # 文档（按子系统分子文件夹）
│   └── crm_demo/             # 示例：CRM 演示子系统文档
│       └── *.md
│
├── ontology/                 # 本体（按子系统分子文件夹，再按 common / modules）
│   └── crm_demo/
│       ├── common/           # 公共本体
│       │   └── *.owl
│       └── modules/          # 模块本体（注意是 modules 不是 moduels）
│           └── *.owl
│
├── src/
│   └── datacloud_mock/       # 仿真服务代码（包名：下划线）
│       ├── __init__.py
│       ├── main.py           # 服务总入口（FastAPI app）
│       └── crm_demo/         # 示例：CRM 演示子系统
│           ├── __init__.py
│           ├── apis/         # 该子系统的 API 路由
│           │   └── __init__.py
│           └── data_init/    # 数据初始化脚本（建议用下划线，便于 import）
│               └── __init__.py
│
├── data/                     # 数据文件（CSV、配置等，可按子系统分子目录）
│   └── crm_demo/
│       └── ...
│
└── tests/                    # 测试用例（按子系统分子目录）
    └── crm_demo/
        └── test_*.py
```

### Python 工程上的建议

- **包与目录名**：Python 包名用**下划线**（如 `data_init`），不要用连字符（`data-init` 不能作为包导入）。
- **服务入口**：统一从 `src/datacloud_mock/main.py` 的 FastAPI `app` 启动；各子系统的路由在 `main.py` 中挂载（mount 或 include_router）。

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

## 3. 服务代码（src/datacloud_mock）

- **用途**：仿真的 API 与数据初始化逻辑，可被 `main.py` 统一启动。
- **规则**：
  - 包根目录：`src/datacloud_mock/`
  - **总入口**：`main.py`，其中创建 FastAPI `app`，并挂载各子系统的路由。
  - 按子系统分子包：`datacloud_mock/<子系统名>/`，如 `crm_demo/`
  - 每个子系统下建议：
    - `apis/`：该子系统的接口（Blueprint/Router），在 `main.py` 中挂载。
    - `data_init/`：数据初始化脚本（建表、导入 CSV 等）；若需被其他代码 import，目录名用下划线 `data_init`。

**创建示例**：

```bash
mkdir -p src/datacloud_mock/crm_demo/apis
mkdir -p src/datacloud_mock/crm_demo/data_init
touch src/datacloud_mock/crm_demo/__init__.py
touch src/datacloud_mock/crm_demo/apis/__init__.py
touch src/datacloud_mock/crm_demo/data_init/__init__.py
```

在 `main.py` 中挂载子系统路由示例：

```python
# 在 main.py 中
from fastapi import FastAPI
from datacloud_mock.crm_demo.apis import router as crm_router

app = FastAPI(title="datacloud-mock")
app.include_router(crm_router, prefix="/crm_demo", tags=["crm_demo"])
```

---

## 4. 测试（tests）

- **用途**：单测、接口测试等。
- **规则**：
  - 根目录：`tests/`
  - 按子系统：`tests/<子系统名>/`，如 `tests/crm_demo/`
  - 测试文件命名：`test_*.py`，便于 pytest 自动发现。

**创建示例**：

```bash
mkdir -p tests/crm_demo
# 添加 test_xxx.py
```

---

## 5. 数据文件（data）

- **用途**：CSV 示例、配置等，与代码分离。
- **规则**：可按子系统建 `data/<子系统名>/`，其下再按业务或模块分子目录。

---

## 服务启动

### 方式一：通过 uvicorn 运行 main（推荐）

```bash
# 在仓库根目录（含 pyproject.toml 的目录）
uv sync
uv run uvicorn datacloud_mock.main:app --reload --host 0.0.0.0 --port 8000
```

- 默认地址：<http://127.0.0.1:8000>
- 文档：<http://127.0.0.1:8000/docs>

### 方式二：以模块方式运行（需 main.py 内启动 uvicorn）

若在 `main.py` 中写了 `if __name__ == "__main__": uvicorn.run(app, ...)`，则：

```bash
uv run python -m datacloud_mock.main
```

### 方式三：命令行入口（若已配置 pyproject scripts）

```bash
uv run datacloud-mock
```

（当前 `pyproject.toml` 中配置为 `datacloud_mock.cli:main`，若未实现 `cli.py` 则此命令可能不可用，以方式一为准。）

---

## 快速自检

```bash
# 安装依赖
uv sync

# 启动服务（任选一种）
uv run uvicorn datacloud_mock.main:app --reload --port 8000

# 运行测试
uv run pytest tests/ -v
```

---

## 许可证

MIT License
