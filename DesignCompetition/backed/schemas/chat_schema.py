
# backend/schemas/chat_schema.py

from pydantic import BaseModel
from typing import Optional

# -----------------------------
# 请求模型：前端发送的数据
# -----------------------------
class ChatRequest(BaseModel):
    user_id: str              # 当前用户 ID
    message: str              # 用户输入的消息
    session_id: Optional[str] = None  # 可选：多轮会话 ID

# -----------------------------
# 响应模型：后端返回的数据
# -----------------------------
class ChatResponse(BaseModel):
    reply: str                # AI 生成的回复文本
    session_id: Optional[str] = None  # 返回的会话 ID，可用于多轮记忆

