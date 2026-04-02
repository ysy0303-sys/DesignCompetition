from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
# 修正导入路径：backed → backend（根据你的实际项目结构调整）
from backed.database.session import get_db
from backed.schemas.auth_schema import RegisterRequest, RegisterResponse, LoginRequest, LoginResponse
from backed.services.auth_service import AuthService

router = APIRouter(prefix="/user", tags=["用户认证"])

@router.post("/register", response_model=RegisterResponse)
def register_user(
    req: RegisterRequest,
    db: Session = Depends(get_db)
):
    try:
        result = AuthService(db).register(req)

        return {
            "code": 200,
            "msg": "注册成功",
            "data": result
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/login", response_model=LoginResponse)
def login(
    req: LoginRequest,
    db: Session = Depends(get_db)
):
    try:
        result = AuthService(db).login(req)

        return {
            "code": 200,
            "msg": "登录成功",
            "data": result
        }

    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
# def register_user(req: RegisterRequest, db: Session = Depends(get_db)):
#     auth_service = AuthService(db)
#     try:
#         # 调用 Service 层拿到 data 部分
#         result = auth_service.register(req)
#
#         # 构造前端要求的统一响应格式
#         return {
#             "code": 200,
#             "msg": "注册成功",
#             "data": result
#         }
#     except ValueError as e:
#         # 如果用户名已存在，返回错误信息
#         return {
#             "code": 400,
#             "msg": str(e),
#             "data": None
#         }
# @router.post("/login", response_model=LoginResponse)
# def login(req: LoginRequest, db: Session = Depends(get_db)):
#     auth_service = AuthService(db)
#     try:
#         # 获取逻辑层数据
#         result = auth_service.login(req)
#
#         # 封装成前端要求的格式
#         return {
#             "code": 200,
#             "msg": "登录成功",
#             "data": result
#         }
#     except ValueError as e:
#         # 处理业务逻辑错误（如密码错误）
#         return {
#             "code": 401,  # 或者 200，取决于你们前端习惯如何判断错误
#             "msg": str(e),
#             "data": None
#         }