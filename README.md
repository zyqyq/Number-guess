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

### 2.5 机器人玩家

- 在等待大厅，房主可以通过「添加机器人」补齐人数，也可以移除已添加的机器人；房间人数上限仍为 4，机器人计入这 4 个名额。
- 机器人不建立 WebSocket 连接，`Player.isBot` 为 `true`，昵称按 `机器人1`、`机器人2`……递增生成。
- 轮到机器人时，服务端驱动任务会停顿 0.6~1.8 秒后代替它行动：从仍有存牌的颜色中随机抽一张、随机选定一张公共牌，再随机选择位置判定或点数判定（点数判定随机选一种手牌颜色）。
- 机器人**不会**提交猜测，因此牌局只能由真人猜中或牌堆耗尽结束。
- 机器人随牌局状态推进，重置牌局、解散房间或牌局结束时会自动停止；新开一局会重新拉起驱动。

### 2.6 系统管理后台（仅本机）

- **入口**：首页填写管理昵称、管理房间号后点「加入房间」即跳转管理后台（本机访问时口令由 `/api/admin/access` 从后端同步）；也可在服务器本机直接访问 `http://localhost:8000/admin`。管理房间号为保留号，随机建房会跳过；普通玩家输入该号会在首页直接提示无法加入，绕过前端直连 WebSocket 也会被服务端以 `1008 / room_reserved` 拒绝，且不会触发自动重连。
- **口令与开关走配置文件**：`config.json`（项目根目录，首次启动自动生成，模板见 `config.example.json`）的 `admin` 段决定管理昵称、房间号和「是否仅允许本机登录」（`localOnly`，默认 `true`）。环境变量 `ADMIN_USERNAME` / `ADMIN_ROOM` / `ADMIN_LOCAL_ONLY` 优先级更高。改完点管理后台「安全设置 → 重载配置」即可热生效，无需重启。
- **访问限制**：`localOnly` 为 true 时，管理页面、`/api/admin/*` 与管理 WebSocket 只接受回环地址（`127.0.0.1` / `::1`），局域网设备访问 `/admin` 会直接收到 403 页面；关闭该开关后任何来源都可访问，仅依赖口令，请谨慎。
- **IP 黑名单**：`config.json` 的 `security.ipBlacklist`，支持单个 IP 与 CIDR 网段（如 `10.0.0.0/8`）。命中黑名单的来源，游戏连接、presence 登记、管理接口与管理 WebSocket 全部拒绝（关闭码 `1008 / ip_banned`），优先级高于仅本机开关；命中次数会记入配置并展示在「安全设置」页。
- **违禁词库**：`config.json` 的 `security.bannedWords`。昵称在 WebSocket 握手时校验，命中即拒绝（`1008 / banned_nickname`）并在事件流记录命中词；首页输入昵称时会按 `/api/banned-words` 做本地预检提示（只作体验优化，真正拦截在后端）。文字聊天使用同一套词库（见 2.7）。
- **连入终端**：一行一台终端，显示昵称、IP、类型（玩家 / 访客 / 管理端）、房间号、连入时间（东八区）、在线时长，支持按状态筛选与关键字搜索。「强制断开」会让对方收到 `4001` 关闭码并回到首页；管理端自身连接不可被断开。
- **房间管理**：以卡片展示每个房间的状态、轮次、时长、存活人数、阶段与成员（房主 / 机器人 / 离线 / 当前回合标记）。可执行「重置牌局」（回到等待阶段，玩家自动退回大厅）、「关闭房间」（断开房内所有连接）、「移出玩家」（对方收到 `4001` 关闭码并回到首页）。
- **系统管理**：进程运行时长、在线终端数、房间数、峰值内存、Python / FastAPI 版本、1/5/15 分钟负载、磁盘占用进度条，以及最近 120 条服务端事件（连接、建房、管理员操作等）。
- 数据每 2 秒由管理端 WebSocket 全量推送一次；面板上的时间统一按东八区渲染。安全设置子页可在线维护黑名单与违禁词，改动即时写回 `config.json` 并热生效。

### 2.7 聊天室（文字 + 语音）

