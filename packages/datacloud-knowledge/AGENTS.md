# AGENTS.md

## Python环境
使用uv 及 pyproject.toml 管理 Python 环境

## 变更约束
任何改动必须用git技能提交到本地

## 文档编写指南

1. 强制实行 **SSOT**（单一事实来源）与“引用代替抄写”
* DRY (Don't Repeat Yourself) 原则。
* 彻底剥离重复描述。任何业务实体、接口、字段，全局只允许被全面定义一次。
* 凡是涉及使用的地方，一律使用 Markdown 的内链跳转。

## Git Workflow

### Commit Message Format

**默认使用中文提交信息**

```
<type>(<scope>): <描述>

types:
  feat     - 新功能
  fix      - Bug 修复
  docs     - 文档
  style    - 格式调整
  refactor - 代码重构
  test     - 测试
  chore    - 构建/配置
```

**示例:**
- `feat: 添加用户登录功能`
- `fix: 修复订单计算错误`
- `docs: 更新 API 文档`
- `refactor: 重构数据库连接逻辑`

### Atomic Commits
- One logical change per commit
- Implementation + its tests belong together
- Split commits across different concerns/directories

---