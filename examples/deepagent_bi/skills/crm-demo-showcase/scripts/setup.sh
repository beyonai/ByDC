#!/usr/bin/env bash
# =============================================================================
# CRM Demo Showcase — 环境一键安装脚本
#
# 幂等设计：已安装则跳过，可安全重复执行。
# 用法: bash scripts/setup.sh
# =============================================================================
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

info()  { echo -e "${CYAN}>>>${NC} $*"; }
ok()    { echo -e "${GREEN}  ✓${NC} $*"; }
warn()  { echo -e "${YELLOW}  ⚠${NC} $*"; }
fail()  { echo -e "${RED}  ✗${NC} $*"; }

VENV_DIR="${CRM_VENV_DIR:-/tmp/ont_env}"
PYTHON_BIN="${VENV_DIR}/bin/python"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REQUIREMENTS="${SCRIPT_DIR}/requirements.txt"

echo ""
echo "============================================"
echo "  CRM Demo Showcase 环境安装"
echo "============================================"
echo ""

# ---- Step 1: Install uv ----
info "Step 1/5: 安装 uv 包管理器 ..."
export PATH="$HOME/.local/bin:$PATH"
if command -v uv &>/dev/null; then
    ok "uv 已安装: $(uv --version 2>&1)"
else
    info "安装中 ..."
    pip install uv
    if command -v uv &>/dev/null; then
        ok "uv 安装成功: $(uv --version 2>&1)"
    else
        fail "uv 安装失败"
        exit 1
    fi
fi

# ---- Step 2: Create venv (idempotent) ----
info "Step 2/5: 创建 Python 虚拟环境 ..."
if [ -f "$PYTHON_BIN" ]; then
    ok "venv 已存在: $VENV_DIR ($("$PYTHON_BIN" --version 2>&1))"
else
    info "创建中: $VENV_DIR"
    uv venv --python 3.12 --link-mode copy "$VENV_DIR"
    ok "venv 创建完成 ($("$PYTHON_BIN" --version 2>&1))"
fi

# ---- Step 3: Install dependencies ----
info "Step 3/5: 安装 Python 依赖 ..."
if [ ! -f "$REQUIREMENTS" ]; then
    fail "未找到 requirements.txt: $REQUIREMENTS"
    exit 1
fi
uv pip install --python "$PYTHON_BIN" -r "$REQUIREMENTS" \
    -i https://mirrors.aliyun.com/pypi/simple/ --extra-index-url https://pypi.org/simple/
ok "依赖安装完成"

# ---- Step 4: Verify imports ----
info "Step 4/5: 验证 Python 包导入 ..."
if "$PYTHON_BIN" -c "import by_framework; import by_datacloud; print('OK')" 2>/dev/null; then
    ok "by_framework / by_datacloud 导入正常"
else
    fail "Python 包导入失败，请检查依赖"
    exit 1
fi

# ---- Step 5: Check environment variables ----
info "Step 5/5: 检查环境变量 ..."
MISSING=0

# Required
for VAR in BEYOND_TOKEN USER_CODE; do
    if [ -z "${!VAR:-}" ]; then
        fail "$VAR 未设置"
        MISSING=$((MISSING + 1))
    else
        ok "$VAR 已设置"
    fi
done

# Optional with default
if [ -n "${BE_DOMAINNAME:-}" ]; then
    ok "BE_DOMAINNAME = $BE_DOMAINNAME"
else
    warn "BE_DOMAINNAME 未设置（将使用默认值 ByaiService）"
fi

# Redis (optional at install time)
for VAR in REDIS_HOST REDIS_PORT REDIS_PASSWORD; do
    if [ -z "${!VAR:-}" ]; then
        warn "$VAR 未设置（Redis 相关功能将跳过）"
    else
        ok "$VAR 已设置"
    fi
done

echo ""
echo "============================================"
if [ $MISSING -gt 0 ]; then
    echo -e "  ${RED}⚠ 缺少 $MISSING 个必需环境变量${NC}"
    echo "  请设置后重新运行: bash scripts/setup.sh"
    echo "============================================"
    exit 1
else
    echo -e "  ${GREEN}✅ 环境安装完成！${NC}"
    echo "============================================"
fi
