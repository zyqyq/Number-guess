# 功能规划（第二弹）：帮助中心 / 旁观模式 / 房主禁聊 / 房间列表 / 分享链接 / 安全口令

> 状态：**预研与前期规划**（2026-10-22）。本文只做考察与方案设计，不含代码改动；待文中「待确认决策点」逐条确认后再分批实施。

## 0. 需求原文与拆解

| # | 需求 | 关键动作 |
| --- | --- | --- |
| 1 | 项目文件夹下写游戏规则+操作方法文档（合并一个 md）；网页首页设「帮助」入口，帮助页图文并茂 | 新增 `docs/HELP.md` + `/help` 路由页 + 首页入口按钮 + 实机截图 |
| 2 | 旁观模式 | 主动旁观（按键）/ 自动旁观（满员或已开始）/ 管理员隐身旁观；旁观者可见性、房主踢人/禁言、组队期与游戏期两种审批交互、显著 UI 区分 |
| 3 | 管理员禁止指定运行中房间的聊天功能 | 房间级 `chatDisabled` 开关 + 管理后台操作入口 |
| 4 | 首页增加房间列表 | 展示「正在运行 / 正在等人」的房间；两种展示方式由管理员设置；房主可隐身不公开 |
| 5 | URL 分享 | 分享链接夹带房间号，访问即预填 |
| 6 | 安全口令 | 管理员开启后，首次访问主页须在 URL 携带长字符串口令；管理员可新建（随机生成）并设有效期 |

## 1. 现状盘点（设计落点）

| 关注点 | 现状（代码位置） | 对新功能的意义 |
| --- | --- | --- |
| 房间状态 | `backend/main.py` 的 `GameRoom`，全内存，`rooms: Dict[str, GameRoom]` | 旁观者、隐私开关、禁聊开关都作为房间字段新增，零迁移成本 |
| 连接模型 | 每玩家一条 `/ws/{房间号}/{昵称}`，`player_id = 房间号_昵称`；`room.ws_connections: Dict[player_id, WebSocket]` 是广播、私聊、踢人的唯一通道 | 旁观者需要独立的连接表，`broadcast_state` / `send_to_player` / 断线清理要区分「参赛者 / 旁观者」 |
| 满员拒绝 | `main.py` WS 握手处 `len(room.players) >= 4` → `1008 room_full` | 功能 2 的「自动旁观」正好改这里：带旁观意图时转入旁观通道而非拒绝 |
| 房主 | 第一个进房的人即房主（建房时 `GameRoom(room_id, player_id)`），前端以 `hostId` 派生 | 旁观审批、踢人、禁言、隐身开关全部复用现有房主判定 |
| 聊天 | `SendChat` → `cmd_send_chat` → `broadcast_chat`（广播给 `ws_connections` 全员，含本人） | 禁聊开关加在 `cmd_send_chat` 入口；旁观者发言要带身份标记与禁言检查 |
| 房间列表 API | `GET /api/rooms` 已存在（`main.py`），返回 `roomId/playerCount/gamePhase` | 功能 4 的数据源已就位，只需扩展字段 + 隐私过滤 |
| 配置 | `backend/config.py` + `config.json`（`admin` / `security` 两段，原子写回，管理后台可热增删） | 功能 4 的展示方式、功能 6 的口令库都作为新的配置段接入，复用同一套机制 |
| 管理后台 | `/ws/admin` + `admin.build_snapshot()`（2 秒全量推送）+ `admin.execute_command()` 指令分发；前端 4 个子页（终端/房间/安全/系统） | 功能 2/3/4/6 的管理端操作都挂在 `execute_command` 与对应子页上 |
| 首页 | `EntryPage.vue`：房间号 + 昵称 → 创建/加入；已支持 `?roomId=` 预填（`onMounted` 读取 query 并置 readonly） | 功能 5 的数据通路已经存在，缺的只是「复制分享链接」入口与体验细节 |
| 语音 | WebRTC Mesh 单例 `src/services/voice.ts`，成员表由服务端 `voiceParticipants` 驱动 | 旁观者允许加入语音（D5 已确认），复用同一成员表 |

