from datetime import date, timedelta, datetime
from sqlalchemy.orm import Session
from backed.database.models import Suggestion
from backed.core.websocket_manager import manager
import asyncio


def check_weekly_trigger(db: Session, plan_id: str):
    """判断是否需要生成周报"""

    last = db.query(Suggestion).filter(
        Suggestion.plan_id == plan_id,
        Suggestion.type == "周报建议"
    ).order_by(Suggestion.week_end.desc()).first()

    if not last:
        return True

    days = (date.today() - last.week_end).days
    return days >= 7


def generate_weekly_report(db: Session, plan_id: str, user_id: int):
    """生成单个 plan 的周报"""

    today = date.today()
    week_end = today
    week_start = today - timedelta(days=6)

    # 防重复
    exist = db.query(Suggestion).filter(
        Suggestion.plan_id == plan_id,
        Suggestion.type == "周报建议",
        Suggestion.week_start == week_start,
        Suggestion.week_end == week_end
    ).first()

    if exist:
        return

    # 👉 TODO: 换成你真实 TaskState 分析
    extra_data = {
        "avg_gpa": 4,
        "completed_tasks": 10,
        "focus_time": 500
    }

    content = f"📊 本周总结：完成{extra_data['completed_tasks']}个任务，GPA={extra_data['avg_gpa']}"

    suggestion = Suggestion(
        user_id=user_id,
        plan_id=plan_id,
        type="周报建议",
        content=content,
        week_start=week_start,
        week_end=week_end,
        extra_data=extra_data,
        create_time=datetime.now()
    )

    db.add(suggestion)
    db.commit()

    # ✅ WebSocket 推送
    asyncio.create_task(
        manager.send_to_user(user_id, {
            "type": "weekly_report",
            "plan_id": plan_id,
            "content": content,
            "week_start": str(week_start),
            "week_end": str(week_end)
        })
    )


def auto_generate_weekly(db: Session):
    """定时任务调用"""

    # 👉 这里你应该查 Plan 表
    plans = db.execute("SELECT DISTINCT plan_id, user_id FROM task").fetchall()

    for plan_id, user_id in plans:
        if check_weekly_trigger(db, plan_id):
            generate_weekly_report(db, plan_id, user_id)