# 数字迷踪 · 猜牌对决

一款基于 WebSocket 的多人在线桌游，支持 4 名玩家同时在线对战。

## 🎮 游戏简介

**数字迷踪**是一款推理类桌游，玩家需要通过线索推导自己手牌的数字，并率先猜对所有手牌获胜。

### 游戏规则

1. **牌组构成**：共 60 张牌，5 种颜色（红、蓝、绿、橙、粉），每种颜色 12 张
   - 颜色与数字绑定循环：红 1、蓝 2、绿 3、橙 4、粉 5、红 6……粉 60
   - 点数规律：`点数 = floor((数字 - 1) / 5) + 1`，范围 1~12

2. **游戏流程**：
   - 每名玩家抽取 5 张手牌（只能看别人的，不能看自己的）
   - 每轮当前玩家选择一张公共牌进行判定
   - 通过位置判定或点数判定获取线索
   - 收集足够线索后提交猜测

3. **胜利条件**：率先正确猜出自己所有 5 张手牌数字的玩家获胜

## 🚀 快速开始

### 环境要求

- Node.js 18+ 
- Python 3.9+

### 安装与运行

```bash
cd guess-number-client

# 一键启动前后端服务
./start.sh
```

启动后访问：
- **前端地址**：http://localhost:5173
- **后端地址**：http://localhost:8000
- **API 健康检查**：http://localhost:8000/api/health

## 📋 功能特性

### 前端功能

- ✅ **开始界面**：房间号输入、昵称设置、新建/加入房间
- ✅ **等待大厅**：玩家列表、房主管理、开始游戏
- ✅ **游戏主界面**：
  - 公共牌区（显示数字和点数图标）
  - 其他玩家手牌（显示完整信息）
  - 自己的手牌（隐藏数字，仅显示颜色底色）
  - 备选区表格（按颜色分行，支持点击选择和右键搁置）
  - 操作按钮区（选色抽牌、位置判定、点数判定、提交猜测）
- ✅ **响应式设计**：支持桌面和移动设备

### 后端功能

- ✅ **WebSocket 通信**：实时状态同步
- ✅ **房间管理**：创建、加入、解散房间
- ✅ **游戏逻辑**：发牌、判定、回合切换
- ✅ **断线重连**：支持玩家断线后重新连接
- ✅ **RESTful API**：健康检查、版本信息、房间列表

## 🏗️ 技术架构

### 前端技术栈

- **框架**：Vue 3 + TypeScript
- **构建工具**：Vite
- **状态管理**：Pinia
- **路由**：Vue Router
- **样式**：CSS Modules

### 后端技术栈

- **框架**：FastAPI
- **WebSocket**：原生 WebSocket 支持
- **异步**：asyncio

### 项目结构

```
guess-number-client/
├── src/                      # 前端源码
│   ├── components/           # 可复用组件
│   │   ├── CandidateTable.vue   # 备选区表格
│   │   ├── PlayerHand.vue       # 玩家手牌
│   │   └── PublicCards.vue      # 公共牌区
│   ├── views/                # 页面组件
│   │   ├── EntryPage.vue        # 开始界面
│   │   ├── LobbyPage.vue        # 等待大厅
│   │   └── GameRoom.vue         # 游戏主界面
│   ├── stores/               # 状态管理
│   ├── services/             # 服务层（WebSocket）
│   ├── composables/          # 组合式函数
│   ├── utils/                # 工具函数
│   ├── types/                # TypeScript 类型定义
│   └── router/               # 路由配置
├── backend/                  # 后端源码
│   └── main.py               # FastAPI 应用
├── dist/                     # 构建输出
├── start.sh                  # 启动脚本
└── README.md                 # 项目文档
```

## 🎨 界面设计

### 颜色系统

5 种颜色及其浅色版本统一管理在 `src/utils/game.ts`：

| 颜色 | 标准色值 | 浅色版本 |
|------|----------|----------|
| 红   | #ef5350  | #ffcdd2  |
| 蓝   | #42a5f5  | #bbdefb  |
| 绿   | #66bb6a  | #c8e6c9  |
| 橙   | #ffa726  | #ffe0b2  |
| 粉   | #ec407a  | #f8bbd9  |

### 卡片展示

- **公共牌区**：显示数字（32px 白色粗体）+ 点数图标（小圆点）
- **其他玩家手牌**：显示完整数字和点数
- **自己的手牌**：仅显示颜色底色，不显示数字
- **备选区**：表格布局，每行一种颜色，单元格底色为该数字牌的标准色

## 📝 开发指南

### 前端开发

```bash
# 安装依赖
npm install

# 开发模式
npm run dev

# 构建生产版本
npm run build

# 类型检查
npm run type-check
```

### 后端开发

```bash
# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r backend/requirements.txt

# 运行服务器
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

## 🔌 WebSocket 协议

### 连接格式

```
ws://localhost:8000/ws/{room_id}/{player_name}
```

### 客户端指令

| 指令 | 参数 | 说明 |
|------|------|------|
| `JoinRoom` | `roomId`, `playerName` | 加入房间 |
| `StartGame` | - | 开始游戏（仅房主） |
| `SelectColorToDraw` | `color` | 选择颜色抽牌 |
| `JudgeByPosition` | `publicCardId` | 位置判定 |
| `JudgeByPoint` | `publicCardId`, `targetColor` | 点数判定 |
| `SubmitGuess` | `guesses` | 提交猜测 |
| `SkipTurn` | - | 跳过回合（仅房主） |

### 服务端事件

| 事件 |  payload | 说明 |
|------|----------|------|
| `Event_StateUpdate` | `GameState` | 游戏状态更新 |
| `Event_SyncFullState` | `FullStateSnapshot` | 全量状态同步 |
| `Event_GuessResult` | `{ correct: boolean }` | 猜测结果 |
| `Event_PlayerDisconnected` | `{ playerId, isCurrentTurnPlayer, paused }` | 玩家断线 |
| `Event_GameOver` | `GameOverInfo` | 游戏结束 |

## 📄 许可证

MIT License

---

**享受游戏！** 🎉
