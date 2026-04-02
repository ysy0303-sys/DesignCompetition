# backed/schemas/auth_schema.py
from pydantic import BaseModel, Field
from typing import Optional, Any
# 注册请求模型（校验前端传入的参数）
class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50, description="用户名，3-50个字符")
    password: str = Field(min_length=6, max_length=100, description="密码，至少6位")
    major: Optional[str] = Field(default="", description="专业（选填）")
    grade: Optional[str] = Field(default="", description="年级（选填）")

class RegisterData(BaseModel):
    user_id: str
    access_token: str

# 注册响应模型（统一返回格式）
class RegisterResponse(BaseModel):
    code: int = Field(description="状态码：200成功，其他失败")
    msg: str = Field(description="提示信息")
    data: RegisterData

# 登录请求模型
class LoginRequest(BaseModel):
    username: str = Field(description="用户名",alias="account")
    password: str = Field(description="密码")

# 登录响应模型
class LoginData(BaseModel):
    user_id: str
    access_token: str

class LoginResponse(BaseModel):
    code: int
    msg: str
    data: LoginData