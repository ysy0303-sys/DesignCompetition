# backend/api/task_routes.py
from datetime import date, datetime, timedelta
from typing import List
from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware  # 全局中间件移到main.py，这里不用
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from calendar import monthrange
from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from backed.database.models import User,Goal,TaskState,Suggestion
from backed.database.session import get_db
from backed.core.auth import get_current_user_id  # Token解析工具
from sqlalchemy import func
from backed.database.models import Task,TaskStatusEnum,GoalTypeEnum,TaskPriorityEnum
from uuid import uuid4
from sqlalchemy.orm import Session
import calendar
from datetime import datetime
from enum import Enum
from typing import List
from fastapi import FastAPI, APIRouter, HTTPException
from pydantic import BaseModel, Field

# 导入项目内部模块（根据你的项目结构调整导入路径）
from backed.schemas.task_schema import (
    PlanRequest, SessionCreateResponse, YearMonthsResponse, MonthDaysResponse,
    DayDetailResponse, TaskTimerToggleRequest, TaskTimerToggleResponse,
    TaskTimerClearRequest, TaskTimerClearResponse, GPACalculateRequest,TimePoint,StudyTimeResponse,
    GPACalculateResponse, GPAWeekTrendResponse, TaskCompletionToggleRequest,UserGoalsProgressResponse,
    TaskCompletionToggleResponse, TaskCompletionDayResponse,TaskDailyGPAInfo,GoalTaskProgress,ReResponse,
    TaskCompletionWeekResponse, TaskCompletionMonthResponse,TaskTimerSubmitRequest,GoalDailyProgress,
    DailySuggestionRequest, DailySuggestionResponse, WeeklyCheckResponse,
    WeeklyReportRequest, WeeklyReportResponse, WeeklyReport,PlancreateResponse,ApiResponse,TargetResponse,
    GPATrendPoint, TaskCompletionWeekItem, TaskCompletionMonthItem,MonthItem,DayItem,TaskGPAItem,
)
from backed.services.task_service import (
    settings, store, timer_store, completion_store, weekly_report_store,
    _resolve_dates_from_goal, _validate_plan_dates, _call_model,
    _build_task_timer_key, _calculate_time_score, _calculate_gpa_score,
    _build_gpa_state, _compute_daily_gpa_from_records, _build_task_completion_key,
    _compute_daily_completion, _generate_daily_suggestion, _check_weekly_trigger,
    _analyze_weekly_data, _check_alert_conditions, _generate_weekly_report_content,get_day_detail_from_db,
    _generate_adjusted_plan, _format_elapsed_seconds,_build_daily_completion_key,check_weekly_trigger_task
)

# 1. 关键改造：创建APIRouter实例（替代原代码的app）
router = APIRouter(tags=["学习计划/任务管理"])



# ===================== 健康检查 =====================
@router.get("/health")
def health() -> dict:
    return {"status": "ok", "time": datetime.now().isoformat(timespec="seconds")}

