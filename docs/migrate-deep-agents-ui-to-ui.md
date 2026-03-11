# 将 deep-agents-ui 从 datacloud-agent/ui 迁移到 ui（仓库根）

本文说明如何把 `datacloud-agent/ui/deep-agents-ui` 移动到仓库根目录下的 `ui/deep-agents-ui`（与 `ui/openclaw` 同级）。

## 已完成的配置与引用更新

以下已在仓库中更新，无需再改：

- **.gitmodules**：子模块名改为 `ui/deep-agents-ui`，path 为 `ui/deep-agents-ui`
- **datacloud-agent/scripts/start_with_ui.sh**：`UI_DIR` 改为 `${REPO_ROOT}/ui/deep-agents-ui`（仓库根下的 ui）
- **datacloud-agent/scripts/README.md**：启动 UI 的 `cd` 改为 `cd ../../ui/deep-agents-ui`，子模块重装说明改为“在仓库根目录执行”
- **docs/usage.md、docs/openclaw-gateway-architecture.md**：已按 `ui/deep-agents-ui`（仓库根）书写，无需修改

## 你需要执行的迁移步骤

在 **whale_datacloud 仓库根目录** 下执行。

### 1. 解除当前子模块（旧路径）

若当前子模块在 `datacloud-agent/ui/deep-agents-ui`：

```bash
git submodule deinit -f datacloud-agent/ui/deep-agents-ui
git rm -f datacloud-agent/ui/deep-agents-ui
```

若 Git 里登记的是 `ui/deep-agents-ui` 而实际目录在 `datacloud-agent/ui/` 下，则先只做物理移动（见下），再视情况执行 `git submodule sync`。

### 2. 物理移动目录

```bash
# 确保目标存在
mkdir -p ui

# 移动整个目录（含 .git 与 node_modules、.next 等）
mv datacloud-agent/ui/deep-agents-ui ui/
```

（Windows PowerShell 可用：`Move-Item -Path datacloud-agent\ui\deep-agents-ui -Destination ui\`）

### 3. 修正子模块在 Git 中的元数据路径

子模块的 git 元数据在 `.git/modules/` 下。若存在 `.git/modules/datacloud-agent/ui/deep-agents-ui`，需改为 `.git/modules/ui/deep-agents-ui`：

```bash
mkdir -p .git/modules/ui
mv .git/modules/datacloud-agent/ui/deep-agents-ui .git/modules/ui/deep-agents-ui
# 清理空目录（可选）
rmdir .git/modules/datacloud-agent/ui 2>/dev/null
rmdir .git/modules/datacloud-agent 2>/dev/null
```

### 4. 更新子模块内的 .git 文件

编辑 **ui/deep-agents-ui/.git**（若为文件），内容改为：

```
gitdir: ../../.git/modules/ui/deep-agents-ui
```

（原来可能是 `gitdir: ../../../.git/modules/datacloud-agent/ui/deep-agents-ui`）

### 5. 重新登记并提交

```bash
git add .gitmodules
git add ui/deep-agents-ui
git status
git commit -m "chore: move deep-agents-ui from datacloud-agent/ui to ui/"
```

若之前用 `git rm` 删除了旧路径，这里会看到“删除 datacloud-agent/ui/deep-agents-ui”和“添加 ui/deep-agents-ui”。

---

## 可选：不保留子模块历史的简单做法

若不需要保留 deep-agents-ui 的 submodule 历史，可以按“新子模块”处理：

1. 删除旧目录：  
   `rm -rf datacloud-agent/ui/deep-agents-ui`  
   并执行 `git submodule deinit` / `git rm` 清理旧 submodule 记录。
2. 在仓库根添加新子模块：  
   `git submodule add https://github.com/langchain-ai/deep-agents-ui.git ui/deep-agents-ui`
3. 提交 `.gitmodules` 与 `ui/deep-agents-ui`。

这样就不需要手动移动 `.git/modules` 和改 `ui/deep-agents-ui/.git`。

---

迁移完成后，`ui/` 下应有 `openclaw` 与 `deep-agents-ui` 两个前端工程，脚本与文档中的路径已按此假设更新。