## 2. 总体设计原则

1. **旁观者不进 `room.players`**。`start_game`（要求恰好 4 人）、`turnOrder`、`deal_initial_hands`、`check_game_over` 全部围绕 `players` 编写，旁观者混入会直接破坏牌局逻辑并泄露手牌。旁观者用独立容器 `room.spectators` + `room.spectator_conns`。
2. **复用现有通道，不新建协议栈**。旁观者仍走 `/ws/{room}/{nickname}`，仅追加 query 参数；管理端仍走 `/ws/admin`，新增指令。
3. **内存态优先，配置持久化沿用 config.json**。房间级开关（禁聊/隐身）不落盘（重启即失，与现有房间生命周期一致）；全局设置（房间列表展示方式、安全口令库）落 config.json。
4. **安全口令不挡静态资源**。`/assets/*` 必须放行否则页面白屏；`/admin` 豁免（已有 localOnly + 口令双保险）；本机回环建议豁免（见 D6），避免管理员把自己关在门外。

---

## 3. 功能 1：帮助文档 + 帮助页

### 3.1 交付物

| 文件 | 说明 |
| --- | --- |
| `docs/HELP.md` | 游戏规则 + 操作方法合并文档（项目文件夹内），面向玩家也面向开发者 |
| `public/help/*.png` | 从运行中的网页截取的界面图（`vite build` 时原样拷贝，相对路径 `/help/xx.png` 引用） |
| `src/views/HelpPage.vue` | `/help` 路由页：结构化排版 + 插图 + 锚点目录 |
| `src/router/index.ts` | 新增 `{ path: '/help', component: HelpPage }` |
| `EntryPage.vue` | 两个主按钮下方增加「📖 玩法帮助」次级按钮；`/help?from=` 可选带回跳 |

### 3.2 内容结构（HELP.md 与帮助页同源）

1. **游戏是什么**：4 人推理桌游，看得见别人的牌、看不见自己的牌。
2. **牌组与点数**：60 张 / 5 色 / 颜色-数字循环绑定 / 点数公式（引用 README §2.1）。
3. **开局**：发牌规则、公共牌区、可见性示意（配截图）。
4. **回合三步**：抽牌 → 选牌 → 判定（位置判定 / 点数判定各配一张游戏页截图 + 高亮圈注）。
5. **提交猜测**：随时可猜；猜错公开数字；牌堆耗尽平局。
6. **操作方法**：建房/加房/大厅（添加机器人、开始游戏）/ 游戏页各区域说明 / 聊天室（文字+语音）/ 旁观模式（功能 2 落地后补一节）/ 管理后台入口提示。
7. **常见问题**：麦克风不可用（HTTPS）、房间已满（自动旁观）、断线暂停。

### 3.3 截图清单（首批 6 张，功能 2 落地后补 2 张）

| 文件名 | 内容 |
| --- | --- |
| `entry.png` | 首页（房间号/昵称/创建/加入/帮助入口） |
| `lobby.png` | 大厅（玩家列表、机器人、开始游戏、右侧聊天室） |
| `game-board.png` | 游戏页全景（公共牌区 / 其他玩家 / 自己手牌 / 回合指引） |
| `game-turn.png` | 轮到自己的状态（步骤条 + 选色抽牌按钮） |
| `chat-voice.png` | 聊天室双页签（文字对齐 + 语音成员表） |
| `admin.png` | 管理后台房间管理卡片 |
| `spectate.png`（后补） | 旁观模式 UI 特征 |
| `spectate-approve.png`（后补） | 房主审批弹窗 |

> 实现方式说明：`docs/HELP.md` 用相对路径 `![](../public/help/entry.png)` 插图，帮助页用 `/help/entry.png` 绝对路径，两边内容手工同源（帮助页是权威版，md 是精简版）；后续若内容频繁变动，可加一个小脚本从 HELP.md 生成帮助页数据，本期先不做。

---

## 4. 功能 2：旁观模式（核心批次）

### 4.1 数据模型（`GameRoom` 新增字段）

