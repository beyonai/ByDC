# G23 skill 能力模型标签

## 1. 任务定义

### 1.1 背景（§4.5）

重构方案 §4.5 要求 skill 能力模型支持以下字段：
- `allowlist_tags`：允许该 skill 执行的标签白名单（平台/租户/场景维度）
- `blocklist_tags`：禁止该 skill 执行的标签黑名单
- `risk_level`：skill 的风险等级（`low / medium / high`），影响审计与 hook 行为

**当前实现：**
- `risk_level` 已在 `HookAudit`（`tool_hook_plugins/types.py:71`）中定义，但在 skill 能力模型中未作为一等字段
- `allowlist_tags / blocklist_tags` 在整个 skill 能力模型中**不存在**
- `sandbox_executor.py:742` 从 audit 中提取 risk_level，但 skill 定义本身不携带该字段
- `execution.py:1032` 中 risk_level 硬编码为 `"medium"`

### 1.2 目标

1. 在 skill 能力模型（`SkillMeta` 或等价结构）中添加 `allowlist_tags`、`blocklist_tags`、`risk_level` 字段。
2. 在工具执行路径中，根据 `allowlist_tags / blocklist_tags` 过滤可用 skill。
3. 将 `risk_level` 从 skill 定义传递到 `HookAudit`，替换硬编码的 `"medium"`。
4. 每次 skill 调用的审计字段完整记录（`risk_level`、`allowlist_tags`、`blocklist_tags`）。

---

## 2. 详细任务

### 2.1 扩展 skill 能力模型

定位 skill 元数据定义位置（`skills/` 目录或 `sandbox_executor.py` 中的 skill 注册逻辑），添加字段：

```python
class SkillMeta(TypedDict, total=False):
    name: str
    description: str
    risk_level: Literal["low", "medium", "high"]   # 新增，默认 "medium"
    allowlist_tags: list[str]                        # 新增，空列表 = 不限制
    blocklist_tags: list[str]                        # 新增，空列表 = 不限制
```

### 2.2 执行路径中的标签过滤

在 `sandbox_executor.py` 的工具选择/执行路径中，添加标签过滤逻辑：

```python
def _is_skill_allowed(skill_meta: SkillMeta, context_tags: list[str]) -> bool:
    """根据 allowlist/blocklist 判断 skill 是否可执行。"""
    blocklist = skill_meta.get("blocklist_tags") or []
    allowlist = skill_meta.get("allowlist_tags") or []

    # blocklist 优先：context_tags 与 blocklist 有交集则禁止
    if blocklist and any(t in blocklist for t in context_tags):
        return False

    # allowlist 非空时：context_tags 必须与 allowlist 有交集
    if allowlist and not any(t in allowlist for t in context_tags):
        return False

    return True
```

`context_tags` 来源：`gateway_context` 中的租户/场景标签（若无则为空列表，不过滤）。

### 2.3 risk_level 传递到 HookAudit

在 `_build_hook_context`（`sandbox_executor.py`）中，从 skill 元数据读取 `risk_level`：

```python
# 旧（硬编码）
audit = HookAudit(risk_level="medium", ...)

# 新（从 skill 元数据读取）
skill_risk = (skill_meta or {}).get("risk_level", "medium")
audit = HookAudit(risk_level=skill_risk, ...)
```

同步更新 `execution.py:1032` 中硬编码的 `"medium"`。

### 2.4 内置 skill 示例更新

更新 `skills/builtin/group_agg.py` 和 `time_series.py`，添加 `risk_level` 字段示例：

```python
SKILL_META: SkillMeta = {
    "name": "group_agg",
    "description": "...",
    "risk_level": "low",
    "allowlist_tags": [],
    "blocklist_tags": [],
}
```

### 2.5 单元测试

新增 `tests/dca/unit/test_skill_capability_tags.py`：

```python
def test_skill_allowed_with_empty_tags():
    """无 allowlist/blocklist 时，任何 context_tags 均允许。"""
    ...

def test_skill_blocked_by_blocklist():
    """context_tags 与 blocklist 有交集时，skill 被禁止。"""
    ...

def test_skill_blocked_by_allowlist_mismatch():
    """allowlist 非空且 context_tags 无交集时，skill 被禁止。"""
    ...

def test_risk_level_propagated_to_hook_audit():
    """skill 的 risk_level 正确传递到 HookAudit。"""
    ...
```

---

## 3. 验收标准

| # | 验收项 | 检查方式 |
|---|--------|---------|
| 1 | `SkillMeta` 含 `allowlist_tags / blocklist_tags / risk_level` | grep 或代码审查 |
| 2 | `_is_skill_allowed` 函数存在且逻辑正确 | 单元测试覆盖 |
| 3 | `HookAudit.risk_level` 从 skill 元数据读取，无硬编码 `"medium"` | `grep '"medium"' sandbox_executor.py` 无结果 |
| 4 | 内置 skill 示例含 `risk_level` 字段 | 代码审查 |
| 5 | 新增单元测试通过 | `pytest tests/dca/unit/test_skill_capability_tags.py` 绿色 |
| 6 | 全量单测通过 | `pytest packages/datacloud-analysis/tests/` 绿色 |

---

## 4. 依赖

**前置**：01-收口前置波次完成。

## 5. 并行性

可与 G22、G24、G25 并行执行。

## 6. 提交规范

```
refactor(g23): add allowlist_tags/blocklist_tags/risk_level to skill capability model
```
