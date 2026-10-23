from __future__ import annotations

import asyncio
import mimetypes
import os
import random
import time
import uuid
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.websockets import WebSocketState

try:  # 兼容 `python -m uvicorn backend.main:app` 与直接运行两种导入方式
    from . import admin as admin_module
    from . import config as app_config
    from . import registry as term_registry
except ImportError:  # pragma: no cover
    import admin as admin_module  # type: ignore
    import config as app_config  # type: ignore
    import registry as term_registry  # type: ignore


app = FastAPI(title="猜数字桌游", version="1.0.0")


class Color:
    RED = "红"
    BLUE = "蓝"
    GREEN = "绿"
    ORANGE = "橙"
    PINK = "粉"

    ALL = [RED, BLUE, GREEN, ORANGE, PINK]


class Card:
    def __init__(self, color: str, number: int):
        self.id = str(uuid.uuid4())[:8]
        self.color = color
        self.number = number
        self.isSelected = False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "color": self.color,
            "number": self.number,
            "isSelected": self.isSelected,
        }


class Clue:
    def __init__(
        self,
        clue_type: str,
        public_card_id: str,
        public_card_number: int,
        target_color: Optional[str] = None,
        result: Any = None,
    ):
        self.id = str(uuid.uuid4())[:8]
        self.type = clue_type
        self.publicCardId = public_card_id
        self.publicCardNumber = public_card_number
        self.targetColor = target_color
        self.result = result
        self.timestamp = int(random.random() * 1_000_000_000)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "publicCardId": self.publicCardId,
            "publicCardNumber": self.publicCardNumber,
            "targetColor": self.targetColor,
            "result": self.result,
            "timestamp": self.timestamp,
        }


class Player:
    def __init__(self, player_id: str, player_name: str, is_bot: bool = False):
        self.playerId = player_id
        self.playerName = player_name
        self.isAlive = True
        self.isOnline = True
        self.isBot = is_bot
        self.hand: List[Card] = []
        self.clues: List[Clue] = []
        self.accessToken = str(uuid.uuid4())

    def to_dict(self) -> dict:
        return {
            "playerId": self.playerId,
            "playerName": self.playerName,
            "isAlive": self.isAlive,
            "isOnline": self.isOnline,
            "isBot": self.isBot,
            "hand": [card.to_dict() for card in self.hand],
            "clues": [clue.to_dict() for clue in self.clues],
        }


class GameRoom:
    def __init__(self, room_id: str, host_id: str):
        self.roomId = room_id
        self.hostId = host_id
        self.gamePhase = "WAITING"
        self.subPhase: Optional[str] = None
        self.roundNumber = 0
        self.currentTurnPlayerId: Optional[str] = None
        self.turnOrder: List[str] = []
        self.players: Dict[str, Player] = {}
        self.color_decks: Dict[str, List[Card]] = {}
        self.publicCards: List[Card] = []
        self.removedPublicCardIds: set[str] = set()
        self.deckRemainingCount: Dict[str, int] = {color: 0 for color in Color.ALL}
        self.pendingJudgement: Optional[dict] = None
        self.gameOverInfo: Optional[dict] = None
        self.selectedPublicCardId: Optional[str] = None
        self.seed = str(uuid.uuid4())[:8]
        self.usedCardNumbers: List[dict] = []
        self.ws_connections: Dict[str, WebSocket] = {}
        # 房间生命周期时间点（管理后台用来算时长）
        self.createdAt = time.time()
        self.gameStartedAt: Optional[float] = None
        self.gameEndedAt: Optional[float] = None
        # 机器人：不持有 WebSocket，由一个常驻驱动任务轮询当前回合并代为行动
        self.botTask: Optional[asyncio.Task] = None
        self.botSeq = 0
        # 文字聊天：房间级、跨牌局保留；chatHistory 最多保留 100 条，快照只带 50 条
        self.chatHistory: List[dict] = []
        self.chatSeq = 0
        self.chatLastAt: Dict[str, float] = {}
        # 语音通话：WebRTC mesh。服务端只维护成员表与禁麦标记，媒体流点对点直连，
        # 信令（offer/answer/ICE）通过房间 WebSocket 转发
        self.voiceParticipants: List[str] = []
        self.voiceHostMuted: set[str] = set()
        # 房间列表可见性：房主可把房间设为隐身，隐身房间不出现在首页公开列表
        # （管理后台走 /ws/admin 快照，仍能看到全部房间）
        self.isPrivate = False
        # 管理员可单独关闭某个正在进行的房间的聊天（房内所有人，含旁观者），
        # 只影响发言，不影响系统消息与语音通话
        self.chatDisabled = False
        # ------------------------------------------------------------ 旁观者
        # 旁观者与参赛者分表存放：start_game / turnOrder / deal_initial_hands /
        # check_game_over 全都只看 players，旁观者天然不参与牌局计算。
        self.spectators: Dict[str, Player] = {}
        self.spectator_conns: Dict[str, WebSocket] = {}
        # 视角代入（D1）：旁观者 -> 代入的参赛者 id；None 表示尚未选择
        self.spectatorView: Dict[str, Optional[str]] = {}
        self.spectatorMuted: set[str] = set()        # 被房主禁言
        self.spectatorVoiceBanned: set[str] = set()  # 审批时未授予语音
        self.spectatorHidden: set[str] = set()       # 管理员隐身旁观（对其他端不可见）
        # 游戏中待审批：player_id -> {playerName, event, decision, allowChat, allowVoice}
        self.spectatorPending: Dict[str, dict] = {}

    def add_bot(self) -> Optional[Player]:
        """在等待阶段由房主添加一个机器人，房间人数上限仍为 4。"""
        if self.gamePhase != "WAITING" or len(self.players) >= 4:
            return None

        used_names = {p.playerName for p in self.players.values()}
        used_ids = set(self.players.keys())
        seq = self.botSeq
        while True:
            seq += 1
            name = f"机器人{seq}"
            bot_id = f"{self.roomId}__bot{seq}"
            if name not in used_names and bot_id not in used_ids:
                break

        self.botSeq = seq
        bot = Player(bot_id, name, is_bot=True)
        self.players[bot_id] = bot
        return bot

    def remove_bot(self, player_id: str) -> bool:
        player = self.players.get(player_id)
        if not player or not player.isBot:
            return False
        self.players.pop(player_id, None)
        self.ws_connections.pop(player_id, None)
        self.turnOrder = [pid for pid in self.turnOrder if pid != player_id]
        return True

    def start_bot_driver(self):
        if not any(p.isBot for p in self.players.values()):
            return
        if self.botTask is not None and not self.botTask.done():
            return
        self.botTask = asyncio.create_task(self._bot_driver())

    def stop_bot_driver(self):
        task = self.botTask
        self.botTask = None
        if task is not None and not task.done():
            task.cancel()

    def _bot_can_act(self, player_id: str) -> bool:
        return (
            self.gamePhase == "PLAYING"
            and self.currentTurnPlayerId == player_id
            and not self.gameOverInfo
        )

    async def _bot_driver(self):
        """常驻轮询：轮到机器人时替它抽牌、选牌、判定；不提交猜测。"""
        try:
            while True:
                await asyncio.sleep(0.2)
                if self.gamePhase != "PLAYING":
                    return
                pid = self.currentTurnPlayerId
                player = self.players.get(pid) if pid else None
                if not player or not player.isBot or not player.isAlive:
                    continue
                try:
                    await self._bot_act(player)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    print(f"[机器人] {player.playerName} 行动异常：{exc}")
                    await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            return

    async def _bot_act(self, player: Player):
        pid = player.playerId

        if self.subPhase == "DRAW_PHASE":
            # 思考停顿，避免瞬间连动
            await asyncio.sleep(random.uniform(0.9, 1.8))
            if not self._bot_can_act(pid):
                return
            available = [c for c in Color.ALL if self.color_decks.get(c)]
            if not available:
                await next_turn(self)
                return
            await cmd_select_color_to_draw(self, pid, random.choice(available))
            return

        if self.subPhase == "ACTION_PHASE":
            visible = [c for c in self.publicCards if c.id not in self.removedPublicCardIds]
            if not visible:
                await next_turn(self)
                return
            target = random.choice(visible)

            await asyncio.sleep(random.uniform(0.6, 1.3))
            if not self._bot_can_act(pid):
                return
            if self.selectedPublicCardId != target.id:
                await cmd_select_public_card(self, pid, target.id)

            await asyncio.sleep(random.uniform(0.7, 1.4))
            if not self._bot_can_act(pid):
                return
            if self.selectedPublicCardId != target.id:
                # 选牌未生效（牌已不可用等），交给下一轮循环重试
                return

            hand_colors = [c.color for c in player.hand]
            if hand_colors and random.random() < 0.5:
                await cmd_judge_by_point(self, pid, target.id, random.choice(hand_colors))
            else:
                await cmd_judge_by_position(self, pid, target.id)
            return

    def add_player(self, player: Player, ws: WebSocket):
        self.players[player.playerId] = player
        self.ws_connections[player.playerId] = ws

    def remove_player(self, player_id: str):
        self.players.pop(player_id, None)
        self.ws_connections.pop(player_id, None)

    # ---------------------------------------------------------- 旁观者

    def member_of(self, member_id: str) -> Optional[Player]:
        """参赛者与旁观者统一取 Player（聊天 / 语音需要昵称）。"""
        return self.players.get(member_id) or self.spectators.get(member_id)

    def conn_of(self, member_id: str) -> Optional[WebSocket]:
        """参赛者与旁观者的连接统一取出（状态推送 / 信令转发共用）。"""
        return self.ws_connections.get(member_id) or self.spectator_conns.get(member_id)

    def add_spectator(self, player: Player, ws: WebSocket, hidden: bool = False):
        self.spectators[player.playerId] = player
        self.spectator_conns[player.playerId] = ws
        if hidden:
            self.spectatorHidden.add(player.playerId)

    def remove_spectator(self, spectator_id: str) -> Optional[Player]:
        """移出旁观者并清掉所有附带标记（视角 / 禁言 / 隐身 / 语音限制）。"""
        self.spectator_conns.pop(spectator_id, None)
        self.spectatorView.pop(spectator_id, None)
        self.spectatorMuted.discard(spectator_id)
        self.spectatorVoiceBanned.discard(spectator_id)
        self.spectatorHidden.discard(spectator_id)
        return self.spectators.pop(spectator_id, None)

    def visible_spectators(self) -> List[dict]:
        """下发给普通端的旁观者列表；管理员隐身旁观不在其中。"""
        return [
            {
                "playerId": pid,
                "playerName": player.playerName,
                "muted": pid in self.spectatorMuted,
                "voiceBanned": pid in self.spectatorVoiceBanned,
                "viewId": self.spectatorView.get(pid),
            }
            for pid, player in self.spectators.items()
            if pid not in self.spectatorHidden
        ]

    def default_spectate_view(self) -> Optional[str]:
        """默认视角：回合顺序里的第一位参赛者（回合未开始时取第一个玩家）。"""
        for pid in self.turnOrder:
            if pid in self.players:
                return pid
        return next(iter(self.players), None)

    def resolve_spectate_view(self, spectator_id: str) -> Optional[str]:
        """取旁观者当前代入的玩家；目标中途退出则回退到默认视角。"""
        target = self.spectatorView.get(spectator_id)
        if target in self.players:
            return target
        target = self.default_spectate_view()
        self.spectatorView[spectator_id] = target
        return target

    def get_state(self) -> dict:
        return {
            "roomId": self.roomId,
            "hostId": self.hostId,
            "gamePhase": self.gamePhase,
            "subPhase": self.subPhase,
            "roundNumber": self.roundNumber,
            "currentTurnPlayerId": self.currentTurnPlayerId,
            "turnOrder": self.turnOrder,
            "deckRemainingCount": self.deckRemainingCount,
            "publicCards": [c.to_dict() for c in self.publicCards if c.id not in self.removedPublicCardIds],
            "players": {pid: player.to_dict() for pid, player in self.players.items()},
            "pendingJudgement": self.pendingJudgement,
            "gameOverInfo": self.gameOverInfo,
            "seed": self.seed,
            "usedCardNumbers": self.usedCardNumbers,
            # 聊天室：最近 50 条历史（含系统消息），供晚加入者补上下文
            "chat": list(self.chatHistory[-CHAT_SNAPSHOT:]),
            # 语音通话成员表（机器人不参与）
            "voice": {
                "participants": list(self.voiceParticipants),
                "hostMuted": list(self.voiceHostMuted),
            },
            # 房主可把房间设为隐身（不影响房内玩法，只影响首页公开列表）
            "isPrivate": self.isPrivate,
            # 旁观者列表（含各自代入的视角；管理员隐身旁观不在此列）
            "spectators": self.visible_spectators(),
            # 管理员是否关闭了本房聊天（前端据此置灰输入框）
            "chatDisabled": self.chatDisabled,
        }

    async def broadcast_state(self):
        """状态双通道：参赛者与旁观者各推一份。

        内容完全一致——手牌裁剪发生在前端 store（`myHand` 把「自己」的手牌
        显示为 ?），因此旁观者只要把 myPlayerId 设成代入的玩家即可获得与
        真身一模一样的视角，服务端不必维护第二套裁剪逻辑。
        """
        state = self.get_state()
        for player_id, ws in list(self.ws_connections.items()):
            try:
                await ws.send_json({"event": "Event_StateUpdate", "payload": state})
            except Exception as exc:
                print(f"发送状态给 {player_id} 失败：{exc}")
        for spectator_id, ws in list(self.spectator_conns.items()):
            try:
                await ws.send_json({"event": "Event_StateUpdate", "payload": state})
            except Exception as exc:
                print(f"发送状态给旁观者 {spectator_id} 失败：{exc}")

    async def send_to_player(self, player_id: str, event: str, payload: Any):
        """按 id 投递事件：参赛者与旁观者共用一张连接查找表。"""
        ws = self.conn_of(player_id)
        if not ws:
            return
        try:
            await ws.send_json({"event": event, "payload": payload})
        except Exception as exc:
            print(f"发送 {event} 给 {player_id} 失败：{exc}")

    # ------------------------------------------------------------ 文字聊天

    def push_chat(self, message: dict):
        """写入聊天历史（环形保留，防止长时间挂机后无限增长）。"""
        self.chatHistory.append(message)
        if len(self.chatHistory) > CHAT_HISTORY_KEEP:
            del self.chatHistory[: len(self.chatHistory) - CHAT_HISTORY_KEEP]

    async def broadcast_chat(self, message: dict):
        """房间内广播一条聊天消息（含发送者本人，前端不做本地回显）。

        旁观者同样收得到（否则聊天室只剩一半上下文）；被禁言只是不能发。
        """
        self.push_chat(message)
        for pid in list(self.ws_connections.keys()):
            await self.send_to_player(pid, "Event_Chat", message)
        for sid in list(self.spectator_conns.keys()):
            await self.send_to_player(sid, "Event_Chat", message)

    def next_chat_id(self) -> str:
        self.chatSeq += 1
        return f"{self.roomId}-c{self.chatSeq}"


