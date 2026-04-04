from datetime import timedelta
from sqlalchemy.orm import Session
from backed.database.models import User
from backed.schemas.auth_schema import RegisterRequest, LoginRequest
from backed.core.auth import create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES
from backed.core.security import get_password_hash, verify_password
from datetime import datetime, timezone

class AuthService:
    def __init__(self, db: Session):
        self.db = db
    def register(self, req: RegisterRequest) -> dict:
        existing_user = self.db.query(User).filter(User.username == req.username).first()
        if existing_user:
            raise ValueError("用户名已存在")
        
        truncated_password = req.password[:72]
        hashed_pwd = get_password_hash(truncated_password)

        new_user = User(
            username=req.username,
            password=hashed_pwd,
            major=req.major,
            grade=req.grade,
            create_time=datetime.now(timezone.utc)
        )

        self.db.add(new_user)
        self.db.commit()
        self.db.refresh(new_user)

        access_token = create_access_token(
            data={"sub": str(new_user.id)},
            expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        )

        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user_id": str(new_user.id)
        }

    def login(self, req: LoginRequest) -> dict:
        """用户登录，返回用户信息 + Token"""
        # 1. 检查用户是否存在
        user = self.db.query(User).filter(User.username == req.username).first()
        if not user:
            raise ValueError("用户名或密码错误")

        # 2. 验证密码
        if not verify_password(req.password, user.password):
            raise ValueError("用户名或密码错误")

        # 3. 生成Token（包含用户ID）
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": str(user.id)},
            expires_delta=access_token_expires
        )

        # 4. 返回用户信息（包含Token和user_id）
        return {
            "access_token": access_token,
            "user_id": str(user.id),
        }
