# Number-guess

# 📐 在线桌游“猜数字”

## 一、游戏核心机制（最终确认）

### 1.1 牌组构成
- **总牌数**：60张，5种颜色（红、蓝、绿、橙、粉）各12张。
- **数字规律**：颜色与数字绑定循环（红1、蓝2、绿3、橙4、粉5、红6……粉60）。
- **点数规律**：`点数 = floor((数字 - 1) / 5) + 1`，范围 1~12。

### 1.2 初始发牌
- 每人从牌堆抽取5张**颜色不同**的牌，按**数字从小到大**在面前排列。
- **可见性**：玩家仅知自己牌的颜色（数字未知），但可看到其他玩家完整的颜色+数字。

### 1.3 公开牌区（公共牌堆）
- 开局亮出5张颜色各异的公牌。
- 每轮次，当前玩家**选择一种颜色**（系统展示该颜色剩余数量），从该颜色剩余牌中**按预洗牌顺序**抽取一张加入公牌区（此时公牌变为6张）。
- **判定后**：被选中的公牌**移入弃牌堆**，公牌区恢复为5张。

### 1.4 判定机制（二选一）
- **1类判定（位置）**：选定一张公牌，系统返回该数字位于当前玩家手牌（5张）中的位置（索引 0~5：0=小于最小，5=大于最大，1~4=介于第N张与第N+1张之间）。
- **2类判定（点数）**：选定一张公牌 + 指定自己手牌中的某颜色，系统返回两者点数是否相同。

### 1.5 胜负、退出与平局
- **随时提交猜测**：任何存活玩家可在任何时候提交自己5张牌的完整数字。
  - **正确**：整场游戏结束，该玩家获胜。
  - **错误**：该玩家手牌**全部数字公开**，标记出局（转为旁观者），游戏继续。
- **平局**：若牌堆（所有颜色队列）耗尽且无玩家猜对，**强制平局，无胜者**。

---

## 二、后端核心架构

### 2.1 状态机（含暂停与高优先级中断）
# 数字迷踪 · 猜牌对决技术方案

## 1. 项目定位

“数字迷踪”是一款基于浏览器的 4 人在线推理桌游。玩家看得到其他人的数字牌，却看不到自己的数字牌，需要通过公共牌判定获得线索，并率先推断出自己的 5 张手牌。

本文档说明当前项目的游戏规则、运行配置、启动方式和技术实现。项目当前为单进程内存态服务，适合局域网或内网穿透试玩，不提供数据库持久化。

## 2. 游戏规则

### 2.1 牌组与点数

- 牌组共 60 张，分为红、蓝、绿、橙、粉 5 种颜色，每种颜色 12 张。
- 数字与颜色循环绑定：红为 1、6、11……56；蓝为 2、7、12……57；依次类推，粉为 5、10、15……60。
- 点数按 5 个数字一组计算：`((数字 - 1) // 5) % 3 + 1`，点数范围为 1~3。
- 服务端按颜色维护独立牌队列。牌局开始时每组随机洗牌，抽牌时从对应颜色队列取出一张。

### 2.2 开局

1. 房间最多 4 名玩家，房主点击开始后才能进入牌局。
2. 每名玩家获得 5 张手牌，按颜色顺序展示。
3. 公共牌区开局放置 5 张牌，每种颜色 1 张。
4. 服务端保存真实牌面；玩家自己的数字在界面中隐藏为 `?`，其他玩家的数字可见。

### 2.3 回合流程

每轮由当前玩家执行以下流程：

1. **抽牌**：从仍有存牌的颜色中选择一种，抽出 1 张加入公共牌区，公共牌暂时变为 6 张。
2. **选择公共牌**：选择一张公共牌作为本轮判定牌。
3. **执行一种判定**：
   - **位置判定**：返回该公共牌数字在当前玩家 5 张手牌排序后的插入位置。`0` 表示小于全部手牌，`5` 表示大于全部手牌，`1~4` 表示位于两张手牌之间。
   - **点数判定**：选择自己手牌的一种颜色，返回该手牌与公共牌的点数是否相同。
