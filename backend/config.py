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
    """原子写回配置文件；失败时打印日志但不影响内存中的配置。"""
    tmp_path = f"{CONFIG_PATH}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as fh:
            json.dump(_DATA, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(tmp_path, CONFIG_PATH)
        return True
    except OSError as exc:
        print(f"[config] 写入 {CONFIG_PATH} 失败：{exc}")
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
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


# 模块导入即加载一次配置；管理后台修改后由对应指令负责 save + 热生效
load_config()
