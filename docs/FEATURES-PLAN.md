# 功能规划：聊天室 / 视觉指引 / 管理后台 / 机器人

本文是四项新功能的考察结论与实施方案，供评审确认后分阶段落地。第四项「机器人」与前文的管理后台共用连接注册表，建议按文末顺序实施。

## 0. 本次已完成的修复

**问题**：一轮内可从公牌区选定多张牌。根因是 `cmd_select_public_card` 只覆盖 `selectedPublicCardId`，却把每张被点选的牌都追加进 `removedPublicCardIds` / `usedCardNumbers`；判定命令也不校验传入的 `publicCardId` 是否就是已选定的那张。

**修改**（`backend/main.py`）：

| 位置 | 修改 |
| --- | --- |
| `cmd_select_public_card` | 改为切换语义：重复选同一张忽略；选另一张时回滚上一张的弃置与使用记录，保证任何时刻只有一张牌被占用 |
| `cmd_judge_by_position` / `cmd_judge_by_point` | 必须先选定公共牌，且传入的 `publicCardId` 必须等于 `selectedPublicCardId`；实际判定一律以服务端记录的选定牌为准 |
| 新增 `cmd_deselect_public_card` | 取消选择时回滚 `removedPublicCardIds` 与 `usedCardNumbers`（原实现只清空字段，残留记录会让公牌区一轮少两张） |
| `handle_command` | `DeselectPublicCard` 改走新函数，不再绕过阶段校验 |

**验证**：4 个 WebSocket 客户端完整跑一轮，9 项断言全部通过——抽牌后 6 张、选定仅 1 条使用记录、改选替换不累加、未选定牌判定被拒、取消后恢复 6 张、判定进入 `JUDGE_RESULT`、回合推进为 2 轮且公牌恢复 5 张。

## 1. 现状盘点

| 关注点 | 现状 |
| --- | --- |
| 后端 | 单文件 `backend/main.py`（约 750 行），FastAPI + 原生 WebSocket，房间状态全内存，`rooms: Dict[str, GameRoom]` |
| 连接 | 每名玩家一条 `ws://host/ws/{房间号}/{玩家名}`，`player_id = 房间号_昵称` |
| 房间号 | 前端 `generateRoomId()` 随机 1000–9999，无保留号机制 |
| 终端信息 | 后端不记录 IP、连接时间；玩家进入房间前（欢迎页）不建立任何长连接 |
| 聊天 | 无。玩家在 `WAITING` 阶段已在房间内，可直接复用现有连接 |
| 语音 | 无。局域网 `http://` 访问时 `getUserMedia` 不可用（非安全上下文），这是语音功能的前置约束 |
| 管理 | 无后台，只有 `KickPlayer` 一个房主级动作 |
| 机器人 | 无。`Player` 无 `isBot` 字段；开局要求恰好 4 人 |
| 视觉 | 右侧 `.right-panel` 仅在 `isMyTurn` 时显示「轮到你了！」，无强调样式 |

## 2. 总体建议

保持「单进程 + 内存态」架构不变，把新增能力按模块拆出，避免 `main.py` 继续膨胀：

```
backend/
├── main.py        # app 装配、房间 WebSocket、游戏规则（现有）
├── registry.py    # 连接/终端注册表（管理员终端列表、强制断开的数据源）
├── chat.py        # 聊天消息模型与广播
├── voice.py       # 语音信令转发与静音状态机
├── admin.py       # 管理后台 WebSocket 与动作
└── bots.py        # 机器人回合调度
src/
├── components/ChatPanel.vue       # 文本聊天（大厅/房间共用）
├── components/VoicePanel.vue      # 语音控制 + 音量/设备设置
├── components/AdminTerminals.vue  # 子页 1：连入终端详情
├── components/AdminRooms.vue      # 子页 2：房间管理
├── components/AdminSystem.vue     # 子页 3：系统管理
└── views/AdminPage.vue            # /admin 容器 + 三个标签页
```

通信仍走「JSON over WebSocket」：房间相关指令复用现有连接，管理后台单独一条 `/ws/admin`。

## 3. 功能 A：房间聊天室（文本 + 语音）

### 3.1 文本聊天

**协议**

```jsonc
// 客户端 → 服务端
{ "cmd": "ChatSend", "text": "开一局？" }

// 服务端 → 房间内所有人
{ "event": "Event_ChatMessage",
  "payload": { "id": "c1", "playerId": "1234_P1", "playerName": "阿伟",
               "text": "开一局？", "ts": 1760934000000, "kind": "text" } }
```

