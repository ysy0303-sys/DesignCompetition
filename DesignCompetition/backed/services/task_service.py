# backend/services/task_service.py
import json
import os
import re
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from threading import Lock
from typing import List, Literal
from urllib import error, request
from uuid import uuid4
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_serializer, field_validator, model_validator
from sqlalchemy.orm import Session
from backed.database.session import get_db
from backed.crud.goal_crud import create_goal, create_task
from backed.config.settings import settings
from backed.database.models import TaskStatusEnum, TaskPriorityEnum
from datetime import date
from uuid import uuid4
from typing import List, Tuple
from threading import Lock
from backed.database.models import Task as TaskORM
from backed.schemas.task_schema import TaskSchema
from backed.database.models import TaskState
# 导入模型
from backed.schemas.task_schema import (
    PlanRequest, PlanModelResponse, ChecklistItem, WeeklyReport,
    GPATrendPoint, TaskCompletionDayResponse
)

# ===================== 环境配置 =====================
load_dotenv(override=True)

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


# ===================== 存储类（内存版，后续可替换为数据库） =====================
class SessionStore:
    def __init__(self):
        self._data: dict[str, dict] = {}
        self._lock = Lock()

# 创建任务
    def create(
        self,
        db: Session,
        user_id: int,
        goal_id:str,
        start_date: date,
        deadline: date,
        goal_summary: str,
        tasks: list
    ) -> tuple[str, list[int]]:


        # 按日期整理
        by_date = {}
        for task in sorted(tasks, key=lambda item: item.date):
            by_date.setdefault(task.date, []).append(task)

        years = (
            list(range(start_date.year, deadline.year + 1))
            if deadline >= start_date else [start_date.year]
        )

            # ===== 数据库写入 =====
        priority_map = {
                "高": TaskPriorityEnum.HIGH,
                "中": TaskPriorityEnum.MID,
                "低": TaskPriorityEnum.LOW,
        }

        db_tasks = []
        plan_ids=[]

        for t in tasks:
            task_plan_id = str(uuid4())  # ⭐ 每个任务唯一 plan_id
            plan_ids.append(task_plan_id)

            db_task = TaskORM(
                user_id=user_id,
                plan_id=task_plan_id,  # ✅ 任务ID
                goal_id=goal_id,  # ✅ 关联目标
                title=t.title,
                description=t.description,
                task_date=t.date,
                planned_duration_minutes=t.planned_duration_minutes,
                priority=priority_map.get(t.priority, TaskPriorityEnum.MID),
                status=TaskStatusEnum.TODO.value,
                depends_on=json.dumps(t.depends_on, ensure_ascii=False),
                category="study",
                plan_version="V1",
            )
            db_tasks.append(db_task)

        db.add_all(db_tasks)
        db.commit()

        return plan_ids, years

# 获取计划
    def get(self, plan_id: str) -> dict:
        with self._lock:
            item = self._data.get(plan_id)
        if not item:
            raise HTTPException(status_code=404, detail="计划不存在，请重新创建")
        return item
# 更新任务计划版本
    #更新任务
    #版本号+1
    #更新时间
    def update_plan_version(self, plan_id: str, new_tasks: List[TaskSchema]) -> int:
        with self._lock:
            item = self._data.get(plan_id)
            if not item:
                raise HTTPException(status_code=404, detail="计划不存在，请重新创建")

            by_date: dict[date, List[TaskSchema]] = {}
            for task in sorted(new_tasks, key=lambda x: x.date):
                by_date.setdefault(task.date, []).append(task)

            item["plan_version"] += 1
            item["tasks_by_date"] = by_date
            item["last_report_date"] = date.today()
            return item["plan_version"] #返回新版本号
# 更新  最后生成周报时间
    def update_last_report_date(self, plan_id: str) -> None:
        with self._lock:
            item = self._data.get(plan_id)
            if item:
                item["last_report_date"] = date.today()

# 任务计时系统
class TaskTimerStore:
    def __init__(self):
        self._active: dict[str, dict] = {}
        self._completed_seconds: dict[str, int] = {}
        self._task_records: List[dict] = []
        self._lock = Lock()
    # 开始计时
    def start(self, task_key: str, now: datetime) -> datetime:
        with self._lock:
            self._active[task_key] = {"started_at": now}
        return now
    # 停止计时，计算实际学习时间，返回(开始时间, 学习秒数)
    def stop(self, task_key: str, now: datetime) -> tuple[datetime | None, int]:
        with self._lock:
            active = self._active.pop(task_key, None)

        if not active:
            return None, 0

        started_at = active["started_at"]
        elapsed_seconds = max(int((now - started_at).total_seconds()), 0)
        with self._lock:
            self._completed_seconds[task_key] = self._completed_seconds.get(task_key, 0) + elapsed_seconds
        return started_at, elapsed_seconds
    # 获取任务开始时间
    def get_active_started_at(self, task_key: str) -> datetime | None:
        with self._lock:
            active = self._active.get(task_key)
            if not active:
                return None
            return active["started_at"]
    #清空某个计划的所有计时数据
    def clear_by_plan(self, plan_id: str) -> int:
        prefix = f"{plan_id}:"
        with self._lock:
            active_keys = [key for key in self._active if key.startswith(prefix)]
            completed_keys = [key for key in self._completed_seconds if key.startswith(prefix)]
            before_len = len(self._task_records)
            self._task_records = [item for item in self._task_records if
                                  not str(item.get("task_key", "")).startswith(prefix)]
            removed_records = before_len - len(self._task_records)

            for key in active_keys:
                self._active.pop(key, None)
            for key in completed_keys:
                self._completed_seconds.pop(key, None)

            return len(active_keys) + len(completed_keys) + removed_records
    # 获取任务历史记录
    def get_task_records_by_plan(self, plan_id: str) -> List[dict]:
        with self._lock:
            return [item for item in self._task_records if item.get("plan_id") == plan_id]
    #保存一次学习记录
    def add_task_record(self, record: dict) -> None:
        with self._lock:
            self._task_records.append(record)