rooms: Dict[str, GameRoom] = {}


def get_point(number: int) -> int:
    """根据数字计算点数 (1-3)"""
    return ((number - 1) // 5) % 3 + 1


def create_color_decks() -> Dict[str, List[Card]]:
    """为每种颜色创建独立打乱的12张牌队列
    每种颜色的固定数字序列:
      红: 1,6,11,16,21,26,31,36,41,46,51,56
      蓝: 2,7,12,17,22,27,32,37,42,47,52,57
      绿: 3,8,13,18,23,28,33,38,43,48,53,58
      橙: 4,9,14,19,24,29,34,39,44,49,54,59
      粉: 5,10,15,20,25,30,35,40,45,50,55,60
    """
    decks = {}
    for idx, color in enumerate(Color.ALL):
        cards = [Card(color, (idx + 1) + i * 5) for i in range(12)]
        random.shuffle(cards)
        decks[color] = cards
    return decks


def update_deck_remaining(room: GameRoom):
    counts = {color: 0 for color in Color.ALL}
    for color in Color.ALL:
        counts[color] = len(room.color_decks.get(color, []))
    room.deckRemainingCount = counts


def draw_specific_color(room: GameRoom, color: str) -> Optional[Card]:
    color_deck = room.color_decks.get(color, [])
    if not color_deck:
        return None
    return color_deck.pop()


def draw_any_card(room: GameRoom) -> Optional[Card]:
    for color in Color.ALL:
        color_deck = room.color_decks.get(color, [])
        if color_deck:
            return color_deck.pop()
    return None


def find_card(cards: List[Card], card_id: str) -> Optional[Card]:
    for card in cards:
        if card.id == card_id:
            return card
    return None


def find_player_card(player: Player, color: str) -> Optional[Card]:
    for card in player.hand:
        if card.color == color:
            return card
    return None


def deal_initial_hands(room: GameRoom):
    for player in room.players.values():
        player.hand = []
        for color in Color.ALL:
            card = draw_specific_color(room, color)
            if card is None:
                card = draw_any_card(room)
            if card is not None:
                player.hand.append(card)
        player.hand.sort(key=lambda card: card.number)


def build_public_cards(room: GameRoom, count: int = 6):
    room.publicCards = []
    for _ in range(count):
        card = draw_any_card(room)
        if card is None:
            break
        room.publicCards.append(card)


def check_game_over(room: GameRoom) -> bool:
    if room.gamePhase == "GAME_OVER":
        return True

    all_empty = all(len(room.color_decks.get(c, [])) == 0 for c in Color.ALL)
    if all_empty:
        room.gamePhase = "GAME_OVER"
        room.gameEndedAt = time.time()
        room.gameOverInfo = {
            "winnerId": None,
            "winnerName": None,
            "correctGuess": None,
            "reason": "deck_exhausted",
        }
        return True

    alive_players = [player for player in room.players.values() if player.isAlive]
    if len(alive_players) <= 1 and room.gamePhase == "PLAYING":
        room.gamePhase = "GAME_OVER"
        room.gameEndedAt = time.time()
        winner = alive_players[0] if alive_players else None
        room.gameOverInfo = {
            "winnerId": winner.playerId if winner else None,
            "winnerName": winner.playerName if winner else None,
            "correctGuess": None,
            "reason": "correct_guess" if winner else "deck_exhausted",
        }
        return True

    return False


async def next_turn(room: GameRoom):
    if check_game_over(room):
        await room.broadcast_state()
        return

    alive_ids = [pid for pid, player in room.players.items() if player.isAlive]
    if not alive_ids:
        room.gamePhase = "GAME_OVER"
        room.gameEndedAt = time.time()
        room.gameOverInfo = {
            "winnerId": None,
            "winnerName": None,
            "correctGuess": None,
            "reason": "deck_exhausted",
        }
        await room.broadcast_state()
        return

    # 使用 turnOrder 顺序推进（跳过已出局玩家）
    if not room.turnOrder:
        room.turnOrder = [pid for pid in room.players.keys()]

    if room.currentTurnPlayerId not in room.turnOrder:
        # 取第一个仍然存活的玩家
        for pid in room.turnOrder:
            if pid in alive_ids:
                room.currentTurnPlayerId = pid
                break
    else:
        idx = room.turnOrder.index(room.currentTurnPlayerId)
        found = False
        for i in range(1, len(room.turnOrder) + 1):
            candidate = room.turnOrder[(idx + i) % len(room.turnOrder)]
            if candidate in alive_ids:
                room.currentTurnPlayerId = candidate
                found = True
                break
        if not found and alive_ids:
            room.currentTurnPlayerId = alive_ids[0]

    # 清除已被判定弃置的公共牌
    room.publicCards = [c for c in room.publicCards if c.id not in room.removedPublicCardIds]
    room.removedPublicCardIds.clear()

    room.roundNumber += 1
    room.subPhase = "DRAW_PHASE"
    room.pendingJudgement = None
    room.selectedPublicCardId = None
    update_deck_remaining(room)
    await room.broadcast_state()
    room.start_bot_driver()


def start_game(room: GameRoom) -> bool:
    if len(room.players) != 4:
        return False

    room.color_decks = create_color_decks()
    room.publicCards = []
    room.usedCardNumbers = []
    room.roundNumber = 1
    room.gamePhase = "PLAYING"
    room.subPhase = "DRAW_PHASE"
    room.gameStartedAt = time.time()
    room.gameEndedAt = None
    room.pendingJudgement = None
    room.gameOverInfo = None
    room.selectedPublicCardId = None
    room.removedPublicCardIds = set()
    # 抽取 5 张公共牌（每种颜色各一张）
    room.publicCards = []
    for c in Color.ALL:
        card = draw_specific_color(room, c)
        if card:
            room.publicCards.append(card)
    deal_initial_hands(room)
    update_deck_remaining(room)
    # 随机决定玩家出牌顺序，并指定第一位为当前回合玩家
    room.turnOrder = random.sample(list(room.players.keys()), k=len(room.players))
    room.currentTurnPlayerId = room.turnOrder[0]
    return True


async def cmd_start_game(room: GameRoom, player_id: str):
    if player_id != room.hostId or room.gamePhase != "WAITING":
        return
    if start_game(room):
        await room.broadcast_state()
        room.start_bot_driver()


async def cmd_select_color_to_draw(room: GameRoom, player_id: str, color: Optional[str]):
    if room.gamePhase != "PLAYING" or room.subPhase != "DRAW_PHASE":
        return
    if room.currentTurnPlayerId != player_id or color not in Color.ALL:
        return

    player = room.players.get(player_id)
    if not player:
        return

    new_card = draw_specific_color(room, color)
    if not new_card:
        return

    # 抽出的牌添加到公共牌区
    room.publicCards.append(new_card)

    room.subPhase = "ACTION_PHASE"
    update_deck_remaining(room)
    await room.broadcast_state()


async def cmd_select_public_card(room: GameRoom, player_id: str, public_card_id: Optional[str]):
    if room.gamePhase != "PLAYING" or room.subPhase != "ACTION_PHASE":
        return
    if room.currentTurnPlayerId != player_id or not public_card_id:
        return

    public_card = find_card(room.publicCards, public_card_id)
    if not public_card:
        return

    # 每回合只能选定一张公共牌：重复选择同一张直接忽略；切换时回滚上一张牌的弃置与使用记录
    if room.selectedPublicCardId == public_card.id:
        return
    if room.selectedPublicCardId:
        prev_card = find_card(room.publicCards, room.selectedPublicCardId)
        room.removedPublicCardIds.discard(room.selectedPublicCardId)
        if prev_card:
            for i in range(len(room.usedCardNumbers) - 1, -1, -1):
                used = room.usedCardNumbers[i]
                if used.get("color") == prev_card.color and used.get("number") == prev_card.number:
                    room.usedCardNumbers.pop(i)
                    break

    room.selectedPublicCardId = public_card.id
    room.removedPublicCardIds.add(public_card.id)
    room.usedCardNumbers.append({"color": public_card.color, "number": public_card.number})
    await room.broadcast_state()


async def cmd_deselect_public_card(room: GameRoom, player_id: str):
    # 取消当前回合已选定的公共牌，并回滚该牌本回合留下的弃置与使用记录
    if room.gamePhase != "PLAYING" or room.subPhase != "ACTION_PHASE":
        return
    if room.currentTurnPlayerId != player_id or not room.selectedPublicCardId:
        return

    card = find_card(room.publicCards, room.selectedPublicCardId)
    room.removedPublicCardIds.discard(room.selectedPublicCardId)
    if card:
        for i in range(len(room.usedCardNumbers) - 1, -1, -1):
            used = room.usedCardNumbers[i]
            if used.get("color") == card.color and used.get("number") == card.number:
                room.usedCardNumbers.pop(i)
                break
    room.selectedPublicCardId = None
    await room.broadcast_state()


async def cmd_judge_by_position(room: GameRoom, player_id: str, public_card_id: Optional[str]):
    if room.gamePhase != "PLAYING" or room.subPhase != "ACTION_PHASE":
        return
    if room.currentTurnPlayerId != player_id or not public_card_id:
        return

    # 必须先选定公共牌，且只能对选定的那一张做判定
    if not room.selectedPublicCardId or public_card_id != room.selectedPublicCardId:
        return

    public_card = find_card(room.publicCards, room.selectedPublicCardId)
    if not public_card:
        return

    player = room.players.get(player_id)
    if not player:
        return

    # 位置判定：按数字排序手牌，找出公牌数字落在哪个区间
    sorted_hand = sorted(player.hand, key=lambda c: c.number)
    position = 0
    left_color = None
    right_color = sorted_hand[0].color if sorted_hand else None
    for i, card in enumerate(sorted_hand):
        if public_card.number < card.number:
            position = i
            left_color = sorted_hand[i - 1].color if i > 0 else None
            right_color = card.color
            break
    else:
        # 大于所有
        position = len(sorted_hand)
        left_color = sorted_hand[-1].color if sorted_hand else None
        right_color = None

    result = {"position": position, "leftColor": left_color, "rightColor": right_color}
    player.clues.append(Clue("position", public_card.id, public_card.number, result=result))
    room.pendingJudgement = {
        "selectedPublicCardId": public_card.id,
        "judgeType": "position",
        "result": result,
    }
    room.subPhase = "JUDGE_RESULT"
    await room.broadcast_state()
    await asyncio.sleep(1.2)
    room.pendingJudgement = None
    await next_turn(room)


async def cmd_judge_by_point(room: GameRoom, player_id: str, public_card_id: Optional[str], target_color: Optional[str]):
    if room.gamePhase != "PLAYING" or room.subPhase != "ACTION_PHASE":
        return
    if room.currentTurnPlayerId != player_id or not public_card_id or target_color not in Color.ALL:
        return

    # 必须先选定公共牌，且只能对选定的那一张做判定
    if not room.selectedPublicCardId or public_card_id != room.selectedPublicCardId:
        return

    public_card = find_card(room.publicCards, room.selectedPublicCardId)
    if not public_card:
        return

    player = room.players.get(player_id)
    if not player:
        return

    target_card = find_player_card(player, target_color)
    if not target_card:
        return

    same_point = get_point(public_card.number) == get_point(target_card.number)
    player.clues.append(
        Clue(
            "point",
            public_card.id,
            public_card.number,
            target_color=target_color,
            result=same_point,
        )
    )
    room.pendingJudgement = {
        "selectedPublicCardId": public_card.id,
        "judgeType": "point",
        "targetColor": target_color,
        "result": same_point,
    }
    room.subPhase = "JUDGE_RESULT"
    await room.broadcast_state()
    await asyncio.sleep(1.2)
    room.pendingJudgement = None
    await next_turn(room)


async def cmd_skip_turn(room: GameRoom, player_id: str):
    if player_id != room.hostId or room.gamePhase != "PLAYING" or room.subPhase != "ACTION_PHASE":
        return
    await next_turn(room)


async def cmd_submit_guess(room: GameRoom, player_id: str, guesses: Optional[List[int]]):
    if room.gamePhase != "PLAYING" or not guesses:
        return

    player = room.players.get(player_id)
    if not player:
        return

    actual_numbers: List[int] = []
    for color in Color.ALL:
        card = find_player_card(player, color)
        if card:
            actual_numbers.append(card.number)

    correct = guesses == actual_numbers
    result_payload = {
        "correct": correct,
        "guesses": guesses,
        "playerId": player_id,
        "playerName": player.playerName,
        "isHost": player_id == room.hostId,
    }
    if correct:
        room.gamePhase = "GAME_OVER"
        room.gameEndedAt = time.time()
        room.gameOverInfo = {
            "winnerId": player.playerId,
            "winnerName": player.playerName,
            "correctGuess": guesses,
            "reason": "correct_guess",
        }
        result_payload["gameOverInfo"] = room.gameOverInfo
        await room.broadcast_state()
    else:
        result_payload["correctNumbers"] = actual_numbers

    # 向所有玩家广播猜测结果
    for pid, ws in list(room.ws_connections.items()):
        try:
            await ws.send_json({"event": "Event_GuessResult", "payload": result_payload})
        except Exception:
            pass


async def cmd_kick_player(room: GameRoom, kicker_id: str, kicked_id: Optional[str]):
    if kicker_id != room.hostId or not kicked_id or kicked_id == room.hostId:
        return
    if kicked_id in room.players:
        kicked = room.players[kicked_id]
        was_current = room.currentTurnPlayerId == kicked_id
        if kicked.isBot:
            room.stop_bot_driver()
        if kicked_id in room.voiceParticipants:
            # 先退出语音（此时玩家还在房间里，系统消息能显示昵称）
            await cmd_voice_leave(room, kicked_id)
        # 先取出连接再移除玩家：remove_player 会清掉 ws_connections，
        # 之后再取就取不到，被踢者的 socket 将永远关不掉
        kicked_ws = room.ws_connections.pop(kicked_id, None)
        room.remove_player(kicked_id)
        room.turnOrder = [pid for pid in room.turnOrder if pid != kicked_id]
        if kicked_ws is not None:
            try:
                await kicked_ws.close(code=4001, reason="kicked")
            except Exception:
                pass
        if was_current and room.gamePhase == "PLAYING":
            room.currentTurnPlayerId = None
            await next_turn(room)
            return
        await room.broadcast_state()
        room.start_bot_driver()


async def cmd_leave_room(room: GameRoom, player_id: str):
    """玩家主动退出房间。

    与「断线」严格区分：断线只把 isOnline 置 False 并保留占位等对方重连；
    主动退出立刻从名单里移除，其他人不会再看到一个永远不在的占位。
    房主退出时把房主交给下一位真人；房里没有真人了就直接关掉房间。
    """
    player = room.players.get(player_id)
    if player is None:
        return
    name = player.playerName

    if player_id == room.hostId:
        successor = next(
            (pid for pid, p in room.players.items() if pid != player_id and not p.isBot),
            None,
        )
        if successor is None:
            # 没有别的真人接任，房间留着也没人能开局
            await admin_close_room(room, by="房主离开")
            return
        room.hostId = successor
        new_host = room.players[successor].playerName
        term_registry.log_event(f"房主退出房间 {room.roomId}，{new_host} 接任房主", "info")
        await room.broadcast_chat(
            system_chat(room, f"{name} 离开了房间，{new_host} 成为新房主")
        )

    was_current = room.currentTurnPlayerId == player_id
    if player_id in room.voiceParticipants:
        # 先退出语音（此时玩家还在 players 里，系统消息能带上昵称）
        await cmd_voice_leave(room, player_id, notify_chat=False)
    room.ws_connections.pop(player_id, None)
    room.remove_player(player_id)
    room.turnOrder = [pid for pid in room.turnOrder if pid != player_id]
    # 旁观者正代入此人时回退到仍在座的第一位
    for sid, view in list(room.spectatorView.items()):
        if view == player_id:
            room.spectatorView[sid] = room.default_spectate_view()

    await room.broadcast_chat(system_chat(room, f"{name} 离开了房间"))
    if was_current and room.gamePhase == "PLAYING":
        room.currentTurnPlayerId = None
        await next_turn(room)
        return
    await room.broadcast_state()


# 等人阶段断线多久后彻底移出房间（玩家在宽限期内用同一昵称重连不会被误删）
DISCONNECT_GRACE_SECONDS = 45.0


async def remove_offline_after_grace(room: GameRoom, player_id: str):
    """等人阶段长时间离线（直接关标签页而不是点退出）的玩家，宽限期后移出名单。"""
    await asyncio.sleep(DISCONNECT_GRACE_SECONDS)
    player = room.players.get(player_id)
    if player is None or player.isOnline or player_id in room.ws_connections:
        return
    if room.gamePhase != "WAITING":
        return
    term_registry.log_event(
        f"{player.playerName} 长时间离线，已从房间 {room.roomId} 移除", "info"
    )
    await cmd_leave_room(room, player_id)


async def cmd_add_bot(room: GameRoom, player_id: str):
    if player_id != room.hostId or room.gamePhase != "WAITING":
        return
    bot = room.add_bot()
    if bot:
        await room.broadcast_chat(system_chat(room, f"{bot.playerName} 加入了房间"))
        await room.broadcast_state()


async def cmd_remove_bot(room: GameRoom, player_id: str, bot_id: Optional[str]):
    if player_id != room.hostId or room.gamePhase != "WAITING" or not bot_id:
        return
    bot = room.players.get(bot_id)
    if room.remove_bot(bot_id):
        if bot is not None:
            await room.broadcast_chat(system_chat(room, f"{bot.playerName} 离开了房间"))
        await room.broadcast_state()


async def cmd_reconnect(room: GameRoom, player_id: str, access_token: Optional[str]):
    player = room.players.get(player_id)
    if not player:
        return
    if not access_token or player.accessToken == access_token:
        player.isOnline = True
        await room.broadcast_state()


# ---------------------------------------------------------------- 文字聊天

CHAT_MAX_LEN = 300          # 单条消息最大字符数
CHAT_MIN_INTERVAL = 1.0     # 同一玩家两条消息的最小间隔（秒）
CHAT_HISTORY_KEEP = 100     # 房间内保留的聊天历史上限
CHAT_SNAPSHOT = 50          # 状态快照里携带的聊天条数


def system_chat(room: GameRoom, text: str) -> dict:
    """构造一条系统消息（加入/离开/语音动态等）。"""
    return {
        "id": room.next_chat_id(),
        "from": "system",
        "fromName": "系统",
        "text": text,
        "ts": time.time(),
        "system": True,
    }


async def cmd_send_chat(room: GameRoom, player_id: str, text: Any):
    player = room.member_of(player_id)
    if player is None or player.isBot:
        return
    # 旁观者发言：受房主禁言约束（管理员隐身旁观一律禁言）
    is_spectator = player_id not in room.players
    if is_spectator and player_id in room.spectatorMuted:
        await room.send_to_player(
            player_id, "Event_ChatRejected", {"reason": "你已被房主禁言，暂时不能发言"}
        )
        return
    raw = str(text or "").strip()
    if not raw:
        return
    # 管理员对单个房间的禁聊：优先级低于房主对旁观者的禁言（提示语区分开，
    # 让被禁言者先看到「被房主禁言」，而不是笼统的「聊天已关闭」）
    if room.chatDisabled:
        await room.send_to_player(
            player_id, "Event_ChatRejected", {"reason": "聊天功能已被管理员关闭"}
        )
        return
    if len(raw) > CHAT_MAX_LEN:
        raw = raw[:CHAT_MAX_LEN]

    now = time.time()

    # 违禁词：与昵称校验共用同一套词库（归一化匹配，防拆字绕过）。
    # 先判违禁再判限速：命中词库时给出明确原因，避免被「发送太频繁」掩盖。
    hit_word = app_config.check_banned_text(raw)
    if hit_word:
        app_config.record_word_hit(hit_word)
        term_registry.log_event(
            f"拦截聊天违禁词（{player.playerName}，房间 {room.roomId}，命中「{hit_word}」）", "warn"
        )
        await room.send_to_player(
            player_id,
            "Event_ChatRejected",
            {"reason": f"内容包含违禁词：{hit_word}", "word": hit_word},
        )
        return

    if now - room.chatLastAt.get(player_id, 0.0) < CHAT_MIN_INTERVAL:
        await room.send_to_player(
            player_id, "Event_ChatRejected", {"reason": "发送太频繁，请稍后再试"}
        )
        return
    room.chatLastAt[player_id] = now

    await room.broadcast_chat(
        {
            "id": room.next_chat_id(),
            "from": player_id,
            "fromName": player.playerName,
            "text": raw,
            "ts": now,
            "system": False,
            # 旁观者发言带「旁观」徽标，与参赛者区分
            "spectator": is_spectator,
        }
    )


# ---------------------------------------------------------------- 旁观者

SPECTATE_APPROVAL_TIMEOUT = 60.0  # 游戏中申请旁观：房主 60 秒未响应自动拒绝（D4）

# 管理员签发的一次性隐身旁观凭证：token -> {roomId, expiresAt}
ADMIN_SPECTATE_TOKENS: Dict[str, dict] = {}

# 旁观者允许发送的指令（其余写操作用 Event_ActionRejected 统一拒绝）
SPECTATOR_ALLOWED_CMDS = {
    "SendChat",
    "SpectateSetView",
    "SpectatorLeave",
    "Reconnect",
    "VoiceJoin",
    "VoiceLeave",
    "VoiceSignal",
    "VoiceSetMute",
}


def issue_admin_spectate_token(room_id: str) -> str:
    """签发一次性隐身旁观凭证（仅存内存、120 秒内有效）。"""
    token = uuid.uuid4().hex
    now = time.time()
    for key in [k for k, v in ADMIN_SPECTATE_TOKENS.items() if v["expiresAt"] < now]:
        ADMIN_SPECTATE_TOKENS.pop(key, None)
    ADMIN_SPECTATE_TOKENS[token] = {"roomId": room_id, "expiresAt": now + 120}
    return token


def consume_admin_spectate_token(token: str, room_id: str) -> bool:
    """核销凭证：一次性使用，用后立即失效。"""
    info = ADMIN_SPECTATE_TOKENS.pop((token or "").strip(), None)
    if not info:
        return False
    return info["roomId"] == room_id and info["expiresAt"] >= time.time()


def unique_spectator_id(room: GameRoom, player_name: str) -> str:
    """旁观者 id：与参赛者/已有旁观者重名时加后缀，绝不复用参赛者 id。"""
    base = f"{room.roomId}_{player_name}"
    spectator_id = base
    seq = 1
    while spectator_id in room.players or spectator_id in room.spectators:
        seq += 1
        spectator_id = f"{base}_s{seq}"
    return spectator_id


async def register_spectator(
    websocket: WebSocket,
    room: GameRoom,
    player_name: str,
    ip: str,
    client_id: str,
    admin_token: str,
) -> Optional[str]:
    """旁观者接入全流程；成功返回 spectator_id，被拒/超时返回 None（连接已关闭）。"""
    hidden = bool(admin_token) and consume_admin_spectate_token(admin_token, room.roomId)
    display_name = f"{player_name}（管理员）" if hidden else player_name

    if not hidden:
        hit_word = app_config.check_banned_text(player_name)
        if hit_word:
            app_config.record_word_hit(hit_word)
            term_registry.log_event(
                f"拒绝含违禁词的旁观昵称（{ip}，命中「{hit_word}」）", "warn"
            )
            await websocket.send_json({"error": f"昵称包含违禁内容：{hit_word}"})
            await websocket.close(code=1008, reason="banned_nickname")
            return None

    spectator_id = unique_spectator_id(room, display_name)
    allow_chat = True
    allow_voice = True

    # 组队期（WAITING）与已结束（GAME_OVER）直接进；只有牌局进行中需要房主批准（D3）
    if room.gamePhase == "PLAYING" and not hidden:
        pending = {
            "playerName": display_name,
            "event": asyncio.Event(),
            "decision": None,
            "allowChat": True,
            "allowVoice": True,
        }
        room.spectatorPending[spectator_id] = pending
        await websocket.send_json(
            {
                "event": "Event_SpectatorWaiting",
                "payload": {"text": "正在等待房主批准旁观…"},
            }
        )
        await room.send_to_player(
            room.hostId,
            "Event_SpectatorAsk",
            {"playerId": spectator_id, "playerName": display_name},
        )
        term_registry.log_event(
            f"旁观申请待批准（{display_name}，房间 {room.roomId}）", "info"
        )
        approved = False
        client_gone = False
        deadline = time.time() + SPECTATE_APPROVAL_TIMEOUT
        try:
            while True:
                remaining = deadline - time.time()
                if remaining <= 0:
                    break
                try:
                    await asyncio.wait_for(
                        pending["event"].wait(), timeout=min(0.5, remaining)
                    )
                except asyncio.TimeoutError:
                    # 轮询式等待：客户端中途关掉页面时立刻撤销申请，
                    # 避免房主看到一个永远点不掉的幽灵弹窗
                    if websocket.client_state != WebSocketState.CONNECTED:
                        client_gone = True
                        break
                    continue
                approved = bool(pending["decision"])
                allow_chat = bool(pending["allowChat"])
                allow_voice = bool(pending["allowVoice"])
                break
        finally:
            room.spectatorPending.pop(spectator_id, None)

        if client_gone:
            return None

        if not approved:
            reason = (
                "房主未响应，旁观请求已超时"
                if pending["decision"] is None
                else "房主拒绝了你的旁观申请"
            )
            term_registry.log_event(
                f"旁观被拒绝（{display_name}，房间 {room.roomId}，{reason}）", "warn"
            )
            try:
                await websocket.send_json(
                    {
                        "event": "Event_SpectatorRejected",
                        "payload": {"reason": reason, "text": reason},
                    }
                )
                await websocket.close(code=1008, reason="spectate_rejected")
            except Exception:
                pass
            return None

    spectator = Player(spectator_id, display_name)
    room.add_spectator(spectator, websocket, hidden=hidden)
    room.spectatorView[spectator_id] = room.default_spectate_view()
    if hidden:
        # 管理员隐身旁观：不发言、不语音，避免暴露
        room.spectatorMuted.add(spectator_id)
        room.spectatorVoiceBanned.add(spectator_id)
    else:
        if not allow_chat:
            room.spectatorMuted.add(spectator_id)
        if not allow_voice:
            room.spectatorVoiceBanned.add(spectator_id)

    if client_id:
        term_registry.get_or_create(client_id, ip, websocket.headers.get("user-agent", ""), "spectator")
        term_registry.attach_socket(client_id, websocket, "room")
        term_registry.bind_player(client_id, display_name, room.roomId)

    term_registry.log_event(
        f"管理员隐身旁观房间 {room.roomId}（{ip}）" if hidden else f"{display_name} 进入旁观（房间 {room.roomId}）",
        "warn" if hidden else "info",
    )

    await websocket.send_json(
        {
            "event": "Event_SpectateReady",
            "payload": {
                "playerId": spectator_id,
                "playerName": display_name,
                "viewId": room.spectatorView.get(spectator_id),
                "hidden": hidden,
                "muted": spectator_id in room.spectatorMuted,
                "voiceBanned": spectator_id in room.spectatorVoiceBanned,
            },
        }
    )
    await websocket.send_json({"event": "Event_SyncFullState", "payload": room.get_state()})
    await room.broadcast_state()
    if not hidden:
        await room.broadcast_chat(system_chat(room, f"{display_name} 进入旁观"))
    return spectator_id


async def unregister_spectator(room: GameRoom, spectator_id: str, websocket: WebSocket):
    """旁观者断线清理；连接已被新连接接管（刷新重连）时不误删。"""
    if room.spectator_conns.get(spectator_id) is not websocket:
        return
    was_hidden = spectator_id in room.spectatorHidden
    player = room.remove_spectator(spectator_id)
    if spectator_id in room.voiceParticipants:
        await cmd_voice_leave(room, spectator_id, notify_chat=not was_hidden)
    await room.broadcast_state()
    if player and not was_hidden:
        await room.broadcast_chat(system_chat(room, f"旁观者 {player.playerName} 离开了房间"))


async def cmd_spectate_set_view(room: GameRoom, player_id: str, target: Any):
    """旁观者切换代入视角（D1）：目标必须是本房参赛者。"""
    if player_id not in room.spectators:
        return
    target_id = str(target or "")
    if target_id not in room.players:
        target_id = room.default_spectate_view() or ""
    room.spectatorView[player_id] = target_id
    target = room.players.get(target_id)
    await room.send_to_player(
        player_id,
        "Event_SpectateView",
        {"targetPlayerId": target_id, "targetName": target.playerName if target else ""},
    )
    await room.broadcast_state()


async def cmd_spectator_respond(
    room: GameRoom,
    host_id: str,
    target_id: Any,
    allow: Any,
    allow_chat: Any,
    allow_voice: Any,
):
    """房主审批游戏中旁观申请。"""
    if host_id != room.hostId:
        return
    pending = room.spectatorPending.get(str(target_id or ""))
    if pending is None:
        return
    pending["decision"] = bool(allow)
    pending["allowChat"] = bool(allow_chat)
    pending["allowVoice"] = bool(allow_voice)
    pending["event"].set()
    term_registry.log_event(
        f"房主{'批准' if pending['decision'] else '拒绝'}旁观申请"
        f"（{pending['playerName']}，房间 {room.roomId}）",
        "info",
    )


async def cmd_kick_spectator(room: GameRoom, host_id: str, target_id: Any):
    """房主踢出旁观者：先摘连接再 close，避免断线分支拿不到条目。"""
    if host_id != room.hostId:
        return
    spectator_id = str(target_id or "")
    player = room.spectators.get(spectator_id)
    if player is None:
        return
    ws = room.spectator_conns.pop(spectator_id, None)
    room.remove_spectator(spectator_id)
    if spectator_id in room.voiceParticipants:
        await cmd_voice_leave(room, spectator_id, notify_chat=False)
    if ws is not None:
        try:
            await ws.send_json(
                {
                    "event": "Event_SpectatorRejected",
                    "payload": {"reason": "kicked", "text": "你已被房主移出旁观"},
                }
            )
            await ws.close(code=4001, reason="spectator_kicked")
        except Exception:
            pass
    term_registry.log_event(
        f"房主移出旁观者 {player.playerName}（房间 {room.roomId}）", "warn"
    )
    await room.broadcast_state()
    await room.broadcast_chat(system_chat(room, f"房主将旁观者 {player.playerName} 移出房间"))


async def cmd_mute_spectator(room: GameRoom, host_id: str, target_id: Any, muted: Any):
    """房主禁言 / 解禁旁观者。"""
    if host_id != room.hostId:
        return
    spectator_id = str(target_id or "")
    if spectator_id not in room.spectators:
        return
    if bool(muted):
        room.spectatorMuted.add(spectator_id)
    else:
        room.spectatorMuted.discard(spectator_id)
    await room.send_to_player(
        spectator_id, "Event_SpectatorMuted", {"muted": bool(muted)}
    )
    await room.broadcast_state()


# ---------------------------------------------------------------- 语音通话


async def cmd_voice_join(room: GameRoom, player_id: str):
    """加入语音通话：新成员拿到既有成员列表并主动发 offer，老成员收到通知。

    旁观者同样可以加入（D5）；管理员隐身旁观与「审批时未授予语音」的旁观者除外。
    """
    player = room.member_of(player_id)
    if player is None or player.isBot:
        return
    if player_id in room.spectatorVoiceBanned:
        await room.send_to_player(
            player_id, "Event_VoiceKicked", {"by": "房主（未开放旁观语音）"}
        )
        return

    if player_id in room.voiceParticipants:
        # 页面刷新后重连：先静默移除再走完整流程，双方重建 PeerConnection
        room.voiceParticipants.remove(player_id)
        for pid in list(room.voiceParticipants):
            await room.send_to_player(
                pid,
                "Event_VoicePeerLeft",
                {"playerId": player_id, "playerName": player.playerName},
            )

    room.voiceParticipants.append(player_id)
    room.voiceHostMuted.discard(player_id)
    term_registry.log_event(f"{player.playerName} 加入语音通话（房间 {room.roomId}）", "info")

    await room.send_to_player(
        player_id,
        "Event_VoicePeers",
        {"peers": [pid for pid in room.voiceParticipants if pid != player_id]},
    )
    for pid in list(room.voiceParticipants):
        if pid == player_id:
            continue
        await room.send_to_player(
            pid,
            "Event_VoicePeerJoined",
            {"playerId": player_id, "playerName": player.playerName},
        )
    await room.broadcast_chat(system_chat(room, f"{player.playerName} 加入了语音通话"))
    await room.broadcast_state()


async def cmd_voice_leave(room: GameRoom, player_id: str, notify_chat: bool = True):
    if player_id not in room.voiceParticipants:
        return
    room.voiceParticipants.remove(player_id)
    room.voiceHostMuted.discard(player_id)
    player = room.member_of(player_id)
    name = player.playerName if player else player_id
    for pid in list(room.voiceParticipants):
        await room.send_to_player(
            pid, "Event_VoicePeerLeft", {"playerId": player_id, "playerName": name}
        )
    if notify_chat and player is not None:
        await room.broadcast_chat(system_chat(room, f"{name} 离开了语音通话"))
    await room.broadcast_state()


async def cmd_voice_signal(room: GameRoom, player_id: str, to: Any, data: Any):
    """转发 WebRTC 信令（offer / answer / ICE candidate），点对点直达。"""
    if player_id not in room.voiceParticipants:
        return
    target = str(to or "")
    if not target or target == player_id or target not in room.voiceParticipants:
        return
    if not isinstance(data, dict):
        return
    await room.send_to_player(target, "Event_VoiceSignal", {"from": player_id, "data": data})


async def cmd_voice_set_mute(room: GameRoom, player_id: str, muted: bool):
    """自己的静音开关：只广播状态供他人看到禁麦徽标，实际禁音在本地轨道完成。"""
    if player_id not in room.voiceParticipants:
        return
    for pid in list(room.voiceParticipants):
        if pid == player_id:
            continue
        await room.send_to_player(
            pid, "Event_VoiceMuteState", {"playerId": player_id, "muted": bool(muted)}
        )


async def cmd_voice_mute_all(room: GameRoom, player_id: str, muted: bool):
    """房主全体禁麦 / 解除禁麦：服务端记录标记并推送事件，客户端禁用麦克风轨道。"""
    if player_id != room.hostId:
        return
    if muted:
        room.voiceHostMuted.update(room.voiceParticipants)
    else:
        room.voiceHostMuted.clear()
    for pid in list(room.voiceParticipants):
        await room.send_to_player(pid, "Event_VoiceHostMuted", {"muted": bool(muted)})
    action = "全体禁麦" if muted else "解除全体禁麦"
    term_registry.log_event(f"房主{action}（房间 {room.roomId}）", "warn")
    await room.broadcast_state()


async def cmd_voice_kick(room: GameRoom, player_id: str, target_id: Any):
    """房主把某名成员移出语音通话。"""
    if player_id != room.hostId:
        return
    target = str(target_id or "")
    if not target or target not in room.voiceParticipants:
        return
    room.voiceParticipants.remove(target)
    room.voiceHostMuted.discard(target)
    target_player = room.member_of(target)
    name = target_player.playerName if target_player else target
    host = room.players.get(player_id)
    for pid in list(room.voiceParticipants):
        await room.send_to_player(
            pid, "Event_VoicePeerLeft", {"playerId": target, "playerName": name}
        )
    await room.send_to_player(
        target, "Event_VoiceKicked", {"by": host.playerName if host else "房主"}
    )
    await room.broadcast_chat(system_chat(room, f"{name} 被移出语音通话"))
    await room.broadcast_state()


async def cmd_voice_close(room: GameRoom, player_id: str):
    """房主关闭通话：全员退出并销毁本地 PeerConnection。"""
    if player_id != room.hostId or not room.voiceParticipants:
        return
    host = room.players.get(player_id)
    by = host.playerName if host else "房主"
    room.voiceParticipants = []
    room.voiceHostMuted.clear()
    # 参赛者与旁观者都要收到（旁观者可能也加入了语音）
    for pid in list(room.ws_connections.keys()) + list(room.spectator_conns.keys()):
        await room.send_to_player(pid, "Event_VoiceClosed", {"by": by})
    await room.broadcast_chat(system_chat(room, f"{by} 关闭了语音通话"))
    await room.broadcast_state()


async def handle_command(room: GameRoom, player_id: str, message: dict):
    cmd = message.get("cmd") or message.get("action")

    # ---------------------------------------------------------- 旁观者分支
    # 旁观者天然不在 players 里，服务端在这里统一拦截写操作：即使前端把按钮
    # 显示出来（视角代入时很可能出现「轮到你了」的 UI），也改不了牌局。
    if player_id not in room.players:
        if player_id not in room.spectators:
            return
        if cmd in SPECTATOR_ALLOWED_CMDS:
            if cmd == "SendChat":
                await cmd_send_chat(room, player_id, message.get("text"))
            elif cmd == "SpectateSetView":
                await cmd_spectate_set_view(room, player_id, message.get("targetPlayerId"))
            elif cmd == "SpectatorLeave":
                await room.send_to_player(player_id, "Event_SpectatorLeft", {})
                await unregister_spectator(room, player_id, room.spectator_conns.get(player_id))
            elif cmd == "VoiceJoin":
                await cmd_voice_join(room, player_id)
            elif cmd == "VoiceLeave":
                await cmd_voice_leave(room, player_id)
            elif cmd == "VoiceSignal":
                await cmd_voice_signal(room, player_id, message.get("to"), message.get("data"))
            elif cmd == "VoiceSetMute":
                await cmd_voice_set_mute(room, player_id, bool(message.get("muted")))
            return
        await room.send_to_player(
            player_id, "Event_ActionRejected", {"reason": "旁观者不可操作"}
        )
        return

    if cmd == "StartGame":
        await cmd_start_game(room, player_id)
    elif cmd == "SelectColorToDraw":
        await cmd_select_color_to_draw(room, player_id, message.get("color"))
    elif cmd == "JudgeByPosition":
        await cmd_judge_by_position(room, player_id, message.get("publicCardId"))
    elif cmd == "JudgeByPoint":
        await cmd_judge_by_point(room, player_id, message.get("publicCardId"), message.get("targetColor"))
    elif cmd == "SkipTurn":
        await cmd_skip_turn(room, player_id)
    elif cmd == "SubmitGuess":
        await cmd_submit_guess(room, player_id, message.get("guesses"))
    elif cmd == "KickPlayer":
        await cmd_kick_player(room, player_id, message.get("playerId"))
    elif cmd == "LeaveRoom":
        await cmd_leave_room(room, player_id)
    elif cmd == "AddBot":
        await cmd_add_bot(room, player_id)
    elif cmd == "RemoveBot":
        await cmd_remove_bot(room, player_id, message.get("playerId"))
    elif cmd == "Reconnect":
        await cmd_reconnect(room, player_id, message.get("accessToken"))
    elif cmd == "SelectPublicCard":
        await cmd_select_public_card(room, player_id, message.get("publicCardId"))
    elif cmd == "DeselectPublicCard":
        await cmd_deselect_public_card(room, player_id)
    elif cmd == "ResetGame":
        if player_id == room.hostId:
            await reset_room_state(room)
            term_registry.log_event(f"房主重置房间 {room.roomId}", "info")
            await room.broadcast_state()
    elif cmd == "DissolveRoom":
        if player_id == room.hostId:
            await admin_close_room(room, by="房主")
    elif cmd == "SetRoomPrivacy":
        await cmd_set_room_privacy(room, player_id, message.get("private"))
    elif cmd == "SpectatorRespond":
        await cmd_spectator_respond(
            room,
            player_id,
            message.get("playerId"),
            message.get("allow"),
            message.get("allowChat", True),
            message.get("allowVoice", True),
        )
    elif cmd == "KickSpectator":
        await cmd_kick_spectator(room, player_id, message.get("playerId"))
    elif cmd == "MuteSpectator":
        await cmd_mute_spectator(room, player_id, message.get("playerId"), message.get("muted"))
    elif cmd == "SendChat":
        await cmd_send_chat(room, player_id, message.get("text"))
    elif cmd == "VoiceJoin":
        await cmd_voice_join(room, player_id)
    elif cmd == "VoiceLeave":
        await cmd_voice_leave(room, player_id)
    elif cmd == "VoiceSignal":
        await cmd_voice_signal(room, player_id, message.get("to"), message.get("data"))
    elif cmd == "VoiceSetMute":
        await cmd_voice_set_mute(room, player_id, bool(message.get("muted")))
    elif cmd == "VoiceMuteAll":
        await cmd_voice_mute_all(room, player_id, bool(message.get("muted")))
    elif cmd == "VoiceKick":
        await cmd_voice_kick(room, player_id, message.get("playerId"))
    elif cmd == "VoiceClose":
        await cmd_voice_close(room, player_id)


async def cmd_set_room_privacy(room: GameRoom, player_id: str, private: Any):
    """房主切换房间隐身：隐身房间不出现在首页公开列表（管理员仍可见）。"""
    if player_id != room.hostId:
        return
    room.isPrivate = bool(private)
    term_registry.log_event(
        f"房主将房间 {room.roomId} 设为{'隐身' if room.isPrivate else '公开'}", "info"
    )
    await room.broadcast_state()
    await room.broadcast_chat(
        system_chat(
            room,
            "房主已开启房间隐身，本房不再出现在首页房间列表"
            if room.isPrivate
            else "房主已关闭房间隐身，本房重新出现在首页房间列表",
        )
    )


async def reset_room_state(room: GameRoom):
    """重置到等待界面，保持房间号与玩家（房主重置与管理员重置共用）。"""
    room.stop_bot_driver()
    room.gamePhase = "WAITING"
    room.subPhase = None
    room.roundNumber = 0
    room.currentTurnPlayerId = None
    room.turnOrder = []
    room.color_decks = {}
    room.publicCards = []
    room.removedPublicCardIds = set()
    room.deckRemainingCount = {color: 0 for color in Color.ALL}
    room.pendingJudgement = None
    room.gameOverInfo = None
    room.selectedPublicCardId = None
    room.usedCardNumbers = []
    room.gameStartedAt = None
    room.gameEndedAt = None
    for p in room.players.values():
        p.hand = []
        p.clues = []
        p.isAlive = True
    # 重置牌局会结束当前语音通话（聊天记录与旁观者保留）
    if room.voiceParticipants:
        room.voiceParticipants = []
        room.voiceHostMuted.clear()
        for pid in list(room.ws_connections.keys()) + list(room.spectator_conns.keys()):
            await room.send_to_player(pid, "Event_VoiceClosed", {"by": "牌局重置"})
    # 旁观者的代入视角若指向已不存在的玩家，回退到默认视角
    for sid in list(room.spectatorView.keys()):
        if room.spectatorView.get(sid) not in room.players:
            room.spectatorView[sid] = room.default_spectate_view()


async def admin_reset_room(room: GameRoom):
    await reset_room_state(room)
    term_registry.log_event(f"管理员重置房间 {room.roomId}", "warn")
    await room.broadcast_state()


async def admin_set_chat_disabled(room: GameRoom, disabled: bool):
    """管理员开关单个房间的聊天。

    只拦「真人发言」：系统消息（加入/离开/语音动态）与语音通话都不受影响，
    否则房内会失去上下文，也看不出为什么发不出去。
    """
    room.chatDisabled = bool(disabled)
    action = "关闭" if room.chatDisabled else "恢复"
    term_registry.log_event(
        f"管理员{action}房间 {room.roomId} 的聊天", "warn" if room.chatDisabled else "info"
    )
    text = (
        "管理员已关闭本房间的聊天功能"
        if room.chatDisabled
        else "管理员已恢复本房间的聊天功能"
    )
    await room.broadcast_chat(system_chat(room, text))
    await room.broadcast_state()


async def admin_close_room(room: GameRoom, by: str = "管理员"):
    room.stop_bot_driver()
    rooms.pop(room.roomId, None)
    term_registry.log_event(f"{by}关闭房间 {room.roomId}", "warn")
    # 参赛者与旁观者一并通知并断开
    for pid, ws in list(room.ws_connections.items()) + list(room.spectator_conns.items()):
        try:
            await ws.send_json({"event": "Event_RoomClosed", "payload": {}})
        except Exception:
            pass
    for pid in list(room.ws_connections.keys()) + list(room.spectator_conns.keys()):
        await room.send_to_player(pid, "Event_AdminNotice", {"text": "房间已关闭"})
    room.ws_connections.clear()
    room.spectator_conns.clear()
    room.spectators.clear()
    room.spectatorView.clear()
    room.spectatorMuted.clear()
    room.spectatorVoiceBanned.clear()
    room.spectatorHidden.clear()
    room.spectatorPending.clear()


async def admin_kick_player(room: GameRoom, player_id: Optional[str]):
    """管理员把某名玩家移出房间（cmd_kick_player 内部会以 4001 断其连接）。"""
    if not player_id or player_id not in room.players:
        return
    player = room.players[player_id]
    await cmd_kick_player(room, room.hostId, player_id)
    term_registry.log_event(f"管理员移出玩家 {player.playerName}（房间 {room.roomId}）", "warn")


async def refresh_after_terminal_kick(room: GameRoom):
    """终端被强制断开后刷新房间状态。

    玩家的 isOnline 已由管理端置为 False；若断开的正是当前回合玩家，
    则与普通断线一致进入 PAUSED，等其重连或由管理员继续操作。
    """
    if room.gamePhase == "PLAYING" and room.currentTurnPlayerId:
        current = room.players.get(room.currentTurnPlayerId)
        if current is not None and not current.isOnline and room.currentTurnPlayerId not in room.ws_connections:
            room.subPhase = "PAUSED"
    await room.broadcast_state()


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
DIST_PATH = os.path.join(PROJECT_ROOT, "dist")

# 无人在线多久后回收房间（关标签页而不是点退出留下的空壳）
IDLE_ROOM_SECONDS = 300.0
_empty_since: Dict[str, float] = {}


async def _idle_room_reaper():
    """定时回收「一个人都不在线」超过 5 分钟的房间。

    否则房间会永远留在 rooms 里：首页房间列表能看到一个进不去的幽灵房，
    管理后台也一直挂着它。
    """
    while True:
        await asyncio.sleep(30)
        now = time.time()
        for rid, room in list(rooms.items()):
            if room.ws_connections or room.spectator_conns:
                _empty_since.pop(rid, None)
                continue
            since = _empty_since.setdefault(rid, now)
            if now - since >= IDLE_ROOM_SECONDS:
                _empty_since.pop(rid, None)
                await admin_close_room(room, by="系统空闲回收")

mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(_idle_room_reaper())
    print(f"📁 前端静态文件路径：{DIST_PATH}")
    print(f"📁 路径存在：{os.path.exists(DIST_PATH)}")
    if os.path.exists(DIST_PATH):
        print("✅ 前端已构建，可正常访问")
    else:
        print("⚠️  前端未构建，请先运行 setup.sh")
    print(f"⚙️  配置文件：{app_config.CONFIG_PATH}")
    print(
        f"⚙️  管理口令：{app_config.admin_username()} / 房间 {app_config.admin_room()}"
        f"；仅本机登录：{'开' if app_config.admin_local_only() else '关'}"
    )
    print(
        f"⚙️  IP 黑名单 {len(app_config.ip_entries())} 条；违禁词 {len(app_config.word_entries())} 个"
    )
    tls = _tls_kwargs()
    print(
        "🔒 HTTPS：已启用（自签证书，支持语音通话）"
        if tls
        else "🔒 HTTPS：未启用（未找到 certs/server.crt，语音通话不可用）"
    )


# ---------------------------------------------------------------- 安全口令
# 开启后除「管理后台 / 静态资源 / 回环地址（决策 D6）」外，进站一律需要口令。
# 口令来自 URL 的 ?key=...（校验通过即种 7 天 Cookie 并从地址栏抹掉口令）
# 或 access_key Cookie；WebSocket 握手同样校验（同源握手浏览器会自动带 Cookie）。

ACCESS_COOKIE = "access_key"
ACCESS_COOKIE_MAX_AGE = 7 * 24 * 3600
_access_denied_log: Dict[str, float] = {}


def _is_static_asset(path: str) -> bool:
    """静态资源不校验：否则页面拿不到 JS/CSS/图标，连输口令的界面都渲染不出来。"""
    if path.startswith("/assets/"):
        return True
    rel = path.lstrip("/")
    if not rel or rel.endswith("index.html"):
        return False
    root = os.path.realpath(DIST_PATH)
    candidate = os.path.realpath(os.path.join(root, rel))
    if not candidate.startswith(root + os.sep):
        return False
    return os.path.isfile(candidate)


def _access_exempt_path(path: str) -> bool:
    """管理后台整条链路豁免——它自己有「仅本机开关 + 昵称房间号口令」两层。"""
    return path == "/admin" or path.startswith("/admin/") or path.startswith("/api/admin")


def access_allowed_ws(websocket: WebSocket) -> bool:
    """WebSocket 握手校验：管理通道已在别处判定，这里只管游戏与在线登记。"""
    if not app_config.access_enabled():
        return True
    if app_config.access_exempt_loopback() and admin_module.is_local_ws(websocket):
        return True
    if app_config.access_key_valid(websocket.cookies.get(ACCESS_COOKIE)):
        return True
    return app_config.access_key_valid(websocket.query_params.get("key"))


def _access_denied_page(reason: str = "") -> str:
    hint = f"<p class=\"reason\">{reason}</p>" if reason else ""
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>403 · 需要访问口令</title>
<style>body{{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
background:#f2f4f8;font-family:-apple-system,"PingFang SC",sans-serif;color:#334155}}
.card{{background:#fff;padding:36px 40px;border-radius:16px;box-shadow:0 12px 40px rgba(15,23,42,.10);
max-width:520px;width:calc(100% - 48px)}}h1{{margin:0 0 10px;font-size:20px;color:#0f172a}}
p{{margin:8px 0;line-height:1.7;font-size:13.5px;color:#64748b}}
.reason{{color:#dc2626}}code{{background:#f1f5f9;padding:2px 6px;border-radius:4px;color:#0f172a}}
form{{display:flex;gap:8px;margin-top:18px}}input{{flex:1;min-width:0;padding:9px 12px;border:1px solid #d8dee9;
border-radius:8px;font-size:14px;outline:none}}input:focus{{border-color:#667eea}}
button{{padding:9px 18px;border:0;border-radius:8px;background:linear-gradient(45deg,#667eea,#764ba2);
color:#fff;font-size:14px;cursor:pointer}}</style></head><body><div class="card">
<h1>需要访问口令</h1>
{hint}
<p>本服务已开启访问口令。请使用管理员提供的<b>带口令的完整链接</b>打开，或在此输入口令。</p>
<form method="get"><input name="key" type="text" placeholder="粘贴访问口令" autocomplete="off" autofocus>
<button type="submit">进入</button></form>
<p>一次验证通过后，本设备 <b>7 天</b>内无需再输。口令在管理后台「安全设置 → 访问口令」生成；
在服务器本机（<code>127.0.0.1</code>）访问默认不需要口令。</p>
</div></body></html>"""


@app.middleware("http")
async def access_guard(request: Request, call_next):
    if not app_config.access_enabled():
        return await call_next(request)

    path = request.url.path
    if _access_exempt_path(path) or _is_static_asset(path):
        return await call_next(request)
    if app_config.access_exempt_loopback() and admin_module.is_local_request(request):
        return await call_next(request)
    # 已持有有效 Cookie：放行，且不重复计入命中次数
    if app_config.access_key_valid(request.cookies.get(ACCESS_COOKIE)):
        return await call_next(request)

    raw_key = (request.query_params.get("key") or "").strip()
    if raw_key and app_config.access_key_valid(raw_key, record=True):
        # 校验通过即换发 Cookie，并把 URL 里的口令抹掉：避免口令留在地址栏、
        # 浏览历史与 Referer 里，也免得前端把 ?key= 当成业务参数解析
        pairs = [(k, v) for k, v in request.query_params.multi_items() if k != "key"]
        location = path + (f"?{urlencode(pairs)}" if pairs else "")
        response = RedirectResponse(location, status_code=302)
        response.set_cookie(
            ACCESS_COOKIE,
            raw_key,
            max_age=ACCESS_COOKIE_MAX_AGE,
            httponly=True,
            samesite="strict",
            secure=request.url.scheme == "https",
            path="/",
        )
        return response

    ip = app_config.normalize_ip(request.client.host if request.client else "")
    now = time.time()
    if now - _access_denied_log.get(ip, 0.0) > 60:
        _access_denied_log[ip] = now
        if not raw_key:
            term_registry.log_event(f"未携带访问口令被拦（{ip}，{path}）", "info")
        if raw_key:
            term_registry.log_event(f"访问口令无效（{ip}）", "warn")

    if path.startswith("/api/"):
        return JSONResponse(
            {"detail": "需要访问口令", "reason": "access_denied"}, status_code=403
        )
    reason = "口令无效或已过期" if raw_key else ""
    return HTMLResponse(
        _access_denied_page(reason), status_code=403, headers={"Cache-Control": "no-store"}
    )


# ---------------------------------------------------------------- API 路由
# 注意：这些路由必须注册在 SPA 兜底路由 /{path:path} 之前，否则会被 index.html 抢走。


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "guess-number-game", "version": "1.0.0"}


@app.get("/api/version")
async def get_version():
    return {"backend": "FastAPI + Python", "frontend": "Vue 3 + TypeScript", "version": "1.0.0"}


@app.get("/api/rooms")
async def list_rooms():
    """首页公开房间列表。

    管理员可整体关闭该功能：关闭后直接返回空列表，首页连面板占位都不渲染。
    开启时只返回「等人中 / 进行中」且未被房主设为隐身的房间：已结束的房间加入
    无意义，隐身房间是房主的主动选择。管理后台展示的是 /ws/admin 快照，不受此处
    过滤影响。
    """
    if not app_config.room_list_enabled():
        return {"enabled": False, "rooms": [], "serverTime": time.time()}
    visible_phases = ("WAITING", "PLAYING")
    items = []
    for rid, room in rooms.items():
        if room.isPrivate or room.gamePhase not in visible_phases:
            continue
        host = room.players.get(room.hostId)
        items.append(
            {
                "roomId": rid,
                "playerCount": len(room.players),
                "maxPlayers": 4,
                "gamePhase": room.gamePhase,
                "hostName": host.playerName if host else None,
                "spectatorCount": len(getattr(room, "spectators", {}) or {}),
                "createdAt": room.createdAt,
                "chatDisabled": bool(getattr(room, "chatDisabled", False)),
            }
        )
    # 等人中的房间排前面；同级按创建时间正序（先开的房间先展示）
    items.sort(key=lambda r: (0 if r["gamePhase"] == "WAITING" else 1, r["createdAt"]))
    return {"enabled": True, "rooms": items, "serverTime": time.time()}


@app.get("/api/admin/access")
async def admin_access(request: Request):
    """管理后台入口校验：默认仅回环地址返回 200，其余一律 403。"""
    ip = app_config.normalize_ip(request.client.host if request.client else "")
    if not admin_module.origin_allowed(request):
        if app_config.is_ip_banned(ip):
            message = "当前来源 IP 已被加入黑名单，禁止访问管理后台"
            reason = "ip_banned"
        else:
            message = "管理后台仅允许在本机（127.0.0.1 / localhost）访问"
            reason = "local_only"
        return JSONResponse(
            {"ok": False, "reason": reason, "message": message},
            status_code=403,
        )
    return {
        "ok": True,
        "adminUser": app_config.admin_username(),
        "adminRoom": app_config.admin_room(),
        "localOnly": app_config.admin_local_only(),
        "serverTime": time.time(),
    }


@app.get("/api/banned-words")
async def banned_words():
    """违禁词库（公开只读）：供首页在输入昵称时做本地预检。

    预检只是体验优化，真正的拦截在后端 WebSocket 握手处完成。
    """
    return {"words": [str(e.get("word")) for e in app_config.word_entries()]}


# ------------------------------------------------------- 管理端 / 终端 WebSocket


@app.websocket("/ws/presence/{client_id}")
async def presence_endpoint(websocket: WebSocket, client_id: str):
    """欢迎页的轻量在线登记：只用于管理后台展示「连入终端」，不参与游戏。"""
    await websocket.accept()
    ip = app_config.normalize_ip(websocket.client.host if websocket.client else "")
    if app_config.is_ip_banned(ip):
        banned = app_config.record_ip_hit(ip) or ip
        term_registry.log_event(f"拒绝黑名单终端连入（{ip}，命中 {banned}）", "warn")
        await websocket.send_json({"error": "你的 IP 已被禁止连入"})
        await websocket.close(code=1008, reason="ip_banned")
        return
    # 第二道闸：安全口令（黑名单优先于口令，见 §8.4 优先级）
    if not access_allowed_ws(websocket):
        term_registry.log_event(f"拒绝无口令的在线登记（{ip}）", "warn")
        await websocket.send_json({"error": "需要访问口令"})
        await websocket.close(code=1008, reason="access_denied")
        return
    user_agent = websocket.headers.get("user-agent", "")
    term_registry.get_or_create(client_id, ip, user_agent, "guest")
    term_registry.attach_socket(client_id, websocket, "presence")
    try:
        while True:
            message = await websocket.receive_text()
            if message == "ping":
                term_registry.touch(client_id)
    except Exception:
        pass
    finally:
        term_registry.detach_socket(client_id, websocket)


@app.websocket("/ws/admin")
async def admin_endpoint(websocket: WebSocket):
    # 第一道闸：来源校验（仅本机开关 + IP 黑名单）
    ip = app_config.normalize_ip(websocket.client.host if websocket.client else "")
    if not admin_module.origin_allowed_ws(websocket):
        reason = "ip_banned" if app_config.is_ip_banned(ip) else "local_only"
        term_registry.log_event(f"拒绝管理端连接：{ip}（{reason}）", "warn")
        await websocket.close(code=1008, reason=reason)
        return

    await websocket.accept()

    client_id = websocket.query_params.get("clientId") or f"admin-{uuid.uuid4().hex[:8]}"
    term_registry.get_or_create(client_id, ip, websocket.headers.get("user-agent", ""), "admin")
    term_registry.attach_socket(client_id, websocket, "admin")

    # 第二道闸：口令（昵称 + 房间号）
    try:
        auth = await asyncio.wait_for(websocket.receive_json(), timeout=10)
    except Exception:
        term_registry.detach_socket(client_id, websocket)
        await websocket.close(code=1008, reason="auth_timeout")
        return

    if not admin_module.check_credentials(auth.get("user"), auth.get("room")):
        term_registry.log_event(f"管理端口令错误（{ip}）", "warn")
        try:
            await websocket.send_json({"event": "Event_AdminDenied", "payload": {"reason": "口令错误"}})
        except Exception:
            pass
        term_registry.detach_socket(client_id, websocket)
        await websocket.close(code=1008, reason="bad_credentials")
        return

    term_registry.log_event(f"管理员进入后台（{ip}）", "warn")
    try:
        await websocket.send_json(
            {"event": "Event_AdminSnapshot", "payload": admin_module.build_snapshot(rooms)}
        )
    except Exception:
        term_registry.detach_socket(client_id, websocket)
        return

    async def push_loop():
        try:
            while True:
                await asyncio.sleep(2.0)
                await websocket.send_json(
                    {"event": "Event_AdminSnapshot", "payload": admin_module.build_snapshot(rooms)}
                )
        except asyncio.CancelledError:
            return
        except Exception:
            return

    push_task = asyncio.create_task(push_loop())
    try:
        while True:
            message = await websocket.receive_json()
            # 隐身旁观：签发一次性凭证并直接回给该管理端（execute_command 只能返回 bool，
            # 拿不到 token，所以在这里单独处理）
            if message.get("cmd") == "AdminSpectate":
                target = rooms.get(str(message.get("roomId") or ""))
                if target is None:
                    await websocket.send_json(
                        {"event": "Event_AdminNotice", "payload": {"text": "房间已不存在，无法旁观"}}
                    )
                    continue
                token = issue_admin_spectate_token(target.roomId)
                term_registry.log_event(
                    f"管理员签发隐身旁观凭证（房间 {target.roomId}）", "warn"
                )
                await websocket.send_json(
                    {
                        "event": "Event_AdminSpectateToken",
                        "payload": {"roomId": target.roomId, "token": token},
                    }
                )
                continue
            if message.get("cmd") == "AdminAddAccessToken":
                raw_days = message.get("days")
                try:
                    days = float(raw_days) if raw_days not in (None, "", 0) else None
                except (TypeError, ValueError):
                    days = None
                saved, entry = app_config.add_access_token(
                    str(message.get("note") or ""), days
                )
                term_registry.log_event(
                    "管理员生成访问口令"
                    if saved
                    else "生成访问口令（仅内存生效，写入 config.json 失败）",
                    "warn",
                )
                await websocket.send_json(
                    {
                        "event": "Event_AdminAccessToken",
                        "payload": {
                            "token": entry["token"],
                            "note": entry["note"],
                            "expiresAt": entry["expiresAt"],
                        },
                    }
                )
                await websocket.send_json(
                    {"event": "Event_AdminSnapshot", "payload": admin_module.build_snapshot(rooms)}
                )
                continue
            changed = await admin_module.execute_command(rooms, message)
            if changed:
                await websocket.send_json(
                    {"event": "Event_AdminSnapshot", "payload": admin_module.build_snapshot(rooms)}
                )
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        print(f"[admin] 管理端连接异常：{exc}")
    finally:
        push_task.cancel()
        term_registry.detach_socket(client_id, websocket)
        term_registry.log_event(f"管理员退出后台（{ip}）", "info")


# ------------------------------------------------------------ 静态资源与页面

if os.path.exists(DIST_PATH):

    @app.get("/admin", response_class=HTMLResponse)
    async def admin_page(request: Request):
        """直接访问 /admin 时由服务端把关：非本机（或被拉黑）返回 403，本机走 SPA 路由。"""
        ip = app_config.normalize_ip(request.client.host if request.client else "")
        if not admin_module.origin_allowed(request):
            banned = app_config.is_ip_banned(ip)
            title = "403 · IP 已被封禁" if banned else "403 · 仅限本机访问"
            detail = (
                "当前来源 IP 在黑名单中，已被禁止访问管理后台。"
                if banned
                else "管理后台仅允许在服务器本机通过 http://localhost:8000/admin 访问。"
            )
            return HTMLResponse(
                f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>{title}</title>
<style>body{{margin:0;height:100vh;display:flex;align-items:center;justify-content:center;
background:#f2f4f8;font-family:-apple-system,"PingFang SC",sans-serif;color:#334155}}
.card{{background:#fff;padding:40px 48px;border-radius:16px;box-shadow:0 12px 40px rgba(15,23,42,.10);
text-align:center;max-width:520px}}h1{{margin:0 0 12px;font-size:22px;color:#dc2626}}
p{{margin:6px 0;line-height:1.7;font-size:14px;color:#64748b}}code{{background:#f1f5f9;
padding:2px 6px;border-radius:4px;color:#0f172a}}</style></head><body><div class="card">
<h1>{title}</h1><p>{detail}</p>
<p>当前来源地址不在允许范围内。</p></div></body></html>""",
                status_code=403,
            )
        index_path = os.path.join(DIST_PATH, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return HTMLResponse("<h1>前端未构建，请先运行 npm run build</h1>", status_code=503)

    @app.get("/")
    async def read_index():
        index_path = os.path.join(DIST_PATH, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return {"error": "前端未构建，请先运行 setup.sh"}

    app.mount("/assets", StaticFiles(directory=os.path.join(DIST_PATH, "assets")), name="assets")

    @app.get("/{path:path}")
    async def serve_spa(path: str):
        # 未命中的 API 路径不应返回 HTML，否则前端 fetch 会解析失败
        if path.startswith("api/") or path.startswith("ws/"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        index_path = os.path.join(DIST_PATH, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return {"error": "页面不存在"}

else:

    @app.get("/")
    async def no_frontend():
        return {
            "message": "欢迎使用猜数字桌游 API",
            "status": "后端运行正常",
            "notice": "前端尚未构建，请运行 ./setup.sh 完成环境配置",
        }


@app.websocket("/ws/{room_id}/{player_name}")
async def websocket_endpoint(websocket: WebSocket, room_id: str, player_name: str):
    # 保留号：管理入口房间号、presence 与管理通道都不允许被当成游戏房
    if room_id in (app_config.admin_room(), "presence", "admin"):
        await websocket.accept()
        await websocket.send_json({"error": "该房间号已保留"})
        await websocket.close(code=1008, reason="room_reserved")
        return

    await websocket.accept()

    ip = app_config.normalize_ip(websocket.client.host if websocket.client else "")
    user_agent = websocket.headers.get("user-agent", "")
    client_id = websocket.query_params.get("clientId") or ""

    # 第一道闸：IP 黑名单（单 IP 或 CIDR 网段）
    if app_config.is_ip_banned(ip):
        banned = app_config.record_ip_hit(ip) or ip
        term_registry.log_event(f"拒绝黑名单连入（{ip}，命中 {banned}）", "warn")
        await websocket.send_json({"error": "你的 IP 已被禁止连入"})
        await websocket.close(code=1008, reason="ip_banned")
        return

    # 第二道闸：安全口令（黑名单优先于口令）
    if not access_allowed_ws(websocket):
        term_registry.log_event(f"拒绝无口令的游戏连接（{ip}，房间 {room_id}）", "warn")
        await websocket.send_json({"error": "需要访问口令"})
        await websocket.close(code=1008, reason="access_denied")
        return

    player_id = f"{room_id}_{player_name}"
    room = rooms.get(room_id)

    # ------------------------------------------------------------ 旁观者接入
    # spectate=1 走旁观流程（不占用 players 名额）；adminToken 为管理员一次性凭证
    spectate = (websocket.query_params.get("spectate") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    admin_token = (websocket.query_params.get("adminToken") or "").strip()
    if spectate:
        if room is None:
            await websocket.send_json({"error": "房间不存在，无法旁观"})
            await websocket.close(code=1008, reason="room_not_found")
            return
        spectator_id = await register_spectator(
            websocket, room, player_name, ip, client_id, admin_token
        )
        if spectator_id is None:
            return
        try:
            while True:
                data = await websocket.receive_json()
                if client_id:
                    term_registry.touch(client_id)
                await handle_command(room, spectator_id, data)
        except WebSocketDisconnect:
            print(f"旁观者 {player_name} 断开连接")
            if client_id:
                term_registry.detach_socket(client_id, websocket)
                term_registry.clear_room_binding(client_id, room_id)
            await unregister_spectator(room, spectator_id, websocket)
        return

    is_new_room = room is None
    if room is None:
        room = GameRoom(room_id, player_id)
        rooms[room_id] = room

    is_new_player = player_id not in room.players
    if player_id in room.players:
        player = room.players[player_id]
        player.isOnline = True
    else:
        if len(room.players) >= 4:
            await websocket.send_json({"error": "房间已满"})
            await websocket.close(code=1008, reason="room_full")
            return
        # 第二道闸：昵称违禁词（文字聊天的同一套词库，聊天功能落地后复用）
        hit_word = app_config.check_banned_text(player_name)
        if hit_word:
            app_config.record_word_hit(hit_word)
            term_registry.log_event(f"拒绝含违禁词的昵称（{ip}，命中「{hit_word}」）", "warn")
            await websocket.send_json({"error": f"昵称包含违禁内容：{hit_word}"})
            await websocket.close(code=1008, reason="banned_nickname")
            return
        player = Player(player_id, player_name)
        room.add_player(player, websocket)

    room.ws_connections[player_id] = websocket

    if client_id:
        term_registry.get_or_create(client_id, ip, user_agent, "player")
        term_registry.attach_socket(client_id, websocket, "room")
        term_registry.bind_player(client_id, player_name, room_id)

    level = "info"
    if is_new_room:
        term_registry.log_event(f"创建房间 {room_id}（房主 {player_name}，{ip}）", level)

    await websocket.send_json({"event": "Event_SyncFullState", "payload": room.get_state()})
    await room.broadcast_state()

    if is_new_player:
        await room.broadcast_chat(system_chat(room, f"{player_name} 加入了房间"))
    else:
        await room.broadcast_chat(system_chat(room, f"{player_name} 重新连接了房间"))

    left_room = False
    try:
        while True:
            data = await websocket.receive_json()
            if client_id:
                term_registry.touch(client_id)
            await handle_command(room, player_id, data)
            # 主动退出 / 房主解散之后，服务端已经把人（或整个房间）清掉了，
            # 这里收尾关连接，不再走下面那套「断线保留占位」的逻辑
            if player_id not in room.players:
                left_room = True
                break
    except WebSocketDisconnect:
        print(f"玩家 {player_name} 断开连接")
        if player_id in room.players:
            room.players[player_id].isOnline = False
        room.ws_connections.pop(player_id, None)
        if client_id:
            term_registry.detach_socket(client_id, websocket)
            term_registry.clear_room_binding(client_id, room_id)

        # 断开连接即退出语音通话，并通知房间内其他成员
        if player_id in room.voiceParticipants:
            await cmd_voice_leave(room, player_id)

        is_current = room.currentTurnPlayerId == player_id
        paused = False
        if is_current and room.gamePhase == "PLAYING":
            room.subPhase = "PAUSED"
            paused = True

        await room.broadcast_state()
        await room.broadcast_chat(system_chat(room, f"{player_name} 断线了，等待重连"))

        # 等人阶段：宽限期过了还没回来就把占位清掉（点「退出」走 LeaveRoom，不受此限）
        if room.gamePhase == "WAITING" and player_id in room.players:
            asyncio.create_task(remove_offline_after_grace(room, player_id))

        for pid in list(room.ws_connections.keys()):
            await room.send_to_player(
                pid,
                "Event_PlayerDisconnected",
                {
                    "playerId": player_id,
                    "isCurrentTurnPlayer": is_current,
                    "paused": paused,
                },
            )

    if left_room:
        if client_id:
            term_registry.detach_socket(client_id, websocket)
            term_registry.clear_room_binding(client_id, room_id)
        try:
            await websocket.close(code=1000, reason="left")
        except Exception:
            pass


def _tls_kwargs() -> dict:
    """检测到 scripts/gen-cert.sh 生成的自签证书时返回 uvicorn 的 SSL 参数。

    语音通话需要 getUserMedia，浏览器只在安全上下文（HTTPS）下开放，
    因此生产模式默认走 HTTPS；没有证书时回退纯 HTTP（失去语音能力）。
    """
    cert = os.path.join(PROJECT_ROOT, "certs", "server.crt")
    key = os.path.join(PROJECT_ROOT, "certs", "server.key")
    if os.path.exists(cert) and os.path.exists(key):
        return {"ssl_certfile": cert, "ssl_keyfile": key}
    return {}


if __name__ == "__main__":
    import uvicorn

    tls = _tls_kwargs()
    scheme = "https" if tls else "http"
    print("🚀 正在启动服务器...")
    if tls:
        print(f"🔒 已启用 HTTPS（自签证书）：{scheme}://localhost:8000")
        print("💡 浏览器首次访问需手动信任证书；未生成证书可执行 ./scripts/gen-cert.sh")
    else:
        print("⚠️  未检测到证书，以 HTTP 启动（浏览器将禁用语音通话）")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info", **tls)