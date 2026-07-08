from __future__ import annotations

import asyncio
import mimetypes
import os
import random
import uuid
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


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
    def __init__(self, player_id: str, player_name: str):
        self.playerId = player_id
        self.playerName = player_name
        self.isAlive = True
        self.isOnline = True
        self.hand: List[Card] = []
        self.clues: List[Clue] = []
        self.accessToken = str(uuid.uuid4())

    def to_dict(self) -> dict:
        return {
            "playerId": self.playerId,
            "playerName": self.playerName,
            "isAlive": self.isAlive,
            "isOnline": self.isOnline,
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
        self.deck: List[Card] = []
        self.publicCards: List[Card] = []
        self.deckRemainingCount: Dict[str, int] = {color: 12 for color in Color.ALL}
        self.pendingJudgement: Optional[dict] = None
        self.gameOverInfo: Optional[dict] = None
        self.selectedPublicCardId: Optional[str] = None
        self.seed = str(uuid.uuid4())[:8]
        self.ws_connections: Dict[str, WebSocket] = {}

    def add_player(self, player: Player, ws: WebSocket):
        self.players[player.playerId] = player
        self.ws_connections[player.playerId] = ws

    def remove_player(self, player_id: str):
        self.players.pop(player_id, None)
        self.ws_connections.pop(player_id, None)

    def get_state(self) -> dict:
        return {
            "roomId": self.roomId,
            "gamePhase": self.gamePhase,
            "subPhase": self.subPhase,
            "roundNumber": self.roundNumber,
            "currentTurnPlayerId": self.currentTurnPlayerId,
            "turnOrder": self.turnOrder,
            "deckRemainingCount": self.deckRemainingCount,
            "publicCards": [c.to_dict() for c in self.publicCards if c.id != self.selectedPublicCardId],
            "players": {pid: player.to_dict() for pid, player in self.players.items()},
            "pendingJudgement": self.pendingJudgement,
            "gameOverInfo": self.gameOverInfo,
            "seed": self.seed,
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


rooms: Dict[str, GameRoom] = {}


def create_deck() -> List[Card]:
    deck: List[Card] = []
    for color in Color.ALL:
        for number in range(1, 13):
            deck.append(Card(color, number))
    random.shuffle(deck)
    return deck


def update_deck_remaining(room: GameRoom):
    counts = {color: 12 for color in Color.ALL}
    for card in room.deck:
        counts[card.color] -= 1
    room.deckRemainingCount = counts


def draw_specific_color(room: GameRoom, color: str) -> Optional[Card]:
    for index, card in enumerate(room.deck):
        if card.color == color:
            return room.deck.pop(index)
    return None


def draw_any_card(room: GameRoom) -> Optional[Card]:
    if not room.deck:
        return None
    return room.deck.pop()


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
        player.hand.sort(key=lambda card: Color.ALL.index(card.color))


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

    if not room.deck:
        room.gamePhase = "GAME_OVER"
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

    room.roundNumber += 1
    room.subPhase = "DRAW_PHASE"
    room.pendingJudgement = None
    update_deck_remaining(room)
    await room.broadcast_state()


def start_game(room: GameRoom) -> bool:
    if len(room.players) != 4:
        return False

    room.deck = create_deck()
    room.publicCards = []
    room.roundNumber = 1
    room.gamePhase = "PLAYING"
    room.subPhase = "DRAW_PHASE"
    room.pendingJudgement = None
    room.gameOverInfo = None
    # 抽取 5 张不同颜色的公共牌
    room.publicCards = []
    colors = Color.ALL.copy()
    random.shuffle(colors)
    picked = colors[:5]
    for c in picked:
        card = draw_specific_color(room, c)
        if card is None:
            card = draw_any_card(room)
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


async def cmd_judge_by_position(room: GameRoom, player_id: str, public_card_id: Optional[str]):
    if room.gamePhase != "PLAYING" or room.subPhase != "ACTION_PHASE":
        return
    if room.currentTurnPlayerId != player_id or not public_card_id:
        return

    public_card = find_card(room.publicCards, public_card_id)
    if not public_card:
        return

    player = room.players.get(player_id)
    if not player:
        return

    position = random.randint(0, 5)
    player.clues.append(Clue("position", public_card.id, public_card.number, result=position))
    room.pendingJudgement = {
        "selectedPublicCardId": public_card.id,
        "judgeType": "position",
        "result": position,
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

    public_card = find_card(room.publicCards, public_card_id)
    if not public_card:
        return

    player = room.players.get(player_id)
    if not player:
        return

    target_card = find_player_card(player, target_color)
    if not target_card:
        return

    same_point = public_card.number == target_card.number
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
        "playerName": player.playerName,
        "isHost": player_id == room.hostId,
    }
    if correct:
        room.gamePhase = "GAME_OVER"
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
        room.remove_player(kicked_id)
        await room.broadcast_state()


async def cmd_reconnect(room: GameRoom, player_id: str, access_token: Optional[str]):
    player = room.players.get(player_id)
    if not player:
        return
    if not access_token or player.accessToken == access_token:
        player.isOnline = True
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
    elif cmd == "Reconnect":
        await cmd_reconnect(room, player_id, message.get("accessToken"))
    elif cmd == "SelectPublicCard":
        room.selectedPublicCardId = message.get("publicCardId")
        await room.broadcast_state()
    elif cmd == "DeselectPublicCard":
        room.selectedPublicCardId = None
        await room.broadcast_state()
    elif cmd == "ResetGame":
        if player_id == room.hostId:
            rooms.pop(room.roomId, None)
            # 创建新房间
            new_room = GameRoom(room.roomId, player_id)
            for pid, p in room.players.items():
                ws = room.ws_connections.get(pid)
                if ws:
                    new_room.add_player(p, ws)
            rooms[room.roomId] = new_room
            await new_room.broadcast_state()
    elif cmd == "DissolveRoom":
        if player_id == room.hostId:
            rooms.pop(room.roomId, None)
            for pid, ws in list(room.ws_connections.items()):
                try:
                    await ws.send_json({"event": "Event_RoomClosed", "payload": {}})
                except Exception:
                    pass


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


if os.path.exists(DIST_PATH):
    app.mount("/assets", StaticFiles(directory=os.path.join(DIST_PATH, "assets")), name="assets")

    @app.get("/")
    async def read_index():
        index_path = os.path.join(DIST_PATH, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return {"error": "前端未构建，请先运行 setup.sh"}

    @app.get("/{path:path}")
    async def serve_spa(path: str):
        if path.startswith("assets/"):
            return FileResponse(os.path.join(DIST_PATH, path))
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


@app.websocket("/ws/{room_id}/{player_name}")
async def websocket_endpoint(websocket: WebSocket, room_id: str, player_name: str):
    await websocket.accept()

    player_id = f"{room_id}_{player_name}"
    room = rooms.get(room_id)
    if not room:
        room = GameRoom(room_id, player_id)
        rooms[room_id] = room

    if player_id in room.players:
        player = room.players[player_id]
        player.isOnline = True
    else:
        if len(room.players) >= 4:
            await websocket.send_json({"error": "房间已满"})
            await websocket.close()
            return
        player = Player(player_id, player_name)
        room.add_player(player, websocket)

    room.ws_connections[player_id] = websocket

    await websocket.send_json({"event": "Event_SyncFullState", "payload": room.get_state()})
    await room.broadcast_state()

    try:
        while True:
            data = await websocket.receive_json()
            await handle_command(room, player_id, data)
    except WebSocketDisconnect:
        print(f"玩家 {player_name} 断开连接")
        if player_id in room.players:
            room.players[player_id].isOnline = False
        room.ws_connections.pop(player_id, None)

        is_current = room.currentTurnPlayerId == player_id
        paused = False
        if is_current and room.gamePhase == "PLAYING":
            room.subPhase = "PAUSED"
            paused = True

        await room.broadcast_state()

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


if __name__ == "__main__":
    import uvicorn

    print("🚀 正在启动服务器...")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")