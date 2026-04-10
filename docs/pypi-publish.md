# PyPI 发布说明

本文档适用于当前仓库对外发布的单一总包：

- `by-datacloud`

总包在构建时会直接打入以下源码模块：

- `datacloud_analysis`
- `datacloud_data_sdk`
- `datacloud_data_service`
- `datacloud_knowledge`

## 发布前提

1. 确认 PyPI 包名未被占用。
2. 确认 `by-framework` 已经可以从公网 PyPI 安装。
3. 在 GitHub 仓库 Settings 中创建名为 `pypi` 的 Environment。
4. 在 PyPI 为 `by-datacloud` 配置 Trusted Publisher。

推荐配置：

- PyPI project name: `by-datacloud`

GitHub 侧配置保持一致：

- Owner: `beyonai`
- Repository: `by-datacloud`
- Workflow file: `.github/workflows/publish-pypi.yml`
- Environment: `pypi`

## 本地发布前检查

在仓库根目录执行：

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

## 自动发布方式

为总包更新版本号后，创建并推送 tag：

```bash
git tag by-datacloud-v0.1.0
git push origin by-datacloud-v0.1.0
```

tag 推送后，GitHub Actions 会自动：

1. 在仓库根目录执行 `uv build`
2. 通过 Trusted Publishing 上传到 PyPI

## 发布后验证

建议在干净环境执行公网安装验证：

```bash
python3 -m venv .venv-release-check
source .venv-release-check/bin/activate
pip install -U pip
pip install by-datacloud
python -c "import by_datacloud, datacloud_knowledge, datacloud_data_sdk, datacloud_analysis"
```

## 手工发布方式

如果临时不走 GitHub Actions，也可以在仓库根目录手工执行：

```bash
uv build
uv publish dist/*
```

手工发布更适合首个版本试发；稳定后建议统一使用 GitHub tag 发布。
