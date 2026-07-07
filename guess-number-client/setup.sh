#!/bin/bash

# =============================================================================
# 猜数字桌游 - 环境配置脚本 (macOS)
# 功能：检查环境、安装依赖、构建前端
# 用法：./setup.sh
# =============================================================================

set -e  # 遇到错误立即退出

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "🎮  猜数字桌游 - 环境配置脚本"
echo "=========================================="
echo ""

# -------------------------
# 1. 检查 Git
# -------------------------
echo "🔍 [1/5] 检查 Git..."
if ! command -v git &> /dev/null; then
    echo "❌ 错误：未检测到 Git"
    echo "💡 请安装 Git: brew install git"
    exit 1
fi
echo "✅ Git 版本：$(git --version | awk '{print $3}')"

# -------------------------
# 2. 检查 Node.js (v18+)
# -------------------------
echo ""
echo "🔍 [2/5] 检查 Node.js..."
if ! command -v node &> /dev/null; then
    echo "❌ 错误：未检测到 Node.js"
    echo "💡 请安装 Node.js (v18+): brew install node@18"
    exit 1
fi

NODE_VERSION=$(node -v | cut -d'v' -f2 | cut -d'.' -f1)
if [ "$NODE_VERSION" -lt 18 ]; then
    echo "❌ 错误：Node.js 版本过低 (当前 v$NODE_VERSION, 需要 v18+)"
    echo "💡 请升级 Node.js: brew upgrade node"
    exit 1
fi
echo "✅ Node.js 版本：$(node -v)"

# -------------------------
# 3. 检查 npm
# -------------------------
echo ""
echo "🔍 [3/5] 检查 npm..."
if ! command -v npm &> /dev/null; then
    echo "❌ 错误：未检测到 npm"
    exit 1
fi
echo "✅ npm 版本：$(npm -v)"

# -------------------------
# 4. 检查 Python3 (v3.9+)
# -------------------------
echo ""
echo "🔍 [4/5] 检查 Python3..."
if ! command -v python3 &> /dev/null; then
    echo "❌ 错误：未检测到 Python3"
    echo "💡 请安装 Python3: brew install python@3.9"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | awk '{print $2}' | cut -d'.' -f2)
if [ "$PYTHON_VERSION" -lt 9 ]; then
    echo "⚠️  警告：Python 版本较低 (当前 $(python3 --version), 建议 v3.9+)"
fi
echo "✅ Python 版本：$(python3 --version)"

# -------------------------
# 5. 安装前端依赖并构建
# -------------------------
echo ""
echo "🔍 [5/5] 配置前端环境..."

if [ ! -d "node_modules" ]; then
    echo "📦 正在安装前端依赖 (首次安装可能需要几分钟)..."
    npm install
else
    echo "⚠️  node_modules 已存在，跳过安装"
    echo "💡 如需重新安装，请删除 node_modules 后重新运行"
fi

echo ""
echo "🏗️  正在构建前端静态资源..."
npm run build

echo ""
echo "=========================================="
echo "✅ 环境配置完成！"
echo "=========================================="
echo ""
echo "📋 下一步操作："
echo "   1. 运行启动脚本：./start.sh"
echo "   2. 访问游戏：http://localhost:8000"
echo ""
echo "💡 提示："
echo "   - 前端构建产物位于：./dist/"
echo "   - 后端入口文件：./backend/main.py"
echo ""