4. 服务端记录线索，展示判定结果约 1.2 秒后切换下一位存活玩家。
5. 本轮被选中的公共牌计入已使用牌，下一轮公共牌区恢复为 5 张。

### 2.4 猜测与结束

- 任意存活玩家都可以提交 5 个数字，顺序必须与红、蓝、绿、橙、粉颜色顺序一致。
- 猜测正确：立即结束牌局，提交者获胜。
- 猜测错误：服务端返回正确数字；当前版本保留该玩家继续游戏，不自动出局。
- 所有颜色牌堆均耗尽：牌局结束，判定为平局。
- 房主可以在判定阶段执行 `SkipTurn` 跳过当前回合，也可以重置已结束的牌局或解散房间。

## 3. 程序配置与启动

### 3.1 环境要求

- macOS 或 Linux
- Node.js 18 及以上、npm（仅开发调试与构建需要）
- Python 3.9 及以上（生产运行仅需 Python 与后端依赖）

### 3.2 一键配置

```bash
cd guess-number-client
chmod +x setup.sh start.sh
./setup.sh
```

`setup.sh` 会检查 Git、Node.js、npm 和 Python，安装前端依赖，并执行 `npm run build` 生成 `dist/`。后端依赖清单位于 [backend/requirements.txt](guess-number-client/backend/requirements.txt)。

### 3.3 启动开发环境

```bash
cd guess-number-client
./start.sh
```

启动脚本会自动创建 `venv/`，安装 FastAPI、Uvicorn、WebSocket 等后端依赖，安装前端 npm 依赖，然后启动：

- 前端开发服务器：`http://localhost:5173`
- 后端 API 与 WebSocket：`http://localhost:8000`
- 健康检查：`http://localhost:8000/api/health`

浏览器访问 `http://localhost:5173` 开始游戏。按 `Ctrl+C` 停止前端和后端服务。

开发模式为两个进程：Vite 开发服务器（5173，提供模块热更新，并将 `/api` 与 `/ws` 代理到 8000）加 Uvicorn（8000）。若 `venv/` 已损坏（如从其他环境拷贝导致 shebang 失效或包文件缺失），删除 `venv/` 后由脚本重建，或按 3.5 手动重建。

### 3.4 生产模式（单进程，一条指令启动前后端）

前端执行 `npm run build` 后，`src/` 被编译为纯静态文件输出到 `dist/`（一个 `index.html` + 一个 JS + 一个 CSS）。后端启动时自动挂载该目录：`/` 返回 `index.html`，`/assets/*` 返回 JS 与 CSS。配合同一进程内的 `/api/*` REST 接口和 `/ws/{房间号}/{玩家名}` WebSocket，**生产模式下不需要单独启动前端服务**，一条 uvicorn 指令即同时提供页面、接口与实时对战通道：

```bash
# 第 1 步：构建前端（仅源码改动后需要执行，产物输出到 dist/）
cd guess-number-client
npm run build

# 第 2 步：启动生产服务（0.0.0.0 监听，局域网其他设备可直接访问）
cd guess-number-client
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

`python3` 需替换为已安装后端依赖的解释器。使用虚拟环境（`venv/` 损坏时先 `rm -rf venv` 重建）：

```bash
cd guess-number-client
python3 -m venv venv
./venv/bin/pip install -r backend/requirements.txt
./venv/bin/python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

局域网访问地址（`<Mac-局域网IP>` 按本机实际网卡地址调整，可用 `ifconfig` 查看）：

| 设备位置 | 地址 |
| --- | --- |
| 本机 | `http://localhost:8000` |
| 同网段其他设备 | `http://<Mac-局域网IP>:8000` |

前端 WebSocket 地址默认跟随 `window.location.host` 动态拼接（见 `src/services/websocket.ts` 与两个 view），设备从哪个地址打开页面就会连回同一后端，无需额外配置；仅当 WebSocket 需要独立主机时才设置 `VITE_WS_HOST`。

> 本机（Mac mini）当前使用受管 Python 3.13 环境运行生产服务，已验证指令：
> `cd /Users/zyqyq/Program/Number-guess/guess-number-client && /Users/zyqyq/.workbuddy/binaries/python/envs/number-guess/bin/python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000`