- `GameRoom` 增加 `chatHistory: List[dict]`（保留最近 100 条）；新连接建立后先推 `Event_ChatHistory`，再推状态快照。
- 服务端校验：去首尾空白、长度 ≤ 200、同一玩家 1 秒内最多 1 条，超限静默丢弃。
- `kind` 预留 `"system"`，用于「某某加入/离开房间」「房主关闭了语音」等提示。
- 断线重连不重复推送历史，前端按 `id` 去重。

**前端**：`ChatPanel.vue` 同时挂在大厅与游戏房间右侧（可折叠抽屉，未读小红点）。大厅布局为单列卡片，聊天面板作为右侧浮动面板或折叠条；游戏房间已有 `.right-panel`，聊天放在其下方独立区块，避免挤压操作按钮。

### 3.2 语音通话（WebRTC 网状连接）

4 人房最多 6 条点对点连接，无需媒体服务器；服务端只做信令转发与状态管理。

**协议**

```jsonc
{ "cmd": "VoiceJoin" }                                   // 加入语音
{ "cmd": "VoiceLeave" }                                  // 离开语音
{ "cmd": "VoiceSignal", "target": "playerId", "data": {} } // offer/answer/candidate 透传
{ "cmd": "VoiceMuteAll", "muted": true }                 // 房主：全员禁麦
{ "cmd": "VoiceMutePlayer", "playerId": "x", "muted": true } // 房主：指定禁麦
{ "cmd": "VoiceDisable" }                                // 房主：关闭通话

{ "event": "Event_VoiceSignal", "payload": { "from": "playerId", "data": {} } }
{ "event": "Event_VoiceState",  "payload": {
    "enabled": true, "participants": ["p1","p2"],
    "mutedAll": false, "mutedPlayers": ["p3"] } }
```

- 状态并入 `get_state()` 的 `voice` 字段，随 `Event_StateUpdate` 广播，UI 直接从快照渲染麦克风图标。
- 房主禁麦后：被禁者收到状态即关闭本地音轨；其余客户端同时把该 peer 的音量设为 0（双保险，防止客户端不改）。
- 通话关闭后所有客户端销毁 `RTCPeerConnection` 并释放麦克风。

**音量与设备（设置面板，开局前即可用）**

| 设置项 | 实现 |
| --- | --- |
| 听音量 | 每个远端流接一个 `GainNode`，0–200% 增益，`localStorage` 持久化 |
| 说音量 | 本地麦克风流先过 `GainNode` 再进 `RTCPeerConnection`（0–200%） |
| 麦克风设备 | `enumerateDevices()` 的 `audioinput`，`getUserMedia({ audio: { deviceId } })` 切换 |
| 扬声器设备 | `HTMLAudioElement.setSinkId()`（Chrome/Edge 支持；Safari/iOS 部分支持，需降级为系统选择） |
| 输入电平 | `AudioContext.createAnalyser()` 实时显示说话音量条，便于确认设备是否有效 |

设置面板放在大厅（进入房间未开局时）右侧，实时试听；进入游戏后仍可从语音面板重新打开。

**关键前置：安全上下文**

`getUserMedia` 仅在 `https://` 或 `localhost` 下可用。当前局域网访问是 `http://192.168.x.x:8000`，**语音在局域网设备上会直接不可用**。可选方案：

1. **本地自签证书**（推荐，零外部依赖）：`openssl req -x509 -newkey rsa:2048 -nodes -keyout certs/key.pem -out certs/cert.pem -days 365 -subj "/CN=192.168.2.1"`，uvicorn 加 `--ssl-keyfile certs/key.pem --ssl-certfile certs/cert.pem`；每台设备首次访问点「继续前往」，之后即为安全上下文。缺点：证书告警需要手动跳过一次。
2. **内网反向代理**：Caddy 内部 CA 自动签发，需在每台设备安装根证书，配置成本更高。
3. **隧道服务**：cloudflared/ngrok 提供 HTTPS，但依赖外网，局域网低延迟优势消失。
4. **不做语音**：仅文本聊天，语音留待有域名/证书后再开。

> 建议先按方案 1 落地，并在实现时加「语音不可用」的优雅降级提示（检测 `window.isSecureContext`）。

## 4. 功能 B：轮次视觉指引

> 状态：**已实施**（2026-10-20）。纯模板 + CSS 改动，未改通信协议。

目标：轮到自己时，右侧操作栏显著到不可能忽略。

