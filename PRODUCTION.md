# 生产模式启动说明

项目已改为「根目录即应用目录」结构，Python 虚拟环境随项目内置在 `venv/`（Python 3.13.12，已安装 FastAPI / Uvicorn / WebSocket 依赖），无需外部环境。

## 一条指令启动前后端（HTTPS）

语音通话要求浏览器处于安全上下文（HTTPS / localhost），因此生产模式默认启用本地自签证书：

```bash
# 一次性生成证书（已生成过可跳过；本机 IP 变化后重新执行一次）
cd /Users/zyqyq/Program/Number-guess && ./scripts/gen-cert.sh

# 启动（改过前端源码才需要先 npm run build）
cd /Users/zyqyq/Program/Number-guess && ./venv/bin/python -m uvicorn backend.main:app \
  --host 0.0.0.0 --port 8000 \
  --ssl-certfile certs/server.crt --ssl-keyfile certs/server.key
```

`--host 0.0.0.0` 表示监听全部网卡，同网段其他设备可直接访问；前端构建产物 `dist/` 由后端同进程托管，因此**不需要**另开 Vite 或 Node 进程。不带证书参数启动也能跑（纯 HTTP），但浏览器会禁用语音通话，仅保留文字聊天。

## 前置条件

| 场景 | 操作 |
| --- | --- |
| 首次启动 / 依赖变更 | `cd /Users/zyqyq/Program/Number-guess && ./venv/bin/pip install -r backend/requirements.txt` |
| 修改过前端源码 | `cd /Users/zyqyq/Program/Number-guess && npm run build`（生成 `dist/`） |
| 生成 / 更新 HTTPS 证书 | `cd /Users/zyqyq/Program/Number-guess && ./scripts/gen-cert.sh` |
| venv 损坏需重建 | `cd /Users/zyqyq/Program/Number-guess && rm -rf venv && python3 -m venv venv && ./venv/bin/pip install -r backend/requirements.txt` |

## 访问地址

| 设备位置 | 地址 |
| --- | --- |
| 本机 | https://localhost:8000 |
| 共享 LAN 192.168.2.0/24 | https://192.168.2.1:8000 |
| 上游路由器网段 | https://192.168.2.2:8000 |

自签证书不被浏览器默认信任：每台设备首次访问提示「不安全」时选择「高级 → 继续访问」即可，只需确认一次。证书 SAN 覆盖 `localhost`、`127.0.0.1`、`::1` 与生成时本机的所有 IPv4（含常见内网地址），有效期 825 天；`certs/` 已 gitignore。

## 管理后台（默认仅本机）

```bash
open https://localhost:8000/admin     # 只有服务器本机能打开（localOnly=true 时）
```

也可以用游戏首页进入：昵称填管理昵称、房间号填管理房间号，点「加入房间」。

- 管理页面、`/api/admin/*`、`/ws/admin` 三处默认只接受回环地址（127.0.0.1 / ::1）。局域网设备访问会得到 **403**，管理 WebSocket 握手直接失败。
- **口令与开关由 `config.json` 决定**（项目根目录，模板 `config.example.json`，gitignore）：
  ```json
  {
    "admin": { "username": "adminzyq", "room": "6666", "localOnly": true },
    "security": { "ipBlacklist": [], "bannedWords": [] }
  }
  ```
  改完在管理后台「安全设置 → 重载配置」热生效；环境变量 `ADMIN_USERNAME` / `ADMIN_ROOM` / `ADMIN_LOCAL_ONLY` 优先级更高：
  ```bash
  ADMIN_USERNAME=adminzyq ADMIN_ROOM=6666 ADMIN_LOCAL_ONLY=true ./venv/bin/python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
  ```
- `localOnly` 设为 `false` 后任何来源都可访问管理后台，仅剩口令防护，请谨慎关闭。
- **IP 黑名单**：`security.ipBlacklist` 支持单 IP 与 CIDR 网段，命中即拒绝一切连入（游戏 / presence / 管理），也可在「安全设置」页在线增删，写回 `config.json`。
- **违禁词库**：`security.bannedWords` 同时拦截昵称与文字聊天内容（归一化匹配，挡拆写变体），支持在「安全设置」页在线维护。
- 若以后加了 Nginx / Caddy 反向代理，所有请求的来源都会变成代理自身（多为 127.0.0.1），本机限制会失效，需要在代理层再做一层内网 ACL；IP 黑名单同理。

## 停止服务

```bash
lsof -ti :8000 | xargs kill
```

## 备注

- 旧的独立环境路径 `~/.workbuddy/binaries/python/envs/number-guess` 已迁移进项目 `venv/`，旧命令作废。
- 房间、牌局与聊天记录全部保存在内存，进程重启会清空所有房间。
- macOS 防火墙需放行 Python 入站（系统已将该解释器加入允许列表）。
- 开发模式（`./start.sh` + `npm run dev`）检测到证书时同样以 HTTPS 启动 Vite，并把 `/api`、`/ws` 代理到 8000，页面与后端协议不一致的问题不存在。