```python
self.spectators: Dict[str, Player] = {}        # player_id -> Player（复用 Player 类，不发牌）
self.spectator_conns: Dict[str, WebSocket] = {}  # player_id -> 连接
self.spectator_chat_banned: set[str] = set()   # 被房主禁言的旁观者
self.spectator_pending: Dict[str, dict] = {}   # 等待房主审批的旁观者 {playerId, playerName, ts}
self.is_private = False                        # 房主隐身开关（功能 4 共用）
```

`get_state()` 新增 `spectators` 段：`[{playerId, playerName, chatBanned, hidden}]`，其中 `hidden=true` 为管理员隐身旁观（不推送该条给任何人，仅管理快照可见）。

### 4.2 接入路径（WS 握手改造）

`/ws/{room}/{nickname}` 增加 query：`spectate=1`（主动旁观）/ `adminToken=xxx`（管理员隐身旁观凭证）。

```
握手流程：
  参赛者正常流程（现有）
  ├─ 房间未满 且 gamePhase == WAITING 且 !spectate=1 → 现有参赛者逻辑
  ├─ spectate=1 → 转旁观者流程（无论房间状态）
  └─ 房间已满 或 gamePhase != WAITING：
        ├─ spectate=1 → 旁观者流程（自动旁观）
        └─ 否则 → 维持现有 1008 room_full 拒绝
旁观者流程：
  ├─ adminToken 有效 → 隐身旁观（不广播、不可见、禁言）
  ├─ gamePhase == WAITING → 直接进入，广播系统消息「XX 进入旁观」
  └─ gamePhase == PLAYING/GAME_OVER → 进入 spectator_pending，向房主推 Event_SpectatorAsk
        ├─ 房主批准 → 进入 spectators，广播系统消息
        └─ 房主拒绝 / 60 秒超时 → close(1008, reason="spectate_rejected")
```

刷新重连： spectator 重新走上述流程；已在 `spectator_pending` 审批通过名单（按 `player_id` 记忆）的不再重复弹窗。

### 4.3 指令与事件协议（新增）

| 方向 | 名称 | 载荷 | 说明 |
| --- | --- | --- | --- |
| C→S | `SpectateSetView` | `{targetPlayerId}` | 旁观者切换代入视角（D1），服务端回该视角 state |
| C→S | `SpectatorRespond` | `{playerId, allow, allowChat, allowVoice}` | 房主对 pending 旁观者的审批（仅房主、仅游戏中） |
| C→S | `SpectatorLeave` | — | 主动退出旁观（也可直接断连） |
| C→S | `KickSpectator` | `{playerId}` | 房主踢出旁观者并断开其连接 |
| C→S | `MuteSpectator` | `{playerId, muted}` | 房主禁言/解禁旁观者 |
| C→S | `SetRoomPrivacy` | `{private}` | 房主设置房间隐身（功能 4） |
| S→C | `Event_SpectatorAsk` | `{playerId, playerName}` | 游戏中旁观者待审批（只推房主） |
| S→C | `Event_SpectatorJoined` / `Event_SpectatorLeft` | `{playerId, playerName}` | 旁观者进出（广播，含系统消息） |
| S→C | `Event_SpectatorRejected` | `{by}` | 被房主拒绝（随即关连接） |
| S→C | `Event_RoomPrivacyChanged` | `{private}` | 房间隐身状态变化 |
| 管理 | `AdminSpectate` | `{roomId}` | 签发隐身旁观凭证（返回 token，前端凭 token 重连房间 WS） |
| 管理 | `AdminSetChatDisabled` | `{roomId, disabled}` | 功能 3，见 §5 |

### 4.4 信息可见性（按 D1 修订：视角代入）

