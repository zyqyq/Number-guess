"""可配置项：管理口令、仅本机开关、IP 黑名单、违禁词库。

配置文件：项目根目录 config.json，服务启动时读取；不存在则按默认值自动生成。
管理后台的增删操作会即时写回该文件并热生效，无需重启服务。

环境变量优先级高于配置文件（方便部署时临时覆盖，不改文件）：
  ADMIN_USERNAME    管理后台昵称口令
  ADMIN_ROOM        管理后台房间号口令
  ADMIN_LOCAL_ONLY  true/false，管理后台是否仅允许本机登录
"""

from __future__ import annotations

import copy
import ipaddress
import json
import os
import secrets
import time
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config.json")

DEFAULTS: Dict[str, Any] = {
    "admin": {
        "username": "adminzyq",
        "room": "6666",
        # 管理后台是否只允许本机（回环地址）登录；false 时任何来源都可访问，
        # 仅依赖「昵称 + 房间号」口令，安全性下降，请谨慎关闭。
        "localOnly": True,
    },
    "security": {
        # 每条形如 {"ip": "192.168.2.7", "addedAt":  epoch, "hits": 0}
        # ip 支持单个地址，也支持 CIDR 网段（如 10.0.0.0/8）
        "ipBlacklist": [],
        # 每条形如 {"word": "广告", "addedAt": epoch, "hits": 0}
        "bannedWords": [],
    },
    "roomList": {
        # 是否在首页展示公开房间列表（只保留紧凑列表一种排布），由管理员开关
        "enabled": True,
    },
    "access": {
        # 安全口令：开启后，除管理后台 / 静态资源 / 回环地址外，一律需要口令才能进站
        "enabled": False,
        # 回环地址（127.0.0.1 / ::1）豁免，防止管理员把自己锁在门外（决策 D6）
        "exemptLoopback": True,
        # 每条形如 {"id": "a1b2c3d4", "token": "43 位随机串", "note": "给手机用",
        #           "createdAt": epoch, "expiresAt": epoch|null, "hits": 0}
        "tokens": [],
    },
}

_DATA: Dict[str, Any] = copy.deepcopy(DEFAULTS)


def _env_bool(name: str) -> Optional[bool]:
    raw = os.environ.get(name)
    if raw is None:
        return None
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _normalize_ip(raw: str) -> str:
    """去掉 IPv6 映射前缀与空白，统一为小写。"""
    ip = (raw or "").strip().lower()
    if ip.startswith("::ffff:"):
        ip = ip[len("::ffff:"):]
    if ip.startswith("[") and ip.endswith("]"):
        ip = ip[1:-1]
    return ip


def normalize_ip(raw: str) -> str:
    """对外暴露的 IP 规范化（供 main.py / admin.py 复用）。"""
    return _normalize_ip(raw)


def _migrate_entries(items: Any, key: str) -> List[dict]:
    """兼容旧版纯字符串列表；统一转成 {key, addedAt, hits} 结构。"""
    result: List[dict] = []
    if not isinstance(items, list):
        return result
    for item in items:
        if isinstance(item, dict) and item.get(key):
            entry = {
                key: str(item[key]),
                "addedAt": float(item.get("addedAt") or 0),
                "hits": int(item.get("hits") or 0),
            }
            result.append(entry)
        elif isinstance(item, str) and item.strip():
            result.append({key: item.strip(), "addedAt": 0.0, "hits": 0})
    return result


