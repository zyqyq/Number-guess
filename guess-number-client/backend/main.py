from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
import mimetypes
import json
import uuid
import random
from datetime import datetime
import asyncio
from typing import Dict, List, Optional, Any

app = FastAPI(title="猜数字桌游", version="1.0.0")

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
        self.result = result
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'type': self.type,
            'publicCardId': self.publicCardId,
            'publicCardNumber': self.publicCardNumber,
            'targetColor': self.targetColor,
            'result': self.result
        }

class Player:
    """玩家类"""
    def __init__(self, player_id: str, player_name: str):
        self.playerId = player_id
        self.playerName = player_name
        self.hand: List[Card] = []
        self.clues: List[Clue] = []
        self.isAlive = True
        self.isOnline = True
    
    def to_dict(self, reveal_hand: bool = False) -> dict:
        hand_data = [card.to_dict() for card in self.hand] if reveal_hand else [{'id': c.id, 'color': c.color} for c in self.hand]
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
        self.players: Dict[str, Player] = {}
        self.publicCards: List[Card] = []
        self.gamePhase = 'waiting'  # waiting, playing, ended
        self.currentPlayerId: Optional[str] = None
        self.turnOrder: List[str] = []
        self.turnIndex = 0
        self.ws_connections: Dict[str, WebSocket] = {}
    
    def add_player(self, player: Player):
        if len(self.players) < 4:
            self.players[player.playerId] = player
            if len(self.players) == 1:
                self.hostId = player.playerId
    
    def remove_player(self, player_id: str):
        if player_id in self.players:
            del self.players[player_id]
        if player_id in self.ws_connections:
            del self.ws_connections[player_id]
    
    async def broadcast_state(self):
        """广播游戏状态给所有玩家"""
        state = self.get_game_state()
        for pid, ws in list(self.ws_connections.items()):
            try:
                await ws.send_json(state)
            except Exception as e:
                print(f"发送消息给 {pid} 失败：{e}")
    
    def get_game_state(self) -> dict:
        """获取游戏状态快照"""
        players_data = {}
        for pid, player in self.players.items():
            reveal = (self.gamePhase == 'ended')
            players_data[pid] = player.to_dict(reveal_hand=reveal)
        
        return {
            'roomId': self.roomId,
            'hostId': self.hostId,
            'players': players_data,
            'publicCards': [card.to_dict() for card in self.publicCards],
            'gamePhase': self.gamePhase,
            'currentPlayerId': self.currentPlayerId,
            'turnOrder': self.turnOrder
        }
    
    def generate_public_cards(self):
        """生成公共牌（6 张，每种颜色至少一张）"""
        self.publicCards = []
        colors_used = set()
        
        for i in range(6):
            if i < 5:
                color = Color.ALL[i]
                colors_used.add(color)
            else:
                color = random.choice(Color.ALL)
            
            number = random.randint(1, 9)
            self.publicCards.append(Card(color, number))
    
    def deal_hands(self):
        """发牌：每个玩家 5 张手牌"""
        for pid, player in self.players.items():
            player.hand = []
            for _ in range(5):
                color = random.choice(Color.ALL)
                number = random.randint(1, 9)
                player.hand.append(Card(color, number))
    
    def start_game(self):
        """开始游戏"""
        if len(self.players) != 4:
            return False
        
        self.generate_public_cards()
        self.deal_hands()
        self.turnOrder = list(self.players.keys())
        random.shuffle(self.turnOrder)
        self.currentPlayerId = self.turnOrder[0]
        self.turnIndex = 0
        self.gamePhase = 'playing'
        return True

# 全局房间存储
rooms: Dict[str, GameRoom] = {}

# WebSocket 连接管理
active_connections: Dict[str, WebSocket] = {}

# ==================== HTTP API ====================

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
        print("⚠️  前端未构建，请先运行环境配置脚本")

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
            "notice": "前端尚未构建，请运行 ./setup.sh 完成环境配置"
        }

@app.get("/api/health")
async def health_check():
    return {
        "status": "ok",
        "service": "guess-number-game",
        "version": "1.0.0"
    }

@app.get("/api/version")
async def get_version():
    return {
        "backend": "FastAPI + Python",
        "frontend": "Vue 3 + TypeScript",
        "version": "1.0.0"
    }

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

# ==================== WebSocket 端点 ====================

