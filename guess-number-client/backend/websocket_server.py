"""
后端 WebSocket 服务实现 - 猜数字桌游
支持多玩家在线对战、线索判定、游戏状态管理等功能
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from typing import Dict, List, Optional, Any
import json
import uuid
import random
from datetime import datetime
import asyncio

app = FastAPI(title="猜数字桌游 WebSocket 服务", version="1.0.0")

# ==================== 数据结构定义 ====================

class Color:
    """颜色枚举"""
    RED = '红'
    BLUE = '蓝'
    GREEN = '绿'
    ORANGE = '橙'
    PINK = '粉'
    
    ALL = [RED, BLUE, GREEN, ORANGE, PINK]

class Card:
    """卡牌类"""
    def __init__(self, color: str, number: int):
        self.id = str(uuid.uuid4())[:8]
        self.color = color
        self.number = number
        self.isSelected = False
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'color': self.color,
            'number': self.number,
            'isSelected': self.isSelected
        }

class Clue:
    """线索类"""
    def __init__(self, clue_type: str, public_card_id: str, public_card_number: int, 
                 target_color: Optional[str] = None, result: Any = None):
        self.id = str(uuid.uuid4())[:8]
        self.type = clue_type  # 'position' or 'point'
        self.publicCardId = public_card_id
        self.publicCardNumber = public_card_number
        self.targetColor = target_color
        self.result = result  # position: 0-5, point: True/False
        self.timestamp = int(datetime.now().timestamp() * 1000)
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'type': self.type,
            'publicCardId': self.publicCardId,
            'publicCardNumber': self.publicCardNumber,
            'targetColor': self.targetColor,
            'result': self.result,
            'timestamp': self.timestamp
        }

class Player:
    """玩家类"""
    def __init__(self, player_id: str, player_name: str):
        self.playerId = player_id
        self.playerName = player_name
        self.isAlive = True
        self.isOnline = True
        self.hand: List[Card] = []
        self.clues: List[Clue] = []
        self.accessToken = str(uuid.uuid4())
    
    def to_dict(self, hide_numbers: bool = False) -> dict:
        hand_data = []
        for card in self.hand:
            if hide_numbers:
                hand_data.append({
                    'id': card.id,
                    'color': card.color,
                    'number': None
                })
            else:
                hand_data.append(card.to_dict())
        
        return {
            'playerId': self.playerId,
            'playerName': self.playerName,
            'isAlive': self.isAlive,
            'isOnline': self.isOnline,
            'hand': hand_data,
            'clues': [clue.to_dict() for clue in self.clues]
        }

class GameRoom:
    """游戏房间类"""
    def __init__(self, room_id: str, host_id: str):
        self.roomId = room_id
        self.hostId = host_id
        self.gamePhase = 'WAITING'  # WAITING, PLAYING, GAME_OVER
        self.subPhase = None  # DRAW_PHASE, ACTION_PHASE, JUDGE_RESULT, PAUSED
        self.roundNumber = 0
        self.currentTurnPlayerId: Optional[str] = None
        self.players: Dict[str, Player] = {}
        self.deck: List[Card] = []
        self.publicCards: List[Card] = []
        self.deckRemainingCount: Dict[str, int] = {}
        self.pendingJudgement: Optional[dict] = None
        self.gameOverInfo: Optional[dict] = None
        self.seed = str(uuid.uuid4())[:8]
        self.ws_connections: Dict[str, WebSocket] = {}
    
    def add_player(self, player: Player, ws: WebSocket):
        self.players[player.playerId] = player
        self.ws_connections[player.playerId] = ws
    
    def remove_player(self, player_id: str):
        if player_id in self.players:
            del self.players[player_id]
        if player_id in self.ws_connections:
            del self.ws_connections[player_id]
    
    def get_state(self, view_player_id: Optional[str] = None) -> dict:
        """获取游戏状态，可选择性地隐藏其他玩家的手牌数字"""
        players_data = {}
        for pid, player in self.players.items():
            # 只对自己显示完整手牌，对其他玩家隐藏数字
            hide = view_player_id is not None and pid != view_player_id
            players_data[pid] = player.to_dict(hide_numbers=hide)
        
        return {
            'roomId': self.roomId,
            'gamePhase': self.gamePhase,
            'subPhase': self.subPhase,
            'roundNumber': self.roundNumber,
            'currentTurnPlayerId': self.currentTurnPlayerId,
            'deckRemainingCount': self.deckRemainingCount,
            'publicCards': [card.to_dict() for card in self.publicCards],
            'players': players_data,
            'pendingJudgement': self.pendingJudgement,
            'gameOverInfo': self.gameOverInfo,
            'seed': self.seed
        }
    
    async def broadcast_state(self):
        """广播游戏状态给所有玩家"""
        for player_id, ws in self.ws_connections.items():
            state = self.get_state(view_player_id=player_id)
            try:
                await ws.send_json({'event': 'Event_StateUpdate', 'payload': state})
            except Exception as e:
                print(f"Failed to send state to {player_id}: {e}")
    
    async def send_to_player(self, player_id: str, event: str, payload: Any):
        """发送事件给指定玩家"""
        if player_id in self.ws_connections:
            try:
                await self.ws_connections[player_id].send_json({
                    'event': event,
                    'payload': payload
                })
            except Exception as e:
                print(f"Failed to send {event} to {player_id}: {e}")

# ==================== 全局状态管理 ====================

rooms: Dict[str, GameRoom] = {}

# ==================== 辅助函数 ====================

def create_deck() -> List[Card]:
    """创建一副完整的牌（每种颜色 12 张，共 60 张）"""
    deck = []
    for color in Color.ALL:
        for number in range(1, 13):
            deck.append(Card(color, number))
    random.shuffle(deck)
    return deck

def initialize_deck_remaining() -> Dict[str, int]:
    """初始化剩余牌数统计"""
    return {color: 12 for color in Color.ALL}

def draw_card_from_deck(room: GameRoom, color: str) -> Optional[Card]:
    """从牌堆抽取指定颜色的牌"""
    # 找到第一张指定颜色的牌
    for i, card in enumerate(room.deck):
        if card.color == color:
            return room.deck.pop(i)
    return None

def update_deck_remaining(room: GameRoom):
    """更新剩余牌数统计"""
    counts = initialize_deck_remaining()
    for card in room.deck:
        counts[card.color] -= 1
    room.deckRemainingCount = counts

def check_game_over(room: GameRoom):
    """检查游戏是否结束"""
    # 检查是否有玩家猜对
    if room.gameOverInfo:
        return True
    
    # 检查牌堆是否耗尽
    if len(room.deck) == 0:
        room.gamePhase = 'GAME_OVER'
        room.gameOverInfo = {
            'winnerId': None,
            'winnerName': None,
            'reason': 'deck_exhausted'
        }
        return True
    
    return False

# ==================== WebSocket 连接处理 ====================

@app.websocket("/ws/{room_id}/{player_name}")
async def websocket_endpoint(websocket: WebSocket, room_id: str, player_name: str):
    await websocket.accept()
    
    player_id = str(uuid.uuid4())[:6]
    player = Player(player_id, player_name)
    
    # 创建或加入房间
    if room_id not in rooms:
        room = GameRoom(room_id, player_id)
        rooms[room_id] = room
    else:
        room = rooms[room_id]
    
    room.add_player(player, websocket)
    
    # 发送初始状态
    state = room.get_state(view_player_id=player_id)
    await websocket.send_json({'event': 'Event_SyncFullState', 'payload': state})
    await room.broadcast_state()
    
    try:
        while True:
            message = await websocket.receive_json()
            await handle_command(room, player_id, message)
    except WebSocketDisconnect:
        print(f"Player {player_name} disconnected from room {room_id}")
        room.remove_player(player_id)
        
        # 检查是否是当前回合玩家
        is_current = room.currentTurnPlayerId == player_id
        paused = False
        
        if is_current and room.gamePhase == 'PLAYING':
            room.subPhase = 'PAUSED'
            paused = True
        
        await room.broadcast_state()
        
        # 通知其他玩家
        for pid in room.ws_connections:
            await room.send_to_player(pid, 'Event_PlayerDisconnected', {
                'playerId': player_id,
                'isCurrentTurnPlayer': is_current,
                'paused': paused
            })

# ==================== 命令处理 ====================

async def handle_command(room: GameRoom, player_id: str, message: dict):
    """处理客户端命令"""
    cmd = message.get('cmd')
    
    if cmd == 'StartGame':
        await cmd_start_game(room, player_id)
    elif cmd == 'SelectColorToDraw':
        await cmd_select_color_to_draw(room, player_id, message.get('color'))
    elif cmd == 'JudgeByPosition':
        await cmd_judge_by_position(room, player_id, message.get('publicCardId'))
    elif cmd == 'JudgeByPoint':
        await cmd_judge_by_point(room, player_id, message.get('publicCardId'), message.get('targetColor'))
    elif cmd == 'SkipTurn':
        await cmd_skip_turn(room, player_id)
    elif cmd == 'SubmitGuess':
        await cmd_submit_guess(room, player_id, message.get('guesses'))
    elif cmd == 'KickPlayer':
        await cmd_kick_player(room, player_id, message.get('playerId'))
    elif cmd == 'Reconnect':
        await cmd_reconnect(room, player_id, message.get('accessToken'))

async def cmd_start_game(room: GameRoom, player_id: str):
    """开始游戏"""
    if player_id != room.hostId:
        return  # 只有房主可以开始游戏
    
    if room.gamePhase != 'WAITING':
        return
    
    # 初始化游戏
    room.deck = create_deck()
    room.publicCards = []
    room.roundNumber = 0
    room.gamePhase = 'PLAYING'
    update_deck_remaining(room)
    
    # 发牌：每个玩家 5 张
    for player in room.players.values():
        for _ in range(5):
            if room.deck:
                card = room.deck.pop()
                player.hand.append(card)
        # 按颜色排序手牌
        player.hand.sort(key=lambda c: Color.ALL.index(c.color))
    
    update_deck_remaining(room)
    
    # 随机选择起始玩家
    player_ids = list(room.players.keys())
    room.currentTurnPlayerId = random.choice(player_ids)
    room.subPhase = 'DRAW_PHASE'
    
    await room.broadcast_state()

async def cmd_select_color_to_draw(room: GameRoom, player_id: str, color: str):
    """选择颜色抽牌"""
    if room.currentTurnPlayerId != player_id:
        return
    if room.subPhase != 'DRAW_PHASE':
        return
    if color not in Color.ALL:
        return
    
    player = room.players.get(player_id)
    if not player:
        return
    
    # 抽取牌
    card = draw_card_from_deck(room, color)
    if not card:
        return  # 该颜色已无牌
    
    # 将新牌加入手牌
    player.hand.append(card)
    player.hand.sort(key=lambda c: Color.ALL.index(c.color))
    
    # 弃置一张牌
    room.subPhase = 'ACTION_PHASE'
    update_deck_remaining(room)
    await room.broadcast_state()

async def cmd_judge_by_position(room: GameRoom, player_id: str, public_card_id: str):
    """位置判定"""
    if room.currentTurnPlayerId != player_id:
        return
    if room.subPhase != 'ACTION_PHASE':
        return
    
    # 查找公共牌
    public_card = None
    for card in room.publicCards:
        if card.id == public_card_id:
            public_card = card
            break
    
    if not public_card:
        # 如果没有这张公共牌，需要先抽取公牌
        if room.deck:
            new_public_card = room.deck.pop()
            room.publicCards.append(new_public_card)
            public_card = new_public_card
        else:
            return
    
    # 执行位置判定：随机生成 0-5 的位置
    position = random.randint(0, 5)
    
    # 创建线索
    clue = Clue(
        clue_type='position',
        public_card_id=public_card.id,
        public_card_number=public_card.number,
        result=position
    )
    
    player = room.players.get(player_id)
    if player:
        player.clues.append(clue)
    
    room.pendingJudgement = {
        'selectedPublicCardId': public_card.id,
        'judgeType': 'position',
        'result': position
    }
    
    room.subPhase = 'JUDGE_RESULT'
    await room.broadcast_state()
    
    # 延迟后进入下一轮
    await asyncio.sleep(2)
    room.pendingJudgement = None
    await next_turn(room)

async def cmd_judge_by_point(room: GameRoom, player_id: str, public_card_id: str, target_color: str):
    """点数判定"""
    if room.currentTurnPlayerId != player_id:
        return
    if room.subPhase != 'ACTION_PHASE':
        return
    if target_color not in Color.ALL:
        return
    
    # 查找公共牌
    public_card = None
    for card in room.publicCards:
        if card.id == public_card_id:
            public_card = card
            break
    
    if not public_card:
        # 如果没有这张公共牌，需要先抽取公牌
        if room.deck:
            new_public_card = room.deck.pop()
            room.publicCards.append(new_public_card)
            public_card = new_public_card
        else:
            return
    
    player = room.players.get(player_id)
    if not player:
        return
    
    # 找到目标颜色的手牌
    target_card = None
    for card in player.hand:
        if card.color == target_color:
            target_card = card
            break
    
    if not target_card:
        return
    
    # 执行点数判定：比较点数是否相同
    same_point = public_card.number == target_card.number
    
    # 创建线索
    clue = Clue(
        clue_type='point',
        public_card_id=public_card.id,
        public_card_number=public_card.number,
        target_color=target_color,
        result=same_point
    )
    
    player.clues.append(clue)
    
    room.pendingJudgement = {
        'selectedPublicCardId': public_card.id,
        'judgeType': 'point',
        'targetColor': target_color,
        'result': same_point
    }
    
    room.subPhase = 'JUDGE_RESULT'
    await room.broadcast_state()
    
    # 延迟后进入下一轮
    await asyncio.sleep(2)
    room.pendingJudgement = None
    await next_turn(room)

async def cmd_skip_turn(room: GameRoom, player_id: str):
    """跳过本轮（仅房主可用）"""
    if player_id != room.hostId:
        return
    if room.subPhase != 'ACTION_PHASE':
        return
    
    await next_turn(room)

async def cmd_submit_guess(room: GameRoom, player_id: str, guesses: List[int]):
    """提交猜测"""
    player = room.players.get(player_id)
    if not player:
        return
    
    # 获取玩家手牌的数字（按颜色顺序）
    actual_numbers = []
    for color in Color.ALL:
        for card in player.hand:
            if card.color == color:
                actual_numbers.append(card.number)
                break
    
    # 检查猜测是否正确
    correct = (guesses == actual_numbers)
    
    if correct:
        room.gamePhase = 'GAME_OVER'
        room.gameOverInfo = {
            'winnerId': player_id,
            'winnerName': player.playerName,
            'correctGuess': guesses,
            'reason': 'correct_guess'
        }
        await room.broadcast_state()
        await room.send_to_player(player_id, 'Event_GameOver', room.gameOverInfo)
    else:
        # 返回错误结果
        await room.send_to_player(player_id, 'Event_GuessResult', {
            'correct': False,
            'correctNumbers': actual_numbers
        })

async def cmd_kick_player(room: GameRoom, kicker_id: str, kicked_id: str):
    """踢出玩家（仅房主可用）"""
    if kicker_id != room.hostId:
        return
    if kicked_id == room.hostId:
        return  # 不能踢房主
    
    if kicked_id in room.players:
        room.remove_player(kicked_id)
        await room.broadcast_state()

async def cmd_reconnect(room: GameRoom, player_id: str, access_token: str):
    """重连"""
    player = room.players.get(player_id)
    if player and player.accessToken == access_token:
        player.isOnline = True
        await room.broadcast_state()

async def next_turn(room: GameRoom):
    """进入下一轮"""
    # 检查游戏是否结束
    if check_game_over(room):
        await room.broadcast_state()
        return
    
    room.roundNumber += 1
    
    # 轮换玩家
    player_ids = list(room.players.keys())
    current_index = player_ids.index(room.currentTurnPlayerId) if room.currentTurnPlayerId in player_ids else 0
    next_index = (current_index + 1) % len(player_ids)
    room.currentTurnPlayerId = player_ids[next_index]
    room.subPhase = 'DRAW_PHASE'
    
    await room.broadcast_state()

# ==================== HTTP API ====================

@app.get("/")
async def root():
    return {"message": "猜数字桌游 WebSocket 服务", "version": "1.0.0"}

@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "guess-number-ws", "version": "1.0.0"}

@app.get("/api/rooms")
async def list_rooms():
    return {
        "rooms": [
            {
                "roomId": rid,
                "playerCount": len(room.players),
                "gamePhase": room.gamePhase
            }
            for rid, room in rooms.items()
        ]
    }

if __name__ == "__main__":
    import uvicorn
    print("🚀 正在启动 WebSocket 服务器...")
    uvicorn.run(app, host="0.0.0.0", port=8765, log_level="info")
