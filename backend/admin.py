"""系统管理员后台：本机访问校验、快照组装、管理动作执行。

安全模型（三层）：
1. **来源限制**：`config.admin_local_only()` 为 true 时，管理页面、管理 API 与
   管理 WebSocket 只接受回环地址（127.0.0.1 / ::1）；该开关在 config.json 的
   `admin.localOnly` 中配置（环境变量 ADMIN_LOCAL_ONLY 可覆盖）。
2. **IP 黑名单**：命中黑名单（单 IP 或 CIDR 网段）的来源一律拒绝，优先级高于
   仅本机开关。
3. **口令**：昵称 + 房间号作为管理入口口令，在 config.json 的 `admin` 段配置，
   避免本机上他人误入。

IP 黑名单与违禁词库同样由 config.json 驱动，管理后台可在线增删并热生效。
"""

from __future__ import annotations

import os
import platform
import resource
import shutil
import sys
import time
from typing import Any, Dict, List, Optional

import fastapi

try:  # 兼容 `python -m uvicorn backend.main:app` 与直接运行两种导入方式
    from . import config as app_config
    from . import registry as term_registry
except ImportError:  # pragma: no cover
    import config as app_config  # type: ignore
    import registry as term_registry  # type: ignore

LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", "0:0:0:0:0:0:0:1"}

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SERVER_STARTED_AT = time.time()


def normalize_host(host: Optional[str]) -> str:
    if not host:
        return ""
    host = host.strip().lower()
    if host.startswith("["):
        host = host.strip("[]")
    # IPv4-mapped IPv6：::ffff:127.0.0.1
    if host.startswith("::ffff:"):
        host = host[len("::ffff:"):]
    return host


def is_loopback(host: Optional[str]) -> bool:
    """判断对端地址是否为本机回环地址。"""
    h = normalize_host(host)
    if not h:
        return False
    if h in LOOPBACK_HOSTS:
        return True
    # 127.0.0.0/8 全部属于回环
    return h.startswith("127.")


def is_local_request(request: Any) -> bool:
    client = getattr(request, "client", None)
    return is_loopback(getattr(client, "host", None))


def is_local_ws(websocket: Any) -> bool:
    client = getattr(websocket, "client", None)
    return is_loopback(getattr(client, "host", None))


def _origin_ip(request: Any) -> str:
    client = getattr(request, "client", None)
    return app_config.normalize_ip(getattr(client, "host", None))


def _origin_ip_ws(websocket: Any) -> str:
    client = getattr(websocket, "client", None)
    return app_config.normalize_ip(getattr(client, "host", None))


def origin_allowed(request: Any) -> bool:
    """管理来源总闸：黑名单优先，其次受仅本机开关约束。"""
    ip = _origin_ip(request)
    if app_config.is_ip_banned(ip):
        return False
    if app_config.admin_local_only() and not is_loopback(ip):
        return False
    return True


def origin_allowed_ws(websocket: Any) -> bool:
    ip = _origin_ip_ws(websocket)
    if app_config.is_ip_banned(ip):
        return False
    if app_config.admin_local_only() and not is_loopback(ip):
        return False
    return True


def _room_duration(room: Any, ref: float) -> float:
    if room.gamePhase == "PLAYING" and room.gameStartedAt:
        return max(0.0, ref - room.gameStartedAt)
    if room.gamePhase == "GAME_OVER":
        end = room.gameEndedAt or ref
        return max(0.0, end - (room.gameStartedAt or room.createdAt))
    return max(0.0, ref - room.createdAt)


