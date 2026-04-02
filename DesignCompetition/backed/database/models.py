import enum
from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Enum, ForeignKey, Index,
    Boolean, Date, Text, Double,JSON
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

from sqlalchemy.sql import desc
'''
留一套核心模型，删除冗余的 XXXNew/XXXDB 重复定义；
字段名对齐业务代码（如 planned_duration_minutes、brain_power_score）；
所有表通过 user_id/plan_id 关联，形成完整业务链路；
兼容你原有数据库表结构，仅补充必要字段，不破坏历史数据。
'''
# 基础模型类（全局唯一）
Base = declarative_base()

# ========== 枚举类型定义（统一业务状态） ==========
class CourseTypeEnum(enum.Enum):
    """课程类型枚举"""
    COMPULSORY = "必修"
    ELECTIVE = "选修"
    PUBLIC = "公共课"

class TaskStatusEnum(enum.Enum):
    """任务状态枚举（对齐业务代码）"""
    TODO = "未完成"
    DOING = "进行中"
    DONE = "已完成"
    CANCELLED = "已取消"

class TaskPriorityEnum(enum.Enum):
    """任务优先级枚举"""
    LOW = "低"
    MID = "中"
    HIGH = "高"

class GoalTypeEnum(enum.Enum):
    """目标类型枚举"""
    LEARNING = "学习目标"
    SCORE = "分数目标"
    TASK = "任务目标"
    OTHER = "其他目标"

class SuggestionTypeEnum(enum.Enum):
    """建议类型枚举"""
    DAILY = "每日建议"
    WEEKLY = "周报建议"
    SYSTEM = "系统建议"

# ========== 核心业务模型（无冗余，统一一套） ==========
class User(Base):
    __tablename__ = "user"  # 复用原有user表，删除UserNew
    id = Column(Integer, primary_key=True, autoincrement=True, comment="用户ID")
    username = Column(String(50), unique=True, nullable=False, comment="用户名")
    password = Column(String(100), nullable=False, comment="密码（建议加密存储）")
    major = Column(String(100), comment="专业")
    grade = Column(String(20), comment="年级")
    create_time = Column(DateTime, default=datetime.now, comment="创建时间")

    # 关联关系（覆盖所有业务）
    goals = relationship("Goal", back_populates="user", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="user", cascade="all, delete-orphan")
    task_states = relationship("TaskState", back_populates="user", cascade="all, delete-orphan")
    suggestions = relationship("Suggestion", back_populates="user", cascade="all, delete-orphan")
    study_records = relationship("StudyRecord", back_populates="user", cascade="all, delete-orphan")

    # 索引：提升用户名查询效率
    __table_args__ = (Index("idx_user_username", "username"),)

class StudyRecord(Base):
    __tablename__ = "study_record"  # 复用原有表
    id = Column(Integer, primary_key=True, autoincrement=True, comment="学习记录ID")
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, comment="关联用户ID")
    semester = Column(String(20), comment="学期（如2024-2025-1）")
    course_name = Column(String(100), nullable=False, comment="课程名")
    credit = Column(Float, comment="学分")
    score = Column(Float, comment="分数")
    course_type = Column(Enum(CourseTypeEnum), comment="课程类型")
    create_time = Column(DateTime, default=datetime.now, comment="创建时间")

    # 关联关系
    user = relationship("User", back_populates="study_records")

    # 索引
    __table_args__ = (Index("idx_studyrecord_user_semester", "user_id", "semester"),)

class Goal(Base):
    __tablename__ = "goal"  # 复用原有goal表，补充字段
    id = Column(Integer, primary_key=True, autoincrement=True, comment="目标ID")
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, comment="关联用户ID")
    goal_id = Column(String(32), nullable=True, comment="任务凭证ID，用于任务关联")
    goal_type = Column(Enum(GoalTypeEnum, values_callable=lambda obj: [e.value for e in obj]), comment="目标类型")
    content = Column(String(500), nullable=False, comment="目标内容")
    start_date = Column(Date, comment="开始日期（替换原有start_time，对齐代码）")
    end_date = Column(Date, comment="结束日期（替换原有end_time）")
    progress = Column(Float, default=0.0, comment="进度（0-100）")
    plan_version = Column(String(20), default="V1", comment="计划版本（新增）")
    create_time = Column(DateTime, default=datetime.now, comment="创建时间")

    # 关联关系
    user = relationship("User", back_populates="goals")

    # 索引
    __table_args__ = (Index("idx_goal_user_type", "user_id", "goal_type"),)