- **核心机制：视角代入**。旁观者不是「信息被裁剪的第三种角色」，而是**代入某位参赛者的座位**：服务端以 `spectateViewId`（默认第一位玩家/房主）为视角生成 state，等价于「我就是这位玩家」——自己的手牌正常可见、他人的手牌仍是 `?`、线索与回合提示与真身完全一致。实现上 `get_state(viewer_id)` 只多一个参数，`viewer_id` 取参赛者 id 时天然得到该视角，不必写第二套裁剪逻辑。
- **UI 直接复用**：GameRoom 现有三栏布局、手牌区、公共牌区、回合指引、右侧聊天室全部沿用，只在外层加旁观水印/徽标与视角切换器（见 §4.5），改动量远小于「独立旁观界面」。
- **只读约束**：旁观者有 `viewerId` 但**不是参赛者**。所有写指令（`StartGame` / `SubmitGuess` / `JudgeRound` / `DrawCard` / `SkipTurn` / `RestartGame`）一律返回 `Event_ActionRejected{reason: "旁观者不可操作"}`；服务端判断依据是 `player_id not in room.players`，而非前端隐藏按钮。
- **视角切换**：`SpectateSetView{targetPlayerId}` 仅对旁观者生效，目标必须是本房参赛者，服务端记 `spectatorTarget[player_id] = targetPlayerId` 并回一帧新 state；切换失败（目标中途退出）回退到第一位存活玩家。
- 聊天：旁观者可发言（消息带「旁观」徽标，`ChatMessage` 新增 `spectator?: boolean`）；被禁言后 `SendChat` 返回 `Event_ChatRejected{reason: "你已被房主禁言"}`；管理员隐身旁观一律禁言。
- 语音：旁观者**允许加入语音通话**（D5 已确认），与参赛者共用 `voiceParticipants` 成员表，可被房主单独禁麦/踢出；管理员隐身旁观不进语音（否则会被成员列表暴露）。

### 4.5 UI 设计

| 场景 | 设计 |
| --- | --- |
| 旁观模式特征 | **复用参赛者界面 + 显著标识**：右上角斜纹徽标「👁 旁观中 · 代入 张三」、顶栏通栏提示条（含视角切换器）、写操作按钮（开始/判定/提交猜测）禁用并提示「旁观者不可操作」、手牌区加「代入视角」角标。**不做灰度滤镜**（会看不清牌面，与 D1 的信息可见性冲突） |
| 视角切换器 | 游戏页顶栏下拉「视角：张三(房主) / 乙 / 丙 / 丁」，切换发 `SpectateSetView`；下游 state 立即替换，无需重连 |
| 大厅旁观入口 | 大厅新增「👁 以旁观者身份进入」按钮；满员/已开始的房间在用户落地时自动转旁观并提示原因 |
| 大厅成员列表 | 房主视角：旁观者行显示在参赛者下方分区，昵称栏后内联「踢出」「禁言」两个小按钮（对应需求：组队阶段直接设置） |
| 游戏中旁观审批 | 房主屏幕中央弹窗：「XX 请求旁观」+「允许参与聊天 / 参与语音」复选框 + 允许/拒绝按钮；60 秒无响应自动拒绝 |
| 旁观者自己的界面 | 顶部提示「正在等待房主批准…」；被拒后提示并回首页 |
| 管理后台 | 房间卡片新增「隐身旁观」按钮；成员列表旁观者单独分区展示（管理员可见全部，含 hidden） |

### 4.6 与现有逻辑的冲突点（必须处理的清单）

| 现有逻辑 | 影响 | 处理 |
| --- | --- | --- |
| `broadcast_state` 只遍历 `ws_connections` | 旁观者收不到状态 | 改为「参赛者 + 旁观者」双通道，各自 `get_state(for_spectator=…)` |
| `cmd_send_chat` 广播给 `ws_connections` | 旁观者收不到聊天 | `broadcast_chat` 扩展到 spectator_conns（禁言者除外，审批中者除外） |
| `cmd_kick_player` / 管理员踢人 | 只处理参赛者 | 新增 `cmd_kick_spectator`（先 pop conn 再 close 4001，与现有修复同一模式） |
| 断线清理（WS disconnect 分支） | 旁观者断线无感知 | 增加 spectator 分支：移出 spectators + 系统消息（hidden 除外） |
| `admin_close_room` | 不断旁观者连接 | 关闭时向 spectator_conns 推 `Event_RoomClosed` 并清空 |
| `reset_room_state` | 旁观者应保留 |  spectator 不清空（聊天记录同样保留），仅结束语音 |
| `cmd_voice_*` | 旁观者不在 `voiceParticipants` | 天然隔离，无需改动 |

