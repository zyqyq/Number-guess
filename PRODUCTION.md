# 生产模式启动说明

项目已改为「根目录即应用目录」结构，Python 虚拟环境随项目内置在 `venv/`（Python 3.13.12，已安装 FastAPI / Uvicorn / WebSocket 依赖），无需外部环境。

## 一条指令启动前后端

```bash
cd /Users/zyqyq/Program/Number-guess && ./venv/bin/python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

`--host 0.0.0.0` 表示监听全部网卡，同网段其他设备可直接访问；前端构建产物 `dist/` 由后端同进程托管，因此**不需要**另开 Vite 或 Node 进程。

## 前置条件

| 场景 | 操作 |
| --- | --- |
| 首次启动 / 依赖变更 | `cd /Users/zyqyq/Program/Number-guess && ./venv/bin/pip install -r backend/requirements.txt` |
| 修改过前端源码 | `cd /Users/zyqyq/Program/Number-guess && npm run build`（生成 `dist/`） |
| venv 损坏需重建 | `cd /Users/zyqyq/Program/Number-guess && rm -rf venv && python3 -m venv venv && ./venv/bin/pip install -r backend/requirements.txt` |

## 访问地址

| 设备位置 | 地址 |
| --- | --- |
| 本机 | http://localhost:8000 |
| 共享 LAN 192.168.2.0/24 | http://192.168.2.1:8000 |
| 上游路由器网段 | http://192.168.2.2:8000 |

## 停止服务

```bash
lsof -ti :8000 | xargs kill
```

## 备注

- 旧的独立环境路径 `~/.workbuddy/binaries/python/envs/number-guess` 已迁移进项目 `venv/`，旧命令作废。
- 房间与牌局状态全部保存在内存，进程重启会清空所有房间。
- macOS 防火墙需放行 Python 入站（系统已将该解释器加入允许列表）。
