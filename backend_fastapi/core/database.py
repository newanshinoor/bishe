# backend_fastapi/core/database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# 统一管理数据库连接字符串
DB_URL = "mysql+pymysql://root:123456@localhost:3306/fruit_shop"

# 创建全局的引擎实例
engine = create_engine(DB_URL)

# 创建会话工厂，用于后续的数据操作
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 创建声明性基类，所有数据库模型都要继承它
Base = declarative_base()

# 获取数据库会话的依赖函数 (供 FastAPI 路由使用)
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()