---

## 5. 功能 3：管理员禁止指定房间聊天

- `GameRoom.chatDisabled: bool = False`，`get_state()` 输出该字段（前端聊天输入框置灰提示「管理员已关闭本房聊天」）。
- `cmd_send_chat` 入口检查：`room.chatDisabled` → 回 `Event_ChatRejected{reason: "聊天功能已被管理员关闭"}`（不广播）。
- 管理指令 `AdminSetChatDisabled{roomId, disabled}`（`admin.execute_command` 新增分支），写事件日志；`_room_dict` 快照加 `chatDisabled`。
- `AdminRooms.vue` 房间卡片操作区加「禁止聊天 / 恢复聊天」切换按钮（当前状态用徽标显示）。
- 生效范围：房内所有人（含旁观者，禁言逻辑先于 chatDisabled 判断，提示语区分）。

## 6. 功能 4：首页房间列表

### 6.1 数据层

`GET /api/rooms` 扩展（**只返回公开房间**，`is_private=false` 且 `gamePhase in (WAITING, PLAYING)`）：

```json
{"rooms": [{"roomId": "1234", "playerCount": 3, "gamePhase": "WAITING",
            "hostName": "张三", "spectatorCount": 1, "createdAt": 1690000000,
            "chatDisabled": false}]}
```

> `GAME_OVER` 房间不展示（牌局已结束，加入无意义）；满员进行中房展示「已满 · 可旁观」，点击后以旁观意图进入（与功能 2 衔接）。

### 6.2 展示方式（管理员设置）

- ~~`config.json` 新增 `roomList: {"mode": "grid"}`，取值 `grid`（卡片） / `compact`（紧凑列表）。~~ **已调整（2026-10-22 深夜）**：只保留**紧凑列表**一种排布，配置项改为 `roomList: {"enabled": true}` 总开关；管理后台「系统管理」页改为**开启 / 关闭**房间列表（`AdminSetRoomListEnabled` 指令，写回配置）。关闭时 `/api/rooms` 直接返回空列表，首页连面板占位都不渲染，与没有该功能时完全一致。
- 首页 `EntryPage.vue` 增加列表面板（桌面端右侧 320px / 窄屏堆叠到下方），每 4 秒轮询 `/api/rooms`；点击某一房 → 预填房间号并触发加入（满员时提示将转旁观）。

### 6.3 房主隐身

- 指令 `SetRoomPrivacy{private}` → `room.is_private`；大厅房主操作区加「🔒 房间隐身」开关（默认关闭，tooltip 说明「隐身房间不出现在首页列表」）。
- `/api/rooms` 过滤 `is_private`；管理快照不受影响（管理员可见全部）。

## 7. 功能 5：URL 分享

现状已支持 `?roomId=1234` 预填（只读）。补齐：

1. **大厅房间号旁**与**游戏页顶部**各加一个「🔗 复制分享链接」按钮，复制 `${location.origin}/?roomId=${roomId}`（HTTPS 下自动带 https，手机扫码/转发均可用）。
2. 分享落地体验优化：带 `roomId` 进入时输入框只读但提供「✕ 换个房间」清空按钮；昵称仍走本地缓存自动填。
3. 若该房间已满员/已开始，落地页直接提示「该房间已开始，你将以旁观者身份进入」并默认勾选旁观意图（与功能 2 联动，需功能 2 落地后生效；此前维持现有「房间已满」提示）。
4. 兼容别名 `?room=`（与 `?roomId=` 等价），便于口头传播短链。

## 8. 功能 6：安全口令

### 8.1 模型（config.json 新增 `access` 段）

```json
"access": {
  "enabled": false,
  "tokens": [
    {"token": "43 位 base64url 随机串", "note": "给手机用",
     "createdAt": 1690000000, "expiresAt": null, "hits": 0}
  ]
}
```