def _as_bool(value: Any, default: bool = False) -> bool:
    """配置里的布尔值兼容字符串写法（json 里偶尔会写 "false"）。"""
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def _migrate_access(raw: Any) -> Dict[str, Any]:
    """规范化 access 段：剔除无效口令，补齐 id / 时间戳，兼容旧结构。"""
    data = raw if isinstance(raw, dict) else {}
    tokens: List[dict] = []
    for item in data.get("tokens") or []:
        if not isinstance(item, dict):
            continue
        token = str(item.get("token") or "").strip()
        if not token:
            continue
        expires = item.get("expiresAt")
        try:
            expires = float(expires) if expires is not None else None
        except (TypeError, ValueError):
            expires = None
        tokens.append(
            {
                "id": str(item.get("id") or token[:10]),
                "token": token,
                "note": str(item.get("note") or "")[:60],
                "createdAt": float(item.get("createdAt") or 0),
                "expiresAt": expires,
                "hits": int(item.get("hits") or 0),
            }
        )
    return {
        "enabled": _as_bool(data.get("enabled"), False),
        "exemptLoopback": _as_bool(data.get("exemptLoopback"), True),
        "tokens": tokens,
    }


def _merge(defaults: Dict[str, Any], loaded: Dict[str, Any]) -> Dict[str, Any]:
    merged = copy.deepcopy(defaults)
    for section, value in (loaded or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(section), dict):
            merged[section].update(value)
        else:
            merged[section] = value
    merged["security"]["ipBlacklist"] = _migrate_entries(
        merged["security"].get("ipBlacklist"), "ip"
    )
    merged["security"]["bannedWords"] = _migrate_entries(
        merged["security"].get("bannedWords"), "word"
    )
    merged["access"] = _migrate_access(merged.get("access"))
    return merged


def load_config() -> Dict[str, Any]:
    """从磁盘读取配置并刷新内存；文件缺失或损坏时回退默认值。"""
    global _DATA
    raw: Dict[str, Any] = {}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except FileNotFoundError:
        pass
    except (ValueError, OSError) as exc:
        print(f"[config] 读取 {CONFIG_PATH} 失败，使用默认配置：{exc}")
    _DATA = _merge(DEFAULTS, raw)
    return _DATA


def save_config() -> bool:
    """写回配置文件，两级策略；失败时打印日志但不影响内存中的配置。

    1) 首选「临时文件 + os.replace」原子替换，避免写一半时进程被杀导致文件损坏；
    2) 若原子替换被环境拒绝（受限沙箱会拦截 rename、部分网络盘 / 只读挂载的
       上级目录不允许 rename 等），退回到原地覆盖写——它能覆盖已有文件，
       只是在写到一半被打断时有极小概率留下不完整内容。
    """
    payload = json.dumps(_DATA, ensure_ascii=False, indent=2) + "\n"
    tmp_path = f"{CONFIG_PATH}.tmp"

    atomic_error: Optional[OSError] = None
    try:
        with open(tmp_path, "w", encoding="utf-8") as fh:
            fh.write(payload)
        os.replace(tmp_path, CONFIG_PATH)
        return True
    except OSError as exc:
        atomic_error = exc
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    # 降级：直接覆盖目标文件
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
            fh.write(payload)
        print(f"[config] 原子替换被拒绝（{atomic_error}），已退回原地覆盖写并成功")
        return True
    except OSError as exc:
        print(
            f"[config] 写入 {CONFIG_PATH} 失败：原子替换={atomic_error}；原地覆盖={exc}"
        )
        return False


def config_dict() -> Dict[str, Any]:
    """返回当前配置的深拷贝（供管理后台展示 / 测试）。"""
    return copy.deepcopy(_DATA)


# ---------------------------------------------------------------- 管理口令


def admin_username() -> str:
    return os.environ.get("ADMIN_USERNAME") or str(_DATA["admin"]["username"] or "adminzyq")


def admin_room() -> str:
    return os.environ.get("ADMIN_ROOM") or str(_DATA["admin"]["room"] or "6666")


def admin_local_only() -> bool:
    env = _env_bool("ADMIN_LOCAL_ONLY")
    if env is not None:
        return env
    return bool(_DATA["admin"].get("localOnly", True))


# ---------------------------------------------------------------- IP 黑名单


def ip_entries() -> List[dict]:
    return _DATA["security"]["ipBlacklist"]


def _entry_matches(entry_ip: str, ip: str) -> bool:
    if entry_ip == ip:
        return True
    try:
        network = ipaddress.ip_network(entry_ip, strict=False)
        return ipaddress.ip_address(ip) in network
    except ValueError:
        return False


