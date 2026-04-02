import pymysql
import os
from dotenv import load_dotenv
from pymysql.cursors import DictCursor
import uuid
import json
from datetime import datetime, date
from fastapi import HTTPException
load_dotenv()


class MySQLService:
    def __init__(self):
        self.host = os.getenv("DB_HOST", "localhost")
        self.port = int(os.getenv("DB_PORT", 3306))
        self.user = os.getenv("DB_USER")
        self.password = os.getenv("DB_PASSWORD", "030303")
        self.database = os.getenv("DB_NAME")

    def _get_connection(self):
        return pymysql.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            database=self.database,
            cursorclass=DictCursor,
            charset='utf8mb4'
        )

    # ========== 修正1：适配 user 表 + 增加 user_id 类型校验 ==========
    def get_user_basic(self, user_id):
        try:
            user_id = int(user_id)
        except (ValueError, TypeError):
            return {"id": user_id, "username": f"用户{user_id}", "major": "", "grade": ""}

        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                sql = "SELECT id, username, major, grade FROM user WHERE id = %s"
                cursor.execute(sql, (user_id,))
                return cursor.fetchone() or {"id": user_id, "username": f"用户{user_id}", "major": "", "grade": ""}

    # ========== 修正2：适配 study_record 表 + 防护除以0 ==========
    def get_user_gpa(self, user_id):
        try:
            user_id = int(user_id)
        except (ValueError, TypeError):
            return 0.0

        with self._get_connection() as conn:
            with conn.cursor(cursor=pymysql.cursors.DictCursor) as cursor:
                sql = """
                    SELECT score, credit FROM study_record WHERE user_id = %s
                """
                cursor.execute(sql, (user_id,))
                records = cursor.fetchall()

                if not records:
                    return 0.0

                total_credit = sum(r['credit'] for r in records)
                if total_credit == 0:
                    return 0.0

                total_score = sum(r['score'] * r['credit'] for r in records)
                avg_score = total_score / total_credit

                if avg_score >= 90:
                    return 4.0
                elif avg_score >= 80:
                    return 3.0
                elif avg_score >= 70:
                    return 2.0
                else:
                    return 1.0

    # ========== 修正3：适配 task_state 表 ==========
    def get_latest_state(self, user_id):
        try:
            user_id = int(user_id)
        except (ValueError, TypeError):
            return {"focus_score": 100, "brain_score": 100, "state_tag": "良好"}

        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                sql = """
                    SELECT focus_score, brain_score, state_tag
                    FROM task_state
                    WHERE user_id = %s
                    ORDER BY create_time DESC LIMIT 1
                """
                cursor.execute(sql, (user_id,))
                result = cursor.fetchone()
                return result or {"focus_score": 100, "brain_score": 100, "state_tag": "良好"}

    # ========== 修正4：适配 task 表 ==========
    def get_unfinished_task_count(self, user_id):
        try:
            user_id = int(user_id)
        except (ValueError, TypeError):
            return 0

        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                sql = "SELECT COUNT(*) as total FROM task WHERE user_id = %s AND status = 'TODO'"
                cursor.execute(sql, (user_id,))
                result = cursor.fetchone()
                return result['total'] if result else 0

    # ========== 保留 query_score（无错误） ==========
    def query_score(self, user_id):
        try:
            user_id = int(user_id)
        except (ValueError, TypeError):
            return []

        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                sql = """
                    SELECT semester, course_name, score, credit, course_type
                    FROM study_record
                    WHERE user_id = %s
                    ORDER BY create_time DESC
                """
                cursor.execute(sql, (user_id,))
                return cursor.fetchall()

    # ========== 保留 query_tasks（无错误） ==========
    def query_tasks(self, user_id):
        try:
            user_id = int(user_id)
        except (ValueError, TypeError):
            return []

        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                sql = """
                    SELECT title, category, priority, end_time
                    FROM task
                    WHERE user_id = %s AND status = 'TODO'
                    ORDER BY priority DESC, end_time ASC
                """
                cursor.execute(sql, (user_id,))
                return cursor.fetchall()

    # ========== 修正5：query_goal 替换 create_time 为 end_time ==========
    def query_goal(self, user_id):
        try:
            user_id = int(user_id)
        except (ValueError, TypeError):
            return None

        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                sql = """
                    SELECT goal_type, content, progress, end_time
                    FROM goal
                    WHERE user_id = %s
                    ORDER BY end_time DESC LIMIT 1  # ✅ 替换为 end_time
                """
                cursor.execute(sql, (user_id,))
                return cursor.fetchone()

    # ========== 计划管理 ==========
    def create_plan(self, start_date, deadline, goal_summary, tasks):
        """创建学习计划"""
        plan_id = str(uuid.uuid4())
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                # 1. 插入计划主记录
                sql_plan = """
                    INSERT INTO study_plan (id, goal_summary, start_date, end_date, 
                                           original_goal, plan_version, created_at)
                    VALUES (%s, %s, %s, %s, %s, 1, NOW())
                """
                cursor.execute(sql_plan, (plan_id, goal_summary, start_date,
                                          deadline, goal_summary))

                # 2. 批量插入任务
                for task in tasks:
                    sql_task = """
                        INSERT INTO task (plan_id, title, description, task_date,
                                         planned_duration_minutes, priority, depends_on,
                                         status, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, 'TODO', NOW())
                    """
                    cursor.execute(sql_task, (
                        plan_id, task.title, task.description, task.date,
                        task.planned_duration_minutes, task.priority,
                        json.dumps(task.depends_on) if task.depends_on else None
                    ))

                conn.commit()

        years = list(range(start_date.year, deadline.year + 1)) if deadline >= start_date else [start_date.year]
        return plan_id, years

    def get_plan(self, plan_id):
        """获取计划详情"""
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                # 获取计划主记录
                sql = "SELECT * FROM study_plan WHERE id = %s"
                cursor.execute(sql, (plan_id,))
                plan = cursor.fetchone()

                if not plan:
                    raise HTTPException(status_code=404, detail="计划不存在")

                # 获取关联任务
                sql_tasks = "SELECT * FROM task WHERE plan_id = %s ORDER BY task_date"
                cursor.execute(sql_tasks, (plan_id,))
                tasks = cursor.fetchall()

                # 按日期分组任务
                tasks_by_date = {}
                for task in tasks:
                    task_date = task['task_date']
                    if task_date not in tasks_by_date:
                        tasks_by_date[task_date] = []
                    tasks_by_date[task_date].append(task)

                return {
                    "start_date": plan['start_date'],
                    "deadline": plan['end_date'],
                    "goal_summary": plan['goal_summary'],
                    "years": list(range(plan['start_date'].year, plan['end_date'].year + 1)),
                    "tasks_by_date": tasks_by_date,
                    "cycle_start_date": plan['start_date'],
                    "last_report_date": plan.get('updated_at'),
                    "plan_version": plan['plan_version'],
                    "original_goal": plan['original_goal'],
                }

    def update_plan_version(self, plan_id, new_tasks):
        """更新计划版本"""
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                # 更新计划版本号
                sql = "UPDATE study_plan SET plan_version = plan_version + 1, updated_at = NOW() WHERE id = %s"
                cursor.execute(sql, (plan_id,))

                # 删除旧任务
                sql_delete = "DELETE FROM task WHERE plan_id = %s"
                cursor.execute(sql_delete, (plan_id,))

                # 插入新任务
                for task in new_tasks:
                    sql_task = """
                        INSERT INTO task (plan_id, title, description, task_date,
                                         planned_duration_minutes, priority, depends_on,
                                         status, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, 'TODO', NOW())
                    """
                    cursor.execute(sql_task, (
                        plan_id, task.title, task.description, task.date,
                        task.planned_duration_minutes, task.priority,
                        json.dumps(task.depends_on) if task.depends_on else None
                    ))

                conn.commit()

                # 获取新版本号
                cursor.execute("SELECT plan_version FROM study_plan WHERE id = %s", (plan_id,))
                result = cursor.fetchone()
                return result['plan_version']

    def update_last_report_date(self, plan_id):
        """更新最后报告日期"""
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                sql = "UPDATE study_plan SET updated_at = NOW() WHERE id = %s"
                cursor.execute(sql, (plan_id,))
                conn.commit()

    # ========== 计时记录管理 ==========
    def start_timer(self, task_key, started_at):
        """开始计时 - 写入 task_timer 表"""
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                # 检查是否已存在记录
                sql_check = "SELECT id FROM task_timer WHERE task_key = %s AND ended_at IS NULL"
                cursor.execute(sql_check, (task_key,))
                existing = cursor.fetchone()

                if existing:
                    # 已存在则更新
                    sql = "UPDATE task_timer SET started_at = %s WHERE task_key = %s AND ended_at IS NULL"
                    cursor.execute(sql, (started_at, task_key))
                else:
                    # 新建记录
                    plan_id = task_key.split(':')[0]
                    sql = """
                        INSERT INTO task_timer (id, plan_id, task_key, started_at, created_at)
                        VALUES (%s, %s, %s, %s, NOW())
                    """
                    cursor.execute(sql, (str(uuid.uuid4()), plan_id, task_key, started_at))
                conn.commit()
        return started_at

    def stop_timer(self, task_key, ended_at):
        """停止计时 - 更新 task_timer 表"""
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                # 获取开始时间
                sql_select = "SELECT started_at FROM task_timer WHERE task_key = %s AND ended_at IS NULL ORDER BY created_at DESC LIMIT 1"
                cursor.execute(sql_select, (task_key,))
                record = cursor.fetchone()

                if not record:
                    return None, 0

                started_at = record['started_at']
                duration_seconds = int((ended_at - started_at).total_seconds())

                # 更新结束时间
                sql_update = "UPDATE task_timer SET ended_at = %s, duration_seconds = %s WHERE task_key = %s AND ended_at IS NULL"
                cursor.execute(sql_update, (ended_at, duration_seconds, task_key))
                conn.commit()

        return started_at, duration_seconds

    def get_active_started_at(self, task_key):
        """获取活动计时开始时间"""
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                sql = "SELECT started_at FROM task_timer WHERE task_key = %s AND ended_at IS NULL ORDER BY created_at DESC LIMIT 1"
                cursor.execute(sql, (task_key,))
                record = cursor.fetchone()
                return record['started_at'] if record else None

    def clear_timer_by_plan(self, plan_id):
        """清除计划的计时记录"""
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                # 删除相关记录
                sql = "DELETE FROM task_timer WHERE plan_id = %s"
                cursor.execute(sql, (plan_id,))
                affected = cursor.rowcount
                conn.commit()
                return affected

    def get_completed_seconds_by_plan(self, plan_id):
        """获取计划的累计计时秒数"""
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                sql = "SELECT SUM(duration_seconds) as total FROM task_timer WHERE plan_id = %s"
                cursor.execute(sql, (plan_id,))
                result = cursor.fetchone()
                return result['total'] if result['total'] else 0

    def add_timer_record(self, record):
        """添加完整的计时记录"""
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                sql = """
                    INSERT INTO task_timer 
                    (id, plan_id, task_key, started_at, ended_at, duration_seconds,
                     focus_score, brain_power_score, time_score, gpa_score, 
                     checkin_valid, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                """
                cursor.execute(sql, (
                    str(uuid.uuid4()),
                    record.get('plan_id'),
                    record.get('task_key'),
                    record.get('started_at'),
                    record.get('ended_at'),
                    record.get('duration_seconds', 0),
                    record.get('focus_score'),
                    record.get('brain_power_score'),
                    record.get('time_score'),
                    record.get('gpa_score'),
                    record.get('checkin_valid', True)
                ))
                conn.commit()

    def get_timer_records_by_plan(self, plan_id):
        """按计划查询计时记录"""
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                sql = "SELECT * FROM task_timer WHERE plan_id = %s ORDER BY created_at DESC"
                cursor.execute(sql, (plan_id,))
                return cursor.fetchall()

    # ========== 任务完成状态管理 ==========
    def set_task_completed(self, task_key, completed):
        """设置任务完成状态"""
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                plan_id = task_key.split(':')[0]
                task_title = task_key.split(':')[-1]

                # 查找任务ID
                sql_task = "SELECT id FROM task WHERE plan_id = %s AND title = %s LIMIT 1"
                cursor.execute(sql_task, (plan_id, task_title))
                task_record = cursor.fetchone()

                if task_record:
                    task_id = task_record['id']

                    # 插入或更新完成状态
                    sql = """
                        INSERT INTO task_completion (id, plan_id, task_id, task_key, completed, completed_at)
                        VALUES (%s, %s, %s, %s, %s, NOW())
                        ON DUPLICATE KEY UPDATE completed = %s, completed_at = NOW()
                    """
                    cursor.execute(sql, (str(uuid.uuid4()), plan_id, task_id, task_key,
                                         completed, completed))
                    conn.commit()

        return completed

    def get_task_completed(self, task_key):
        """获取任务完成状态"""
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                sql = "SELECT completed FROM task_completion WHERE task_key = %s"
                cursor.execute(sql, (task_key,))
                record = cursor.fetchone()
                return bool(record['completed']) if record else False

    def get_completed_count(self, task_keys):
        """统计完成数量"""
        if not task_keys:
            return 0

        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                placeholders = ','.join(['%s'] * len(task_keys))
                sql = f"SELECT COUNT(*) as count FROM task_completion WHERE task_key IN ({placeholders}) AND completed = 1"
                cursor.execute(sql, tuple(task_keys))
                result = cursor.fetchone()
                return result['count'] if result else 0

    def save_daily_stat(self, daily_key, stat):
        """保存每日统计"""
        # daily_key 格式: plan_id:YYYY-MM-DD
        parts = daily_key.split(':')
        plan_id = parts[0]
        date_str = parts[1] if len(parts) > 1 else None

        if not date_str:
            return

        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                # 这里可以保存到 task_completion 表的日统计字段
                # 或者新建一个 daily_stats 表
                pass

    def get_daily_stat(self, daily_key):
        """获取每日统计"""
        parts = daily_key.split(':')
        plan_id = parts[0]
        date_str = parts[1] if len(parts) > 1 else None

        if not date_str:
            return None

        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                sql = """
                    SELECT 
                        COUNT(*) as total_count,
                        SUM(CASE WHEN completed = 1 THEN 1 ELSE 0 END) as completed_count
                    FROM task_completion tc
                    JOIN task t ON tc.task_id = t.id
                    WHERE tc.plan_id = %s AND DATE(t.task_date) = %s
                """
                cursor.execute(sql, (plan_id, date_str))
                result = cursor.fetchone()

                if result and result['total_count']:
                    return {
                        'total_task_count': result['total_count'],
                        'completed_task_count': result['completed_count'] or 0,
                        'completion_rate': round((result['completed_count'] or 0) / result['total_count'] * 100, 2)
                    }
                return None

    # ========== 周报管理 ==========
    def save_weekly_report(self, report):
        """保存周报"""
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                # 使用 suggestion 表存储周报 (type = WEEKLY)
                sql = """
                    INSERT INTO suggestion 
                    (id, user_id, plan_id, content, type, create_time)
                    VALUES (%s, 1, %s, %s, 'WEEKLY', NOW())
                """
                cursor.execute(sql, (
                    str(uuid.uuid4()),
                    report.get('plan_id'),
                    report.get('report_content')
                ))
                conn.commit()

    def get_weekly_reports_by_plan(self, plan_id):
        """按计划查询周报"""
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                sql = """
                    SELECT * FROM suggestion 
                    WHERE plan_id = %s AND type = 'WEEKLY'
                    ORDER BY create_time DESC
                """
                cursor.execute(sql, (plan_id,))
                return cursor.fetchall()

    def get_latest_report(self, plan_id):
        """获取最新周报"""
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                sql = """
                    SELECT * FROM suggestion 
                    WHERE plan_id = %s AND type = 'WEEKLY'
                    ORDER BY create_time DESC LIMIT 1
                """
                cursor.execute(sql, (plan_id,))
                return cursor.fetchone()