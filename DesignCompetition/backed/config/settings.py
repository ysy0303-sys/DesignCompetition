# backed/config/settings.py
import os
from typing import List, Optional
from pydantic_settings import BaseSettings
from dotenv import load_dotenv
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # backed 上一级
load_dotenv(BASE_DIR / ".env", override=True)




# 记忆轮数（user+assistant算一轮）
MAX_HISTORY_ROUNDS = 3

class Settings(BaseSettings):
    """全局配置类"""

    # ===== 应用配置 =====
    APP_NAME: str = "学习规划后端"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = os.getenv("DEBUG", "True") == "True"

    # ===== CORS =====
    CORS_ORIGINS: List[str] = os.getenv("CORS_ORIGINS", "*").split(",")

    # ===== 数据库 =====
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: int = int(os.getenv("DB_PORT", 3306))
    DB_USER: str = os.getenv("DB_USER", "root")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")
    DB_NAME: str = os.getenv("DB_NAME", "education")
    DB_CHARSET: str = os.getenv("DB_CHARSET", "utf8mb4")

    # ===== ✅ LLM配置（关键修复点）=====
    LLM_API_KEY: Optional[str] = os.getenv("LLM_API_KEY")
    LLM_BASE_URL: Optional[str] = os.getenv("LLM_BASE_URL")
    LLM_MODEL: Optional[str] = os.getenv("LLM_MODEL")
    LLM_TIMEOUT: int = int(os.getenv("LLM_TIMEOUT", 180))

    # ===== 任务配置 =====
    MAX_PLAN_DAYS: int = int(os.getenv("MAX_PLAN_DAYS", 730))
    DEFAULT_DAILY_HOURS: float = float(os.getenv("DEFAULT_DAILY_HOURS", 2.0))

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/"
            f"{self.DB_NAME}?charset={self.DB_CHARSET}"
        )

    class Config:
        case_sensitive = True
        env_file = ".env"
        extra = 'ignore'


# 全局配置实例
settings = Settings()

# LLM通用系统提示（复用之前的逻辑）
UNIVERSAL_SYSTEM_PROMPT = (
    "你是全场景任务规划引擎，适配考公、考研、考编、职业资格、语言学习、技能提升、日常学习等所有目标。"
    "你必须仅输出可被 json.loads 直接解析的纯 JSON 字符串，不得输出 markdown、代码块、解释文本。"
    "输出结构必须为：{goal_summary, deadline, tasks[]}。"
    "你必须严格遵守："
    "1) 从 start_date 到 end_date 每一天都必须有任务，不能出现空白日、跳天、遗漏。"
    "2) 每个任务必须包含 date/title/description/estimated_hours/estimated_duration/planned_duration_minutes/priority/depends_on/checklist。"
    "3) 每个 checklist 子任务必须包含 title/estimated_hours/estimated_duration，且 estimated_hours 在 0.1~4。"
    "4) 顶层任务 estimated_hours 必须严格等于其 checklist 所有 estimated_hours 之和。"
    "5) 任务 date 必须严格等于所属当日，不得跨日期混排。"
    "6) estimated_duration 必须是中文时长，如 30分钟、2小时、2小时30分钟。"
    "7) 每天建议输出 2~4 个任务，每个任务 checklist 输出 3~5 个可执行子步骤，内容要具体、可落地。"
    "8) description 需要包含学习对象、完成量与预期产出，避免空泛表述。"
)