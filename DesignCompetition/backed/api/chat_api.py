# backend/api/chat_api.py
from fastapi import APIRouter
# 导入schema（请求/响应模型）
from backed.schemas.chat_schema import ChatRequest, ChatResponse
# 导入业务服务
from backed.services.llm_service import LLMService
from backed.services.profile_service import ProfileService
from backed.database.db_service import MySQLService
from backed.services.chat_agent import ChatAgent

# 全局router（必须保留！）
router = APIRouter()

# 初始化服务（只初始化一次，避免重复创建）
db_service = MySQLService()
profile_service = ProfileService(db_service)
llm_service = LLMService()
agent = ChatAgent(llm_service, profile_service, db_service)

# 完整业务逻辑的chat接口
@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        # 1. 转换user_id类型（schema中是str，Agent需要int）
        user_id = request.user_id

        # 2. 调用ChatAgent处理业务（查询数据库+调用豆包LLM）
        agent_result = agent.handle(user_id, request.message)

        # 3. 提取回复文本（兼容Agent返回的{"reply": "..."}）
        reply_text = agent_result.get("reply", "抱歉，暂无有效回复～")

        # 4. 构造响应（严格匹配ChatResponse模型）
        return ChatResponse(
            reply=reply_text,
            session_id=request.session_id  # 透传会话ID
        )
    except ValueError as e:
        # 处理user_id转换失败（比如前端传非数字）
        return ChatResponse(
            reply=f"用户ID格式错误：{str(e)}",
            session_id=request.session_id
        )
    except Exception as e:
        # 全局异常兜底（避免返回500）
        return ChatResponse(
            reply=f"服务暂时不可用：{str(e)[:50]}，请稍后再试～",
            session_id=request.session_id
        )