def find_ip_entry(ip: str) -> Optional[dict]:
    target = _normalize_ip(ip)
    if not target:
        return None
    for entry in ip_entries():
        if _entry_matches(str(entry.get("ip", "")), target):
            return entry
    return None


def is_ip_banned(ip: str) -> bool:
    return find_ip_entry(ip) is not None


def record_ip_hit(ip: str) -> Optional[str]:
    entry = find_ip_entry(ip)
    if entry is None:
        return None
    entry["hits"] = int(entry.get("hits") or 0) + 1
    save_config()
    return str(entry.get("ip"))


def add_ip(raw_ip: str) -> Tuple[bool, str]:
    """加入黑名单，支持单个 IP 或 CIDR 网段。"""
    ip = _normalize_ip(raw_ip)
    if not ip:
        return False, "请输入 IP 或网段"
    try:
        if "/" in ip:
            ipaddress.ip_network(ip, strict=False)
        else:
            ipaddress.ip_address(ip)
    except ValueError:
        return False, "IP / 网段格式不正确"
    if find_ip_entry(ip) is not None:
        return False, "该 IP 已在黑名单中"
    ip_entries().append({"ip": ip, "addedAt": time.time(), "hits": 0})
    save_config()
    return True, ip


def remove_ip(raw_ip: str) -> Tuple[bool, str]:
    ip = _normalize_ip(raw_ip)
    entries = ip_entries()
    for index, entry in enumerate(entries):
        if str(entry.get("ip")) == ip:
            entries.pop(index)
            save_config()
            return True, ip
    return False, "黑名单中没有该 IP"


# ---------------------------------------------------------------- 违禁词库


def word_entries() -> List[dict]:
    return _DATA["security"]["bannedWords"]


def _normalize_text(text: str) -> str:
    """匹配用归一化：小写 + 去掉空白与零宽字符，降低拆字绕过概率。"""
    raw = (text or "").lower()
    squeezed = "".join(ch for ch in raw if not ch.isspace() and ch not in "\u200b\u200c\u200d\ufeff")
    return squeezed


def _normalize_word(word: str) -> str:
    return _normalize_text(word)


def check_banned_text(text: str) -> Optional[str]:
    """返回命中的违禁词（原始写法），未命中返回 None。"""
    if not text:
        return None
    haystack = _normalize_text(text)
    if not haystack:
        return None
    for entry in word_entries():
        word = str(entry.get("word") or "")
        needle = _normalize_word(word)
        if needle and needle in haystack:
            return word
    return None


def record_word_hit(word: str) -> None:
    for entry in word_entries():
        if str(entry.get("word")) == word:
            entry["hits"] = int(entry.get("hits") or 0) + 1
            save_config()
            return


def add_word(raw_word: str) -> Tuple[bool, str]:
    word = (raw_word or "").strip()
    if not word:
        return False, "请输入违禁词"
    if len(word) > 50:
        return False, "违禁词长度不能超过 50 个字符"
    needle = _normalize_word(word)
    if not needle:
        return False, "违禁词不能全是空白字符"
    for entry in word_entries():
        if _normalize_word(str(entry.get("word") or "")) == needle:
            return False, "该违禁词已存在"
    word_entries().append({"word": word, "addedAt": time.time(), "hits": 0})
    save_config()
    return True, word


def remove_word(raw_word: str) -> Tuple[bool, str]:
    word = (raw_word or "").strip()
    entries = word_entries()
    for index, entry in enumerate(entries):
        if str(entry.get("word")) == word:
            entries.pop(index)
            save_config()
            return True, word
    return False, "词库中没有该词"


# ---------------------------------------------------------------- 首页房间列表


def room_list_enabled() -> bool:
    """首页是否展示公开房间列表（关闭后首页完全看不到该面板）。"""
    raw = _DATA.get("roomList") or {}
    value = raw.get("enabled", True)
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def set_room_list_enabled(enabled: bool) -> Tuple[bool, str]:
    state = "开启" if enabled else "关闭"
    _DATA.setdefault("roomList", {})["enabled"] = bool(enabled)
    if not save_config():
        # 内存里已生效，但写盘失败（只读目录 / 沙箱拦截原子替换），重启后会退回默认值
        return True, f"{state}（仅内存生效，写入 config.json 失败）"
    return True, state