#任务完成统计
class TaskCompletionStore:
    def __init__(self):
        self._completed_tasks: dict[str, bool] = {}
        self._daily_stats: dict[str, dict] = {}
        self._lock = Lock()
    # 判断任务是否完成
    def get_task_completed(self, task_key: str) -> bool:
        with self._lock:
            return self._completed_tasks.get(task_key, False)
    #设置任务完成状态
    def set_task_completed(self, task_key: str, completed: bool) -> None:
        with self._lock:
            self._completed_tasks[task_key] = completed
    #统计完成任务数量
    def get_completed_count(self, task_keys: List[str]) -> int:
        with self._lock:
            return sum(1 for key in task_keys if self._completed_tasks.get(key, False))
    #获取每日统计
    def get_daily_stat(self, daily_key: str) -> dict | None:
        with self._lock:
            return self._daily_stats.get(daily_key)
    #保存每日统计
    def save_daily_stat(self, daily_key: str, stat: dict) -> None:
        with self._lock:
            self._daily_stats[daily_key] = stat

# 用于保存周报
class WeeklyReportStore:
    def __init__(self):
        self._reports: dict[str, WeeklyReport] = {}
        self._lock = Lock()
    #保存周报
    def save(self, report: WeeklyReport) -> None:
        with self._lock:
            self._reports[report.week_id] = report
    #获得某计划的所有周报
    def get_by_plan(self, plan_id: str) -> List[WeeklyReport]:
        with self._lock:
            return [report for report in self._reports.values() if report.plan_id == plan_id]
    # 获得最新周报
    def get_latest(self, plan_id: str) -> WeeklyReport | None:
        reports = self.get_by_plan(plan_id)
        if not reports:
            return None
        return max(reports, key=lambda r: r.created_at)

# ===================== 全局实例化 =====================
# settings = Settings.from_env()
store = SessionStore()
timer_store = TaskTimerStore()
completion_store = TaskCompletionStore()
weekly_report_store = WeeklyReportStore()

# ===================== 核心业务函数 =====================

# 从 AI 返回文本中 提取 JSON
def _extract_json_text(text: str) -> str:
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if fenced:
        text = fenced.group(1).strip()

    if text.startswith("{") and text.endswith("}"):
        return text

    object_match = re.search(r"(\{[\s\S]*\})", text)
    if object_match:
        return object_match.group(1).strip()
    return text

#从 大模型 API 返回结果 中提取文本内容
def _extract_output_text(payload: dict) -> str:
    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    parts: List[str] = []
    for item in payload.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                parts.append(content["text"].strip())
    return "\n".join(p for p in parts if p)

#从 OpenAI格式的返回结果 提取 AI 回复文本
def _extract_chat_message_text(result: dict) -> str:
    try:
        choices = result.get("choices", [])
        if not choices or not isinstance(choices[0], dict):
            return ""
        message = choices[0].get("message", {})
        if not isinstance(message, dict):
            return ""
        content = message.get("content", "")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: List[str] = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str) and text.strip():
                        parts.append(text.strip())
                elif isinstance(item, str) and item.strip():
                    parts.append(item.strip())
            return "\n".join(parts)
    except Exception:
        return ""
    return ""

#把 小时数转换成中文时间
def _format_duration_text(hours: float) -> str:
    total_minutes = int(round(hours * 60))
    whole_hours, minutes = divmod(total_minutes, 60)
    if whole_hours and minutes:
        return f"{whole_hours}小时{minutes}分钟"
    if whole_hours:
        return f"{whole_hours}小时"
    return f"{minutes}分钟"
#把 秒数转换成中文时长
def _format_elapsed_seconds(seconds: int) -> str:
    safe_seconds = max(int(seconds), 0)
    hours, remain = divmod(safe_seconds, 3600)
    minutes, secs = divmod(remain, 60)

    parts: List[str] = []
    if hours > 0:
        parts.append(f"{hours}小时")
    if minutes > 0:
        parts.append(f"{minutes}分钟")
    if secs > 0 or not parts:
        parts.append(f"{secs}秒")
    return "".join(parts)

#任务计时系统
def _build_task_timer_key(plan_id: str, current: date, task_title: str) -> str:
    return f"{plan_id}:{current.isoformat()}:{task_title.strip()}"

#任务完成状态记录
def _build_task_completion_key(plan_id: str, current: date, task_title: str) -> str:
    return f"{plan_id}:{current.isoformat()}:{task_title.strip()}"

#每日统计
def _build_daily_completion_key(plan_id: str, current: date) -> str:
    return f"{plan_id}:{current.isoformat()}"

#每日任务完成率
def _compute_daily_completion(plan_id: str, current: date, tasks: List[TaskSchema]) -> TaskCompletionDayResponse:
    task_keys = [_build_task_completion_key(plan_id, current, task.title) for task in tasks]
    total_task_count = len(task_keys)
    completed_task_count = completion_store.get_completed_count(task_keys)
    completion_rate = round((completed_task_count / total_task_count) * 100, 2) if total_task_count > 0 else 0.0
    updated_at = datetime.now()

    daily = TaskCompletionDayResponse(
        plan_id=plan_id,
        date=current,
        total_task_count=total_task_count,
        completed_task_count=completed_task_count,
        completion_rate=completion_rate,
        updated_at=updated_at,
    )
    completion_store.save_daily_stat(_build_daily_completion_key(plan_id, current), daily.model_dump())
    return daily

#计算 每日学习GPA
def _compute_daily_gpa_from_records(records: List[dict], current: date) -> GPATrendPoint:
    day_records = [
        item
        for item in records
        if str(item.get("date", "")) == current.isoformat() and bool(item.get("checkin_valid", False))
    ]
    if not day_records:
        return GPATrendPoint(date=current, gpa_score=0, valid_count=0)

    avg_focus = round(sum(float(item["focus_score"]) for item in day_records) / len(day_records), 2)
    avg_time = round(sum(float(item["time_score"]) for item in day_records) / len(day_records), 2)
    avg_brain = round(sum(float(item["brain_power_score"]) for item in day_records) / len(day_records), 2)
    gpa_score = _calculate_gpa_score(avg_focus, avg_time, avg_brain)
    return GPATrendPoint(date=current, gpa_score=gpa_score, valid_count=len(day_records))

