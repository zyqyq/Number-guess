from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
import mimetypes

app = FastAPI(title="猜数字桌游", version="1.0.0")

# 获取当前文件所在目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
DIST_PATH = os.path.join(PROJECT_ROOT, "dist")

# 配置 MIME 类型
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

# 挂载静态资源
if os.path.exists(DIST_PATH):
    app.mount("/assets", StaticFiles(directory=os.path.join(DIST_PATH, "assets")), name="assets")
    
    @app.get("/")
    async def read_index():
        index_path = os.path.join(DIST_PATH, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return {"error": "前端未构建，请先运行 setup.sh"}
    
    # 处理 SPA 路由刷新问题
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
    """健康检查接口"""
    return {
        "status": "ok",
        "service": "guess-number-game",
        "version": "1.0.0"
    }

@app.get("/api/version")
async def get_version():
    """获取版本信息"""
    return {
        "backend": "FastAPI + Python",
        "frontend": "Vue 3 + TypeScript",
        "version": "1.0.0"
    }

if __name__ == "__main__":
    import uvicorn
    print("🚀 正在启动服务器...")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
