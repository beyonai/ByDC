# dataCloud 项目仓库命名规范

## 当前命名问题分析

### 现有命名
1. `datacloud_agent` - 超级分析智能体
2. `datacloud_knowlege_service` - 知识服务 ⚠️ **拼写错误**
3. `datacloud_data_service` - 数据服务
4. `datacloud_memory` - 记忆服务

### 发现的问题

1. **拼写错误**：`knowlege` → `knowledge`
2. **命名不一致**：
   - 有些使用 `_service` 后缀，有些没有
   - 全部使用下划线（`_`），不符合GitHub推荐规范
3. **命名规范**：GitHub推荐使用连字符（`-`）而不是下划线（`_`）

## GitHub 仓库命名最佳实践

### 基本原则
- ✅ 使用**小写字母**
- ✅ 使用**连字符（`-`）**分隔单词，而不是下划线（`_`）
- ✅ 命名应该**清晰、简洁、描述性**
- ✅ 保持**命名一致性**
- ✅ 避免使用**空格**和**特殊字符**

### 命名风格对比

| 风格 | 示例 | 推荐度 |
|------|------|--------|
| 连字符（推荐） | `datacloud-agent` | ✅ 最佳实践 |
| 下划线 | `datacloud_agent` | ⚠️ 不推荐 |
| 驼峰命名 | `datacloudAgent` | ❌ 不推荐 |
| 混合风格 | `datacloud_agent-service` | ❌ 避免 |

## 推荐命名方案

### 方案一：统一使用连字符，保留服务后缀（推荐）

```
whale_datacloud/
├── datacloud-agent              # 超级分析智能体
├── datacloud-knowledge-service  # 知识服务（修正拼写）
├── datacloud-data-service       # 数据服务
└── datacloud-memory             # 记忆服务
```

**优点：**
- ✅ 符合GitHub命名规范（使用连字符）
- ✅ 命名清晰，明确标识服务类型
- ✅ 修正了拼写错误
- ✅ 保持一致性（统一使用连字符）

**缺点：**
- ⚠️ 命名稍长

### 方案二：统一使用连字符，简化命名（简洁版）

```
whale_datacloud/
├── datacloud-agent      # 超级分析智能体
├── datacloud-knowledge  # 知识服务
├── datacloud-data      # 数据服务
└── datacloud-memory    # 记忆服务
```

**优点：**
- ✅ 符合GitHub命名规范
- ✅ 命名简洁
- ✅ 修正了拼写错误
- ✅ 保持一致性

**缺点：**
- ⚠️ 命名可能不够明确（缺少service后缀）

### 方案三：统一使用连字符，完整命名（最清晰）

```
whale_datacloud/
├── datacloud-agent-service      # 超级分析智能体服务
├── datacloud-knowledge-service  # 知识服务
├── datacloud-data-service       # 数据服务
└── datacloud-memory-service     # 记忆服务
```

**优点：**
- ✅ 符合GitHub命名规范
- ✅ 命名最清晰，统一使用service后缀
- ✅ 修正了拼写错误
- ✅ 保持完全一致性

**缺点：**
- ⚠️ 命名较长

## 最终推荐

**推荐使用方案一：统一使用连字符，保留服务后缀**

### 命名映射表

| 服务名称 | 当前命名 | 推荐命名 | 说明 |
|---------|---------|---------|------|
| 超级分析智能体 | `datacloud_agent` | `datacloud-agent` | 使用连字符，去掉下划线 |
| 知识服务 | `datacloud_knowlege_service` | `datacloud-knowledge-service` | 修正拼写错误，使用连字符 |
| 数据服务 | `datacloud_data_service` | `datacloud-data-service` | 使用连字符 |
| 记忆服务 | `datacloud_memory` | `datacloud-memory` | 使用连字符 |

### 命名规范总结

1. **统一使用连字符（`-`）**：符合GitHub最佳实践
2. **修正拼写错误**：`knowlege` → `knowledge`
3. **保持一致性**：所有服务统一命名风格
4. **清晰描述性**：命名能够清晰表达服务功能

## 迁移建议

### 步骤1：重命名本地目录
```bash
# 在 whale_datacloud 目录下执行
mv datacloud_agent datacloud-agent
mv datacloud_knowlege_service datacloud-knowledge-service
mv datacloud_data_service datacloud-data-service
mv datacloud_memory datacloud-memory
```

### 步骤2：更新Git仓库（如果已提交）
```bash
# 对于每个仓库，使用git mv重命名
cd datacloud-agent
git mv datacloud_agent datacloud-agent  # 如果仓库名需要更改
```

### 步骤3：更新所有引用
- 更新文档中的仓库引用
- 更新CI/CD配置
- 更新依赖配置（如package.json, requirements.txt等）
- 更新README.md中的链接

### 步骤4：更新GitHub仓库（如果已创建）
- 在GitHub上重命名仓库（Settings → Repository name）
- 或者创建新仓库并迁移代码

## 命名检查清单

- [x] 使用小写字母
- [x] 使用连字符（`-`）而不是下划线（`_`）
- [x] 修正拼写错误（`knowledge`）
- [x] 保持命名一致性
- [x] 命名清晰、描述性
- [x] 避免特殊字符和空格

## 参考资源

- [GitHub命名最佳实践](https://github.com/github/gitignore)
- [Python包命名规范](https://www.python.org/dev/peps/pep-0008/#package-and-module-names)
- [Node.js包命名规范](https://docs.npmjs.com/cli/v8/configuring-npm/package-json#name)