class Task(Base):
    __tablename__ = "task"
    id = Column(Integer, primary_key=True, autoincrement=True, comment="任务ID")
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, comment="关联用户ID")
    plan_id = Column(String(50), nullable=False)
    goal_id = Column(String, index=True)
    title = Column(String(200), nullable=False, comment="任务标题")
    description = Column(Text, comment="任务描述")
    category = Column(String(50), comment="任务分类")
    task_date = Column(Date, comment="任务所属日期")
    start_time = Column(DateTime, comment="任务开始时间")
    end_time = Column(DateTime, comment="任务结束时间")
    # status = Column(Enum(TaskStatusEnum), default=TaskStatusEnum.TODO.value, comment="任务状态")
    status = Column(
        Enum(
            TaskStatusEnum,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],  # 用中文
            name="taskstatusenum"
        ),
        default=TaskStatusEnum.TODO.value,  # 默认值也是中文
        comment="任务状态",
        nullable=False
    )
    # priority = Column(Enum(TaskPriorityEnum), default=TaskPriorityEnum.MID.value, comment="优先级")
    priority = Column(
        Enum(
            TaskPriorityEnum,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
            name="taskpriorityenum"
        ),
        default=TaskPriorityEnum.MID.value,
        comment="任务优先级",
        nullable=False
    )
    plan_version = Column(String(20), default="V1", comment="计划版本")
    planned_duration_minutes = Column(Integer, comment="计划时长（分钟）")
    actual_duration_minutes = Column(Integer, comment="实际时长（分钟）")
    depends_on = Column(String(500), comment="依赖任务")
    gpa = Column(Float, default=0, comment="GPA分数")
    task_type = Column(String(50), comment="任务类型")

    # 关联关系
    user = relationship("User", back_populates="tasks")
    # task_states = relationship("TaskState", back_populates="task", cascade="all, delete-orphan")
    suggestions = relationship("Suggestion", back_populates="task", cascade="all, delete-orphan")

    # 索引
    __table_args__ = (
        Index("idx_task_user_status", "user_id", "status"),
        Index("idx_task_plan_date", "plan_id", "task_date"),
    )

class TaskState(Base):
    __tablename__ = "task_state"  # 复用原有表，补充字段
    id = Column(Integer, primary_key=True, autoincrement=True, comment="任务状态ID")
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, comment="关联用户ID")
    plan_id = Column(String(32), nullable=False, comment="任务凭证ID，与 Task.plan_id 对应")
    duration = Column(Integer, default=0, comment="任务持续时长（分钟）")
    focus_score = Column(Float, comment="专注度评分（0-100）")
    brain_power_score = Column(Float, comment="脑力分数（0-100，对齐代码）")
    time_score = Column(Float, comment="时长完成度分数（0-100，新增）")
    checkin_valid = Column(Boolean, default=True, comment="打卡是否有效（新增）")
    state_tag = Column(String(50), comment="状态标签（如专注/疲劳/分心）")
    task_date = Column(Date, nullable=False, comment="任务日期")
    create_time = Column(DateTime, default=datetime.now, comment="创建时间")

    # 关联关系
    user = relationship("User", back_populates="task_states")
    # task = relationship("Task", back_populates="task_states")

    # 修正索引语法（核心修复）
    __table_args__ = (
        Index("idx_taskstate_user_createtime", "user_id", "create_time", postgresql_using="btree"),
    )

class Suggestion(Base):
    __tablename__ = "suggestion"  # 复用原有表，补充字段
    id = Column(Integer, primary_key=True, autoincrement=True, comment="建议ID")
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, comment="关联用户ID")
    task_id = Column(Integer, ForeignKey("task.id"), nullable=True, comment="关联任务ID")
    # plan_id = Column(String(36), ForeignKey("study_plan.id"), nullable=True, comment="关联学习计划ID（新增）")
    plan_id = Column(String(32), nullable=False, comment="任务凭证ID，与 Task.plan_id 对应")
    content = Column(Text, nullable=False, comment="建议内容")
    type = Column(Enum(SuggestionTypeEnum), default=SuggestionTypeEnum.SYSTEM, comment="建议类型（新增）")
    # ✅ 新增（关键）
    week_start = Column(Date, nullable=True)
    week_end = Column(Date, nullable=True)

    # 👉 存结构化数据（GPA等）
    extra_data = Column(JSON, nullable=True)
    create_time = Column(DateTime, default=datetime.now, comment="创建时间")

    # 关联关系
    user = relationship("User", back_populates="suggestions")
    task = relationship("Task", back_populates="suggestions")







