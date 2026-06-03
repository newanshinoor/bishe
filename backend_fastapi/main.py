import os

# backend_fastapi/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles


def _load_env_file() -> None:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(base_dir)
    for env_path in (os.path.join(project_root, ".env"), os.path.join(base_dir, ".env")):
        if not os.path.exists(env_path):
            continue
        with open(env_path, "r", encoding="utf-8") as env_file:
            for raw_line in env_file:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file()

# 导入拆分好的路由模块
from routers import user
from routers import commodity
from routers import dashboard
from routers import transaction
from routers import payment
from routers import sales_history
from routers import video
from routers import admin_config
from routers import admin_transactions
from routers import admin_blacklist
from core.database import engine
from core.inventory_schema import ensure_inventory_schema
from core.sales_history import ensure_sales_history_schema, sync_existing_transaction_sales_history
from core.system_config import ensure_system_config
from core.transaction_schema import ensure_transaction_schema
from core.customer_risk import ensure_customer_schema

# 1. 初始化 FastAPI 应用
app = FastAPI(title="智能无人果蔬售卖系统 API", version="2.0 (模块化重构)")

# 1.1 挂载静态资源目录，用于后台查看异常证据视频：
# alarm_log.shot_path 保存为 static/alarms/xxx.mp4，前端访问 http://localhost:8000/static/alarms/xxx.mp4。
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
os.makedirs(os.path.join(STATIC_DIR, "alarms"), exist_ok=True)
os.makedirs(os.path.join(STATIC_DIR, "order_videos"), exist_ok=True)
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
app.include_router(sales_history.router)
app.include_router(video.router)
app.include_router(admin_config.router)
app.include_router(admin_transactions.router)
app.include_router(admin_blacklist.router)


@app.on_event("startup")
def initialize_system_config():
    """启动时创建 system_config 表和默认配置记录。"""
    ensure_system_config()
    ensure_inventory_schema()
    transaction.TransactionDB.__table__.create(bind=engine, checkfirst=True)
    ensure_transaction_schema()
    ensure_customer_schema()
    ensure_sales_history_schema()
    sync_existing_transaction_sales_history()

if __name__ == "__main__":
    import uvicorn
    # 运行服务
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