- **右侧栏整栏高亮**：`.right-panel.is-my-turn` 加 2px 橙色边框 + 2.2s 呼吸外发光。
- **回合横幅**：`.turn-indicator.is-mine` 橙色渐变底 + 白色文字 + 脉冲圆点 + 副标题（本阶段该做什么）。
- **统一步骤条**：全程只有一条「① 抽牌 → ② 选牌 → ③ 判定」，两个阶段共用并按 `currentStep` 推进（1 抽牌 / 2 选牌 / 3 判定），已完成步骤打勾变绿，当前步骤橙色描边；步骤条下方不再有说明文字。
- **按钮防误点**：判定阶段未选牌时两个判定按钮置灰禁用；点数判定按钮点击后切换为「点一张手牌」并把 5 张手牌描边高亮，再点一次取消。
- **公共牌待选提示**：轮到本人选牌且尚未选择时，公牌区加 1.9s 呼吸描边（`PublicCards` 的 `attract` 属性）。
- **抽牌按钮**：颜色名居中，剩余张数做成右上角标（两列网格排布），抽完的颜色按钮禁用。
- 非本人回合不再高亮，仅为中性蓝底；所有动画在 `prefers-reduced-motion: reduce` 下关闭。
- 边界处理：新增派生状态 `isMyActiveTurn`（`PLAYING` 且当前回合是自己），避免牌局结束后「轮到你了」与旧步骤条残留。

> 2026-10-20 二次调整：按用户要求取消顶部常驻状态条（改由右侧横幅承载全部回合信息）；页面改为 16:9 全宽三栏布局，线索栏从右侧操作面板移到左侧空白区，右侧空白区预留给后续聊天室。详见 README 4.2。

## 5. 功能 C：系统管理员后台

### 5.1 入口与房间号保留

- 欢迎页提交时判断：昵称 `adminzyq` 且房间号 `6666` → `router.push('/admin')`，不建立游戏连接。
- `generateRoomId()` 增加排除：结果不得为 `6666`（循环重抽）。
- 后端 `websocket_endpoint` 增加守卫：`room_id == "6666"` 的普通玩家连接直接拒绝（提示「该房间号已保留」），避免管理员入口被当成游戏房。
- 管理端连接：`ws://host/ws/admin`，首次消息携带 `{"cmd":"AdminAuth","user":"adminzyq","room":"6666"}`；校验通过才推送数据。**注意**：该鉴权强度仅相当于一个口令，适合局域网自用；如需更严可加 `ADMIN_KEY` 环境变量。

### 5.2 数据基础：终端注册表

现有系统没有 IP 与连接时间，且欢迎页不建连，需补一层注册表（`backend/registry.py`）：

```python
Terminal = {
  "clientId": "uuid",        # 前端生成，localStorage 持久化
  "ip": "192.168.2.7",       # websocket.client.host
  "connectedAt": 1760934000, # epoch 秒
  "nickname": None,          # 欢迎页未填写时为 None
  "roomId": None,
  "kind": "player",          # player | admin
  "ws": websocket,           # 强制断开用
}
```

- 欢迎页挂载时建立 `ws://host/ws/presence?clientId=...`，仅用于登记终端；提交昵称进入房间后，游戏连接携带同一 `clientId`，把昵称与房间号回填到该终端记录。
- 终端断开（presence 或游戏连接全部关闭）后延迟 30 秒移除，避免刷新页面时列表抖动。
- 时间戳统一存 epoch，前端用 `Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai' })` 渲染为东八区时间。

### 5.3 子页 1：连入终端详情

表格一行一终端：昵称（空显示「—」）、IP、连入时间（东八区）、房间号、类型、当前状态（在线/心跳丢失）。

- 「强制断开」按 `clientId` 找到连接，`ws.close(code=4001, reason="admin_kick")` 并清理该玩家在房间内的在线标记（若处于其回合则照常进入 `PAUSED`）。
- 客户端在 `onclose` 中判断 `code === 4001`，弹窗「你已被管理员断开连接」，点击后回欢迎页。
- 列表 2 秒轮询刷新（管理端 WS 推送 `Event_AdminSnapshot`，见 5.6）。

### 5.4 子页 2：房间管理

每个房间一行/卡片：房间号、状态（等待加入 / 游戏中 / 已结束）、游戏时长、轮次、成员昵称（房主带标记、机器人与离线态有图标）。

- 时长：`PLAYING` 用 `now - gameStartedAt`，`WAITING` 用 `now - createdAt`，`GAME_OVER` 用 `gameEndedAt - gameStartedAt`（需在 `GameRoom` 增加这三个时间字段）。
- 点击成员昵称 → 切到子页 1 并高亮该成员的终端行（用 `clientId` 关联；机器人无终端，提示「机器人无连接」）。
- 动作：`AdminCloseRoom`（广播 `Event_RoomClosed` → 关闭所有连接 → 删除房间）、`AdminResetRoom`（复用现有重置逻辑）、`AdminKickPlayer`（复用 `cmd_kick_player`）。

### 5.5 子页 3：系统管理

- 概览：进程启动时间与运行时长、Python/FastAPI 版本、房间总数、在线终端数、活跃游戏数。
- 资源：`os.getloadavg()`（1/5/15 分钟负载）、`resource.getrusage().ru_maxrss`（峰值内存）、`shutil.disk_usage('/')`、`os.cpu_count()`。
- 可选增强：装 `psutil` 后补充实时 CPU/内存曲线；不装也能满足「运行概况」。
- 事件流：最近 50 条服务端日志摘要（连接、断线、房间创建/销毁、管理员操作），内存环形缓冲，便于排障。

