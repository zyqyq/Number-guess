#!/bin/bash

# =============================================================================
# 猜数字桌游 - 启动脚本 (macOS)
# 功能：创建虚拟环境、安装后端依赖、启动 FastAPI 服务器
# 用法：./start.sh
# =============================================================================

set -e  # 遇到错误立即退出

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "🚀  猜数字桌游 - 启动服务器"
echo "=========================================="
echo ""

# -------------------------
# 检查前端是否已构建
# -------------------------
if [ ! -d "dist" ] || [ ! -f "dist/index.html" ]; then
    echo "⚠️  警告：前端尚未构建！"
    echo "💡 请先运行环境配置脚本：./setup.sh"
    echo ""
    read -p "是否继续启动（仅后端 API）？[y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# -------------------------
# 创建/激活 Python 虚拟环境
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

# -------------------------
# 安装后端依赖
# -------------------------
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
    echo "💡 如需重新安装，请删除 venv 文件夹后重新运行"
fi

# -------------------------
# 启动服务器
# -------------------------
echo ""
echo "=========================================="
echo "🎮  正在启动游戏服务器..."
echo "=========================================="
echo ""
echo "📍 访问地址：http://localhost:8000"
echo "📍 API 健康检查：http://localhost:8000/api/health"
echo ""
echo "💡 提示："
echo "   - 按 Ctrl+C 停止服务器"
echo "   - 服务器日志将显示在此终端"
echo ""

# 启动 uvicorn
exec uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
