# backed/core/auth.py
from datetime import datetime, timedelta
from fastapi import HTTPException, status, Depends
from fastapi.security import OAuth2PasswordBearer
from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWTError

print("当前服务器时间:", datetime.utcnow())

# ================= 配置 =================
SECRET_KEY = "your-secret-key-keep-it-safe-1234567890"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440  # 24小时

# ================= Token提取 =================
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/user/login")


# ================= 生成Token =================
def create_access_token(data: dict, expires_delta: timedelta | None = None):
    """生成JWT Token"""
    to_encode = data.copy()

    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    to_encode.update({"exp": expire})

    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


# ================= 解析Token =================
#返回结果int型
def get_current_user_id(token: str = Depends(oauth2_scheme)) -> int:
    """从Token中解析用户ID"""

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token无效",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
            print("收到token:", token)

            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

            print("token过期时间:", payload.get("exp"))

            user_id: str = payload.get("sub")
            if user_id is None:
                raise credentials_exception

            return int(user_id)

    except ExpiredSignatureError:
        # ✅ 单独处理过期（非常重要）
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token已过期，请重新登录",
            headers={"WWW-Authenticate": "Bearer"},
        )

    except JWTError:
        # ✅ 其他所有解析错误
        raise credentials_exception