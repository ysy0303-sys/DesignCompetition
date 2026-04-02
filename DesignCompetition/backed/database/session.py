# backed/database/session.py
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

from backed.config.settings import settings

# 创建数据库引擎
engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True, pool_recycle=3600)
# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
# 基础模型类
Base = declarative_base()

def get_db() -> Session:
    """
    数据库会话依赖（供FastAPI路由使用）
    自动创建会话，请求结束后关闭
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()