- **位置**：游戏页右侧栏与等待大厅右侧各有一个聊天室面板（`ChatPanel.vue`），分「💬 聊天」「🎙️ 语音」两个页签。进入房间即可聊天，不必等牌局开始；大厅与游戏页之间跳转时聊天记录与语音通话均不中断（语音引擎为跨页面单例）。
- **文字聊天**：消息经房间 WebSocket 的 `SendChat` 指令广播（`Event_Chat`），服务端保留最近 100 条历史，晚加入者通过状态快照补齐最近 50 条。加入 / 离开 / 重连、机器人进出、语音动态都会发系统消息。单条最长 300 字符，同一玩家 1 秒内限一条；内容命中违禁词会被拒绝并提示命中词（与昵称同一套词库，归一化匹配可挡拆写）。
- **消息排布**：微信 / QQ 式对齐——自己的发言靠右（蓝色气泡），其他人的发言靠左（灰色气泡）；昵称与时间在气泡外上方、不上底色，气泡朝发送侧收角；系统消息居中灰色小字。
- **语音通话**：WebRTC Mesh（≤4 人点对点直连），媒体流不经过服务器。信令走房间 WebSocket：`VoiceJoin` 后新成员从 `Event_VoicePeers` 拿到既有成员并主动发 offer，老成员收 `Event_VoicePeerJoined` 等待 offer；`VoiceSignal` 点对点转发 offer / answer / ICE。成员表与禁麦标记随游戏快照下发（`voice` 字段）。
- **通话内功能**：自主静音（`VoiceSetMute`，他人可见静音徽标）、麦克风 / 输出设备选择、总音量调节、说话中的成员高亮（WebAudio 能量检测）。房主可「全体禁麦 / 解除禁麦」（`VoiceMuteAll`，服务端强制禁用对方麦克风轨道）、「移出成员」（`VoiceKick`）、「关闭通话」（`VoiceClose`，全员退出）。
- **生命周期**：断线自动退出通话并通知他人；重置牌局会结束当前通话；解散房间随连接一同清理。机器人不参与语音。
- **安全上下文**：语音需要浏览器 `getUserMedia`，仅在 HTTPS 或 localhost 下可用（见 3.4 自签证书）。以 HTTP 打开时语音页签会提示改用 HTTPS 地址，文字聊天不受影响。

## 3. 程序配置与启动

### 3.1 环境要求

- macOS 或 Linux
- Node.js 18 及以上、npm（仅开发调试与构建需要）
- Python 3.9 及以上（生产运行仅需 Python 与后端依赖）

### 3.2 一键配置

```bash
chmod +x setup.sh start.sh
./setup.sh
```

`setup.sh` 会检查 Git、Node.js、npm 和 Python，安装前端依赖，并执行 `npm run build` 生成 `dist/`。后端依赖清单位于 [backend/requirements.txt](/backend/requirements.txt)。

### 3.3 启动开发环境

```bash
./start.sh
```

启动脚本会自动创建 `venv/`，安装 FastAPI、Uvicorn、WebSocket 等后端依赖，安装前端 npm 依赖，然后启动：

- 前端开发服务器：`https://localhost:5173`（检测到 `certs/` 下的自签证书时自动启用 HTTPS，并把 `/api` 与 `/ws` 代理到 8000）
- 后端 API 与 WebSocket：`https://localhost:8000`（配了证书参数时）
- 健康检查：`https://localhost:8000/api/health`

浏览器访问 `https://localhost:5173` 开始游戏（首次需信任自签证书）。按 `Ctrl+C` 停止前端和后端服务。

开发模式为两个进程：Vite 开发服务器（5173，提供模块热更新，并将 `/api` 与 `/ws` 代理到 8000）加 Uvicorn（8000）。若 `venv/` 已损坏（如从其他环境拷贝导致 shebang 失效或包文件缺失），删除 `venv/` 后由脚本重建，或按 3.5 手动重建。没有证书时两者都回退 HTTP，此时浏览器会禁用语音通话（文字聊天不受影响）。

### 3.4 生产模式（单进程，一条指令启动前后端）

前端执行 `npm run build` 后，`src/` 被编译为纯静态文件输出到 `dist/`（一个 `index.html` + 一个 JS + 一个 CSS）。后端启动时自动挂载该目录：`/` 返回 `index.html`，`/assets/*` 返回 JS 与 CSS。配合同一进程内的 `/api/*` REST 接口和 `/ws/{房间号}/{玩家名}` WebSocket，**生产模式下不需要单独启动前端服务**，一条 uvicorn 指令即同时提供页面、接口与实时对战通道。

语音通话依赖 `getUserMedia`，浏览器只在安全上下文（HTTPS / localhost）下开放，因此生产模式默认启用 HTTPS 自签证书：

```bash
# 第 0 步：生成本地自签证书（一次性；已生成过可跳过，本机 IP 变化后重新执行一次）
./scripts/gen-cert.sh

# 第 1 步：构建前端（仅源码改动后需要执行，产物输出到 dist/）
npm run build

# 第 2 步：启动生产服务（0.0.0.0 监听，局域网其他设备可直接访问）
./venv/bin/python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 \
  --ssl-certfile certs/server.crt --ssl-keyfile certs/server.key
```