@app.websocket("/ws/{room_id}/{player_name}")
async def websocket_endpoint(websocket: WebSocket, room_id: str, player_name: str):
    await websocket.accept()
    
    room = rooms.get(room_id)
    if not room:
        await websocket.send_json({'error': '房间不存在'})
        await websocket.close()
        return
    
    player_id = f"{room_id}_{player_name}"
    
    if player_id in room.players:
        player = room.players[player_id]
        player.isOnline = True
    else:
        if len(room.players) >= 4:
            await websocket.send_json({'error': '房间已满'})
            await websocket.close()
            return
        player = Player(player_id, player_name)
        room.add_player(player)
    
    room.ws_connections[player_id] = websocket
    active_connections[f"{room_id}:{player_id}"] = websocket
    
    await room.broadcast_state()
    
    try:
        while True:
            data = await websocket.receive_json()
            await handle_message(room, player_id, data)
    except WebSocketDisconnect:
        print(f"玩家 {player_name} 断开连接")
        if player_id in room.players:
            room.players[player_id].isOnline = False
        if player_id in room.ws_connections:
            del room.ws_connections[player_id]
        key = f"{room_id}:{player_id}"
        if key in active_connections:
            del active_connections[key]

async def handle_message(room: GameRoom, player_id: str, data: dict):
    """处理客户端消息"""
    action = data.get('action')
    
    if action == 'StartGame':
        if player_id == room.hostId and room.gamePhase == 'waiting':
            if room.start_game():
                await room.broadcast_state()
    
    elif action == 'SelectColorToDraw':
        if player_id == room.currentPlayerId:
            color = data.get('color')
            if color in Color.ALL:
                new_card = Card(color, random.randint(1, 9))
                player = room.players[player_id]
                player.hand.append(new_card)
                await room.broadcast_state()
    
    elif action == 'JudgeByPosition':
        if player_id == room.currentPlayerId:
            public_card_id = data.get('publicCardId')
            position = data.get('position')
            target_color = data.get('targetColor')
            
            public_card = next((c for c in room.publicCards if c.id == public_card_id), None)
            if public_card:
                clue = Clue('position', public_card_id, public_card.number, target_color)
                count = sum(1 for p in room.players.values() for c in p.hand if c.color == target_color)
                clue.result = {'count': count, 'position': position}
                
                player = room.players[player_id]
                player.clues.append(clue)
                await room.broadcast_state()
    
    elif action == 'JudgeByPoint':
        if player_id == room.currentPlayerId:
            public_card_id = data.get('publicCardId')
            point = data.get('point')
            target_color = data.get('targetColor')
            
            public_card = next((c for c in room.publicCards if c.id == public_card_id), None)
            if public_card:
                clue = Clue('point', public_card_id, public_card.number, target_color)
                cards_with_color_and_point = sum(1 for p in room.players.values() for c in p.hand if c.color == target_color and c.number == point)
                clue.result = {'count': cards_with_color_and_point, 'point': point}
                
                player = room.players[player_id]
                player.clues.append(clue)
                await room.broadcast_state()
    
    elif action == 'SubmitGuess':
        if player_id == room.currentPlayerId:
            guess = data.get('guess')
            correct = True
            for p in room.players.values():
                for card in p.hand:
                    if card.color not in guess.get(card.color, []):
                        correct = False
                        break
            
            if correct:
                room.gamePhase = 'ended'
                await room.broadcast_state()
            else:
                player = room.players[player_id]
                player.isAlive = False
                await room.next_turn()
    
    elif action == 'NextTurn':
        if player_id == room.currentPlayerId:
            await room.next_turn()

async def next_turn(room: GameRoom):
    """切换到下一个玩家的回合"""
    if room.gamePhase != 'playing':
        return
    
    alive_players = [pid for pid in room.turnOrder if room.players[pid].isAlive]
    
    if len(alive_players) <= 1:
        room.gamePhase = 'ended'
    else:
        current_idx = room.turnOrder.index(room.currentPlayerId)
        next_idx = (current_idx + 1) % len(room.turnOrder)
        room.currentPlayerId = room.turnOrder[next_idx]
        room.turnIndex = next_idx
    
    await room.broadcast_state()

GameRoom.next_turn = next_turn

if __name__ == "__main__":
    import uvicorn
    print("🚀 正在启动服务器...")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