- `enabled=false`（默认）时全站行为与现在完全一致；开启后除下述豁免外一律要求口令。
- 有效期：`expiresAt` 为空表示永不过期；过期自动失效（比对时判断）。

### 8.2 校验点与豁免

| 路径 | 行为 |
| --- | --- |
| `/` 与 SPA 兜底 `/{path:path}`（返回 index.html 的请求） | 无有效口令 → 403 说明页（复用现有 `/admin` 403 页样式，文案改为「需要访问口令」） |
| `/assets/*`、`/favicon.svg` 等静态资源 | **不校验**（否则页面无法加载） |
| `/api/rooms` | 与主页一致校验（首页被挡时列表无意义） |
| `/ws/{room}/{name}`、`/ws/presence` | query `key=` 无效 → `1008 access_denied` |
| `/admin`、`/api/admin/*`、`/ws/admin` | 豁免（已有 localOnly + 管理口令） |
| 回环地址（127.0.0.1 / ::1） | **建议豁免**（决策点 D6），防止管理员误把自己关在门外 |

「首次访问」语义：URL 带 `?key=` 验证通过后种下 HttpOnly Cookie（`access_key`，SameSite=Strict，7 天有效）；之后带 Cookie 即可访问，无需重复在 URL 携带。Cookie 与 URL key 任一有效即放行。

### 8.3 管理界面（AdminSecurity.vue 新增面板）

- 总开关（`AdminSetAccessEnabled`，写 config.json）。
- 「新建口令」按钮 → 后端 `secrets.token_urlsafe(32)` 生成，弹窗展示完整口令 + 一键复制 + 有效期输入（天数，空 = 永久）+ 备注。
- 口令表格：脱敏显示（前 6 后 4）、备注、创建时间、过期时间、命中次数、删除按钮。
- 提示文案：开启后手机等设备需通过「带 key 的完整链接」或「首次访问后 7 天内免 key」访问。

### 8.4 与其他安全层的关系

优先级：**IP 黑名单 > 安全口令 > 仅本机开关**（管理后台自己的层级不变）。安全口令管「进门」，黑名单管「永拒」，二者独立叠加。

## 9. 实现批次与依赖排序

| 批次 | 内容 | 依赖 | 预估改动面 |
| --- | --- | --- | --- |
| **P0** | 功能 1：HELP.md + /help 页 + 首页入口 + 截图 | 无（截图可先行拍 6 张） | 新增 2 文件 + EntryPage 小改 |
| **P1** | 功能 4 + 5：房间列表（API 扩展/隐私/展示方式）+ 分享链接 | 无 | `main.py` API 段、`config.py` 新段、EntryPage、AdminSystem、LobbyPage/GameRoom 小改 |
| **P2a** | 功能 2 数据模型与接入：spectators/spectator_conns、握手改造、state 双通道、断线清理 | 无 | `main.py` WS 段 + `get_state` 参数化 |
| **P2b** | 功能 2 房主控制：审批弹窗、踢人、禁言、大厅内联按钮、系统消息 | P2a | `main.py` 新指令、`types/game.ts`、`websocket.ts`、LobbyPage/GameRoom/ChatPanel |
| **P2c** | 功能 2 UI 特征与旁观者界面（水印/占位/徽标）+ 管理员隐身旁观 | P2b | 新增 `SpectatorOverlay` 类组件、AdminRooms、admin.py |
| **P3** | 功能 3：房间禁聊（后端 + AdminRooms 按钮 + 输入框置灰） | 无（可与 P2 并行） | `main.py` 一处判断 + 两个组件 |
| **P4** | 功能 6：安全口令（config 段 + 校验中间件式改造 + 管理面板 + 403 页） | 建议最后（改全局入口，避免反复挡住自己联调） | `main.py` 路由段、`config.py`、AdminSecurity、新增 403 页 |

每批次独立可测、可回滚；P2 内部按 a/b/c 顺序提交，任一步骤停下系统仍可用（只是旁观链路不完整）。