`./venv/bin/python` 需替换为已安装后端依赖的解释器（venv 重建方式见 3.4 末尾）。证书由 `scripts/gen-cert.sh` 生成，SAN 覆盖 `localhost`、`127.0.0.1`、`::1`、本机当前所有 IPv4 及常见内网地址，有效期 825 天；`certs/` 已加入 `.gitignore`，不会提交。直接运行 `python backend/main.py` 时若检测到证书也会自动启用 TLS。

局域网访问地址（`<Mac-局域网IP>` 按本机实际网卡地址调整，可用 `ifconfig` 查看）：

| 设备位置 | 地址 |
| --- | --- |
| 本机 | `https://localhost:8000` |
| 同网段其他设备 | `https://<Mac-局域网IP>:8000` |

自签证书不被浏览器默认信任，每台设备首次访问会提示「不安全」，选择「高级 → 继续访问」即可，只需确认一次。若未带证书参数启动（纯 HTTP），页面与文字聊天正常，但语音通话不可用。

前端 WebSocket 地址默认跟随 `window.location.host` 动态拼接（见 `src/services/websocket.ts` 与两个 view），HTTPS 页面会自动改用 `wss://`，设备从哪个地址打开页面就会连回同一后端，无需额外配置；仅当 WebSocket 需要独立主机时才设置 `VITE_WS_HOST`。



### 3.5 分别启动

前端（开发服务器，支持热更新）：

```bash
npm install
npm run dev
```

后端：