#计算 时间效率分
def _calculate_time_score(planned_duration_minutes: float, actual_duration_minutes: float) -> tuple[float, bool]:
    planned = max(float(planned_duration_minutes), 0.0)
    actual = max(float(actual_duration_minutes), 0.0)

    if planned <= 0 or actual <= 0:
        return 0.0, False

    if actual < planned * 0.1:
        return 0.0, False

    if actual <= planned:
        return 100.0, True

    return round((planned / actual) * 100, 2), True

#GPA计算公式
def _calculate_gpa_score(focus_score: float, time_score: float, brain_power_score: float) -> float:
    return round(focus_score * 0.5 + time_score * 0.3 + brain_power_score * 0.2, 2)

#根据 GPA 判断学习状态
def _build_gpa_state(gpa_score: float, checkin_valid: bool) -> tuple[str, str]:
    if not checkin_valid:
        return "无效打卡", "实际耗时过短，已触发防作弊规则，请按真实学习时长打卡。"
    if gpa_score >= 85:
        return "高效状态", "保持当前节奏，优先推进高价值任务。"
    if gpa_score >= 70:
        return "稳定状态", "继续保持，可适度缩短分心时间。"
    return "待提升", "建议降低任务粒度并安排固定休息节奏。"


def _is_valid_hours(hours: float, minimum: float, maximum: float) -> bool:
    return minimum <= hours <= maximum

#----------------------日历解析系统---------------
#生成start_date → end_date之间的 所有日期
def _generate_date_list(start_date: date, end_date: date) -> List[date]:
    dates: List[date] = []
    current = start_date
    while current <= end_date:
        dates.append(current)
        current = date.fromordinal(current.toordinal() + 1)
    return dates

#验证规划是否合法
def _validate_plan_dates(start_date: date, end_date: date) -> None:
    if end_date < start_date:
        raise HTTPException(status_code=400, detail="end_date 必须大于或等于 start_date")
    if (end_date.toordinal() - start_date.toordinal()) > 730:
        raise HTTPException(status_code=400, detail="规划区间过长，请控制在 730 天内")

