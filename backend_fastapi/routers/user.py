# backend_fastapi/routers/user.py
from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text
from core.database import engine
import hashlib
import random
import re
import jwt
from datetime import datetime, timedelta, timezone

router = APIRouter(prefix="/api", tags=["用户认证模块"])

# JWT 配置参数（实际部署中建议将密钥放入环境变量）
SECRET_KEY = "your_super_secret_key_fruit_ai"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24


class UserRegister(BaseModel):
    username: str
    password: str
    email: str


class UserLogin(BaseModel):
    username: str
    password: str


class SendEmailRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    email: str
    code: str
    new_password: str


MOCK_EMAIL_STORE = {}


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


# 生成 JWT Token 的函数
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


@router.post("/register")
def register(user: UserRegister):
    if not re.match(r"[^@]+@[^@]+\.[^@]+", user.email):
        return {"status": "error", "message": "邮箱格式不正确"}
    try:
        with engine.connect() as conn:
            check_sql = text("SELECT id FROM users WHERE username = :u OR email = :e")
            if conn.execute(check_sql, {"u": user.username, "e": user.email}).fetchone():
                return {"status": "error", "message": "用户名或邮箱已被注册"}

            insert_sql = text("INSERT INTO users (username, password_hash, email) VALUES (:u, :pwd, :e)")
            conn.execute(insert_sql, {"u": user.username, "pwd": hash_password(user.password), "e": user.email})
            conn.commit()
        return {"status": "success", "message": "注册成功！请登录"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/login")
def login(user: UserLogin):
    try:
        with engine.connect() as conn:
            query = text("SELECT id, password_hash, email FROM users WHERE username = :u")
            db_user = conn.execute(query, {"u": user.username}).fetchone()
            if not db_user or db_user[1] != hash_password(user.password):
                return {"status": "error", "message": "用户名或密码错误"}

        # 验证通过，生成 Token。
        # 这里把 users.id 写入 customer_id，后续交易建单会从 Token 中读取真实顾客编号。
        access_token = create_access_token(data={"sub": user.username, "customer_id": int(db_user[0])})
        return {
            "status": "success",
            "message": "登录成功",
            "username": user.username,
            "customer_id": int(db_user[0]),
            "token": access_token
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/send_email")
def send_email(req: SendEmailRequest):
    if not re.match(r"[^@]+@[^@]+\.[^@]+", req.email):
        return {"status": "error", "message": "邮箱格式不正确"}
    try:
        with engine.connect() as conn:
            check_sql = text("SELECT id FROM users WHERE email = :e")
            if not conn.execute(check_sql, {"e": req.email}).fetchone():
                return {"status": "error", "message": "该邮箱未注册"}

        code = str(random.randint(100000, 999999))
        MOCK_EMAIL_STORE[req.email] = code
        print(f"[Email Simulation] Recipient: {req.email} | Verification code: {code}")
        return {"status": "success", "message": "验证码已发至邮箱(终端可见)"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/reset_password")
def reset_password(req: ResetPasswordRequest):
    if MOCK_EMAIL_STORE.get(req.email) != req.code:
        return {"status": "error", "message": "验证码错误或已过期"}
    try:
        with engine.connect() as conn:
            update_sql = text("UPDATE users SET password_hash = :pwd WHERE email = :e")
            conn.execute(update_sql, {"pwd": hash_password(req.new_password), "e": req.email})
            conn.commit()
        if req.email in MOCK_EMAIL_STORE:
            del MOCK_EMAIL_STORE[req.email]
        return {"status": "success", "message": "密码重置成功"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
