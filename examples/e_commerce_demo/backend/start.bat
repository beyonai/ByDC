@echo off
REM DataCloud Service — 启动脚本（Windows）
REM
REM 用法：
REM   examples\e_commerce_demo\backend\start.bat     （从仓库根目录）
REM   start.bat                                       （从 backend\ 目录）
REM

REM 定位到仓库根目录（whale_datacloud\）
pushd "%~dp0..\..\..\"

echo ^> Working directory: %CD%

REM 确保依赖已同步（首次运行或 pyproject.toml 变更后需要）
REM uv sync --group dev

uv run python examples\e_commerce_demo\backend\datacloud_service\main.py %*

popd