#从用户目标中解析日期
def _extract_date_range_from_goal(goal: str) -> tuple[date, date] | None:
    text = goal.strip()

    patterns = [
        r"(?P<y1>\d{4})[-年/.](?P<m1>\d{1,2})[-月/.](?P<d1>\d{1,2})日?\s*(?:到|至|~|～|-|—)\s*(?:(?P<y2>\d{4})[-年/.])?(?P<m2>\d{1,2})[-月/.](?P<d2>\d{1,2})日?",
        r"从\s*(?P<y1>\d{4})[-年/.](?P<m1>\d{1,2})[-月/.](?P<d1>\d{1,2})日?\s*(?:开始)?\s*(?:到|至|~|～|-|—)\s*(?:(?P<y2>\d{4})[-年/.])?(?P<m2>\d{1,2})[-月/.](?P<d2>\d{1,2})日?",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        try:
            year_1 = int(match.group("y1"))
            month_1 = int(match.group("m1"))
            day_1 = int(match.group("d1"))

            year_2_text = match.group("y2")
            year_2 = int(year_2_text) if year_2_text else year_1
            month_2 = int(match.group("m2"))
            day_2 = int(match.group("d2"))

            start_date = date(year_1, month_1, day_1)
            end_date = date(year_2, month_2, day_2)
            return start_date, end_date
        except Exception:
            continue

    return None

#提取文本中 所有日期
def _extract_all_dates_from_goal(goal: str) -> List[date]:
    text = goal.strip()
    matches = re.finditer(r"(?P<y>\d{4})[-年/.](?P<m>\d{1,2})[-月/.](?P<d>\d{1,2})日?", text)
    result: List[date] = []
    for match in matches:
        try:
            result.append(date(int(match.group("y")), int(match.group("m")), int(match.group("d"))))
        except Exception:
            continue
    return result

#最终解析日期逻辑
from datetime import date, datetime
from typing import Tuple, Optional, List
from fastapi import HTTPException


def _to_date(d) -> date:
    if isinstance(d, date):
        return d
    if isinstance(d, str):
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y年%m月%d日"):
            try:
                return datetime.strptime(d, fmt).date()
            except ValueError:
                continue
    raise ValueError(f"无法解析日期: {d}")


def _resolve_dates_from_goal(
    goal: str,
    fallback_start: date | None = None,
    fallback_end: date | None = None
) -> Tuple[date, date]:

    direct = _extract_date_range_from_goal(goal)
    if direct:
        start, end = direct
        return _to_date(start), _to_date(end)   # ✅ 强制统一

    all_dates = _extract_all_dates_from_goal(goal)
    if len(all_dates) >= 2:
        return _to_date(all_dates[0]), _to_date(all_dates[1])

    if len(all_dates) == 1:
        start = date.today()
        end = _to_date(all_dates[0])

        if end < start:
            start = end

        return start, end

    if fallback_start and fallback_end:
        return _to_date(fallback_start), _to_date(fallback_end)

    raise HTTPException(
        status_code=400,
        detail="无法从 goal 中识别日期，请在目标描述中至少包含一个明确日期"
    )

#任务修复系统
#修复 任务子步骤
def _normalize_checklist(task: TaskSchema) -> List[ChecklistItem]:
    checklist = task.checklist
    if not checklist:
        half = max(round(task.estimated_hours / 2, 2), 0.1)
        remain = round(task.estimated_hours - half, 2)
        if remain < 0.1:
            remain = 0.1
        return [
            ChecklistItem(title="学习核心知识点", estimated_hours=half, estimated_duration=_format_duration_text(half)),
            ChecklistItem(title="完成练习并复盘", estimated_hours=remain, estimated_duration=_format_duration_text(remain)),
        ]

    fixed: List[ChecklistItem] = []
    for item in checklist:
        hours = round(float(item.estimated_hours), 2)
        if not _is_valid_hours(hours, 0.1, 4):
            hours = min(max(hours, 0.1), 4)
        fixed.append(
            ChecklistItem(
                title=item.title.strip() or "子任务",
                estimated_hours=hours,
                estimated_duration=item.estimated_duration.strip() or _format_duration_text(hours),
            )
        )
    return fixed

#保证任务时间 = checklist时间总和
def _align_task_hours_with_checklist(task: TaskSchema) -> TaskSchema:
    checklist = _normalize_checklist(task)
    checklist_total = round(sum(item.estimated_hours for item in checklist), 2)

    if checklist_total <= 0:
        checklist_total = max(task.estimated_hours, 0.5)

    return task.model_copy(
        update={
            "estimated_hours": checklist_total,
            "estimated_duration": task.estimated_duration.strip() or _format_duration_text(checklist_total),
            "planned_duration_minutes": max(task.planned_duration_minutes, int(round(checklist_total * 60))),
            "checklist": checklist,
        }
    )

#确保任务日期 = 指定日期
def _normalize_task_date(task: TaskSchema, target_date: date) -> TaskSchema:
    return task.model_copy(update={"date": target_date})

#---------------Fallback自动任务系统-------------
#识别学习类型
def _detect_scenario(goal: str) -> str:
    lower_goal = goal.lower()
    if "考研" in goal:
        return "考研"
    if "考公" in goal or "公务员" in goal:
        return "考公"
    if "考编" in goal or "事业编" in goal:
        return "考编"
    if "资格" in goal or "证" in goal:
        return "资格考试"
    if "english" in lower_goal or "英语" in goal:
        return "语言学习"
    return "通用"

#根据进度判断阶段
def _phase_label(day_index: int, total_days: int) -> str:
    if total_days <= 1:
        return "冲刺"
    progress = day_index / max(total_days - 1, 1)
    if progress < 0.35:
        return "基础"
    if progress < 0.7:
        return "强化"
    if progress < 0.9:
        return "冲刺"
    return "复盘"

#生成 单个任务
def _build_fallback_task(goal: str, current: date, day_index: int, total_days: int, slot: int) -> TaskSchema:
    goal_hint = goal.strip()[:24] if goal.strip() else "学习计划"
    scenario = _detect_scenario(goal)
    phase = _phase_label(day_index, total_days)

    if scenario == "考研":
        focus_list = ["数学", "英语", "专业课"]
    elif scenario == "考公":
        focus_list = ["行测数量", "行测言语", "申论写作"]
    elif scenario == "考编":
        focus_list = ["教育综合", "学科知识", "教案表达"]
    elif scenario == "资格考试":
        focus_list = ["核心知识", "法规规范", "案例分析"]
    elif scenario == "语言学习":
        focus_list = ["词汇语法", "阅读理解", "听说表达"]
    else:
        focus_list = ["核心知识", "题目训练", "总结复盘"]

    focus = focus_list[(day_index + slot) % len(focus_list)]

    if slot == 0:
        checklist = [
            ChecklistItem(title=f"{focus}重点知识梳理", estimated_hours=0.6, estimated_duration="36分钟"),
            ChecklistItem(title=f"{focus}典型题训练与订正", estimated_hours=0.9, estimated_duration="54分钟"),
            ChecklistItem(title=f"{focus}错因归类与笔记沉淀", estimated_hours=0.5, estimated_duration="30分钟"),
        ]
        title = f"{goal_hint}{phase}阶段-{focus}主线推进"
        description = f"围绕{focus}完成知识梳理、训练和订正，输出结构化笔记与错题归因。"
        priority = "高"
        depends_on: List[str] = []
    else:
        checklist = [
            ChecklistItem(title=f"{focus}限时练习与节奏控制", estimated_hours=0.6, estimated_duration="36分钟"),
            ChecklistItem(title="整理高频失分点并二次练习", estimated_hours=0.8, estimated_duration="48分钟"),
            ChecklistItem(title="复盘当天任务并安排次日预习", estimated_hours=0.6, estimated_duration="36分钟"),
        ]
        title = f"{goal_hint}{phase}阶段-{focus}巩固提升"
        description = "通过限时训练和复盘闭环提升稳定性，形成次日可执行的改进清单。"
        priority = "中"
        depends_on = [f"{goal_hint}{phase}阶段-{focus}主线推进"]

    return TaskSchema(
        date=current,
        title=title,
        description=description,
        estimated_hours=2.0,
        estimated_duration="2小时",
        planned_duration_minutes=120,
        priority=priority,
        depends_on=depends_on,
        checklist=checklist,
    )

#生成一天2个任务
def _build_fallback_day_tasks(goal: str, current: date, day_index: int, total_days: int) -> List[TaskSchema]:
    first = _build_fallback_task(goal, current, day_index, total_days, slot=0)
    second = _build_fallback_task(goal, current, day_index, total_days, slot=1)
    second = second.model_copy(update={"depends_on": [first.title]})
    return [first, second]

#生成完整学习计划
def _build_fallback_plan(goal: str, start_date: date, end_date: date) -> PlanModelResponse:
    tasks: List[TaskSchema] = []
    date_list = _generate_date_list(start_date, end_date)
    total_days = len(date_list)
    for day_index, current in enumerate(date_list):
        tasks.extend(_build_fallback_day_tasks(goal, current, day_index, total_days))
    return PlanModelResponse(goal_summary=goal.strip() or "学习计划", deadline=end_date, tasks=tasks)

#---------------任务修复系统核心----------------------
#作用：保证每一天都有任务
def _normalize_and_fill_tasks(goal: str, tasks: List[TaskSchema], start_date: date, end_date: date) -> List[TaskSchema]:
    expected_dates = _generate_date_list(start_date, end_date)
    total_days = len(expected_dates)
    raw_by_date: dict[date, List[TaskSchema]] = {}
    for task in tasks:
        if task.date < start_date or task.date > end_date:
            continue
        aligned = _align_task_hours_with_checklist(task)
        aligned = _normalize_task_date(aligned, task.date)
        raw_by_date.setdefault(task.date, []).append(aligned)

    normalized: List[TaskSchema] = []
    for day_index, current in enumerate(expected_dates):
        day_tasks = raw_by_date.get(current, [])
        if not day_tasks:
            day_tasks = _build_fallback_day_tasks(goal, current, day_index, total_days)
        if len(day_tasks) < 2:
            extra = _build_fallback_task(goal, current, day_index, total_days, slot=1)
            extra = extra.model_copy(
                update={
                    "title": f"{extra.title}（补全）",
                    "priority": "高",
                    "depends_on": [day_tasks[0].title] if day_tasks else [],
                }
            )
            day_tasks.append(extra)
        for task in day_tasks:
            normalized.append(_normalize_task_date(_align_task_hours_with_checklist(task), current))

    return sorted(normalized, key=lambda item: (item.date, item.priority.value, item.title))

#----------------AI任务生成核心-----------------
#整个系统 最核心函数。作用：调用AI生成学习计划
def _call_model(
        goal: str,
        start_date: str,
        end_date: str,
        user_id: int,  # 1. 新增：必传参数，关联用户
        db: Session  # 2. 新增：外部传入数据库会话（避免重复创建）
) -> PlanModelResponse:
    if not settings.LLM_API_KEY or not settings.LLM_MODEL:
        raise HTTPException(status_code=400, detail="未配置 ARK_API_KEY 或 ARK_MODEL")

    schema = {
        "goal_summary": "string",
        "deadline": end_date.isoformat(),
        "tasks": [
            {
                "date": "YYYY-MM-DD",
                "title": "string",
                "description": "string",
                "estimated_hours": 2.5,
                "estimated_duration": "2小时30分钟",
                "planned_duration_minutes": 150,
                "priority": "高|中|低",
                "depends_on": ["string"],
                "checklist": [
                    {
                        "title": "string",
                        "estimated_hours": 0.5,
                        "estimated_duration": "30分钟",
                    }
                ],
            }
        ],
    }

    payload = {
        "model": settings.LLM_MODEL,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": UNIVERSAL_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "goal": goal,
                        "start_date": start_date.isoformat(),
                        "end_date": end_date.isoformat(),
                        "output_schema": schema,
                        "constraints": [
                            "必须覆盖 start_date 到 end_date 每一天",
                            "任务与子任务时长必须一致",
                            "每个任务必须返回 planned_duration_minutes（整数分钟）",
                            "子任务时长范围 0.1~4 小时",
                            "返回必须为纯 JSON 字符串",
                        ],
                    },
                    ensure_ascii=False,
                ),
            },
        ],
    }

    req = request.Request(
        url=f"{settings.LLM_BASE_URL}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {settings.LLM_API_KEY}", "Content-Type": "application/json"},
        method="POST",
    )

    last_error: Exception | None = None
    for _ in range(2):
        try:
            with request.urlopen(req, timeout=settings.LLM_TIMEOUT) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                break
        except error.HTTPError as exc:
            last_error = exc
        except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
    else:
        plan = _build_fallback_plan(goal, start_date, end_date)
        normalized_tasks = _normalize_and_fill_tasks(goal, plan.tasks, start_date, end_date)
        return plan.model_copy(update={"deadline": end_date, "tasks": normalized_tasks})

    text = _extract_chat_message_text(result)
    if not text:
        text = _extract_output_text(result)
    if not text:
        plan = _build_fallback_plan(goal, start_date, end_date)
        normalized_tasks = _normalize_and_fill_tasks(goal, plan.tasks, start_date, end_date)
        return plan.model_copy(update={"deadline": end_date, "tasks": normalized_tasks})

    try:
        parsed = json.loads(_extract_json_text(text))
        plan = PlanModelResponse.model_validate(parsed)
    except Exception:
        plan = _build_fallback_plan(goal, start_date, end_date)

    if not plan.tasks:
        plan = _build_fallback_plan(goal, start_date, end_date)

    normalized_tasks = _normalize_and_fill_tasks(goal, plan.tasks, start_date, end_date)
    plan = plan.model_copy(update={"deadline": end_date, "tasks": normalized_tasks})
    # 在 try 前
    print("👉 准备执行 create_goal")


    # 改造：使用外部传入的db会话（不再手动创建）
    try:
        # 创建目标（关联当前用户ID）
        plan_req = PlanRequest(
            goal=goal,
            start_date=str(start_date),
            end_date=str(end_date)
        )
        db_goal = create_goal(db, user_id=user_id, req=plan_req, goal_id=str(uuid4().hex))

        # 批量创建任务（关联用户ID和计划ID）
        for task in plan.tasks:
            task_data = {
                "user_id": user_id,
                "plan_id":str(uuid4()),
                "goal_id": db_goal.goal_id,
                "title": task.title,
                "description": task.description,
                "task_date": task.date,
                "planned_duration_minutes": task.planned_duration_minutes,
                "start_time": datetime.datetime.combine(task.date, datetime.time.min),
                "end_time": datetime.datetime.combine(task.date, datetime.time.max),
            }
            create_task(db, task_data)
        db.commit()
    except Exception as e:
        # 异常时回滚事务
        db.rollback()
        raise HTTPException(status_code=500, detail=f"保存计划失败：{str(e)}")

    return plan