@router.post("/plan/session", response_model=PlancreateResponse)
def create_session(
    req: PlanRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    try:
        start_date, end_date = _resolve_dates_from_goal(req.goal, req.start_date, req.end_date)
        _validate_plan_dates(start_date, end_date)

        # 1️⃣ 生成计划（tasks）但不存数据库
        plan = _call_model(req.goal, start_date, end_date,user_id,db)

        # 2️⃣ 生成 goal_id


        # 3️⃣ 存 goal 表
        db_goal = Goal(
            user_id=user_id,
            goal_id=str(uuid4()),
            goal_type=GoalTypeEnum.LEARNING.value,  # 这里根据实际情况
            content=req.goal,
            start_date=start_date,
            end_date=end_date,
            progress=0.0,
            plan_version="V1",
            create_time=datetime.now()
        )
        db.add(db_goal)
        db.commit()
        db.refresh(db_goal)
        print("🔥 goal stored:", db_goal.id, db_goal.goal_id)
        task_plan_ids = []  # 用于收集每个 task 的 plan_id

        # 4️⃣ 批量存 task 表
        for task in plan.tasks:
            task_id = str(uuid4())  # 生成唯一 plan_id
            task_plan_ids.append(task_id)  # 收集起来

            db_task = Task(
                user_id=user_id,
                plan_id=task_id,  # ✅ 每个任务用自己唯一的 plan_id
                goal_id=db_goal.goal_id,  # 关键：确保 task 有 goal_id
                title=task.title,
                description=task.description,
                task_date=task.date,
                start_time=datetime.combine(task.date, datetime.min.time()),
                end_time=datetime.combine(task.date, datetime.max.time()),
                planned_duration_minutes=task.planned_duration_minutes,
                actual_duration_minutes=0,
                status=TaskStatusEnum.TODO.value,
                priority=TaskPriorityEnum.MID.value,
                plan_version="V1",
                depends_on="",
                gpa=0.0,
                task_type="STUDY"
            )
            db.add(db_task)


        db.commit()

        # 5️⃣ 返回接口
        return PlancreateResponse(
            code=200,
            msg="创建成功",
            data=SessionCreateResponse(
                # plan_id=task_plan_ids,  # 这里可以生成 session/plan id
                goal_id=db_goal.goal_id,
                goal_summary=plan.goal_summary,
                start_date=start_date,
                deadline=end_date,
                years=[]  # 根据你的逻辑
            )
        )

    except Exception as e:
        db.rollback()
        import traceback
        print("ERROR:", traceback.format_exc())
        return PlancreateResponse(
            code=500,
            msg=str(e),
            data=None
        )

#根据goal_id获取任务
@router.get("/goals/{goal_id}/tasks")
def get_tasks_by_goal(goal_id: str, db: Session = Depends(get_db)):
    """
    根据目标ID获取所有任务，并返回固定字段
    """
    tasks = db.query(Task).filter(Task.goal_id == goal_id).all()

    if not tasks:
        raise HTTPException(status_code=404, detail="该目标没有任务")

    return [
        {
            "plan_id": task.plan_id,
            "title": task.title,
            "description": task.description or "",
            "task_date": str(task.task_date),
            "priority": task.priority.value if hasattr(task.priority, "value") else task.priority or "",
            "gpa": task.gpa or "",
            "status": task.status.value if hasattr(task.status, "value") else task.status or ""
        }
        for task in tasks
    ]

#首页用到的
@router.get("/targets", response_model=ApiResponse)
def get_targets(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    try:
        goals = db.query(Goal).filter(Goal.user_id == user_id).all()

        result = [
            TargetResponse(
                id=str(g.id),
                goal=g.content,          # ⭐映射
                start_date=g.start_date,
                end_date=g.end_date
            )
            for g in goals
        ]

        return ApiResponse(
            code=200,
            msg="获取成功",
            data=result
        )
    except Exception:
        return ApiResponse(
            code=500,
            msg="获取失败",
            data=None
        )

# ===================== 日历/任务查询 =====================
@router.get("/plan/session/{plan_id}/years/{year}/months", response_model=YearMonthsResponse)
def get_months(plan_id: str, year: int) -> YearMonthsResponse:
    session = store.get(plan_id)
    years = session["years"]
    if year not in years:
        raise HTTPException(status_code=404, detail="年份不在规划范围内")

    start_date: date = session["start_date"]
    deadline: date = session["deadline"]
    tasks_by_date: dict[date, List[Task]] = session["tasks_by_date"]

    months: List[MonthItem] = []
    for month in range(1, 13):
        day_count = monthrange(year, month)[1]
        task_day_count = 0
        for day in range(1, day_count + 1):
            current = date(year, month, day)
            day_tasks = [task for task in tasks_by_date.get(current, []) if task.date == current]
            if start_date <= current <= deadline and len(day_tasks) > 0:
                task_day_count += 1
        months.append(MonthItem(month=month, month_label=f"{year}-{month:02d}", day_count=day_count,
                                task_day_count=task_day_count))

    return YearMonthsResponse(plan_id=plan_id, year=year, months=months)

#查看某月的详细任务
@router.get("/plan/session/{plan_id}/years/{year}/months/{month}/days", response_model=MonthDaysResponse)
def get_days(plan_id: str, year: int, month: int) -> MonthDaysResponse:
    if month < 1 or month > 12:
        raise HTTPException(status_code=400, detail="月份必须在 1~12")

    session = store.get(plan_id)
    years = session["years"]
    if year not in years:
        raise HTTPException(status_code=404, detail="年份不在规划范围内")

    start_date: date = session["start_date"]
    deadline: date = session["deadline"]
    tasks_by_date: dict[date, List[Task]] = session["tasks_by_date"]

    day_count = monthrange(year, month)[1]
    days: List[DayItem] = []
    for day in range(1, day_count + 1):
        current = date(year, month, day)
        in_range = start_date <= current <= deadline
        tasks = [task for task in tasks_by_date.get(current, []) if task.date == current] if in_range else []
        days.append(DayItem(day=day, date=current, has_task=len(tasks) > 0, task_count=len(tasks)))

    return MonthDaysResponse(plan_id=plan_id, year=year, month=month, days=days)

# 查看某天的详细任务
@router.get("/api/plan/session/{plan_id}/years/{year}/months/{month}/days/{day}", response_model=DayDetailResponse)
def get_day_detail(plan_id: str, year: int, month: int, day: int) -> DayDetailResponse:
    if month < 1 or month > 12:
        raise HTTPException(status_code=400, detail="月份必须在 1~12")

    max_day = monthrange(year, month)[1]
    if day < 1 or day > max_day:
        raise HTTPException(status_code=400, detail=f"日期必须在 1~{max_day}")

    session = store.get(plan_id)
    years = session["years"]
    if year not in years:
        raise HTTPException(status_code=404, detail="年份不在规划范围内")

    current = date(year, month, day)
    start_date: date = session["start_date"]
    deadline: date = session["deadline"]
    if not (start_date <= current <= deadline):
        return DayDetailResponse(plan_id=plan_id, date=current, task_count=0, total_daily_hours=0, tasks=[])

    tasks_by_date: dict[date, List[Task]] = session["tasks_by_date"]
    tasks = [task for task in tasks_by_date.get(current, []) if task.date == current]
    total_daily_hours = round(sum(task.estimated_hours for task in tasks), 2)
    return DayDetailResponse(
        plan_id=plan_id,
        date=current,
        task_count=len(tasks),
        total_daily_hours=total_daily_hours,
        tasks=tasks,
    )

#========================== 首页 ===============================
#首页的每日任务
@router.get("/tasks/day", response_model=DayDetailResponse)
def get_day_detail(
    year: int,
    month: int,
    day: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),  # 直接是用户 ID
) -> DayDetailResponse:

    # 1️⃣ 校验日期
    if month < 1 or month > 12:
        raise HTTPException(status_code=400, detail="月份必须在 1~12")

    max_day = monthrange(year, month)[1]
    if day < 1 or day > max_day:
        raise HTTPException(status_code=400, detail=f"日期必须在 1~{max_day}")

    current = date(year, month, day)

    # 2️⃣ 查询当天任务
    tasks = db.query(Task).filter(
        Task.user_id == user_id,       # 用户 ID
        func.date(Task.task_date) == current  # 对应数据库字段 task_date
    ).all()
    from datetime import date as py_date
    target_date = py_date(year, month, day)

    tasks_data = get_day_detail_from_db(db, user_id, target_date)

    return DayDetailResponse(
        plan_id="auto",
        date=f"{year}-{month:02d}-{day:02d}",  # 格式化日期字符串
        task_count=len(tasks_data),
        tasks=tasks_data
    )

#目标完成度
from collections import Counter
import logging

# 配置日志（只需要配置一次）
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

@router.get("/user/goals/progress", response_model=UserGoalsProgressResponse)
def get_goals_progress(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    获取当前登录用户每个目标的任务完成度 + 每个目标完成百分比 + 总完成率
    """
    goals = db.query(Goal).filter(Goal.user_id == user_id).all()
    result = []

    # 全局统计（算总完成率用）
    grand_total_tasks = 0
    grand_total_completed = 0

    logger.info("=" * 50)
    logger.info(f"【用户 {user_id}】目标进度统计开始")
    logger.info(f"共查询到 {len(goals)} 个目标")
    logger.info("=" * 50)

    for index, goal in enumerate(goals):
        logger.info(f"\n▶ 第 {index+1} 个目标 | 目标ID: {goal.goal_id}")
        logger.info(f"目标内容: {goal.content}")

        # 1. 获取当前目标下所有任务
        tasks = db.query(Task).filter(Task.goal_id == goal.goal_id).all()
        total = len(tasks)
        grand_total_tasks += total

        logger.info(f"该目标总任务数: {total}")

        # 打印每个任务的真实状态（排查关键！）
        if tasks:
            logger.info("=== 该目标下所有任务的状态 ===")
            for task in tasks:
                logger.info(f"任务ID: {task.id} | 状态: [{task.status}]")  # 加[]防止隐藏空格
        else:
            logger.info("该目标下暂无任务")

        # 2. 统计状态
        status_counter = Counter(task.status for task in tasks)

        # 用枚举匹配，不是用字符串！
        completed = status_counter.get(TaskStatusEnum.DONE.value, 0)
        in_progress = status_counter.get(TaskStatusEnum.DOING.value, 0)
        not_started = status_counter.get(TaskStatusEnum.TODO.value, 0)
        canceled = status_counter.get(TaskStatusEnum.CANCELLED.value, 0)

        logger.info(f"✅ 已完成: {completed}")
        logger.info(f"🔄 进行中: {in_progress}")
        logger.info(f"📌 未开始: {not_started}")
        logger.info(f"❌ 已取消: {canceled}")
        logger.info(f"📊 状态统计原始数据: {dict(status_counter)}")

        # 3. 计算当前目标完成百分比
        if total > 0:
            percentage = round((completed / total) * 100, 1)
        else:
            percentage = 0.0

        logger.info(f"🎯 该目标最终完成率: {percentage}%")

        # 4. 加入全局统计
        grand_total_completed += completed

        # 5. 组装每个目标的进度
        progress = GoalTaskProgress(
            goal_title=goal.content,
            completion_percentage=percentage
        )
        result.append(progress)

    # 6. 计算总完成率
    if grand_total_tasks > 0:
        overall_percentage = round((grand_total_completed / grand_total_tasks) * 100, 1)
    else:
        overall_percentage = 0.0

    # 全局统计日志
    logger.info("\n" + "=" * 50)
    logger.info(f"🌍 全局总统计")
    logger.info(f"用户所有目标总任务数: {grand_total_tasks}")
    logger.info(f"用户所有目标已完成数: {grand_total_completed}")
    logger.info(f"📈 用户总完成率: {overall_percentage}%")
    logger.info("=" * 50)

    # 7. 返回
    return UserGoalsProgressResponse(
        goals=result,
        overall_completion_rate=overall_percentage
    )

#======== 每周完成率 ==============
@router.get("/user/weekly_completion_rate")
def get_weekly_completion_rate(
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    day: int = Query(..., ge=1, le=31),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    返回本周（目标日期所在周）的任务完成率
    完成率 = 本周完成的任务数 / 本周所有任务数 * 100
    """
    try:
        target_date = date(year, month, day)
    except ValueError:
        raise HTTPException(status_code=400, detail="日期参数非法")

    # 本周起始和结束（周一到周日）
    start_of_week = target_date - timedelta(days=target_date.weekday())
    end_of_week = start_of_week + timedelta(days=6)

    # 本周所有任务（Task 表中的任务）
    tasks_this_week = db.query(Task).filter(Task.user_id==user_id).all()
    total_tasks = 0
    completed_tasks = 0

    for t in tasks_this_week:
        # 判断这个任务在本周是否有打卡记录
        states = db.query(TaskState).filter(
            TaskState.plan_id==t.plan_id,
            TaskState.user_id==user_id,
            TaskState.task_date>=start_of_week,
            TaskState.task_date<=end_of_week
        ).all()

        if states:
            completed_tasks += 1
        total_tasks += 1

    completion_rate = round(completed_tasks / total_tasks * 100, 2) if total_tasks > 0 else 0.0

    return {
        # "start_of_week": str(start_of_week),
        # "end_of_week": str(end_of_week),
        # "total_tasks": total_tasks,
        # "completed_tasks": completed_tasks,
        "completion_rate": completion_rate
    }

#=============== GPA ===================
@router.get("/user/daily_gpa")
def get_daily_gpa(
        year: int = Query(..., ge=2000, le=2100),
        month: int = Query(..., ge=1, le=12),
        day: int = Query(..., ge=1, le=31),
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """获取用户每日任务的 GPA 和平均 GPA，并打印日志"""
    today = date(year, month, day)
    logger.info(f"获取用户 {user_id} 在 {today} 的任务 GPA")

    tasks = db.query(Task).filter(Task.user_id == user_id).all()
    if not tasks:
        logger.warning(f"用户 {user_id} 当天没有任务")
        raise HTTPException(status_code=404, detail="当天没有任务")

    task_gpa_list = []
    gpa_sum = 0
    count = 0

    for task in tasks:
        state = db.query(TaskState).filter(
            TaskState.plan_id == task.plan_id,
            TaskState.task_date == today
        ).first()

        if state:
            gpa = _calculate_gpa_score(
                state.focus_score or 0,
                state.time_score or 0,
                state.brain_power_score or 0
            )
            task_gpa_list.append(TaskGPAItem(plan_id=task.plan_id, title=task.title, gpa_score=gpa))
            gpa_sum += gpa
            count += 1
            logger.info(f"任务 {task.title}({task.plan_id}) GPA: {gpa}")
        else:
            task_gpa_list.append(TaskGPAItem(plan_id=task.plan_id, title=task.title, gpa_score=None))
            logger.info(f"任务 {task.title}({task.plan_id}) 尚未打卡")

    daily_gpa_average = round(gpa_sum / count, 2) if count > 0 else None
    logger.info(f"用户 {user_id} 当天平均 GPA: {daily_gpa_average}")

    return daily_gpa_average


#=================== 学习时长 ===================
#每日学习时长接口
@router.get("/user/study_time/day", response_model=StudyTimeResponse)
def get_day_study_time(
    year: int,
    month: int,
    day: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    query_date = date(year, month, day)

    records = db.query(TaskState).filter(
        TaskState.user_id == user_id,
        TaskState.task_date == query_date
    ).all()

    total = sum(r.duration or 0 for r in records)

    return StudyTimeResponse(
        total_duration=total
        # data=[{
        #     "date": str(query_date),
        #     "duration": total
        # }]
    )

#每周学习时长
@router.get("/user/study_time/week", response_model=StudyTimeResponse)
def get_week_study_time(
    year: int,
    month: int,
    day: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    base_date = date(year, month, day)

    # 👉 找到本周周一
    start_of_week = base_date - timedelta(days=base_date.weekday())

    result = []
    total = 0

    for i in range(7):
        current_day = start_of_week + timedelta(days=i)

        records = db.query(TaskState).filter(
            TaskState.user_id == user_id,
            TaskState.task_date == current_day
        ).all()

        day_total = sum(r.duration or 0 for r in records)

        total += day_total

        result.append({
            "date": str(current_day),
            "duration": day_total
        })

    return StudyTimeResponse(
        total_duration=total,
        # data=result
    )

#每月学习时长
@router.get("/user/study_time/month", response_model=StudyTimeResponse)
def get_month_study_time(
    year: int,
    month: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    days = calendar.monthrange(year, month)[1]

    result = []
    total = 0

    for d in range(1, days + 1):
        current_day = date(year, month, d)

        records = db.query(TaskState).filter(
            TaskState.user_id == user_id,
            TaskState.task_date == current_day
        ).all()

        day_total = sum(r.duration or 0 for r in records)

        total += day_total

        result.append({
            "date": str(current_day),
            "duration": day_total
        })

    return StudyTimeResponse(
        total_duration=total,
        # data=result
    )


#=========== 任务计时 =====================
@router.post("/task/timing/{plan_id}")
def submit_task_timer(
    plan_id: str,
    req: TaskTimerSubmitRequest,
    db: Session = Depends(get_db)
):
    # 1️⃣ 基础校验
    if req.duration <= 0:
        raise HTTPException(status_code=400, detail="duration必须大于0")

    if not (0 <= req.focus_score <= 100):
        raise HTTPException(status_code=400, detail="focus_score必须在0-100之间")

    if not (0 <= req.brain_power_score <= 100):
        raise HTTPException(status_code=400, detail="brain_power_score必须在0-100之间")

    # 2️⃣ 查任务（数据库）
    task = db.query(Task).filter(
        Task.plan_id == plan_id
    ).first()

    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    # 3️⃣ 时间计算
    planned_duration_minutes = float(task.planned_duration_minutes)
    actual_duration_minutes = round(req.duration / 60, 2)

    # 4️⃣ 评分计算
    time_score, checkin_valid = _calculate_time_score(
        planned_duration_minutes,
        actual_duration_minutes
    )

    gpa_score = _calculate_gpa_score(
        req.focus_score,
        time_score,
        req.brain_power_score
    )

    state_tag, suggestion = _build_gpa_state(
        gpa_score,
        checkin_valid
    )
    #关键新增：日期 & 时间
    today = date.today()

    #写数据库
    task_state = TaskState(
        user_id=task.user_id,
        plan_id=plan_id,
        duration=req.duration,
        focus_score=req.focus_score,
        brain_power_score=req.brain_power_score,
        time_score=time_score,
        checkin_valid=checkin_valid,
        state_tag=state_tag,
        task_date=today
    )

    db.add(task_state)
    db.commit()
    db.refresh(task_state)
    #返回结果
    return {
        "plan_id": plan_id,
        "suggestion": suggestion
    }


@router.post("/task/timer/toggle", response_model=TaskTimerToggleResponse)
def toggle_task_timer(req: TaskTimerToggleRequest) -> TaskTimerToggleResponse:
    session = store.get(req.plan_id)
    years = session["years"]
    if req.year not in years:
        raise HTTPException(status_code=404, detail="年份不在规划范围内")

    try:
        current = date(req.year, req.month, req.day)
    except ValueError:
        raise HTTPException(status_code=400, detail="日期参数非法")
    start_date: date = session["start_date"]
    deadline: date = session["deadline"]
    if not (start_date <= current <= deadline):
        raise HTTPException(status_code=400, detail="任务日期不在当前计划区间内")

    tasks_by_date: dict[date, List[Task]] = session["tasks_by_date"]
    day_tasks = [task for task in tasks_by_date.get(current, []) if task.date == current]
    target_task = next((task for task in day_tasks if task.title == req.task_title.strip()), None)
    if not target_task:
        raise HTTPException(status_code=404, detail="未找到对应任务，请检查 task_title")

    task_key = _build_task_timer_key(req.plan_id, current, req.task_title)
    now = datetime.now()
    active_started_at = timer_store.get_active_started_at(task_key)

    if active_started_at is None:
        started_at = timer_store.start(task_key, now)
        return TaskTimerToggleResponse(
            plan_id=req.plan_id,
            date=current,
            task_title=target_task.title,
            is_running=True,
            started_at=started_at,
            duration_seconds=0,
            duration_text="0秒",
        )

    if req.focus_score is None or req.brain_power_score is None:
        raise HTTPException(status_code=400, detail="结束计时时必须提交 focus_score 和 brain_power_score")

    started_at, duration_seconds = timer_store.stop(task_key, now)
    if started_at is None:
        started_at = active_started_at
        duration_seconds = max(int((now - active_started_at).total_seconds()), 0)

    planned_duration_minutes = float(target_task.planned_duration_minutes)
    actual_duration_minutes = round(duration_seconds / 60, 2)
    time_score, checkin_valid = _calculate_time_score(planned_duration_minutes, actual_duration_minutes)
    gpa_score = _calculate_gpa_score(req.focus_score, time_score, req.brain_power_score)
    cognitive_state, suggestion = _build_gpa_state(gpa_score, checkin_valid)

    timer_store.add_task_record(
        {
            "task_key": task_key,
            "plan_id": req.plan_id,
            "date": current.isoformat(),
            "task_title": target_task.title,
            "planned_duration_minutes": round(planned_duration_minutes, 2),
            "actual_duration_minutes": actual_duration_minutes,
            "focus_score": float(req.focus_score),
            "brain_power_score": float(req.brain_power_score),
            "time_score": time_score,
            "gpa_score": gpa_score,
            "checkin_valid": checkin_valid,
            "ended_at": now.isoformat(timespec="seconds"),
        }
    )
    return TaskTimerToggleResponse(
        plan_id=req.plan_id,
        date=current,
        task_title=target_task.title,
        is_running=False,
        started_at=started_at,
        ended_at=now,
        duration_seconds=duration_seconds,
        duration_text=_format_elapsed_seconds(duration_seconds),
        planned_duration_minutes=int(round(planned_duration_minutes)),
        actual_duration_minutes=actual_duration_minutes,
        focus_score=req.focus_score,
        brain_power_score=req.brain_power_score,
        time_score=time_score,
        gpa_score=gpa_score,
        checkin_valid=checkin_valid,
        cognitive_state=cognitive_state,
        suggestion=suggestion,
    )

#清空某个计划的所有正在运行的计时缓存
@router.post("/task/timer/clear-all", response_model=TaskTimerClearResponse)
def clear_task_timer_all(req: TaskTimerClearRequest) -> TaskTimerClearResponse:
    store.get(req.plan_id)
    cleared_count = timer_store.clear_by_plan(req.plan_id)
    return TaskTimerClearResponse(
        plan_id=req.plan_id,
        cleared_count=cleared_count,
        message="计时缓存已清除",
    )

#====================== 完成度折线图 ====================
@router.get("/user/goals/daily_progress", response_model=List[GoalDailyProgress])
def get_daily_goals_progress(
        year: int = Query(...),
        month: int = Query(...),
        day: int = Query(...),
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    查询用户指定日期的目标任务完成度，并返回每个任务的 GPA（如果有打卡数据）
    """
    query_date = date(year, month, day)

    goals = db.query(Goal).filter(Goal.user_id == user_id).all()
    result = []

    for goal in goals:
        tasks = db.query(Task).filter(Task.goal_id == goal.goal_id).all()
        task_list = []

        for task in tasks:
            # 查询 task_state 中当天的数据
            state = db.query(TaskState).filter(
                TaskState.plan_id == task.plan_id,
                # TaskState.task_date == query_date
            ).first()

            if state:
                gpa = _calculate_gpa_score(
                    getattr(state, "focus_score", 0),
                    getattr(state, "time_score", 0),
                    getattr(state, "brain_power_score", 0)
                )
                # status = state.status
            else:
                gpa = 0  # 没打卡数据
                # status = "未完成"  # 或者你表中默认状态

            task_list.append(TaskDailyGPAInfo(
                title=task.title,
                gpa=gpa,

            ))

        result.append(GoalDailyProgress(
            goal_id=goal.goal_id,
            goal_content=goal.content,
            tasks=task_list
        ))

    return result

# ===================== GPA计算 =====================
#计算GPA
@router.post("/gpa/calculate", response_model=GPACalculateResponse)
def calculate_gpa(req: GPACalculateRequest) -> GPACalculateResponse:
    #获取任务打卡记录
    records = timer_store.get_task_records_by_plan(req.plan_id)
    #如果总记录数小于要求的最小完成数，直接返回 400 错误。
    if len(records) < req.min_finished_count:
        raise HTTPException(status_code=400, detail="有效打卡数量不足，无法计算 GPA")
    #区分有效/无效打卡
    finished_count = len(records)
    valid_records = [item for item in records if bool(item.get("checkin_valid", False))]
    invalid_records = [item for item in records if not bool(item.get("checkin_valid", False))]
    valid_finished_count = len(valid_records)

    if valid_finished_count < req.min_finished_count:
        raise HTTPException(status_code=400, detail="有效打卡数量不足，无法计算 GPA")
    #计算平均分和时间效率
    avg_focus = round(sum(float(item["focus_score"]) for item in valid_records) / valid_finished_count, 2)
    avg_brain = round(sum(float(item["brain_power_score"]) for item in valid_records) / valid_finished_count, 2)
    avg_time = round(sum(float(item["time_score"]) for item in valid_records) / valid_finished_count, 2)
    estimated_total_minutes = round(sum(float(item["planned_duration_minutes"]) for item in valid_records), 2)
    actual_total_minutes = round(sum(float(item["actual_duration_minutes"]) for item in valid_records), 2)

    if actual_total_minutes <= 0:
        time_efficiency_ratio = 0.0
    else:
        time_efficiency_ratio = round(estimated_total_minutes / actual_total_minutes, 3)

    gpa_score = _calculate_gpa_score(avg_focus, avg_time, avg_brain)

    return GPACalculateResponse(
        plan_id=req.plan_id,
        finished_count=finished_count,
        valid_finished_count=valid_finished_count,
        invalid_finished_count=len(invalid_records),
        average_focus_score=avg_focus,
        average_brain_power_score=avg_brain,
        average_time_score=avg_time,
        estimated_total_minutes=estimated_total_minutes,
        actual_total_minutes=actual_total_minutes,
        time_efficiency_ratio=time_efficiency_ratio,
        gpa_score=gpa_score,
    )

@router.get("/gpa/{plan_id}/weeks/{year}/{month}/{day}", response_model=GPAWeekTrendResponse)
def get_gpa_weekly_trend(plan_id: str, year: int, month: int, day: int) -> GPAWeekTrendResponse:
    session = store.get(plan_id)
    years = session["years"]
    if year not in years:
        raise HTTPException(status_code=404, detail="年份不在规划范围内")

    try:
        anchor = date(year, month, day)
    except ValueError:
        raise HTTPException(status_code=400, detail="日期参数非法")

    week_start = anchor - timedelta(days=anchor.weekday())
    week_end = week_start + timedelta(days=6)
    records = timer_store.get_task_records_by_plan(plan_id)

    points: List[GPATrendPoint] = []
    for offset in range(7):
        current = week_start + timedelta(days=offset)
        points.append(_compute_daily_gpa_from_records(records, current))

    return GPAWeekTrendResponse(plan_id=plan_id, week_start=week_start, week_end=week_end, points=points)

# ===================== 任务完成状态 =====================
#根据请求切换或设置某个任务的完成状态，并返回当天的任务完成率。
@router.post("/task/completion", response_model=TaskCompletionToggleResponse)
def toggle_task_completion(req: TaskCompletionToggleRequest,user_id: int = Depends(get_current_user_id),db:Session=Depends(get_db)) -> TaskCompletionToggleResponse:
    # 1️⃣ 构造日期
    try:
        current = date(req.year, req.month, req.day)
    except ValueError:
        raise HTTPException(status_code=400, detail="日期参数非法")

    # 2️⃣ 查计划 plan=该任务一行的信息
    plan = db.query(Task).filter(
        Task.plan_id == req.plan_id
    ).first()

    if not plan:
        raise HTTPException(status_code=404, detail="计划不存在")

    if not (plan.start_time.date() <= current <= plan.end_time.date()):
        raise HTTPException(status_code=400, detail="任务日期不在计划区间内")

    #查询当天所以任务
    tasks = db.query(Task).filter(
        Task.user_id == user_id,
        Task.task_date == current
    ).all()

    #找目标任务
    target = next((task for task in tasks if task.plan_id == req.plan_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="未找到对应任务，请检查 task_title")
    #查这个用户+这个任务的完成状态
    state = db.query(Task).filter(
        Task.plan_id == target.plan_id,
        Task.user_id == user_id,
    ).first()
    if not state:
        raise HTTPException(status_code=404, detail="任务不存在")

    # 计算新的完成状态
    if req.completed is None:
        final_completed = state.status != "已完成"  # 如果当前不是已完成，就切换
    else:
        final_completed = req.completed

    # ✅ 更新数据库
    state.status = "已完成" if final_completed else "未完成"
    db.commit()

    task_ids = [t.id for t in tasks]

    completed_count = db.query(Task).filter(
        Task.user_id == user_id,
        Task.plan_id == req.plan_id,
        Task.status == "已完成"
    ).count()

    daily = completed_count / len(tasks) if tasks else 0
    return TaskCompletionToggleResponse(
        plan_id=req.plan_id,
        date=current,
        task_title=target.title,
        completed=final_completed,
        daily_completion=daily,
    )

#获得日完成率
@router.get("/task/completion/{plan_id}/years/{year}/months/{month}/days/{day}",
         response_model=TaskCompletionDayResponse)
def get_daily_completion(plan_id: str, year: int, month: int, day: int) -> TaskCompletionDayResponse:
    session = store.get(plan_id)

    years = session["years"]
    if year not in years:
        raise HTTPException(status_code=404, detail="年份不在规划范围内")

    try:
        current = date(year, month, day)
    except ValueError:
        raise HTTPException(status_code=400, detail="日期参数非法")

    start_date: date = session["start_date"]
    deadline: date = session["deadline"]
    if not (start_date <= current <= deadline):
        return TaskCompletionDayResponse(
            plan_id=plan_id,
            date=current,
            total_task_count=0,
            completed_task_count=0,
            completion_rate=0,
            updated_at=datetime.now(),
        )

    cached = completion_store.get_daily_stat(_build_daily_completion_key(plan_id, current))
    if cached:
        return TaskCompletionDayResponse.model_validate(cached)

    tasks_by_date: dict[date, List[Task]] = session["tasks_by_date"]
    tasks = [task for task in tasks_by_date.get(current, []) if task.date == current]
    return _compute_daily_completion(plan_id, current, tasks)

@router.get("/task/completion/{plan_id}/weeks/{year}/{month}/{day}", response_model=TaskCompletionWeekResponse)
def get_weekly_completion(plan_id: str, year: int, month: int, day: int) -> TaskCompletionWeekResponse:
    session = store.get(plan_id)
    years = session["years"]
    if year not in years:
        raise HTTPException(status_code=404, detail="年份不在规划范围内")

    try:
        anchor = date(year, month, day)
    except ValueError:
        raise HTTPException(status_code=400, detail="日期参数非法")

    week_start = anchor - timedelta(days=anchor.weekday())
    week_end = week_start + timedelta(days=6)

    start_date: date = session["start_date"]
    deadline: date = session["deadline"]
    tasks_by_date: dict[date, List[Task]] = session["tasks_by_date"]

    points: List[TaskCompletionWeekItem] = []
    for offset in range(7):
        current = week_start + timedelta(days=offset)
        if not (start_date <= current <= deadline):
            points.append(
                TaskCompletionWeekItem(
                    date=current,
                    total_task_count=0,
                    completed_task_count=0,
                    completion_rate=0,
                )
            )
            continue

        cached = completion_store.get_daily_stat(_build_daily_completion_key(plan_id, current))
        if cached:
            daily = TaskCompletionDayResponse.model_validate(cached)
        else:
            tasks = [task for task in tasks_by_date.get(current, []) if task.date == current]
            daily = _compute_daily_completion(plan_id, current, tasks)

        points.append(
            TaskCompletionWeekItem(
                date=current,
                total_task_count=daily.total_task_count,
                completed_task_count=daily.completed_task_count,
                completion_rate=daily.completion_rate,
            )
        )

    return TaskCompletionWeekResponse(plan_id=plan_id, week_start=week_start, week_end=week_end, points=points)

@router.get("/task/completion/{plan_id}/months/{year}/{month}", response_model=TaskCompletionMonthResponse)
def get_monthly_completion(plan_id: str, year: int, month: int) -> TaskCompletionMonthResponse:
    session = store.get(plan_id)
    years = session["years"]
    if year not in years:
        raise HTTPException(status_code=404, detail="年份不在规划范围内")

    try:
        _, days_in_month = monthrange(year, month)
    except ValueError:
        raise HTTPException(status_code=400, detail="月份参数非法")

    start_date: date = session["start_date"]
    deadline: date = session["deadline"]
    tasks_by_date: dict[date, List[Task]] = session["tasks_by_date"]

    points: List[TaskCompletionMonthItem] = []
    for day in range(1, days_in_month + 1):
        current = date(year, month, day)
        if not (start_date <= current <= deadline):
            points.append(
                TaskCompletionMonthItem(
                    date=current,
                    total_task_count=0,
                    completed_task_count=0,
                    completion_rate=0,
                )
            )
            continue

        cached = completion_store.get_daily_stat(_build_daily_completion_key(plan_id, current))
        if cached:
            daily = TaskCompletionDayResponse.model_validate(cached)
        else:
            tasks = [task for task in tasks_by_date.get(current, []) if task.date == current]
            daily = _compute_daily_completion(plan_id, current, tasks)

        points.append(
            TaskCompletionMonthItem(
                date=current,
                total_task_count=daily.total_task_count,
                completed_task_count=daily.completed_task_count,
                completion_rate=daily.completion_rate,
            )
        )

    return TaskCompletionMonthResponse(plan_id=plan_id, year=year, month=month, points=points)

# ===================== 每日建议 =====================
@router.post("/daily/suggestion", response_model=DailySuggestionResponse)
def get_daily_suggestion(req: DailySuggestionRequest, db: Session = Depends(get_db)) -> DailySuggestionResponse:
    plan = db.query(Task).filter(Task.plan_id == req.plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="计划不存在")
    if not (plan.start_date.year <= req.year <= plan.end_date.year):
        raise HTTPException(status_code=404, detail="年份不在规划范围内")
    if not (plan.start_date.year <= req.year <= plan.end_date.year):
        raise HTTPException(status_code=404, detail="年份不在规划范围内")
    try:
        current = date(req.year, req.month, req.day)
    except ValueError:
        raise HTTPException(status_code=400, detail="日期参数非法")
    # 从数据库获取该计划所有任务记录
    records = timer_store.get_task_records_by_plan(req.plan_id)
    #计算当天GPA
    daily_gpa_point = _compute_daily_gpa_from_records(records, current)
    daily_gpa = daily_gpa_point.gpa_score if daily_gpa_point.valid_count > 0 else None
    #生成每日建议
    suggestion = _generate_daily_suggestion(daily_gpa, records)

    return DailySuggestionResponse(
        plan_id=req.plan_id,
        date=current,
        suggestion=suggestion,
        daily_gpa=daily_gpa,
    )

#============ 定时周报 =============
@router.get("/weekly/reports/{plan_id}")
def get_weekly_reports(plan_id: str, db: Session = Depends(get_db)):
    return db.query(Suggestion).filter(
        Suggestion.plan_id == plan_id,
        Suggestion.type == "周报建议"
    ).order_by(Suggestion.create_time.desc()).all()
# ===================== 周报相关 =====================
# @router.get("/weekly/check/{plan_id}", response_model=WeeklyCheckResponse)
# def check_weekly_report(plan_id: str,db: Session = Depends(get_db)) -> WeeklyCheckResponse:
#     #判断是否生成周报
#     needs_report, days_since = check_weekly_trigger_task(db, plan_id, date.today())
#     #查当前计划的最新版本
#     latest_task = db.query(Task).filter(Task.plan_id == plan_id).order_by(Task.plan_version.desc()).first()
#
#     plan_version = latest_task.plan_version if latest_task else "V1"
#     return {
#         "plan_id": plan_id,
#         "needs_weekly_report": needs_report,
#         "days_since_last_report": days_since,
#         "current_plan_version": plan_version
#     }
#
# @router.post("/weekly/report", response_model=WeeklyReportResponse)
# def generate_weekly_report(req: WeeklyReportRequest,db: Session = Depends(get_db)) -> WeeklyReportResponse:
#     plan_id = req.get("plan_id")
#     if not plan_id:
#         raise HTTPException(status_code=400, detail="缺少 plan_id")
#
#     auto_generate_weekly_reports_task(db)
#
#     # 返回本周最新周报
#     today = date.today()
#     week_end = today
#     week_start = week_end - timedelta(days=6)
#     week_id = f"{plan_id}_{week_start}_{week_end}"
#     report = db.query(WeeklyReport).filter(WeeklyReport.week_id == week_id).first()
#     return report
#
#
# @router.get("/weekly/reports/{plan_id}", response_model=List[WeeklyReport])
# def get_weekly_reports(plan_id: str, db: Session = Depends(get_db)) -> List[WeeklyReport]:
#     reports = db.query(WeeklyReport).filter(WeeklyReport.plan_id == plan_id).order_by(
#         WeeklyReport.created_at.desc()).all()
#     return reports
#
# @router.post("/task/completion/toggle-with-check", response_model=TaskCompletionToggleResponse)
# def toggle_task_completion_with_check(req: TaskCompletionToggleRequest, db: Session = Depends(get_db)) -> TaskCompletionToggleResponse:
#     result = toggle_task_completion(req,db)
#
#     plan = db.query(Plan).filter(Plan.id == req["plan_id"]).first()
#     needs_report, days_since = check_weekly_trigger_db(plan, date.today())
#     result["needs_weekly_report"] = needs_report
#     result["days_since_last_report"] = days_since
#     return result
#

#============ 推荐 =================
@router.get("/recommendation", response_model=ReResponse)
def get_user_recommendations(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    try:
        # 查询用户目标
        goals = db.query(Goal).filter(Goal.user_id == user_id).all()
        if not goals:
            return ApiResponse(code=404, msg="未找到用户目标", data=None)

        all_recommendations = []

        for goal in goals:
            # 调用推荐服务（AI + fallback）
            recommendations = get_recommendations_service(
                goal_category=goal.category,
                goal_detail=goal.content,  # ⭐映射到数据库字段
                current_phase=getattr(goal, "phase", "基础"),  # 如果表里没有 phase 用默认
                max_results=10
            )
            all_recommendations.extend(recommendations)

        return ReResponse(
            code=200,
            msg="获取成功",
            data=[r.dict() for r in all_recommendations]
        )
    except Exception as e:
        return ApiResponse(
            code=500,
            msg=f"获取失败: {str(e)}",
            data=None
        )