### 5.6 管理端推送

```
Event_AdminSnapshot {
  terminals: [...], rooms: [...], system: {...}, recentEvents: [...]
}
```

管理端 WS 每 2 秒推送一次全量快照（数据量小，实现简单）；动作命令在同一连接上发送，服务端执行后立即回推一次。

## 6. 功能 D：机器人玩家

> 状态：**已实施**（2026-10-20）。人数上限按「维持 4 人房」执行。

### 6.1 数据与交互（已实现）

- `Player` 增加 `isBot`；机器人不建立 WS 连接，`isOnline` 恒为 `True`，`to_dict()` 暴露 `isBot` 供前端显示徽标。
- 大厅房主操作区新增「🤖 添加机器人」与每个机器人行上的「移除」，指令：

```jsonc
{ "cmd": "AddBot" }                       // 服务端分配 机器人1/2/3…
{ "cmd": "RemoveBot", "playerId": "..." }
```

- 命名：`机器人N`（N 在房间内递增，跳过已占用序号），`playerId` 形如 `6666__bot1`，与真人 `房间号_昵称` 的命名空间隔离。
- 添加/移除均要求「房主 + 等待阶段」，进行中不可增删。

### 6.2 人数上限（已确认）

维持现有 4 人房规则：`start_game` 仍要求 `len(room.players) == 4`，机器人计入这 4 个名额，房主可连环添加直到满员。若要支持 5 人以上需同步改发牌与公牌逻辑，另行排期。

### 6.3 回合自动化（已实现，方案与原计划不同）

原计划是每次回合切换时 `create_task` 一个一次性协程，需要处理防重入、旧任务取消、跨机器人连动等边界。实际改为**每房间一个常驻驱动任务**：

- `room.botTask` 在开局后由 `start_bot_driver()` 创建，每 0.2 秒轮询一次；仅当 `gamePhase == PLAYING` 且当前回合玩家 `isBot` 时才代它行动。
- 行动序列：随机延时 0.9–1.8 秒后抽一张「仍有存牌」的颜色 → 随机选一张可见公牌（延时 0.6–1.3 秒）→ 随机位置判定或点数判定（延时 0.7–1.4 秒，点数判定随机挑一种手牌颜色）。
- 每个动作前用 `_bot_can_act()` 复核回合归属，房主跳过回合 / 断线暂停 / 重置 / 关房后旧动作会自然失效。
- 机器人**永不提交猜测**，牌局只能由真人猜中或牌堆耗尽结束。
- 驱动在 `GAME_OVER`、`WAITING` 或非机器人回合时继续空转等待，重置后由下一局 `cmd_start_game` 重新拉起；`stop_bot_driver()` 在重置、解散、踢机器人时取消。
- 断线暂停逻辑只对真人生效，机器人不会触发 `PAUSED`。

## 7. 实施顺序与依赖

| 阶段 | 内容 | 依赖 | 预估 |
| --- | --- | --- | --- |
| P1 | 文本聊天 + 轮次视觉指引 | 无 | 0.5–1 天 |
| P2 | 机器人玩家（已完成） | P1 的回合调度改造 | 1–1.5 天 |
| P3 | 管理后台（注册表 + 三子页） | 终端注册表、房间时间字段 | 2–3 天 |
| P4 | 语音通话 + HTTPS 部署 | 证书方案确认 | 2–4 天 |

建议 P1 先上，能立刻改善对局体验；P4 单独排期，因为涉及部署方式变更（HTTP → HTTPS），需要提前通知常连的几台设备换地址。

## 8. 风险与待确认

1. **语音需要 HTTPS**：局域网 `http://` 下 `getUserMedia` 不可用。是否接受自签证书（首次访问需手动信任一次）？
2. ~~**机器人上限**：维持 4 人房上限，还是需要支持更多人数？~~ 已定：维持 4 人房上限。
3. **管理端鉴权**：「昵称 + 房间号」即可进入，安全性有限；是否追加独立口令（环境变量）？
4. **聊天记录**：仅在内存保留最近 100 条（重启清空），是否符合预期？
5. **iOS/Safari**：`setSinkId` 支持不完整，扬声器切换在 iPhone 上可能只能走系统设置；`getUserMedia` 在 iOS 也要求 HTTPS。
6. **单文件后端**：新增四个模块会改变现有文件结构，若有外部脚本依赖 `backend/main.py` 内部符号，需要同步调整（目前只有 `start.sh` 与 README 引用入口 `backend.main:app`，不受影响）。