# 2. 替换内存存储为数据库查询（示例：修改 get_day_detail 依赖的逻辑）
def get_day_detail_from_db(db: Session, user_id: str, current: date):
    """从数据库获取每日任务"""
    tasks = db.query(TaskORM).filter(
        TaskORM.user_id == user_id,
        TaskORM.task_date == current
    ).all()

    # 转换为 Schema 格式
    schema_tasks = []
    for task in tasks:
        schema_tasks.append(TaskSchema(
            title=task.title,
            description=task.description,
            priority=task.priority.value
           
        ))
    return schema_tasks
#----------周报系统---------------
#判断是否需要生成周报。规则：7天生成一次
def _check_weekly_trigger(plan_id: str, current_date: date) -> tuple[bool, int]:
    session = store.get(plan_id)
    cycle_start = session.get("cycle_start_date")
    last_report = session.get("last_report_date")
    reference_date = last_report if last_report else cycle_start

    if not reference_date:
        return False, 0

    days_since = (current_date - reference_date).days
    return days_since >= 7, days_since

#根据 GPA 给每日建议
def _generate_daily_suggestion(daily_gpa: float | None, records: List[dict]) -> str:
    if daily_gpa is None:
        return "今日暂无学习记录，开始你的学习之旅吧！"

    if daily_gpa >= 85:
        return "太棒了！你今天的状态非常好，继续保持这个高效的学习节奏。"
    elif daily_gpa >= 70:
        return "今天表现不错，状态稳定。建议明天可以适当挑战一下更高难度的任务。"
    elif daily_gpa >= 60:
        return "今天的学习状态还有提升空间。建议明天调整学习时间，保证充足的休息。"
    else:
        return "今天的学习效果不太理想，不要灰心！建议明天从简单的任务开始，逐步找回状态。"

