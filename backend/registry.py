"""终端注册表与服务端事件日志。

管理后台需要知道「谁连进来了」：IP、连入时间、昵称、所在房间。
欢迎页并不建立游戏连接，因此单独有一条 presence WebSocket 只做登记；
玩家进入房间后，游戏连接用同一个 clientId 回填昵称与房间号。

所有状态都是内存态，进程重启即清空，与游戏房间保持一致。
"""

from __future__ import annotations

import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional

# 断开后保留记录的宽限时间，避免刷新页面时列表抖动
GRACE_SECONDS = 30.0

# 服务端事件环形缓冲，供管理后台「系统管理」页展示
EVENT_LOG: Deque[dict] = deque(maxlen=120)


def now_ts() -> float:
    return time.time()


def log_event(text: str, level: str = "info") -> None:
    """记录一条服务端事件（同时打印到控制台）。"""
    EVENT_LOG.append({"ts": now_ts(), "level": level, "text": text})
    print(f"[{level}] {text}")


class Terminal:
    """一个浏览器终端。同一 clientId 的多条连接（presence / 游戏 / 管理）共用一条记录。"""

    def __init__(self, client_id: str, ip: str, user_agent: str, kind: str = "guest"):
        self.clientId = client_id
        self.ip = ip
        self.userAgent = user_agent or ""
        self.kind = kind
        self.connectedAt = now_ts()
        self.lastSeen = self.connectedAt
        self.nickname: Optional[str] = None
        self.roomId: Optional[str] = None
        self.closedAt: Optional[float] = None
        # id(websocket) -> (websocket, channel)
        self.sockets: Dict[int, tuple[Any, str]] = {}

    @property
    def isOnline(self) -> bool:
        return bool(self.sockets)

    def is_stale(self, ref: Optional[float] = None) -> bool:
        ref = ref or now_ts()
        return (not self.sockets) and self.closedAt is not None and ref - self.closedAt > GRACE_SECONDS

    def to_dict(self) -> dict:
        return {
            "clientId": self.clientId,
            "ip": self.ip,
            "userAgent": self.userAgent,
            "kind": self.kind,
            "nickname": self.nickname,
            "roomId": self.roomId,
            "connectedAt": self.connectedAt,
            "lastSeen": self.lastSeen,
            "online": self.isOnline,
            "channels": sorted({ch for _, ch in self.sockets.values()}),
        }


TERMINALS: Dict[str, Terminal] = {}


def prune() -> None:
    ref = now_ts()
    for client_id in [cid for cid, t in TERMINALS.items() if t.is_stale(ref)]:
        TERMINALS.pop(client_id, None)


def get_or_create(client_id: str, ip: str, user_agent: str, kind: str = "guest") -> Terminal:
    prune()
    term = TERMINALS.get(client_id)
    if term is None:
        term = Terminal(client_id, ip, user_agent, kind)
        TERMINALS[client_id] = term
        log_event(f"终端接入 {ip}（{kind}）", "info")
    else:
        # 同一 clientId 换网络（比如 WiFi 切有线）时以最新 IP 为准
        term.ip = ip or term.ip
        if user_agent:
            term.userAgent = user_agent
        if kind == "admin" or term.kind == "guest":
            term.kind = kind
        term.lastSeen = now_ts()
    return term


def attach_socket(client_id: str, ws: Any, channel: str) -> Terminal:
    term = get_or_create(client_id, "", "", "guest")
    term.sockets[id(ws)] = (ws, channel)
    term.closedAt = None
    term.lastSeen = now_ts()
    return term


def touch(client_id: str) -> None:
    term = TERMINALS.get(client_id)
    if term is not None:
        term.lastSeen = now_ts()


def bind_player(client_id: str, nickname: str, room_id: str) -> None:
    term = TERMINALS.get(client_id)
    if term is None:
        return
    term.nickname = nickname
    term.roomId = room_id
    term.kind = "player"


def detach_socket(client_id: str, ws: Any) -> None:
    term = TERMINALS.get(client_id)
    if term is None:
        return
    term.sockets.pop(id(ws), None)
    term.lastSeen = now_ts()
    if not term.sockets:
        term.closedAt = now_ts()


def clear_room_binding(client_id: str, room_id: Optional[str] = None) -> None:
    term = TERMINALS.get(client_id)
    if term is None:
        return
    if room_id is None or term.roomId == room_id:
        term.roomId = None


async def close_terminal(client_id: str, code: int = 4001, reason: str = "admin_kick") -> int:
    """强制断开某个终端的全部连接，返回关闭的连接数。"""
    term = TERMINALS.get(client_id)
    if term is None:
        return 0
    closed = 0
    for ws, _channel in list(term.sockets.values()):
        try:
            await ws.close(code=code, reason=reason)
            closed += 1
        except Exception as exc:  # 连接可能已经断了
            print(f"[registry] 关闭连接失败：{exc}")
    term.sockets.clear()
    term.closedAt = now_ts()
    log_event(f"管理员强制断开 {term.nickname or term.ip}（{closed} 条连接）", "warn")
    return closed


def snapshot_terminals() -> List[dict]:
    prune()
    items = [t.to_dict() for t in TERMINALS.values()]
    items.sort(key=lambda t: (not t["online"], -t["connectedAt"]))
    return items


def online_count() -> int:
    return sum(1 for t in TERMINALS.values() if t.isOnline)


def recent_events(limit: int = 50) -> List[dict]:
    items = list(EVENT_LOG)[-limit:]
    items.reverse()
    return items
