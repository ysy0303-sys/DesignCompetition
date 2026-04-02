# services/profile_service.py
class ProfileService:
    def __init__(self, db):
        # 保留你原有的传参方式（db由外部传入，不自己初始化）
        self.db = db

    def get_chat_profile(self, user_id: int):
        """
        基于你的原始结构扩展：整合所有查询方法，返回完整用户资料
        """
        # 1. 保留你原有的2个核心调用
        user_basic = self.db.get_user_basic(user_id)  # 用户基础信息
        gpa = self.db.get_user_gpa(user_id)           # 用户GPA

        # 2. 新增其他查询（基于修正后的 db_service 方法）
        unfinished_task_count = self.db.get_unfinished_task_count(user_id)  # 未完成任务数
        score_records = self.db.query_score(user_id)                        # 成绩记录
        task_details = self.db.query_tasks(user_id)                          # 任务详情
        latest_goal = self.db.query_goal(user_id)                            # 最新目标
        latest_state = self.db.get_latest_state(user_id)                    # 最新状态

        # 3. 保留你原有的字典合并方式，同时新增其他字段
        return {
            **user_basic,  # 合并基础信息（id/username/major/grade）
            "gpa": gpa,    # 保留你原有的GPA字段
            # 新增其他查询结果字段
            "unfinished_task_count": unfinished_task_count,
            "score_records": score_records,
            "task_details": task_details,
            "latest_goal": latest_goal,
            "latest_state": latest_state
        }