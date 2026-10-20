from __future__ import annotations

import asyncio
import mimetypes
import os
import random
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

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
        }

    async def broadcast_state(self):
        state = self.get_state()
        for player_id, ws in list(self.ws_connections.items()):
            try:
                await ws.send_json({"event": "Event_StateUpdate", "payload": state})
            except Exception as exc:
                print(f"发送状态给 {player_id} 失败：{exc}")

    async def send_to_player(self, player_id: str, event: str, payload: Any):
        ws = self.ws_connections.get(player_id)
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
        """房间内广播一条聊天消息（含发送者本人，前端不做本地回显）。"""
        self.push_chat(message)
        for pid in list(self.ws_connections.keys()):
            await self.send_to_player(pid, "Event_Chat", message)

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
    player = room.players.get(player_id)
    if player is None or player.isBot:
        return
    raw = str(text or "").strip()
    if not raw:
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
        }
    )


# ---------------------------------------------------------------- 语音通话


async def cmd_voice_join(room: GameRoom, player_id: str):
    """加入语音通话：新成员拿到既有成员列表并主动发 offer，老成员收到通知。"""
    player = room.players.get(player_id)
    if player is None or player.isBot:
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
    player = room.players.get(player_id)
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
    target_player = room.players.get(target)
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
    for pid in list(room.ws_connections.keys()):
        await room.send_to_player(pid, "Event_VoiceClosed", {"by": by})
    await room.broadcast_chat(system_chat(room, f"{by} 关闭了语音通话"))
    await room.broadcast_state()


async def handle_command(room: GameRoom, player_id: str, message: dict):
    cmd = message.get("cmd") or message.get("action")

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
    # 重置牌局会结束当前语音通话（聊天记录保留）
    if room.voiceParticipants:
        room.voiceParticipants = []
        room.voiceHostMuted.clear()
        for pid in list(room.ws_connections.keys()):
            await room.send_to_player(pid, "Event_VoiceClosed", {"by": "牌局重置"})


async def admin_reset_room(room: GameRoom):
    await reset_room_state(room)
    term_registry.log_event(f"管理员重置房间 {room.roomId}", "warn")
    await room.broadcast_state()


async def admin_close_room(room: GameRoom, by: str = "管理员"):
    room.stop_bot_driver()
    rooms.pop(room.roomId, None)
    term_registry.log_event(f"{by}关闭房间 {room.roomId}", "warn")
    for pid, ws in list(room.ws_connections.items()):
        try:
            await ws.send_json({"event": "Event_RoomClosed", "payload": {}})
        except Exception:
            pass
    for pid in list(room.ws_connections.keys()):
        await room.send_to_player(pid, "Event_AdminNotice", {"text": "房间已被管理员关闭"})
    room.ws_connections.clear()


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

mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")


@app.on_event("startup")
async def startup_event():
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
    return {
        "rooms": [
            {"roomId": rid, "playerCount": len(room.players), "gamePhase": room.gamePhase}
            for rid, room in rooms.items()
        ]
    }


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

    player_id = f"{room_id}_{player_name}"
    room = rooms.get(room_id)
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

    try:
        while True:
            data = await websocket.receive_json()
            if client_id:
                term_registry.touch(client_id)
            await handle_command(room, player_id, data)
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
        await room.broadcast_chat(system_chat(room, f"{player_name} 离开了房间"))

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