### 3.5 分别启动

前端（开发服务器，支持热更新）：

```bash
cd guess-number-client
npm install
npm run dev
```

后端：

```bash
cd guess-number-client
python3 -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

开发模式下前端由 Vite 提供；生产模式（前后端单进程）见 3.4。

## 4. 技术方案概览

### 4.1 技术栈

- 前端：Vue 3、TypeScript、Vue Router、Pinia、Vite。
- 后端：Python、FastAPI、Uvicorn、原生 WebSocket、asyncio。
- 部署形态：生产模式下前端构建产物 `dist/` 由 FastAPI 同进程托管，前后端共用一个 8000 端口、一条启动指令（见 3.4）。
- 通信：JSON over WebSocket；REST 接口用于健康检查、版本和房间列表。
- 存储：房间、玩家、牌堆和线索均保存在后端内存中，服务重启后数据丢失。

### 4.2 前端结构

- `views/`：入口页、等待大厅和游戏房间。
- `components/`：公共牌、玩家手牌、候选表格等界面组件。
- `stores/game.ts`：保存服务端推送的游戏快照和当前玩家身份。
- `services/websocket.ts`：建立 WebSocket、发送指令、接收状态事件。
- `composables/gameLogic.ts`：处理自己的手牌隐藏、线索计算和候选区展示逻辑。

### 4.3 后端状态与同步

后端以 `GameRoom` 维护一间房间的完整状态，主要阶段为：

`WAITING` 等待玩家 → `PLAYING` 进行中 → `GAME_OVER` 结束。

进行中包含 `DRAW_PHASE`、`ACTION_PHASE`、`JUDGE_RESULT` 和断线时的 `PAUSED`。每次抽牌、判定、回合切换或猜测后，服务端通过 `Event_StateUpdate` 广播游戏快照；新连接通过 `Event_SyncFullState` 同步当前状态。

主要客户端指令包括：`StartGame`、`SelectColorToDraw`、`SelectPublicCard`、`JudgeByPosition`、`JudgeByPoint`、`SubmitGuess`、`SkipTurn`、`ResetGame` 和 `DissolveRoom`。

### 4.4 断线处理

玩家断线后仍保留在房间状态中，并标记为离线。若断线者正处于当前回合，房间进入 `PAUSED`；重连后恢复状态。当前后端通过房间号和玩家身份复用房间连接，重连令牌协议属于后续增强项。

## 5. 目录结构

```text
guess-number-client/
├── backend/
│   ├── main.py                 # FastAPI、WebSocket 和游戏规则
│   └── requirements.txt        # Python 依赖
├── dist/                       # 前端构建产物（npm run build 生成，后端直接托管）
├── src/
│   ├── components/             # 游戏组件
│   ├── composables/            # 组合式逻辑
│   ├── services/websocket.ts   # WebSocket 客户端
│   ├── stores/game.ts          # Pinia 状态
│   ├── types/game.ts           # 类型定义
│   └── views/                  # 页面
├── setup.sh                    # 环境检查、安装和构建
├── start.sh                    # 开发环境一键启动
├── package.json                # 前端脚本与依赖
└── vite.config.ts              # Vite 配置
```

## 6. 已知边界

- 游戏状态仅存于内存，后端重启会清空房间。
- 开发模式使用 Vite 开发服务器（5173，支持热更新）；生产模式为 FastAPI 单进程（8000）托管 `dist/` 静态页面。两种模式均未配置正式域名、HTTPS 或反向代理。
- WebSocket 地址默认跟随页面主机（`window.location.host`）动态拼接，同源部署零配置；跨域或内网穿透部署时需相应设置 `VITE_WS_HOST` 和代理规则。
- `backend/main.py` 的 SPA catch-all 路由注册于 `/api/*` 之前，当前 `/api/health`、`/api/version`、`/api/rooms` 返回 `index.html` 而非 JSON（不影响游戏主流程，WebSocket 不受影响）。
- `backend/websocket_server.py` 保留了一份早期实现，当前启动脚本使用的是 `backend/main.py`。
