from datetime import date, datetime
from sqlalchemy.orm import Session
from backed.database.models import Goal, Task
from backed.schemas.task_schema import PlanRequest
import enum


class GoalTypeEnum(enum.Enum):
    """目标类型枚举"""
    LEARNING = "学习目标"
    SCORE = "分数目标"
    TASK = "任务目标"
    OTHER = "其他目标"
# 目标表CRUD
def create_goal(db: Session, user_id: int, req: PlanRequest, goal_id: str ):
    """创建目标（对接前端目标创建）"""
    try:
        start_date = (
            req.start_date if isinstance(req.start_date, date)
            else datetime.fromisoformat(req.start_date).date()
        )
        end_date = (
            req.end_date if isinstance(req.end_date, date)
            else datetime.fromisoformat(req.end_date).date()
        )
        db_goal = Goal(
            user_id=user_id,
            goal_id=goal_id,
            goal_type=GoalTypeEnum.LEARNING,  # 根据实际枚举值调整
            content=req.goal,
            start_date=start_date,
            end_date=end_date,
            progress=0.0,
            plan_version="V1",
            create_time=datetime.now()
        )

        db.add(db_goal)

        db.flush()  # 强制执行 SQL
        print("✅ db_goal inserted:", db_goal)
        db.commit()  # ⚠️ commit
        return db_goal

    except Exception as e:
        print("❌ create_goal failed:", e)
        db.rollback()
        raise



def get_goal_by_id(db: Session, goal_id: int):
    return db.query(Goal).filter(Goal.id == goal_id).first()

def get_goals_by_user(db: Session, user_id: int, skip: int = 0, limit: int = 100):
    return db.query(Goal).filter(Goal.user_id == user_id).offset(skip).limit(limit).all()

# 任务表CRUD
def create_task(db: Session, task_data: dict):
    """创建任务（关联目标）"""
    db_task = Task(
        user_id=task_data["user_id"],
        plan_id=task_data.get("plan_id"),
        title=task_data["title"],
        description=task_data.get("description", ""),
        category=task_data.get("category", "学习"),
        task_date=task_data["task_date"],
        start_time=task_data.get("start_time"),
        end_time=task_data.get("end_time"),
        status="TODO",  # 对应 TaskStatusEnum
        priority="MID", # 对应 TaskPriorityEnum
        plan_version=task_data.get("plan_version", "V1"),
        planned_duration_minutes=task_data["planned_duration_minutes"],
        actual_duration_minutes=task_data.get("actual_duration_minutes", 0),
        depends_on=task_data.get("depends_on", ""),
        gpa=task_data.get("gpa", 0.0),
        task_type=task_data.get("task_type", "STUDY")
    )
    db.add(db_task)
    # db.commit()
    db.refresh(db_task)
    return db_task

def get_tasks_by_goal(db: Session, goal_id: int):
    return db.query(Task).filter(Task.plan_id == goal_id).all()