#!/bin/bash

# =============================================================================
# 猜数字桌游 - 启动脚本 (macOS/Linux)
# 功能：同时启动前后端服务
#   - 前端：Vite 开发服务器 (默认端口 5173)
#   - 后端：FastAPI + WebSocket 服务器 (默认端口 8000)
# 用法：./start.sh
# =============================================================================

set -e  # 遇到错误立即退出

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "🚀  猜数字桌游 - 启动前后端服务"
echo "=========================================="
echo ""

# -------------------------
# 检查并安装后端依赖
# -------------------------
echo "🐍 检查 Python 虚拟环境..."

if [ ! -d "venv" ]; then
    echo "📦 正在创建虚拟环境..."
    python3 -m venv venv
    echo "✅ 虚拟环境已创建"
else
    echo "⚠️  虚拟环境已存在"
fi

echo "🔌 激活虚拟环境..."
source venv/bin/activate

echo ""
echo "📦 检查后端依赖..."

if [ ! -f "backend/requirements.txt" ]; then
    echo "❌ 错误：未找到 backend/requirements.txt"
    exit 1
fi

# 检查关键包是否已安装
if ! python -c "import fastapi" 2>/dev/null; then
    echo "📦 正在安装后端依赖..."
    pip install --upgrade pip
    pip install -r backend/requirements.txt
else
    echo "⚠️  后端依赖已安装，跳过"
fi

# -------------------------
# 检查前端依赖
# -------------------------
echo ""
echo "📦 检查前端依赖..."

if [ ! -d "node_modules" ]; then
    echo "⚠️  前端依赖未安装，正在安装..."
    npm install
else
    echo "⚠️  前端依赖已安装"
fi

# -------------------------
# 启动服务
# -------------------------
echo ""
echo "=========================================="
echo "🎮  正在启动游戏服务..."
echo "=========================================="
echo ""
echo "📍 前端地址：http://localhost:5173"
echo "📍 后端地址：http://localhost:8000"
echo "📍 API 健康检查：http://localhost:8000/api/health"
echo ""
echo "💡 提示："
echo "   - 按 Ctrl+C 停止所有服务"
echo "   - 服务日志将显示在此终端"
echo ""

# 启动后端（后台运行）
echo "🔧 启动后端服务器..."
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
echo "✅ 后端已启动 (PID: $BACKEND_PID)"

# 等待后端启动
sleep 2

# 启动前端（前台运行，便于 Ctrl+C 统一管理）
echo "🎨 启动前端开发服务器..."
npm run dev

# 清理函数
cleanup() {
    echo ""
    echo "🛑 正在停止服务..."
    if [ ! -z "$BACKEND_PID" ]; then
        kill $BACKEND_PID 2>/dev/null || true
        echo "✅ 后端已停止"
    fi
    echo "👋 再见！"
    exit 0
}

# 注册信号处理
trap cleanup EXIT INT TERM