#分析一周学习数据。输出：平均GPA，学习时间，完成任务数，GPA趋势，任务统计
def _analyze_weekly_data(records: List[dict], week_start: date, week_end: date) -> tuple[float, int, float, List[GPATrendPoint], dict]:
    week_records = []
    for item in records:
        try:
            item_date = date.fromisoformat(str(item.get("date")))
            if week_start <= item_date <= week_end:
                week_records.append(item)
        except:
            continue

    if not week_records:
        return 0.0, 0, 0.0, [], {}

    avg_focus = round(sum(float(r["focus_score"]) for r in week_records if r.get("checkin_valid")) / max(1, len([r for r in week_records if r.get("checkin_valid")])), 2)
    avg_time = round(sum(float(r["time_score"]) for r in week_records if r.get("checkin_valid")) / max(1, len([r for r in week_records if r.get("checkin_valid")])), 2)
    avg_brain = round(sum(float(r["brain_power_score"]) for r in week_records if r.get("checkin_valid")) / max(1, len([r for r in week_records if r.get("checkin_valid")])), 2)
    avg_gpa = _calculate_gpa_score(avg_focus, avg_time, avg_brain)

    total_focus_time = round(sum(float(r.get("actual_duration_minutes", 0)) for r in week_records), 2)
    completed_count = len([r for r in week_records if r.get("checkin_valid")])

    gpa_points = []
    for offset in range(7):
        current = week_start + timedelta(days=offset)
        gpa_points.append(_compute_daily_gpa_from_records(records, current))

    task_type_stats = {}
    for r in week_records:
        title = str(r.get("task_title", ""))
        if title not in task_type_stats:
            task_type_stats[title] = {"count": 0, "gpa_sum": 0.0, "low_gpa_days": 0}
        task_type_stats[title]["count"] += 1
        task_type_stats[title]["gpa_sum"] += float(r.get("gpa_score", 0))
        if float(r.get("gpa_score", 100)) < 60:
            task_type_stats[title]["low_gpa_days"] += 1

    return avg_gpa, completed_count, total_focus_time, gpa_points, task_type_stats

#检测异常
def _check_alert_conditions(task_type_stats: dict) -> tuple[bool, List[str]]:
    alerts = []
    has_alert = False

    for task_title, stats in task_type_stats.items():
        if stats["low_gpa_days"] >= 3:
            has_alert = True
            avg_gpa = round(stats["gpa_sum"] / max(1, stats["count"]), 1)
            alerts.append(f"「{task_title}」本周出现了{stats['low_gpa_days']}次低效执行（平均分{avg_gpa}/100）")

    return has_alert, alerts

#生成完整周报文本
def _generate_weekly_report_content(avg_gpa: float, completed_count: int, total_focus_time: float, alerts: List[str], task_type_stats: dict) -> str:
    report_lines = []
    report_lines.append("📊 本周学习报告")
    report_lines.append("=" * 40)
    if avg_gpa >= 80:
        report_lines.append("🌟 优秀！本周整体表现非常出色！")
    elif avg_gpa >= 60:
        report_lines.append("👍 良好！本周有稳定的学习节奏")
    else:
        report_lines.append("💪 加油！需要调整学习策略")

    report_lines.append("")
    report_lines.append(f"📈 平均GPA: {avg_gpa}/100")
    report_lines.append(f"✅ 完成任务数: {completed_count}")
    report_lines.append(f"⏱️ 总学习时长: {total_focus_time}分钟")
    if alerts:
        report_lines.append("")
        report_lines.append("⚠️ 预警提示:")
        for alert in alerts:
            report_lines.append(f"  - {alert}")

    report_lines.append("")
    report_lines.append("💡 建议:")

    if alerts:
        report_lines.append("  针对预警任务，建议:")
        report_lines.append("  1. 减少单次任务时长，拆分成更小的模块")
        report_lines.append("  2. 调整任务安排时间，选择精力更充沛的时段")
        report_lines.append("  3. 增加中间休息，保持学习状态")
    else:
        report_lines.append("  保持当前的学习节奏，继续加油！")
        report_lines.append("  可以适度挑战更高难度的内容。")

    return "\n".join(report_lines)

#AI自动调整计划。当周报发现问题时：重新生成学习计划
def _generate_adjusted_plan(plan_id: str, alerts: List[str], week_end: date) -> List[TaskSchema]:
    session = store.get(plan_id)
    original_goal = session.get("original_goal", session.get("goal_summary", ""))
    deadline = session["deadline"]

    start_date = week_end + timedelta(days=1)

    if start_date > deadline:
        start_date = deadline

    try:
        plan = _call_model(settings, original_goal, start_date, deadline)
        normalized_tasks = _normalize_and_fill_tasks(original_goal, plan.tasks, start_date, deadline)
        return normalized_tasks
    except:
        return _build_fallback_plan(original_goal, start_date, deadline).tasks


