import os
from typing import List, Optional
from pydantic_settings import BaseSettings
from dotenv import load_dotenv
from pathlib import Path

# 读取 .env 文件
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=True)
MAX_HISTORY_ROUNDS = 3
class Settings(BaseSettings):
    """全局配置类"""

    # ===== 环境 =====
    ENV: str = os.getenv("ENV", "local")  # "railway" 或 "local"

    # ===== 应用配置 =====
    APP_NAME: str = "学习规划后端"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = os.getenv("DEBUG", "True") == "True"

    # ===== CORS =====
    CORS_ORIGINS: List[str] = os.getenv("CORS_ORIGINS", "*").split(",")

    # ===== 数据库 =====
    DB_USER: str = os.getenv("DB_USER", "root")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")
    DB_NAME: str = os.getenv("DB_NAME", "education")
    DB_CHARSET: str = os.getenv("DB_CHARSET", "utf8mb4")

    @property
    def DB_HOST(self) -> str:
        """根据环境返回数据库 Host"""
        if self.ENV == "railway":
            return os.getenv("DB_HOST", "mysql.railway.internal")
        return os.getenv("DB_HOST", "junction.proxy.rlwy.net")

    @property
    def DB_PORT(self) -> int:
        """根据环境返回数据库端口"""
        if self.ENV == "railway":
            return int(os.getenv("DB_PORT", 3306))
        return int(os.getenv("DB_PORT", 57245))

    @property
    def DATABASE_URL(self) -> str:
        """生成 SQLAlchemy 数据库连接 URL"""
        return (
            f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/"
            f"{self.DB_NAME}?charset={self.DB_CHARSET}"
        )

    # ===== LLM配置 =====
    LLM_API_KEY: Optional[str] = os.getenv("LLM_API_KEY")
    LLM_BASE_URL: Optional[str] = os.getenv("LLM_BASE_URL")
    LLM_MODEL: Optional[str] = os.getenv("LLM_MODEL")
    LLM_TIMEOUT: int = int(os.getenv("LLM_TIMEOUT", 180))

    # ===== 任务配置 =====
    MAX_PLAN_DAYS: int = int(os.getenv("MAX_PLAN_DAYS", 730))
    DEFAULT_DAILY_HOURS: float = float(os.getenv("DEFAULT_DAILY_HOURS", 2.0))

    class Config:
        case_sensitive = True
        env_file = ".env"
        extra = "ignore"


# 全局配置实例
settings = Settings()
