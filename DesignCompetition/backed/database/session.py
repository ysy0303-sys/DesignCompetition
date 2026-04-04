from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from backed.config.settings import settings

# 使用 settings.DATABASE_URL
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

# Session 本地实例
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base 类
Base = declarative_base()

# FastAPI 依赖注入
def get_db():
    """获取数据库 Session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
