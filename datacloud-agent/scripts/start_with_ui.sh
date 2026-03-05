#!/bin/bash
# 启动 DataCloud Agent 和 Deep Agents UI
# Usage: ./start_with_ui.sh [content_writer|other_agent]

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 默认 agent 类型
AGENT_TYPE="${1:-content_writer}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  DataCloud Agent + Deep Agents UI${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 检查 agent 目录是否存在
AGENT_DIR="${SCRIPT_DIR}/${AGENT_TYPE}"
if [ ! -d "$AGENT_DIR" ]; then
    echo -e "${RED}错误: Agent 目录不存在: ${AGENT_DIR}${NC}"
    echo "可用的 agents:"
    for dir in "$SCRIPT_DIR"/*/; do
        if [ -f "$dir/langgraph.json" ]; then
            echo "  - $(basename "$dir")"
        fi
    done
    exit 1
fi

# 检查 UI 目录
UI_DIR="${PROJECT_ROOT}/ui/deep-agents-ui"
if [ ! -d "$UI_DIR" ]; then
    echo -e "${RED}错误: UI 目录不存在: ${UI_DIR}${NC}"
    echo "请运行: git submodule update --init --recursive"
    exit 1
fi

# 获取 langgraph.json 中的 assistant ID
if [ -f "${AGENT_DIR}/langgraph.json" ]; then
    # 尝试从 langgraph.json 提取第一个 graph 名称作为 assistant ID
    ASSISTANT_ID=$(grep -o '"[^"]*":\s*"' "${AGENT_DIR}/langgraph.json" | head -1 | sed 's/":\s*"$//' | sed 's/^"//')
    if [ -z "$ASSISTANT_ID" ]; then
        ASSISTANT_ID="agent"
    fi
else
    ASSISTANT_ID="agent"
fi

echo -e "${GREEN}Agent 类型: ${AGENT_TYPE}${NC}"
echo -e "${GREEN}Assistant ID: ${ASSISTANT_ID}${NC}"
echo ""

# 清理函数
cleanup() {
    echo ""
    echo -e "${YELLOW}正在关闭服务...${NC}"
    if [ -n "$AGENT_PID" ]; then
        echo "  停止 Agent (PID: $AGENT_PID)"
        kill $AGENT_PID 2>/dev/null || true
    fi
    if [ -n "$UI_PID" ]; then
        echo "  停止 UI (PID: $UI_PID)"
        kill $UI_PID 2>/dev/null || true
    fi
    echo -e "${GREEN}已清理${NC}"
    exit 0
}

# 捕获中断信号
trap cleanup INT TERM

# 检查端口占用
check_port() {
    local port=$1
    local name=$2
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo -e "${YELLOW}警告: 端口 $port 已被占用 ($name)${NC}"
        return 1
    fi
    return 0
}

# 启动 Agent
echo -e "${BLUE}[1/2] 启动 LangGraph Agent...${NC}"
cd "$AGENT_DIR"

if ! check_port 2024 "LangGraph"; then
    echo -e "${YELLOW}LangGraph 端口 2024 已被占用，尝试使用现有服务...${NC}"
else
    echo "  工作目录: $AGENT_DIR"
    echo "  命令: uv run langgraph dev"
    echo ""
    
    # 启动 agent（后台）
    uv run langgraph dev > /tmp/agent.log 2>&1 &
    AGENT_PID=$!
    
    # 等待 agent 启动
    echo "  等待 Agent 启动..."
    for i in {1..30}; do
        if curl -s http://127.0.0.1:2024/ok >/dev/null 2>&1; then
            echo -e "  ${GREEN}Agent 已启动 (PID: $AGENT_PID)${NC}"
            break
        fi
        if ! kill -0 $AGENT_PID 2>/dev/null; then
            echo -e "  ${RED}Agent 启动失败，查看日志: /tmp/agent.log${NC}"
            cat /tmp/agent.log
            exit 1
        fi
        sleep 1
    done
    
    if ! curl -s http://127.0.0.1:2024/ok >/dev/null 2>&1; then
        echo -e "  ${RED}Agent 启动超时${NC}"
        kill $AGENT_PID 2>/dev/null || true
        exit 1
    fi
fi

echo ""

# 启动 UI
echo -e "${BLUE}[2/2] 启动 Deep Agents UI...${NC}"
cd "$UI_DIR"

if ! check_port 3000 "UI"; then
    echo -e "${YELLOW}UI 端口 3000 已被占用${NC}"
else
    # 检查 node_modules
    if [ ! -d "node_modules" ]; then
        echo "  安装依赖..."
        if command -v yarn &> /dev/null; then
            yarn install
        else
            npm install
        fi
    fi
    
    echo "  工作目录: $UI_DIR"
    echo "  命令: yarn dev"
    echo ""
    
    # 启动 UI（后台）
    if command -v yarn &> /dev/null; then
        yarn dev > /tmp/ui.log 2>&1 &
    else
        npm run dev > /tmp/ui.log 2>&1 &
    fi
    UI_PID=$!
    
    # 等待 UI 启动
    echo "  等待 UI 启动..."
    for i in {1..30}; do
        if curl -s http://localhost:3000 >/dev/null 2>&1; then
            echo -e "  ${GREEN}UI 已启动 (PID: $UI_PID)${NC}"
            break
        fi
        if ! kill -0 $UI_PID 2>/dev/null; then
            echo -e "  ${RED}UI 启动失败，查看日志: /tmp/ui.log${NC}"
            cat /tmp/ui.log
            cleanup
            exit 1
        fi
        sleep 1
    done
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  所有服务已启动!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "  ${BLUE}Agent API:${NC}    http://127.0.0.1:2024"
echo -e "  ${BLUE}UI 地址:${NC}      http://localhost:3000"
echo ""
echo -e "  ${YELLOW}配置信息:${NC}"
echo -e "    - Deployment URL: http://127.0.0.1:2024"
echo -e "    - Assistant ID:   ${ASSISTANT_ID}"
echo ""
echo -e "  ${YELLOW}操作:${NC}"
echo -e "    1. 打开浏览器访问 http://localhost:3000"
echo -e "    2. 输入上述 Deployment URL 和 Assistant ID"
echo -e "    3. 开始与 Agent 交互"
echo ""
echo -e "  按 ${RED}Ctrl+C${NC} 停止所有服务"
echo ""

# 保持脚本运行
wait