> **实施状态（2026-10-22 更新）**：**P1 已完成**——房间列表（`/api/rooms` 过滤与扩展字段）、房主隐身（`SetRoomPrivacy`）、房间列表总开关（`AdminSetRoomListEnabled`）、分享链接（含 `?room=` 别名与「换个房间」）。验证：协议 27/27、UI 28/28、聊天回归 33/33、牌局回归 10/10。
> **P1 后续微调（2026-10-22 23:3x）**：房主操作区「🤖 添加机器人」与「🔒 房间隐身」改为同一行各占一半宽度，隐身的说明文字改为 hover/focus 浮出提示，已隐身时按钮文案为「🔓 解除房间隐身」；房间列表只保留紧凑列表，管理员改为开启/关闭总开关。
> **P0 暂缓**：因排期调整，帮助文档与 `/help` 页的代码改动已全部回退，本文件保留原设计方案（§3），恢复时按 §3 重新实施即可。
> **P2 已完成（2026-10-23）**：旁观者模式全链路落地（P2a + P2b + P2c 一次做完）。
> - 数据模型：`spectators` / `spectator_conns` 与 `players` / `ws_connections` 完全分离，牌局逻辑（`start_game` / `turnOrder` / `deal_initial_hands` / `check_game_over`）无需任何改动；新增 `spectatorView` / `spectatorMuted` / `spectatorVoiceBanned` / `spectatorHidden` / `spectatorPending`。
> - 接入：`/ws/{room}/{name}?spectate=1`（+`adminToken`）；`WAITING`/`GAME_OVER` 直接进，`PLAYING` 走房主审批（`Event_SpectatorAsk` → `SpectatorRespond`，60 秒超时自动拒绝，等待期间轮询 `client_state` 以撤销断开客户端的幽灵申请）。
> - **视角代入按 D1 落地为「复用前端裁剪」**：服务端 `get_state()` 不变（本就全量下发），前端把 `store.myPlayerId` 指向被代入者即可得到与真身完全一致的视角，不必写第二套裁剪逻辑——比原计划的 `get_state(viewer_id)` 更简单且不会出现两套视图漂移。
> - 只读：`handle_command` 前置旁观者分支，白名单仅 `SendChat / SpectateSetView / SpectatorLeave / Voice*`，其余回 `Event_ActionRejected`。
> - 语音（D5）：`cmd_voice_join/leave/kick/close` 改用 `member_of` / `conn_of` 兼容旁观者；`spectatorVoiceBanned` 拒绝审批时未授权的旁观者。
> - 管理隐身旁观（P2c）：`AdminSpectate` 签发一次性 120 秒 `adminToken`，`hidden` 旁观不进入 `state.spectators`、管理快照可见并标记 `hidden`。
> - 验证：协议层 `/tmp/test_spectator.py` **43/43**、UI 层 `/tmp/test_spectator_ui.py` **27/27**、管理后台 `/tmp/test_admin_spectate_ui.py` **11/11**；回归 `test_rooms_p1.py` 28/28、`test_p1_ui.py` 41/41、`test_chat.py` 33/33、`test_regression.py` 10/10。

## 10. 测试方案（沿用现有手段）

- **协议层**（`websockets` + `ssl=CERT_NONE`，仿 `/tmp/test_chat.py`）：旁观接入/审批/拒绝/禁言/踢出/隐身不可见/满员自动旁观/禁聊开关/房间列表过滤/口令校验（含过期、Cookie、豁免路径），预计新增 40+ 断言。
- **UI 层**（playwright-core + `--ignore-certificate-errors` + 假摄像头）：双端 + 第三旁观端 1920×1080 全流程；旁观 UI 特征断言（灰度/徽标/占位）；房主审批弹窗交互；0 console 报错。
- **回归**：现有 `test_chat.py` 33 项 + `test_regression.py` 10 项全量重跑，确保 P2 的 `ws_connections` 拆分没有破坏参赛者链路。

## 11. 风险与边界