```bash
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

- `views/`：入口页、等待大厅、游戏房间和管理后台。
- `components/`：公共牌、玩家手牌、候选表格等界面组件；管理后台的四个子页为 `AdminTerminals.vue`（连入终端）、`AdminRooms.vue`（房间管理）、`AdminSystem.vue`（系统管理）、`AdminSecurity.vue`（安全设置）；`ChatPanel.vue` 为右侧栏聊天室（文字 + 语音两个页签）。
- `stores/game.ts`：保存服务端推送的游戏快照和当前玩家身份。
- `services/websocket.ts`：建立 WebSocket、发送指令、接收状态事件，并处理被管理员断开（`4001`）后的提示与退出；聊天与语音事件在此分发给对应回调。
- `services/presence.ts`：持久化终端 `clientId`，维护欢迎页的在线登记连接，供管理后台识别「谁连进来了」。
- `services/voice.ts`：语音通话引擎（单例）。管理 `RTCPeerConnection` Mesh、本地 / 远程音频分析（说话检测）、设备选择与音量、静音与禁麦状态；跨页面保活，大厅与游戏页跳转不中断通话。
- `composables/gameLogic.ts`：处理自己的手牌隐藏、线索计算和候选区展示逻辑。
- `utils/admin.ts`：管理后台的时间、时长与状态文案格式化（东八区）。
- 轮次指引：右侧操作栏的轮次高亮、「① 抽牌 → ② 选牌 → ③ 判定」统一步骤条（随阶段推进打勾），全部为模板与 CSS 实现，不改通信协议。
- 页面布局（16:9 全宽）：标题栏铺满整屏，中间游戏区保持原有宽度并居中，左右两侧空白区各挂一栏——左侧为个人线索栏，右侧为聊天室；右侧操作区高度与左侧三个板块（公牌 / 其他玩家 / 手牌）上下齐平。屏幕窄于 1600px 时退化为单列，两栏顺次下移。等待大厅同样采用「主体 + 右侧聊天室」的双栏布局。
- 房主身份判定：大厅与游戏页都以服务端快照的 `hostId` 为准（而非 URL 参数），手动填写房号加入的第一人同样取得房主权限。

### 4.3 后端状态与同步

后端以 `GameRoom` 维护一间房间的完整状态，主要阶段为：

`WAITING` 等待玩家 → `PLAYING` 进行中 → `GAME_OVER` 结束。

进行中包含 `DRAW_PHASE`、`ACTION_PHASE`、`JUDGE_RESULT` 和断线时的 `PAUSED`。每次抽牌、判定、回合切换或猜测后，服务端通过 `Event_StateUpdate` 广播游戏快照；新连接通过 `Event_SyncFullState` 同步当前状态。快照除游戏数据外还携带 `chat`（最近 50 条聊天历史）与 `voice`（语音成员表、禁麦标记）。

主要客户端指令包括：`StartGame`、`SelectColorToDraw`、`SelectPublicCard`、`DeselectPublicCard`、`JudgeByPosition`、`JudgeByPoint`、`SubmitGuess`、`SkipTurn`、`AddBot`、`RemoveBot`、`ResetGame`、`KickPlayer` 和 `DissolveRoom`。

聊天室与语音指令（同一条房间连接上发送）：`SendChat`；`VoiceJoin`、`VoiceLeave`、`VoiceSignal`（`to` + SDP / ICE）、`VoiceSetMute`、`VoiceMuteAll`、`VoiceKick`、`VoiceClose`。对应事件：`Event_Chat`、`Event_ChatRejected`、`Event_VoicePeers`、`Event_VoicePeerJoined`、`Event_VoicePeerLeft`、`Event_VoiceSignal`、`Event_VoiceMuteState`、`Event_VoiceHostMuted`、`Event_VoiceKicked`、`Event_VoiceClosed`。

除房间连接外还有两条 WebSocket 通道：

| 通道 | 用途 | 访问限制 |
| --- | --- | --- |
| `/ws/presence/{clientId}` | 欢迎页在线登记，填充管理后台的终端列表 | IP 黑名单命中即拒 |
| `/ws/admin?clientId=…` | 管理后台：首帧 `AdminAuth` 校验口令，之后每 2 秒推送 `Event_AdminSnapshot` | `localOnly` 开关 + IP 黑名单 + 口令 |

管理指令（同一条管理连接上发送）：`AdminKickTerminal`、`AdminResetRoom`、`AdminCloseRoom`、`AdminKickPlayer`、`AdminReloadConfig`、`AdminAddIp` / `AdminRemoveIp`、`AdminAddWord` / `AdminRemoveWord`。

### 4.4 断线处理

玩家断线后仍保留在房间状态中，并标记为离线。若断线者正处于当前回合，房间进入 `PAUSED`；重连后恢复状态。当前后端通过房间号和玩家身份复用房间连接，重连令牌协议属于后续增强项。

## 5. 目录结构

```text
/
├── backend/
│   ├── main.py                 # FastAPI、WebSocket、游戏规则与聊天/语音信令
│   ├── admin.py                # 管理后台：来源校验、快照组装、管理动作
│   ├── registry.py             # 终端注册表与服务端事件日志
│   ├── config.py               # config.json 读写：口令 / localOnly / 黑名单 / 违禁词
│   └── requirements.txt        # Python 依赖
├── config.json                 # 实际生效的配置（gitignore，含口令与黑名单）
├── config.example.json         # 配置模板
├── certs/                      # 自签证书（gitignore，scripts/gen-cert.sh 生成）
├── dist/                       # 前端构建产物（npm run build 生成，后端直接托管）
├── scripts/
│   └── gen-cert.sh             # 生成 HTTPS 自签证书（SAN 覆盖 localhost 与本机 IP）
├── src/
│   ├── components/             # 游戏组件 + 管理后台子页 + ChatPanel（聊天室）
│   ├── composables/            # 组合式逻辑
│   ├── services/               # WebSocket 客户端、终端在线登记、语音引擎（voice.ts）
│   ├── stores/game.ts          # Pinia 状态
│   ├── types/                  # 游戏与管理后台类型定义
│   ├── utils/                  # 通用工具（含管理后台格式化）
│   └── views/                  # 页面（含 AdminPage.vue）
├── setup.sh                    # 环境检查、安装、构建与证书生成
├── start.sh                    # 开发环境一键启动
├── package.json                # 前端脚本与依赖
└── vite.config.ts              # Vite 配置
```

## 6. 已知边界

- 游戏状态仅存于内存，后端重启会清空房间；终端列表、事件日志与聊天历史同样只存在内存里。IP 黑名单与违禁词库在 `config.json` 中持久化，重启后保留。
- HTTPS 使用本地自签证书（`scripts/gen-cert.sh` 生成），浏览器默认不信任，每台设备首次访问需手动「继续访问」；证书 SAN 按生成时的本机 IP 写入，换网络环境后需重新生成。iOS / 部分浏览器对自签证书策略更严，可能需要先在系统里安装并信任该证书。
- 语音通话要求安全上下文：HTTPS（含自签）或 localhost 均可；纯 HTTP 部署时文字聊天可用、语音被浏览器禁用，UI 会提示改用 HTTPS。WebRTC 未配置 STUN / TURN，依赖主机候选地址，适用于同一局域网 / Tailscale 内网；跨 NAT 场景需要补充 STUN。
- 管理后台的来源限制（`localOnly` 与 IP 黑名单）基于对端 TCP 地址判断。若在前面加了反向代理（Nginx / Caddy），所有请求的来源都会变成代理自身（多半是 127.0.0.1），限制随之失效；此时应改为在代理层按 `X-Forwarded-For` 或内网 ACL 再做一层过滤，黑名单同理。
- 管理口令与「仅本机」开关在 `config.json` 中配置（环境变量可覆盖），仅作本机误入防护，不是强认证；如需更强鉴权应引入独立密钥与正式证书。
- 违禁词采用「归一化子串匹配」（忽略大小写、空白与零宽字符），可以挡掉常见变体，但挡不住同音字、图片等变形手段；词库通过 `/api/banned-words` 公开只读（仅供首页预检），请勿放入敏感词。
- `backend/websocket_server.py` 保留了一份早期实现，当前启动脚本使用的是 `backend/main.py`。
