from __future__ import annotations

import base64
import hashlib
import hmac
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "edupilot-dev-secret-change-in-prod")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440
ADMIN_INVITE_CODE = os.getenv("ADMIN_INVITE_CODE", "")
PBKDF2_ROUNDS = 310000
DB_PATH = os.getenv("EDUPILOT_DB", "data/edupilot.db")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


@dataclass
class AuthUser:
    username: str
    role: str


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    return conn


def verify_password(plain_password: str, password_hash: str) -> bool:
    if not plain_password or not password_hash:
        return False
    if not password_hash.startswith("pbkdf2_sha256$"):
        return False
    try:
        _, rounds, salt_b64, digest_b64 = password_hash.split("$", 3)
        salt = base64.b64decode(salt_b64.encode("ascii"))
        expected = base64.b64decode(digest_b64.encode("ascii"))
        calculated = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt, int(rounds))
        return hmac.compare_digest(calculated, expected)
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS)
    salt_b64 = base64.b64encode(salt).decode("ascii")
    digest_b64 = base64.b64encode(digest).decode("ascii")
    return f"pbkdf2_sha256${PBKDF2_ROUNDS}${salt_b64}${digest_b64}"


def create_access_token(username: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode({"sub": username, "role": role, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)


def authenticate_user(username: str, password: str) -> AuthUser | None:
    conn = _get_conn()
    try:
        row = conn.execute("SELECT username, password_hash, role FROM users WHERE username = ?", (username,)).fetchone()
        if not row:
            return None
        if not verify_password(password, row["password_hash"]):
            return None
        return AuthUser(username=row["username"], role=row["role"])
    finally:
        conn.close()


def get_current_user(token: str = Depends(oauth2_scheme)) -> AuthUser:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception

    conn = _get_conn()
    try:
        row = conn.execute("SELECT username, role FROM users WHERE username = ?", (username,)).fetchone()
        if not row:
            raise credentials_exception
        return AuthUser(username=row["username"], role=row["role"])
    finally:
        conn.close()


def resolve_role(requested_role: str | None, admin_code: str | None) -> str:
    role = (requested_role or "user").strip().lower()
    if role != "admin":
        return "user"
    if ADMIN_INVITE_CODE and admin_code == ADMIN_INVITE_CODE:
        return "admin"
    raise HTTPException(status_code=403, detail="Invalid admin invite code")