def _room_dict(room: Any, ref: float) -> dict:
    players = []
    for pid, player in room.players.items():
        terminal = None
        for term in term_registry.TERMINALS.values():
            if term.roomId == room.roomId and term.nickname == player.playerName:
                terminal = term
                break
        players.append(
            {
                "playerId": pid,
                "playerName": player.playerName,
                "isBot": bool(player.isBot),
                "isOnline": bool(player.isOnline),
                "isAlive": bool(player.isAlive),
                "isHost": pid == room.hostId,
                "clientId": terminal.clientId if terminal else None,
            }
        )
    host = room.players.get(room.hostId)
    # 旁观者：管理员可见全部（含 hidden 的隐身旁观），普通端只能看到非 hidden
    spectators = [
        {
            "playerId": sid,
            "playerName": spectator.playerName,
            "hidden": sid in getattr(room, "spectatorHidden", set()),
            "muted": sid in getattr(room, "spectatorMuted", set()),
            "viewId": (getattr(room, "spectatorView", {}) or {}).get(sid),
        }
        for sid, spectator in getattr(room, "spectators", {}).items()
    ]
    return {
        "roomId": room.roomId,
        "gamePhase": room.gamePhase,
        "subPhase": room.subPhase,
        "roundNumber": room.roundNumber,
        "hostName": host.playerName if host else None,
        "createdAt": room.createdAt,
        "gameStartedAt": room.gameStartedAt,
        "gameEndedAt": room.gameEndedAt,
        "durationSeconds": round(_room_duration(room, ref), 1),
        "playerCount": len(room.players),
        "aliveCount": sum(1 for p in room.players.values() if p.isAlive),
        # 房主是否把房间设为隐身（隐身房不出现在首页公开列表，管理员仍可见）
        "isPrivate": bool(getattr(room, "isPrivate", False)),
        "currentTurnPlayerId": room.currentTurnPlayerId,
        "players": players,
        "spectatorCount": len(spectators),
        "spectators": spectators,
    }


def _system_dict(rooms: Dict[str, Any]) -> dict:
    ref = time.time()
    load1 = load5 = load15 = None
    try:
        load1, load5, load15 = os.getloadavg()
    except (AttributeError, OSError):
        pass

    cpu_count = os.cpu_count() or 1
    rss_mb = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024), 1)
    disk = shutil.disk_usage(PROJECT_ROOT)

    active_games = sum(1 for r in rooms.values() if r.gamePhase == "PLAYING")
    waiting = sum(1 for r in rooms.values() if r.gamePhase == "WAITING")

    return {
        "startedAt": SERVER_STARTED_AT,
        "now": ref,
        "uptimeSeconds": round(ref - SERVER_STARTED_AT, 1),
        "pythonVersion": platform.python_version(),
        "fastapiVersion": getattr(fastapi, "__version__", "unknown"),
        "platform": f"{platform.system()} {platform.release()}",
        "pid": os.getpid(),
        "cpuCount": cpu_count,
        "load1": round(load1, 2) if load1 is not None else None,
        "load5": round(load5, 2) if load5 is not None else None,
        "load15": round(load15, 2) if load15 is not None else None,
        "rssMb": rss_mb,
        "diskTotalGb": round(disk.total / (1024 ** 3), 1),
        "diskFreeGb": round(disk.free / (1024 ** 3), 1),
        "diskUsedPct": round(disk.used / disk.total * 100, 1),
        "roomCount": len(rooms),
        "activeGames": active_games,
        "waitingRooms": waiting,
        "onlineTerminals": term_registry.online_count(),
        "totalTerminals": len(term_registry.TERMINALS),
    }


def build_snapshot(rooms: Dict[str, Any]) -> dict:
    ref = time.time()
    room_items = [_room_dict(room, ref) for room in rooms.values()]
    room_items.sort(key=lambda r: (r["gamePhase"] != "PLAYING", r["roomId"]))
    return {
        "serverTime": ref,
        "roomList": {"enabled": app_config.room_list_enabled()},
        "terminals": term_registry.snapshot_terminals(),
        "rooms": room_items,
        "system": _system_dict(rooms),
        "events": term_registry.recent_events(50),
        "security": {
            "localOnly": app_config.admin_local_only(),
            "username": app_config.admin_username(),
            "room": app_config.admin_room(),
            "configPath": app_config.CONFIG_PATH,
            "ipBlacklist": [
                {"ip": e.get("ip"), "addedAt": e.get("addedAt") or 0, "hits": int(e.get("hits") or 0)}
                for e in app_config.ip_entries()
            ],
            "bannedWords": [
                {"word": e.get("word"), "addedAt": e.get("addedAt") or 0, "hits": int(e.get("hits") or 0)}
                for e in app_config.word_entries()
            ],
        },
    }


