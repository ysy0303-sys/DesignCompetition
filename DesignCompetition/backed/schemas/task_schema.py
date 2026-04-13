# backend/schemas/task_schema.py
from datetime import date, datetime
from typing import List, Literal, Optional, Dict, Any
from pydantic import BaseModel, Field, model_validator, field_serializer, field_validator, ConfigDict
import enum
# ===================== 基础通用模型 =====================
class TaskPriorityEnum(enum.Enum):
    HIGH = "高"
    MID = "中"
    LOW = "低"

class ChecklistItem(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    estimated_hours: float = Field(..., ge=0.1, le=4)
    estimated_duration: str = Field(..., min_length=1, max_length=20)

class TaskSchema(BaseModel):
    date: date
    title: str
    description: str
    estimated_hours: float = Field(..., ge=0.5, le=12)
    estimated_duration: str = Field(default="", min_length=0, max_length=20)
    planned_duration_minutes: int = Field(default=0, ge=0, le=720)
    priority: TaskPriorityEnum
    depends_on: List[str] = Field(default_factory=list)
    checklist: List[ChecklistItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def _fill_planned_minutes(self) -> "TaskSchema":
        if self.planned_duration_minutes <= 0:
            self.planned_duration_minutes = max(int(round(self.estimated_hours * 60)), 1)
        return self

    @field_serializer("checklist", when_used="json")
    def _serialize_checklist(self, checklist: List[ChecklistItem]) -> List[str]:
        return [item.title for item in checklist]

    @field_validator("checklist", mode="before")
    @classmethod
    def _coerce_checklist(cls, value):
        if value is None:
            return []
        if not isinstance(value, list):
            return []

        normalized = []
        for item in value:
            if isinstance(item, ChecklistItem):
                normalized.append(item)
                continue
            if isinstance(item, str):
                text = item.strip() or "子任务"
                normalized.append(
                    {
                        "title": text,
                        "estimated_hours": 0.5,
                        "estimated_duration": _format_duration_text(0.5),
                    }
                )
                continue
            if isinstance(item, dict):
                title = str(item.get("title", "")).strip() or "子任务"
                raw_hours = item.get("estimated_hours", 0.5)
                try:
                    hours = float(raw_hours)
                except (TypeError, ValueError):
                    hours = 0.5
                if hours < 0.1:
                    hours = 0.1
                if hours > 4:
                    hours = 4
                normalized.append(
                    {
                        "title": title,
                        "estimated_hours": round(hours, 2),
                        "estimated_duration": str(item.get("estimated_duration", "")).strip() or _format_duration_text(
                            hours),
                    }
                )
        return normalized




# ===================== 计划请求/响应模型 =====================
class PlanRequest(BaseModel):
    goal: str = Field(..., min_length=1, max_length=500)
    start_date: str | None = None
    end_date: str | None = None

class PlanModelResponse(BaseModel):
    goal_summary: str
    deadline: date
    tasks: List[TaskSchema]
    #新增
    goal_id:str|None=None

class SessionCreateResponse(BaseModel):
    goal_id:str #目标
    goal_summary: str
    start_date: date
    deadline: date
    years: List[int]

# 新增
class PlancreateResponse(BaseModel):
    code: int
    msg: str
    data: Optional[SessionCreateResponse]

#新增查询目标
class TargetResponse(BaseModel):
    id: str
    goal: str
    start_date: date
    end_date: date

class ApiResponse(BaseModel):
    code: int
    msg: str
    data: Optional[List[TargetResponse]]
#-----------------

from pydantic import BaseModel
from typing import Optional, Any

# 统一的响应体格式
class ResponseModel(BaseModel):
    code: int
    msg: str
    data: Optional[Any] = None

#==== 首页每日任务 =======
class TaskDay(BaseModel):
    title: str
    description: str
    priority: TaskPriorityEnum
    model_config = ConfigDict(from_attributes=True)
# ===================== 日历统计模型 =====================
class MonthItem(BaseModel):
    month: int
    month_label: str
    day_count: int
    task_day_count: int

class YearMonthsResponse(BaseModel):
    plan_id: str
    year: int
    months: List[MonthItem]

class DayItem(BaseModel):
    day: int
    date: date
    has_task: bool
    task_count: int

class MonthDaysResponse(BaseModel):
    plan_id: str
    year: int
    month: int
    days: List[DayItem]

class DayDetailResponse(BaseModel):
    plan_id: str
    date: date
    task_count: int
    tasks: List[TaskDay]
    model_config = ConfigDict(from_attributes=True)
# ===================== 任务计时模型 =====================
class TaskTimerToggleRequest(BaseModel):
    plan_id: str = Field(..., min_length=1)
    year: int = Field(..., ge=2000, le=2100)
    month: int = Field(..., ge=1, le=12)
    day: int = Field(..., ge=1, le=31)
    task_title: str = Field(..., min_length=1, max_length=200)
    focus_score: float | None = Field(default=None, ge=0, le=100)
    brain_power_score: float | None = Field(default=None, ge=0, le=100)
    brain_load: float | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="before")
    @classmethod
    def _compat_brain_score(cls, value: dict):
        if not isinstance(value, dict):
            return value
        if value.get("brain_power_score") is None and value.get("brain_load") is not None:
            value["brain_power_score"] = value.get("brain_load")
        return value

class TaskTimerSubmitRequest(BaseModel):
    duration: int   # 秒
    focus_score: float
    brain_power_score: float

class TaskTimerToggleResponse(BaseModel):
    plan_id: str
    date: date
    task_title: str
    is_running: bool
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_seconds: int = 0
    duration_text: str = "0秒"
    planned_duration_minutes: int = 0
    actual_duration_minutes: float = 0
    focus_score: float | None = None
    brain_power_score: float | None = None
    time_score: float | None = None
    gpa_score: float | None = None
    checkin_valid: bool | None = None
    cognitive_state: str | None = None
    suggestion: str | None = None

class TaskTimerClearRequest(BaseModel):
    plan_id: str = Field(..., min_length=1)

class TaskTimerClearResponse(BaseModel):
    plan_id: str
    cleared_count: int
    message: str

#==== 首页每日任务 =======
class TaskDay(BaseModel):
    title: str
    description: str
    priority: TaskPriorityEnum
    
#================== 首页目标完成度 ===============
class GoalTaskProgress(BaseModel):
    goal_title: str
    completion_percentage: int

class UserGoalsProgressResponse(BaseModel):
    goals: List[GoalTaskProgress]
    overall_completion_rate:int

#============== 首页GPA展示 ===========

class TaskGPAItem(BaseModel):
    plan_id: str
    title: str
    gpa_score: Optional[float] = None  # 没打卡就为 None

#================= 学习时长 ================
class TimePoint(BaseModel):
    date: str
    duration: int  # 单位：分钟

class StudyTimeResponse(BaseModel):
    total_duration: float
    
#===================== 完成度图 ==========
class TaskDailyGPAInfo(BaseModel):
    title: str
    gpa: Optional[float] = None   # 任务未打卡可为空
    # status: str

class GoalDailyProgress(BaseModel):
    goal_id: str
    goal_content: str
    tasks: List[TaskDailyGPAInfo]

# ===================== GPA计算模型 =====================
class GPATrendPoint(BaseModel):
    date: date
    gpa_score: float
    valid_count: int

class GPACalculateRequest(BaseModel):
    plan_id: str = Field(..., min_length=1)
    min_finished_count: int = Field(default=1, ge=1, le=1000)

class GPACalculateResponse(BaseModel):
    plan_id: str
    finished_count: int
    valid_finished_count: int
    invalid_finished_count: int
    average_focus_score: float
    average_brain_power_score: float
    average_time_score: float
    estimated_total_minutes: float
    actual_total_minutes: float
    time_efficiency_ratio: float
    gpa_score: float

class GPAWeekTrendResponse(BaseModel):
    plan_id: str
    week_start: date
    week_end: date
    points: List[GPATrendPoint]

# ===================== 任务完成状态模型 =====================
class TaskCompletionDayResponse(BaseModel):
    plan_id: str
    date: date
    total_task_count: int
    completed_task_count: int
    completion_rate: float
    updated_at: datetime | None = None

class TaskCompletionToggleRequest(BaseModel):
    plan_id: str = Field(..., min_length=1)
    year: int = Field(..., ge=2000, le=2100)
    month: int = Field(..., ge=1, le=12)
    day: int = Field(..., ge=1, le=31)
    task_title: str = Field(..., min_length=1, max_length=200)
    completed: bool | None = None

class TaskCompletionToggleResponse(BaseModel):
    plan_id: str
    date: date
    task_title: str
    completed: bool
    daily_completion:float
    # daily_completion: TaskCompletionDayResponse

class TaskCompletionWeekItem(BaseModel):
    date: date
    total_task_count: int
    completed_task_count: int
    completion_rate: float

class TaskCompletionWeekResponse(BaseModel):
    plan_id: str
    week_start: date
    week_end: date
    points: List[TaskCompletionWeekItem]

class TaskCompletionMonthItem(BaseModel):
    date: date
    total_task_count: int
    completed_task_count: int
    completion_rate: float

class TaskCompletionMonthResponse(BaseModel):
    plan_id: str
    year: int
    month: int
    points: List[TaskCompletionMonthItem]

# ===================== 每日建议/周报模型 =====================
class DailySuggestionRequest(BaseModel):
    plan_id: str = Field(..., min_length=1)
    year: int = Field(..., ge=2000, le=2100)
    month: int = Field(..., ge=1, le=12)
    day: int = Field(..., ge=1, le=31)

class DailySuggestionResponse(BaseModel):
    plan_id: str
    date: date
    suggestion: str
    daily_gpa: float | None = None

class WeeklyCheckResponse(BaseModel):
    plan_id: str
    needs_weekly_report: bool
    days_since_last_report: int
    current_plan_version: int

class WeeklyReport(BaseModel):
    week_id: str
    plan_id: str
    week_start: date
    week_end: date
    average_gpa: float
    completed_tasks_count: int
    total_focus_time: float
    report_content: str
    plan_version: int
    created_at: datetime

class WeeklyReportRequest(BaseModel):
    plan_id: str = Field(..., min_length=1)

class WeeklyReportResponse(BaseModel):
    week_id: str
    plan_id: str
    week_start: date
    week_end: date
    average_gpa: float
    completed_tasks_count: int
    total_focus_time: float
    report_content: str
    plan_version: int
    created_at: datetime
    gpa_points: List[GPATrendPoint]
    plan_updated: bool = False

#=========== 推荐 ============
class ReResponse(BaseModel):
    code: int = 200               # 状态码，例如 200 成功，404 未找到
    msg: str = "成功"              # 返回信息
    data: Optional[Any] = None

class ResourceType(str, enum.Enum):
    WEBPAGE = "webpage"
    VIDEO = "video"
    COURSE = "course"
    ARTICLE = "article"


class ResourceCategory(str, enum.Enum):
    LEARNING = "learning"
    PRACTICE = "practice"
    REVIEW = "review"
    STRATEGY = "strategy"


class LearningResource(BaseModel):
    id: str
    title: str
    description: str
    url: str
    resource_type: ResourceType
    category: ResourceCategory
    source: str
    publish_date: str
    difficulty: str = "medium"
    duration_minutes: int = 0
    tags: List[str] = []
    view_count: int = 0
    rating: float = 0.0

class RecommendationResponse(BaseModel):
    plan_id: str
    goal_category: str
    current_phase: str
    generated_at: datetime
    recommendations: List[LearningResource]
    total_count: int

# ===================== 工具函数（依赖） =====================
def _format_duration_text(hours: float) -> str:
    total_minutes = int(round(hours * 60))
    whole_hours, minutes = divmod(total_minutes, 60)
    if whole_hours and minutes:
        return f"{whole_hours}小时{minutes}分钟"
    if whole_hours:
        return f"{whole_hours}小时"
    return f"{minutes}分钟"