#================== 建议 =============
def check_weekly_trigger_task(db, plan_id: str, current_date: date):
    """用 task 表判断是否需要生成周报"""
    last_report = db.query(WeeklyReport)\
                    .filter(WeeklyReport.plan_id == plan_id)\
                    .order_by(WeeklyReport.week_end.desc())\
                    .first()
    if last_report:
        reference_date = last_report.week_end
    else:
        # 没有周报时，取该计划最早任务日期
        first_task = db.query(TaskORM).filter(TaskORM.plan_id == plan_id).order_by(TaskORM.task_date.asc()).first()
        if not first_task:
            return False, 0
        reference_date = first_task.task_date

    days_since = (current_date - reference_date).days
    return days_since >= 7, days_since


def auto_generate_weekly_reports_task(db: Session):
    today = date.today()

    # 获取所有 plan_id
    plan_ids = [row[0] for row in db.query(TaskORM.plan_id).distinct().all()]

    for plan_id in plan_ids:
        needs_report, _ = check_weekly_trigger_task(db, plan_id, today)
        if not needs_report:
            continue

        week_end = today
        week_start = week_end - timedelta(days=6)

        # 获取本周任务状态
        records = db.query(TaskState).filter(
            TaskState.plan_id == plan_id,
            TaskState.task_date >= week_start,
            TaskState.task_date <= week_end
        ).all()

        # 调用你的分析函数
        avg_gpa, completed_count, total_focus_time, gpa_points, task_type_stats = \
            _analyze_weekly_data(records, week_start, week_end)
        has_alert, alerts = _check_alert_conditions(task_type_stats)
        report_content = _generate_weekly_report_content(
            avg_gpa, completed_count, total_focus_time, alerts, task_type_stats
        )

        # 生成唯一 week_id
        week_id = f"{plan_id}_{week_start}_{week_end}"

        # 幂等性：已经存在就跳过
        exist = db.query(WeeklyReport).filter(WeeklyReport.week_id == week_id).first()
        if exist:
            continue

        # 保存周报
        # 用 plan_version 取该计划最新任务版本
        latest_task = db.query(TaskORM).filter(TaskORM.plan_id == plan_id).order_by(TaskORM.plan_version.desc()).first()
        plan_version = latest_task.plan_version if latest_task else "V1"

        report = WeeklyReport(
            week_id=week_id,
            plan_id=plan_id,
            week_start=week_start,
            week_end=week_end,
            average_gpa=avg_gpa,
            completed_tasks_count=completed_count,
            total_focus_time=total_focus_time,
            report_content=report_content,
            plan_version=plan_version,
            created_at=datetime.now()
        )
        db.add(report)
        db.commit()

from apscheduler.schedulers.background import BackgroundScheduler


scheduler = BackgroundScheduler()
scheduler.start()

def scheduler_job():
    db = Session()
    try:
        auto_generate_weekly_reports_task(db)
    finally:
        db.close()

scheduler.add_job(
    scheduler_job,
    "cron",
    hour=0,
    minute=0
)


