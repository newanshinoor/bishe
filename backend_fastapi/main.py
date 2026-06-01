import os

# backend_fastapi/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# 导入拆分好的路由模块
from routers import user
from routers import commodity
from routers import dashboard
from routers import transaction
from routers import payment
from routers import video

# 1. 初始化 FastAPI 应用
app = FastAPI(title="智能无人果蔬售卖系统 API", version="2.0 (模块化重构)")

# 1.1 挂载静态资源目录，用于后台查看异常证据视频：
# alarm_log.shot_path 保存为 static/alarms/xxx.mp4，前端访问 http://localhost:8000/static/alarms/xxx.mp4。
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
os.makedirs(os.path.join(STATIC_DIR, "alarms"), exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# 2. 配置跨域 (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. 挂载路由 (将其他文件的接口注册到这里)
app.include_router(user.router)
app.include_router(commodity.router)
app.include_router(dashboard.router)
app.include_router(transaction.router)
app.include_router(payment.router)
app.include_router(video.router)

if __name__ == "__main__":
    import uvicorn
    # 运行服务
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
