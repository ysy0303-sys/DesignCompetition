from typing import List
import datetime
from backed.config.settings import MAX_HISTORY_ROUNDS  # 导入配置

class ChatAgent:
    def __init__(self, llm_service, profile_service, db_service):
        self.llm_service = llm_service
        self.profile_service = profile_service
        self.db_service = db_service
        # 短期记忆：user_id -> 最近N轮对话（N由配置决定）
        self.chat_memory = {}

    # ------------------------ 主处理函数 ------------------------
    def handle(self, user_id: int, message: str):
        intent = self.detect_intent(message)

        if intent == "personal_data_query":
            return self._handle_personal_data(user_id, message)
        else:
            return self._handle_general_qa(user_id, message)

    # ------------------------ 意图识别 ------------------------
    def detect_intent(self, message: str) -> str:
        # 简单关键词匹配，可升级为分类模型
        personal_keywords = ["成绩", "分数", "GPA", "任务", "目标", "未完成"]
        for kw in personal_keywords:
            if kw in message:
                return "personal_data_query"
        return "general_qa"

    # ------------------------ 个人数据查询 ------------------------
    def _handle_personal_data(self, user_id: int, user_message: str):
        """
        处理个人数据查询类问题（成绩、任务、目标），
        SQL 查询数据 + LLM 生成自然语言回答
        """
        try:
            # ----------------- 1. 查询数据库（加默认值兜底） -----------------
            score_info = self.db_service.query_score(user_id) or []       # 返回 list of dict
            task_info = self.db_service.query_tasks(user_id) or []        # 返回 list of dict
            goal_info = self.db_service.query_goal(user_id) or {}         # 返回 dict

            # ----------------- 2. 构建 LLM 系统提示词 -----------------
            system_prompt = f"""
你是用户的个性化学习助手。要求回答必须极度简短，几句话，不超过90字。
以下是用户数据库查询结果：

【成绩】：
{score_info if score_info else '暂无成绩记录'}

【任务】：
{task_info if task_info else '暂无任务记录'}

【目标】：
{goal_info if goal_info else '暂无目标记录'}

要求：
1. 回答用户问题时，将数据库数据转化为自然语言。
2. 风格贴近用户，语言自然、简洁，可加入鼓励。
3. 根据用户状态（专注度/脑力值/状态标签）调整回答长度和复杂度。
4. 对于连续对话，保持上下文连贯。
"""

            # ----------------- 3. 拼接用户问题 -----------------
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ]

            # ----------------- 4. 调用 LLM -----------------
            reply = self.llm_service.chat(messages)

            # ----------------- 5. 更新短期记忆 -----------------
            self._update_memory(user_id, user_message, reply)

            return {"reply": reply}
        except Exception as e:
            # LLM调用失败/数据库查询失败时，返回兜底回复
            fallback_reply = f"抱歉，暂时无法查询你的数据（{str(e)[:50]}），请稍后再试～"
            self._update_memory(user_id, user_message, fallback_reply)
            return {"reply": fallback_reply}

    # ------------------------ 学术/通用问题 ------------------------
    def _handle_general_qa(self, user_id: int, message: str):
        try:
            # 获取用户画像（加默认值兜底）
            profile = self.profile_service.get_chat_profile(user_id) or {}
            # 获取最近短期记忆
            history = self._get_recent_history(user_id)
            # 构建 system prompt
            system_prompt = self.build_prompt(profile)
            # 拼接历史和用户消息
            messages = [{"role": "system", "content": system_prompt}]
            # 历史消息格式修正：区分user/bot角色
            for msg in history:
                messages.append({"role": "user", "content": msg["user"]})
                messages.append({"role": "assistant", "content": msg["bot"]})
            messages.append({"role": "user", "content": message})
            # 调用 LLM
            reply = self.llm_service.chat(messages)
            # 更新短期记忆
            self._update_memory(user_id, message, reply)
            return {"reply": reply}
        except Exception as e:
            fallback_reply = f"抱歉，暂时无法回答你的问题（{str(e)[:50]}），请稍后再试～"
            self._update_memory(user_id, message, fallback_reply)
            return {"reply": fallback_reply}

    def build_prompt(self, profile: dict) -> str:
        # 修正：从嵌套的 latest_state 中读取字段
        state = profile.get("latest_state", {})
        prompt = f"""
你是用户的个性化学习助手。
用户信息：
- 专业：{profile.get('major', '未知') or '未知'}
- 年级：{profile.get('grade', '未知') or '未知'}
- 脑力评分：{state.get('brain_score', 50)}
- 专注度评分：{state.get('focus_score', 50)}
- 状态标签：{state.get('state_tag', '正常')}
请根据用户背景回答学术问题或学习规划问题，语言自然、可理解，必要时给出鼓励。
"""
        return prompt

    # ------------------------ 短期记忆管理 ------------------------
    def _get_recent_history(self, user_id: int) -> List[dict]:
        # 修正：使用配置文件中的 MAX_HISTORY_ROUNDS，而非写死的3
        return self.chat_memory.get(user_id, [])[-MAX_HISTORY_ROUNDS:]

    def _update_memory(self, user_id: int, user_message: str, reply: str):
        if user_id not in self.chat_memory:
            self.chat_memory[user_id] = []
        self.chat_memory[user_id].append({"user": user_message, "bot": reply})
        # 修正：使用配置文件中的 MAX_HISTORY_ROUNDS
        self.chat_memory[user_id] = self.chat_memory[user_id][-MAX_HISTORY_ROUNDS:]