# ---------------------------------------------------------------- 安全口令


def access_enabled() -> bool:
    """安全口令总开关：关闭时全站行为与没有该功能时完全一致。"""
    return bool((_DATA.get("access") or {}).get("enabled", False))


def access_exempt_loopback() -> bool:
    """回环地址是否豁免（决策 D6：默认豁免，防止管理员把自己锁在门外）。"""
    return bool((_DATA.get("access") or {}).get("exemptLoopback", True))


def access_tokens() -> List[dict]:
    return _DATA.setdefault("access", {}).setdefault("tokens", [])


def access_key_valid(raw: Optional[str], record: bool = False) -> bool:
    """校验一个口令串。

    空值 / 未收录 / 已过期一律无效；`record=True` 时累加一次命中并写盘
    （只在「用口令链接进站」时计，Cookie 续期不重复计）。
    """
    key = (raw or "").strip()
    if not key:
        return False
    now = time.time()
    for entry in access_tokens():
        token = str(entry.get("token") or "")
        if not token or not secrets.compare_digest(token, key):
            continue
        expires = entry.get("expiresAt")
        if expires is not None and float(expires) <= now:
            return False
        if record:
            entry["hits"] = int(entry.get("hits") or 0) + 1
            save_config()
        return True
    return False


def _mask_token(token: str) -> str:
    if len(token) <= 12:
        return token[:3] + "…" + token[-2:]
    return f"{token[:6]}…{token[-4:]}"


def access_snapshot() -> Dict[str, Any]:
    """管理后台展示用：口令一律脱敏，完整口令只在生成时返回一次。"""
    now = time.time()
    tokens: List[dict] = []
    for entry in access_tokens():
        expires = entry.get("expiresAt")
        tokens.append(
            {
                "id": str(entry.get("id") or ""),
                "masked": _mask_token(str(entry.get("token") or "")),
                "note": str(entry.get("note") or ""),
                "createdAt": float(entry.get("createdAt") or 0),
                "expiresAt": float(expires) if expires is not None else None,
                "hits": int(entry.get("hits") or 0),
                "expired": expires is not None and float(expires) <= now,
            }
        )
    tokens.sort(key=lambda t: t["createdAt"], reverse=True)
    return {
        "enabled": access_enabled(),
        "exemptLoopback": access_exempt_loopback(),
        "tokens": tokens,
    }


def set_access_enabled(enabled: bool) -> Tuple[bool, str]:
    state = "开启" if enabled else "关闭"
    _DATA.setdefault("access", {})["enabled"] = bool(enabled)
    if not save_config():
        return True, f"{state}（仅内存生效，写入 config.json 失败）"
    return True, state


def add_access_token(note: str = "", days: Optional[float] = None) -> Tuple[bool, dict]:
    """生成一条新口令（43 位 URL 安全随机串）；days 为空或 <=0 表示永不过期。"""
    now = time.time()
    expires: Optional[float] = None
    if days is not None and float(days) > 0:
        expires = now + float(days) * 86400
    entry = {
        "id": secrets.token_hex(6),
        "token": secrets.token_urlsafe(32),
        "note": (note or "").strip()[:60],
        "createdAt": now,
        "expiresAt": expires,
        "hits": 0,
    }
    access_tokens().append(entry)
    return save_config(), entry


def remove_access_token(token_id: str) -> Tuple[bool, str]:
    key = (token_id or "").strip()
    entries = access_tokens()
    for index, entry in enumerate(entries):
        if str(entry.get("id")) == key:
            entries.pop(index)
            save_config()
            return True, key
    return False, "没有找到该口令"


# 模块导入即加载一次配置；管理后台修改后由对应指令负责 save + 热生效
load_config()
