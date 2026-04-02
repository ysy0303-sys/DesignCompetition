# backend/core/dependencies.py
from backed.services.chat_agent import ChatAgent
from backed.services.llm_service import LLMService
from backed.services.profile_service import ProfileService
from backed.database.db_service import MySQLService
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from jose import JWTError, jwt
from backed.database.session import get_db
from backed.database.models import User
from backed.core.auth import SECRET_KEY, ALGORITHM

def get_chat_agent():
    # 初始化数据库服务
    db_service = MySQLService()
    # 初始化LLM服务
    llm_service = LLMService()
    # 初始化用户画像服务（传入DB实例）
    profile_service = ProfileService(db=db_service)

    return ChatAgent(
        llm_service=llm_service,
        profile_service=profile_service,
        db_service=db_service  # 补全缺失的db_service参数
    )



# 数据库会话依赖（供路由使用）
DependencyDB = Depends(get_db)

# 可新增其他通用依赖（如认证依赖、分页依赖等）
class PaginationParams:
    def __init__(self, page: int = 1, page_size: int = 10):
        self.page = max(page, 1)
        self.page_size = max(page_size, 1)
        self.offset = (self.page - 1) * self.page_size

DependencyPagination = Depends(PaginationParams)

#--------------------------

security = HTTPBearer()


# def get_current_user(
#     credentials: HTTPAuthorizationCredentials = Depends(security),
#     db: Session = Depends(get_db)
# ) -> User:
#     """
#     获取当前登录用户
#     """
#
#     token = credentials.credentials
#
#     try:
#         payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
#         user_id: str = payload.get("sub")
#
#         if user_id is None:
#             raise HTTPException(
#                 status_code=status.HTTP_401_UNAUTHORIZED,
#                 detail="Token无效"
#             )
#
#     except JWTError:
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="Token解析失败"
#         )
#
#     user = db.query(User).filter(User.id == user_id).first()
#
#     if user is None:
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="用户不存在"
#         )
#
#     return user