#============= 推荐 =================
# class ResourceStore:
#     def __init__(self):
#         self._resources: Dict[str, List[LearningResource]] = {}
#         self._lock = Lock()
#
#     #添加资源
#     def add_resource(self, category: str, resource: "LearningResource") -> None:
#         with self._lock:
#             if category not in self._resources:
#                 self._resources[category] = []
#             self._resources[category].append(resource)
#     #获取资源
#     def get_resources_by_category(self, category: str) -> List[LearningResource]:
#         with self._lock:
#             return self._resources.get(category, []).copy()
#
#     #搜索资源
#     def search_resources(self, category: str, keywords: List[str], phase: str, max_count: int) -> List[
#         LearningResource]:
#         with self._lock:
#             all_resources = self._resources.get(category, [])
#             if not all_resources:
#                 return []
#
#             filtered = []
#             for resource in all_resources:
#                 match = True
#                 if keywords:
#                     keyword_match = any(
#                         keyword.lower() in resource.title.lower() or
#                         keyword.lower() in resource.description.lower() or
#                         keyword.lower() in [tag.lower() for tag in resource.tags]
#                         for keyword in keywords
#                     )
#                     if not keyword_match:
#                         match = False
#
#                 if match:
#                     filtered.append(resource)
#
#             filtered.sort(key=lambda x: (-x.rating, -x.view_count))
#             return filtered[:max_count]
#
# #初始化数据
# def _init_sample_resources(store: ResourceStore) -> None:
#     sample_data = {
#         "考研": [
#             LearningResource(
#                 id="kaoyan_1",
#                 title="考研数学基础班 - 高等数学",
#                 description="名师讲解考研数学高等数学基础知识点，适合基础阶段学习",
#                 url="https://www.bilibili.com/video/BV1xx411c7mD",
#                 resource_type=ResourceType.VIDEO,
#                 category=ResourceCategory.LEARNING,
#                 source="B站",
#                 publish_date="2025-01-15",
#                 difficulty="medium",
#                 duration_minutes=180,
#                 tags=["数学", "高等数学", "基础班"],
#                 view_count=150000,
#                 rating=4.8
#             ),
#             LearningResource(
#                 id="kaoyan_2",
#                 title="考研英语词汇速记方法",
#                 description="高效记忆考研核心词汇的方法和技巧",
#                 url="https://www.zhihu.com/question/22887420",
#                 resource_type=ResourceType.ARTICLE,
#                 category=ResourceCategory.LEARNING,
#                 source="知乎",
#                 publish_date="2025-02-01",
#                 difficulty="easy",
#                 duration_minutes=30,
#                 tags=["英语", "词汇", "记忆方法"],
#                 view_count=89000,
#                 rating=4.6
#             ),
#             LearningResource(
#                 id="kaoyan_3",
#                 title="考研政治冲刺押题班",
#                 description="考研政治最后冲刺阶段的押题课程",
#                 url="https://www.bilibili.com/video/BV1xx411c7mE",
#                 resource_type=ResourceType.VIDEO,
#                 category=ResourceCategory.REVIEW,
#                 source="B站",
#                 publish_date="2025-11-01",
#                 difficulty="hard",
#                 duration_minutes=240,
#                 tags=["政治", "冲刺", "押题"],
#                 view_count=200000,
#                 rating=4.9
#             ),
#         ],
#         "考公": [
#             LearningResource(
#                 id="gongwu_1",
#                 title="行测数量关系解题技巧",
#                 description="公务员考试行测数量关系部分的快速解题方法",
#                 url="https://www.bilibili.com/video/BV1xx411c7mF",
#                 resource_type=ResourceType.VIDEO,
#                 category=ResourceCategory.LEARNING,
#                 source="B站",
#                 publish_date="2025-01-20",
#                 difficulty="medium",
#                 duration_minutes=150,
#                 tags=["行测", "数量关系", "解题技巧"],
#                 view_count=120000,
#                 rating=4.7
#             ),
#             LearningResource(
#                 id="gongwu_2",
#                 title="申论写作高分模板",
#                 description="公务员考试申论写作的高分模板和范例",
#                 url="https://www.zhihu.com/question/22887421",
#                 resource_type=ResourceType.ARTICLE,
#                 category=ResourceCategory.REVIEW,
#                 source="知乎",
#                 publish_date="2025-02-10",
#                 difficulty="medium",
#                 duration_minutes=45,
#                 tags=["申论", "写作", "模板"],
#                 view_count=95000,
#                 rating=4.5
#             ),
#             LearningResource(
#                 id="gongwu_3",
#                 title="历年国考真题解析",
#                 description="历年国家公务员考试真题详细解析",
#                 url="https://www.bilibili.com/video/BV1xx411c7mG",
#                 resource_type=ResourceType.VIDEO,
#                 category=ResourceCategory.PRACTICE,
#                 source="B站",
#                 publish_date="2025-03-01",
#                 difficulty="hard",
#                 duration_minutes=300,
#                 tags=["真题", "国考", "解析"],
#                 view_count=180000,
#                 rating=4.8
#             ),
#         ],
#         "考编": [
#             LearningResource(
#                 id="kaobian_1",
#                 title="教育综合知识精讲",
#                 description="教师编制考试教育综合知识系统精讲",
#                 url="https://www.bilibili.com/video/BV1xx411c7mH",
#                 resource_type=ResourceType.VIDEO,
#                 category=ResourceCategory.LEARNING,
#                 source="B站",
#                 publish_date="2025-01-25",
#                 difficulty="medium",
#                 duration_minutes=200,
#                 tags=["教育综合", "教师编", "精讲"],
#                 view_count=110000,
#                 rating=4.6
#             ),
#             LearningResource(
#                 id="kaobian_2",
#                 title="学科知识备考指南",
#                 description="各学科教师编制考试的备考策略和方法",
#                 url="https://www.zhihu.com/question/22887422",
#                 resource_type=ResourceType.ARTICLE,
#                 category=ResourceCategory.STRATEGY,
#                 source="知乎",
#                 publish_date="2025-02-15",
#                 difficulty="easy",
#                 duration_minutes=25,
#                 tags=["学科知识", "备考", "策略"],
#                 view_count=75000,
#                 rating=4.4
#             ),
#         ],
#         "资格考试": [
#             LearningResource(
#                 id="zige_1",
#                 title="注册会计师会计科目精讲",
#                 description="CPA考试会计科目的系统讲解",
#                 url="https://www.bilibili.com/video/BV1xx411c7mI",
#                 resource_type=ResourceType.VIDEO,
#                 category=ResourceCategory.LEARNING,
#                 source="B站",
#                 publish_date="2025-02-01",
#                 difficulty="hard",
#                 duration_minutes=360,
#                 tags=["CPA", "会计", "注会"],
#                 view_count=90000,
#                 rating=4.7
#             ),
#             LearningResource(
#                 id="zige_2",
#                 title="法律职业资格考试备考攻略",
#                 description="法考备考的完整攻略和时间规划",
#                 url="https://www.zhihu.com/question/22887423",
#                 resource_type=ResourceType.ARTICLE,
#                 category=ResourceCategory.STRATEGY,
#                 source="知乎",
#                 publish_date="2025-03-01",
#                 difficulty="medium",
#                 duration_minutes=40,
#                 tags=["法考", "备考", "攻略"],
#                 view_count=80000,
#                 rating=4.5
#             ),
#         ],
#         "语言学习": [
#             LearningResource(
#                 id="yuyan_1",
#                 title="雅思听力高频词汇",
#                 description="雅思听力考试中出现频率最高的词汇汇总",
#                 url="https://www.bilibili.com/video/BV1xx411c7mJ",
#                 resource_type=ResourceType.VIDEO,
#                 category=ResourceCategory.LEARNING,
#                 source="B站",
#                 publish_date="2025-01-10",
#                 difficulty="easy",
#                 duration_minutes=120,
#                 tags=["雅思", "听力", "词汇"],
#                 view_count=130000,
#                 rating=4.6
#             ),
#             LearningResource(
#                 id="yuyan_2",
#                 title="托福写作模板与范例",
#                 description="托福写作的高分模板和优秀范文",
#                 url="https://www.zhihu.com/question/22887424",
#                 resource_type=ResourceType.ARTICLE,
#                 category=ResourceCategory.REVIEW,
#                 source="知乎",
#                 publish_date="2025-02-20",
#                 difficulty="medium",
#                 duration_minutes=35,
#                 tags=["托福", "写作", "范文"],
#                 view_count=70000,
#                 rating=4.4
#             ),
#         ],
#     }
#
#     for category, resources in sample_data.items():
#         for resource in resources:
#             store.add_resource(category, resource)
