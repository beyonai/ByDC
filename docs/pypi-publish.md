# PyPI 发布说明

本文档适用于当前仓库内已准备对外发布的三个包：

- `datacloud-knowledge`
- `datacloud-data`
- `datacloud-analysis`

`datacloud-memory` 当前已从公开发布链路中移除，不作为 `datacloud-analysis` 的强依赖。

## 发布前提

1. 确认 PyPI 包名未被占用。
2. 确认 `by-framework` 已经可以从公网 PyPI 安装。
3. 在 GitHub 仓库 Settings 中创建名为 `pypi` 的 Environment。
4. 在 PyPI 为每个项目配置 Trusted Publisher。

推荐为以下三个项目分别配置：

- PyPI project name: `datacloud-knowledge`
- PyPI project name: `datacloud-data`
- PyPI project name: `datacloud-analysis`

GitHub 侧配置保持一致：

- Owner: `beyonai`
- Repository: `by-datacloud`
- Workflow file: `.github/workflows/publish-pypi.yml`
- Environment: `pypi`

## 本地发布前检查

分别进入目标包目录执行：

```bash
uv sync
uv run ruff format .
uv run ruff check .
uv run mypy .
uv build
```

建议额外检查构建产物元数据：

```bash
uv tool run twine check dist/*
```

## 推荐发布顺序

按依赖顺序发布：

1. `datacloud-knowledge`
2. `datacloud-data`
3. `datacloud-analysis`

## 自动发布方式

为目标包更新版本号后，创建并推送对应 tag：

```bash
git tag datacloud-knowledge-v0.1.0
git push origin datacloud-knowledge-v0.1.0
```

```bash
git tag datacloud-data-v0.1.0
git push origin datacloud-data-v0.1.0
```

```bash
git tag datacloud-analysis-v0.1.0
git push origin datacloud-analysis-v0.1.0
```

tag 推送后，GitHub Actions 会自动：

1. 识别要发布的包目录
2. 执行 `uv build`
3. 通过 Trusted Publishing 上传到 PyPI

## 发布后验证

建议在干净环境执行公网安装验证：

```bash
python3 -m venv .venv-release-check
source .venv-release-check/bin/activate
pip install -U pip
pip install datacloud-knowledge
pip install "datacloud-data[sql]"
pip install datacloud-analysis
python -c "import datacloud_knowledge, datacloud_data_sdk, datacloud_analysis"
```

如果需要校验 `by-framework`：

```bash
pip install by-framework
python -c "import by_framework"
```

## 手工发布方式

如果临时不走 GitHub Actions，也可以在包目录手工执行：

```bash
uv build
uv publish
```

手工发布更适合首个版本试发；稳定后建议统一使用 GitHub tag 发布。
