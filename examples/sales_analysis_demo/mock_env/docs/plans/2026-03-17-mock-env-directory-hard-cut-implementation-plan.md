# Mock Env Directory Hard Cut Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 `mock_env` 目录硬切到统一 `resource` 结构，并同步更新代码/脚本/文档引用，确保可运行。

**Architecture:** 保持 `src` 与 `db` 结构不变，将所有资源入口收敛到 `resource/`。先迁移文件，再替换路径引用，最后执行静态验证与运行校验。迁移采用“先复制验证，再删除旧目录”的顺序降低丢文件风险。

**Tech Stack:** Python 3.12, FastAPI, shell file operations, ripgrep, compileall

---

### Task 1: 创建新目录骨架

**Files:**
- Create: `examples/sales_analysis_demo/mock_env/resource/data/crm_demo/`
- Create: `examples/sales_analysis_demo/mock_env/resource/knowledge/crm_demo/`
- Create: `examples/sales_analysis_demo/mock_env/resource/files/`

**Step 1: 创建目录**

Run: `mkdir -p resource/data/crm_demo resource/knowledge/crm_demo resource/files`

**Step 2: 验证目录存在**

Run: `ls resource`
Expected: 包含 `data`、`knowledge`、`files`

---

### Task 2: 迁移资源文件（硬切）

**Files:**
- Move: `examples/sales_analysis_demo/mock_env/mock-resource/data/crm_demo/**`
- Move: `examples/sales_analysis_demo/mock_env/mock-resource/ontology/crm_demo/**`
- Move: `examples/sales_analysis_demo/mock_env/mock-resource/files/**`
- Move: `examples/sales_analysis_demo/mock_env/data/term_example/**`

**Step 1: 迁移数据目录**

Run: `move mock-resource/data/crm_demo -> resource/data/crm_demo`

**Step 2: 迁移知识目录**

Run: `move mock-resource/ontology/crm_demo -> resource/knowledge/crm_demo/ontology`

**Step 3: 迁移术语目录**

Run: `move data/term_example/* -> resource/knowledge/crm_demo/terminology/`

**Step 4: 迁移外部文件目录**

Run: `move mock-resource/files/* -> resource/files/`

**Step 5: 删除空旧目录**

Run: 删除 `mock-resource/` 与 `data/term_example/` 空壳目录

---

### Task 3: 替换代码与脚本中的旧路径

**Files:**
- Modify: `examples/sales_analysis_demo/mock_env/scripts/generate_ontology.py`
- Modify: `examples/sales_analysis_demo/mock_env/scripts/gen_kpi_completion.py`
- Modify: `examples/sales_analysis_demo/mock_env/scripts/gen_attendance.py`
- Modify: `examples/sales_analysis_demo/mock_env/scripts/fix_and_generate_crm_data.py`
- Modify: `examples/sales_analysis_demo/mock_env/scripts/add_bo_bulk.py`
- Modify: `examples/sales_analysis_demo/mock_env/scripts/convert_functions_to_post.py`

**Step 1: 全局搜索旧路径**

Run: `rg "mock-resource|data/term_example" examples/sales_analysis_demo/mock_env`

**Step 2: 逐文件替换为新路径**

- `mock-resource/data/...` -> `resource/data/...`
- `mock-resource/ontology/...` -> `resource/knowledge/.../ontology/...`
- `mock-resource/files/...` -> `resource/files/...`
- `data/term_example/...` -> `resource/knowledge/crm_demo/terminology/...`

**Step 3: 保存并复查**

Run: `rg "mock-resource|data/term_example" ...`
Expected: 仅可能残留在历史设计文档中，不应出现在运行脚本与说明中。

---

### Task 4: 更新用户文档路径

**Files:**
- Modify: `examples/sales_analysis_demo/mock_env/README.md`
- Modify: `examples/sales_analysis_demo/mock_env/docs/crm_demo/销售场景概述.md`

**Step 1: 更新示例路径**

- `datacloud-mock/mock-resource/files/...` -> `datacloud-mock/resource/files/...`
- 资源总入口描述改为 `resource/*`

**Step 2: 校验文档一致性**

Run: `rg "mock-resource|term_example" docs README.md`

---

### Task 5: 验证目录与代码可用

**Files:**
- Validate: `examples/sales_analysis_demo/mock_env/resource/**`
- Validate: `examples/sales_analysis_demo/mock_env/src/**`
- Validate: `examples/sales_analysis_demo/mock_env/scripts/**`

**Step 1: 验证资源目录**

Run: `rg --files resource`
Expected: 能看到全部 CRM 数据、本体、术语、外部文件。

**Step 2: Python 静态编译检查**

Run: `python -m compileall src scripts`
Expected: 无语法错误。

**Step 3: 路径残留检查**

Run: `rg "mock-resource|data/term_example" .`
Expected: 仅保留在历史说明（如 plans）可接受。

---

### Task 6: 形成变更说明

**Files:**
- Modify: `examples/sales_analysis_demo/mock_env/README.md`（如需补迁移说明）

**Step 1: 输出迁移映射**

列出旧路径到新路径映射供团队同步。

**Step 2: 输出启动前置步骤**

明确初始化顺序：DDL -> 数据 -> 知识 -> API。
