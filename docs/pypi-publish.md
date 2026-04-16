# by-datacloud PyPI 发布流程

本文档适用于当前仓库的根级发行包 `by-datacloud`。

当前仓库是 Monorepo，但对外发布到 PyPI 的主包是根目录 `pyproject.toml` 定义的聚合包。构建 wheel 时会包含：

- `by_datacloud`
- `datacloud_analysis`
- `datacloud_data_sdk`
- `datacloud_data_service`
- `datacloud_knowledge`

说明：

- 上述聚合关系来自根 `pyproject.toml` 的 `[tool.hatch.build.targets.wheel]` 与 `force-include` 配置。
- 当前 wheel 配置没有包含 `src/whale_datacloud`，因此它不是本次对外发行物的一部分。
- `packages/` 下各子项目可以保留自己的 `pyproject.toml`，但本流程关注的是根包 `by-datacloud` 的发布。

## 1. 首次发布前准备

### 1.1 确认基础条件

发布前需要确认：

1. PyPI 上尚未被占用的项目名为 `by-datacloud`。
2. 根包依赖可以从公网安装，尤其是 `by-framework`。
3. 仓库已启用 GitHub Actions。
4. 发布人拥有 PyPI 与 GitHub 仓库的维护权限。

### 1.2 配置 GitHub Environment

在 GitHub 仓库 `beyonai/by-datacloud` 中创建环境：

- Environment name: `pypi`

当前自动发布工作流固定使用：

- Workflow file: `.github/workflows/publish-pypi.yml`
- Trigger tag pattern: `by-datacloud-v*`
- Environment: `pypi`

### 1.3 在 PyPI 配置 Trusted Publisher

在 PyPI 项目 `by-datacloud` 中添加 Trusted Publisher，建议使用以下配置：

- Owner: `beyonai`
- Repository name: `by-datacloud`
- Workflow name: `Publish PyPI`
- Workflow file: `.github/workflows/publish-pypi.yml`
- Environment name: `pypi`

完成后，GitHub Actions 可通过 OIDC 直接发布，无需在 GitHub Secrets 中保存 PyPI Token。

## 2. 每次发布前检查

### 2.1 同步版本号

至少检查并同步以下版本信息：

1. 根包版本：

```toml
# pyproject.toml
[project]
version = "x.y.z"
```

2. 根包导出的版本常量：

```python
# src/by_datacloud/__init__.py
__version__ = "x.y.z"
```

3. 如仍保留兼容入口，也建议同步：

```python
# src/whale_datacloud/__init__.py
__version__ = "x.y.z"
```

建议将版本更新作为一次独立提交，避免发布时出现 `pyproject.toml` 与代码内 `__version__` 不一致。

### 2.2 执行质量检查

在仓库根目录执行：

```bash
uv sync
uv run ruff format .
uv run ruff check .
uv run mypy .
uv run pytest
```

如果当前版本发布只涉及文档或极小变更，也至少保证：

```bash
uv run ruff check .
uv run mypy .
```

### 2.3 构建并校验产物

在仓库根目录执行：

```bash
uv build
uv tool run twine check dist/*
```

预期产物位于：

```text
dist/
├── by_datacloud-x.y.z-py3-none-any.whl
└── by_datacloud-x.y.z.tar.gz
```

建议额外检查 wheel 内容是否符合预期：

```bash
python -m zipfile -l dist/by_datacloud-x.y.z-py3-none-any.whl
```

重点确认下列模块已进入 wheel：

- `by_datacloud`
- `datacloud_analysis`
- `datacloud_data_sdk`
- `datacloud_data_service`
- `datacloud_knowledge`

## 3. 推荐发布方式：GitHub Tag 自动发布

当前仓库已经配置好自动发布工作流 `.github/workflows/publish-pypi.yml`，触发规则为：

```yaml
on:
  push:
    tags:
      - "by-datacloud-v*"
```

### 3.1 创建发布提交

完成版本更新与检查后，提交代码：

```bash
git add pyproject.toml src/by_datacloud/__init__.py src/whale_datacloud/__init__.py docs/pypi-publish.md
git commit -m "chore(release): 发布 by-datacloud x.y.z"
```

如果本次没有修改兼容入口或文档，请按实际变更调整 `git add` 文件列表。

### 3.2 打 tag 并推送

```bash
git tag by-datacloud-vx.y.z
git push origin main
git push origin by-datacloud-vx.y.z
```

### 3.3 GitHub Actions 自动执行内容

tag 推送后，工作流会自动：

1. 使用 Python 3.12。
2. 安装 `uv`。
3. 在仓库根目录执行 `uv build`。
4. 上传 `dist/*` 构建产物。
5. 在 `pypi` 环境下通过 `pypa/gh-action-pypi-publish@release/v1` 发布到 PyPI。

## 4. 手工发布方式

仅在以下场景建议手工发布：

- 首次试发到 TestPyPI
- 自动工作流临时不可用
- 需要在本地紧急验证发布链路

### 4.1 构建

```bash
uv build
uv tool run twine check dist/*
```

### 4.2 发布到 PyPI

```bash
uv publish dist/*
```

如果使用 Token 方式而不是 Trusted Publishing，请提前配置 PyPI 凭证。手工发布完成后，仍建议补打 release tag，保持 Git 历史与 PyPI 版本一致。

## 5. 发布后验收

建议在干净虚拟环境中做一次公网安装验证：

```bash
python3 -m venv .venv-release-check
source .venv-release-check/bin/activate
pip install -U pip
pip install by-datacloud==x.y.z
python -c "import by_datacloud, datacloud_analysis, datacloud_data_sdk, datacloud_data_service, datacloud_knowledge; print(by_datacloud.__version__)"
```

建议至少验证：

1. `pip install` 能成功解析并安装全部依赖。
2. 关键模块可正常导入。
3. `by_datacloud.__version__` 与发布版本一致。
4. PyPI 项目主页中的 README、元数据、License 展示正常。

## 6. 常见问题

### 6.1 tag 推送后没有自动发布

优先检查：

1. tag 是否满足 `by-datacloud-v*` 规则。
2. `.github/workflows/publish-pypi.yml` 是否位于默认分支。
3. GitHub `pypi` Environment 是否存在。
4. PyPI Trusted Publisher 配置中的仓库、工作流文件、环境名是否完全一致。

### 6.2 本地 `uv build` 成功，但 PyPI 发布失败

优先检查：

1. 发布版本是否已存在于 PyPI。
2. README 渲染或元数据是否有问题，可重新执行 `uv tool run twine check dist/*`。
3. 依赖是否引用了无法从公网获取的私有包。

### 6.3 包安装后导入不到某个模块

优先检查根 `pyproject.toml`：

- `[tool.hatch.build.targets.wheel].packages`
- `[tool.hatch.build.targets.wheel.force-include]`

如果新加了源码目录，但没有加入上述配置，构建出的 wheel 不会包含对应模块。

## 7. 推荐发布清单

每次正式发布前，按下面顺序过一遍：

1. 同步 `pyproject.toml` 与 `__version__`。
2. 执行 `uv run ruff check .`、`uv run mypy .`、`uv run pytest`。
3. 执行 `uv build` 与 `uv tool run twine check dist/*`。
4. 本地检查 wheel 内容。
5. 推送版本提交。
6. 创建并推送 `by-datacloud-vx.y.z` tag。
7. 观察 GitHub Actions 发布结果。
8. 在干净环境执行 `pip install by-datacloud==x.y.z` 验证。