def check_credentials(user: Optional[str], room: Optional[str]) -> bool:
    return (user or "").strip() == app_config.admin_username() and (room or "").strip() == app_config.admin_room()


async def execute_command(rooms: Dict[str, Any], message: dict) -> bool:
    """执行一条管理指令，返回是否需要立即回推快照。"""
    # 延迟取得游戏主模块，避免循环导入；优先复用已加载的实例
    game = sys.modules.get("backend.main")
    if game is None:  # pragma: no cover
        import backend.main as game  # type: ignore

    cmd = message.get("cmd")
    room_id = message.get("roomId")
    room = rooms.get(room_id) if room_id else None

    if cmd == "AdminKickTerminal":
        client_id = message.get("clientId")
        if not client_id:
            return False
        term = term_registry.TERMINALS.get(client_id)
        # 不允许把管理端自己断线，避免误操作锁死后台
        if term is None or term.kind == "admin":
            return False
        if term.roomId:
            r = rooms.get(term.roomId)
            if r and term.nickname:
                player = r.players.get(f"{r.roomId}_{term.nickname}")
                if player and player.playerName == term.nickname and not player.isBot:
                    player.isOnline = False
                    term_registry.clear_room_binding(client_id)
                    await game.refresh_after_terminal_kick(r)
        await term_registry.close_terminal(client_id)
        return True

    if cmd == "AdminCloseRoom":
        if not room:
            return False
        await game.admin_close_room(room)
        return True

    if cmd == "AdminResetRoom":
        if not room:
            return False
        await game.admin_reset_room(room)
        return True

    if cmd == "AdminKickPlayer":
        if not room:
            return False
        player_id = message.get("playerId")
        if not player_id:
            return False
        await game.admin_kick_player(room, player_id)
        return True

    # ------------------------------------------------------------ 安全设置
    if cmd == "AdminSetRoomListEnabled":
        raw = message.get("enabled")
        if isinstance(raw, str):
            raw = raw.strip().lower() in ("1", "true", "yes", "on")
        ok, detail = app_config.set_room_list_enabled(bool(raw))
        term_registry.log_event(
            f"管理员{detail}首页房间列表"
            if ok
            else f"切换首页房间列表失败：{detail}",
            "info" if ok else "warn",
        )
        return True

    if cmd == "AdminReloadConfig":
        # 管理员改完 config.json 后手动热生效（口令、开关等启动时加载的字段）
        app_config.load_config()
        term_registry.log_event("管理员从 config.json 重载配置", "warn")
        return True

    if cmd == "AdminAddIp":
        ok, detail = app_config.add_ip(str(message.get("ip") or ""))
        term_registry.log_event(
            f"管理员加入 IP 黑名单 {detail}" if ok else f"加入 IP 黑名单失败：{detail}",
            "info" if ok else "warn",
        )
        return True

    if cmd == "AdminRemoveIp":
        ok, detail = app_config.remove_ip(str(message.get("ip") or ""))
        term_registry.log_event(
            f"管理员移除 IP 黑名单 {detail}" if ok else f"移除 IP 黑名单失败：{detail}",
            "info" if ok else "warn",
        )
        return True

    if cmd == "AdminAddWord":
        ok, detail = app_config.add_word(str(message.get("word") or ""))
        term_registry.log_event(
            f"管理员新增违禁词「{detail}」" if ok else f"新增违禁词失败：{detail}",
            "info" if ok else "warn",
        )
        return True

    if cmd == "AdminRemoveWord":
        ok, detail = app_config.remove_word(str(message.get("word") or ""))
        term_registry.log_event(
            f"管理员移除违禁词「{detail}」" if ok else f"移除违禁词失败：{detail}",
            "info" if ok else "warn",
        )
        return True

    return False