| 风险 | 缓解 |
| --- | --- |
| `ws_connections` 拆分影响面大（广播/踢人/断线/admin_close 五处） | P2a 先做「双通道适配层」，五处统一走 `room.iter_player_conns()` / `iter_spectator_conns()`，逐点替换并保留旧行为测试 |
| 视角代入后旁观者能看「代入者」的手牌，需避免误当成自己的回合 | 顶栏徽标常驻「代入 XX 的视角」+ 所有写操作按钮禁用 + 回合指引加「（非你的回合）」标注 |
| 审批弹窗时房主不在电脑前 | 60 秒超时默认拒绝，旁观者侧提示「房主未响应」；房主上线后可从大厅/游戏页补批（D4） |
| 管理员隐身旁观凭证被伪造 | token 由 `AdminSpectate` 指令现场签发（32 位随机，仅存内存），一次性使用，不与任何用户输入相关 |
| 安全口令开启后手机访问受阻 | 回环豁免 + Cookie 7 天 + 口令链接整串分享；开启时管理面板强提示 |
| 内存态导致刷新丢审批状态 | 审批通过名单按 `player_id` 存房间内存，刷新重连不重复弹窗；进程重启全部重来（与现有语义一致） |
| `get_state` 参数化后两套视图不一致 | 单一函数 + 一个 `for_spectator` 参数，字段集合保持一致，仅手牌数字不同 |

## 12. 决策点（已由用户于 2026-10-22 确认）

| # | 决策点 | **确认结论** | 影响 |
| --- | --- | --- | --- |
| D1 | 旁观者信息可见性 | **视角代入**：旁观者主动选择代入某位参赛者的视角，看得见该玩家的手牌与线索；已有 UI 排布基本不用调整（与本文 §4.4/§4.5 修订版一致） | `get_state(viewer_id)` 参数化；新增 `SpectateSetView`；UI 复用 GameRoom |
| D2 | 满员/已开始房间的用户落地 | **是**，自动转旁观并明确提示 | 功能 2 与 5 的衔接体验 |
| D3 | 大厅（组队期）旁观者是否需批准 | **不需要**，直接进；房主可当场踢/禁言 | 审批弹窗只在游戏期出现 |
| D4 | 游戏进行中房主不在时 | 按建议执行：**60 秒超时自动拒绝** | 需加超时定时器 |
| D5 | 旁观者能否加入语音 | **允许**（与管理员的隐身旁观相反：隐身旁观不进语音） | 语音成员表不再按角色过滤，仅按「是否在 voiceParticipants」 |
| D6 | 安全口令是否豁免本机回环 | **豁免**（防自锁） | 校验函数一行判断 |
| D7 | 房间列表是否展示「已结束」房间 | **不展示**，仅「等人中/进行中」 | `/api/rooms` 过滤条件 |
| D8 | 帮助页实现方式 | **Vue 内嵌**结构化内容 + `public/help/` 插图，不引入 markdown 依赖 | P0 实施 |

> 已生效的方案修订：§4.4 信息可见性（改为视角代入）、§4.5 UI 设计（取消灰度滤镜与手牌占位卡，改为水印+视角切换器）、§11 风险表对应行。

## 13. 下一步

§12 决策点已确认。**P1 已完成**（房间列表 + 隐身 + 分享），**P2 已完成**（旁观者模式：视角代入、房主审批/禁言/踢出、管理员隐身旁观），并已按实测反馈打完 P2 补丁：

- 未开局的房间，旁观者先落在**大厅等待界面**（只读、无房主操作），开局后自动切观战页；
- 首页「加入房间」右侧加小箭头，纵向展开「👁 旁观加入」，支持用房间号直接旁观；
- `LeaveRoom` 区分「主动退出 / 断线」：退出即时清占位，断线保留重连并在等人阶段 45 秒后回收；
- 修复房主解散只断连接不通知服务端导致的「房间残留在列表 / 管理后台」「同号重开继承上一局聊天」；
- 聊天卡片改为固定高度、消息在卡片内滚动（大厅与游戏页宽屏/窄屏三种布局都覆盖）。

下一批次为 **P3：管理员禁止指定房间聊天**（`chatDisabled` 字段已预留在 `/api/rooms` 与管理快照里）。

P0（帮助文档 + 帮助页）已暂缓、代码回退，需要时按 §3 重新实施；帮助页截图届时从运行实例采集（`spectate` 相关界面已可实拍）。
